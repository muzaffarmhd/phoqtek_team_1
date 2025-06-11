from fastapi import FastAPI, Form, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import os
import PyPDF2
from docx import Document
import google.generativeai as genai
from google.generativeai import configure, GenerativeModel
from typing import Dict, Optional, List
import tempfile
import uuid
from sentence_transformers import SentenceTransformer
import faiss
import numpy as np
import re
import requests
from bs4 import BeautifulSoup
import arxiv
from scholarly import scholarly
import time
from requests.exceptions import RequestException

# Configure Gemini
configure(api_key="AIzaSyAGDlqX1x0YkUvEKcryow2q_8G338I3ZI8")
model = GenerativeModel('gemini-2.5-flash-preview-05-20', generation_config={"max_output_tokens": 10000})
app = FastAPI()

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize sentence transformer model for embeddings
embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
arxiv_client = arxiv.Client()

# Store chat sessions and knowledge base
knowledge_base: Dict[str, Dict] = {}

def chunk_text(text: str, chunk_size: int = 1000) -> List[str]:
    """Split text into overlapping chunks"""
    chunks = []
    for i in range(0, len(text), chunk_size - 200):
        chunk = text[i:i + chunk_size]
        chunks.append(chunk)
    return chunks

def create_vector_store(text: str) -> tuple:
    """Create FAISS index from text chunks"""
    chunks = chunk_text(text)
    if not chunks:
        return None, []
    embeddings = embedding_model.encode(chunks)
    
    # Create FAISS index
    dimension = embeddings.shape[1]
    index = faiss.IndexFlatL2(dimension)
    index.add(np.array(embeddings).astype('float32'))
    
    return index, chunks

def extract_text_from_file(file_path: str) -> str:
    """Extract text from PDF/DOCX"""
    try:
        if file_path.endswith('.pdf'):
            text = ""
            with open(file_path, 'rb') as f:
                reader = PyPDF2.PdfReader(f)
                if reader.is_encrypted:
                    try:
                        reader.decrypt('')
                    except Exception:
                        # Silently fail if decryption fails
                        pass
                for page in reader.pages:
                    text += page.extract_text() or ""
            return text
        elif file_path.endswith('.docx'):
            doc = Document(file_path)
            return "\n".join([para.text for para in doc.paragraphs])
        else:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error processing file: {str(e)}")

def get_relevant_context(query: str, index, chunks: List[str], k: int = 3) -> str:
    """Retrieve most relevant chunks for the query"""
    if not query or index is None or not chunks:
        return ""
    query_embedding = embedding_model.encode([query])[0]
    distances, indices = index.search(np.array([query_embedding]).astype('float32'), k)
    relevant_chunks = [chunks[i] for i in indices[0]]
    return "\n".join(relevant_chunks)

def extract_citations(text: str) -> List[Dict]:
    """Extract citations with context"""
    patterns = {
        'apa': r'(?P<author>[A-Z][a-z]+\s(?:[A-Z][.]\s)*[A-Z][a-z]+)\s*\((?P<year>\d{4})\)',
        'numeric': r'\[(?P<ref>\d+(?:,\s*\d+)*)\]',
    }
    citations = []
    for style, pattern in patterns.items():
        for match in re.finditer(pattern, text):
            context_start = max(0, match.start() - 100)
            context_end = min(len(text), match.end() + 100)
            citations.append({
                'style': style,
                'match': match.group(),
                'context': text[context_start:context_end].strip(),
            })
    return citations

def download_and_extract_text(url: str) -> str:
    """Download and extract text from PDF URL"""
    try:
        if not url.lower().endswith('.pdf'):
            if 'arxiv.org' in url:
                arxiv_id = url.split('/')[-1].replace('.pdf', '').split('v')[0]
                url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
            else:
                return ""  # Only PDFs are supported

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=20)
        response.raise_for_status()

        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
            temp_file.write(response.content)
            text = extract_text_from_file(temp_file.name)
        os.unlink(temp_file.name)
        return text
    except RequestException:
        return ""
    except Exception:
        return ""

def search_academic_sources(query: str, max_results: int = 3) -> List[Dict]:
    """Search academic sources for relevant papers"""
    papers = []
    try:
        search = arxiv.Search(query=query, max_results=max_results, sort_by=arxiv.SortCriterion.Relevance)
        for result in arxiv_client.results(search):
            try:
                paper = {
                    'title': result.title,
                    'url': result.pdf_url,
                    'text': download_and_extract_text(result.pdf_url) if result.pdf_url else result.summary
                }
                if paper['text']:
                    papers.append(paper)
            except Exception:
                continue
    except Exception:
        pass # ArXiv search may fail

    if len(papers) < max_results:
        try:
            scholar_results = scholarly.search_pubs(query)
            for result in scholar_results:
                if len(papers) >= max_results:
                    break
                try:
                    pdf_url = result.get('eprint_url')
                    if pdf_url and '.pdf' not in pdf_url:
                         pdf_url = f"{pdf_url}.pdf"

                    text = download_and_extract_text(pdf_url) if pdf_url else result.bib.get('abstract', '')
                    if text:
                        papers.append({
                            'title': result.bib.get('title', ''),
                            'url': pdf_url,
                            'text': text
                        })
                    time.sleep(1) # Avoid rate limiting
                except Exception:
                    continue
        except Exception:
            pass # Scholar search may fail
    return papers

@app.post("/query")
async def query(query: str = Form(None), file: UploadFile = File(None), session_id: Optional[str] = Form(None)):
    if not query and not file:
        raise HTTPException(status_code=400, detail="Either query or file must be provided")

    # Case 1: New session with a file upload (this takes precedence)
    if file:
        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[1]) as temp_file:
            content = await file.read()
            temp_file.write(content)
            temp_file_path = temp_file.name
        try:
            text = extract_text_from_file(temp_file_path)
            vector_store, chunks = create_vector_store(text)
            citations = extract_citations(text)
            
            session_id = str(uuid.uuid4())
            chat = model.start_chat(history=[])
            knowledge_base[session_id] = {
                'type': 'file', 'chat': chat, 'vector_store': vector_store,
                'chunks': chunks, 'citations': citations
            }
            
            final_query = query or "Provide a comprehensive summary of the document."
            relevant_context = get_relevant_context(final_query, vector_store, chunks)
            prompt = f"""Based on the following document content, answer the question.
Question: {final_query}
Relevant Content: {relevant_context}"""
            
            response = chat.send_message(prompt)
            return {"answer": response.text, "session_id": session_id}
        finally:
            os.unlink(temp_file_path)

    # Case 2: Follow-up question in an existing session
    elif session_id and session_id in knowledge_base:
        if not query:
            raise HTTPException(status_code=400, detail="Query is required for follow-up questions.")
        
        session_data = knowledge_base[session_id]
        chat = session_data['chat']
        vector_store = session_data.get('vector_store')
        chunks = session_data.get('chunks')

        if vector_store and chunks:
            relevant_context = get_relevant_context(query, vector_store, chunks)
            prompt = f"""Based on the provided context and our conversation history, answer the question.
Question: {query}
Relevant Context: {relevant_context}"""
            response = chat.send_message(prompt)
        else: # Simple chat
            response = chat.send_message(query)
        return {"answer": response.text, "session_id": session_id}

    # Case 3: New session with a research query
    elif query:
        papers = search_academic_sources(query)
        if not papers:
            # Fallback to simple chat if no papers are found
            chat = model.start_chat(history=[])
            response = chat.send_message(query)
            session_id = str(uuid.uuid4())
            knowledge_base[session_id] = {'type': 'simple', 'chat': chat}
            return {"answer": response.text, "session_id": session_id}

        combined_text = "\n\n".join([f"Source: {p['title']}\n{p['text']}" for p in papers])
        vector_store, chunks = create_vector_store(combined_text)
        citations = extract_citations(combined_text)
        
        session_id = str(uuid.uuid4())
        chat = model.start_chat(history=[])
        knowledge_base[session_id] = {
            'type': 'research', 'chat': chat, 'vector_store': vector_store,
            'chunks': chunks, 'papers': papers, 'citations': citations
        }

        prompt = f"""Based on the following research papers, please synthesize an answer for the query: "{query}"
        
Found papers: {[p['title'] for p in papers]}
Key content:
{get_relevant_context(query, vector_store, chunks)}

Provide a comprehensive answer."""
        
        response = chat.send_message(prompt)
        return {"answer": response.text, "session_id": session_id}

    else:
        raise HTTPException(status_code=400, detail="Invalid request or session ID.")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
