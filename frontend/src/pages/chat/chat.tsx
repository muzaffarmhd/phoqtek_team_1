import { ChatInput } from "@/components/custom/chatinput";
import { PreviewMessage, ThinkingMessage } from "../../components/custom/message";
import { useScrollToBottom } from '@/components/custom/use-scroll-to-bottom';
import { useState, useRef } from "react";
import { message } from "../../interfaces/interfaces"
import { Overview } from "@/components/custom/overview";
import { Header } from "@/components/custom/header";
import {v4 as uuidv4} from 'uuid';


export function Chat() {
  const [messagesContainerRef, messagesEndRef] = useScrollToBottom<HTMLDivElement>();
  const [messages, setMessages] = useState<message[]>([]);
  const [question, setQuestion] = useState<string>("");
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [file, setFile] = useState<File | null>(null);
  const [sessionID, setSessionID] = useState<string | null>(null);


  const clearMessages = () => {
    setMessages([]);
    setQuestion("");
    setFile(null);
    setSessionID(null);
  };

  async function handleSubmit(text?: string, uploadedFile?: File) {
    const messageText = text || question;
    const currentFile = uploadedFile || file;
    const traceId = uuidv4();
    const formData = new FormData();

    if (currentFile) {
      formData.append("file", currentFile);
    }
    if (messageText) {
      formData.append("query", messageText);
    }
    if (sessionID) {
      formData.append("session_id", sessionID);
    }

    setIsLoading(true);
    if (currentFile) {
      let fileMessageContent = `File: ${currentFile.name}`;
      if (messageText) {
        fileMessageContent = `${messageText}\n\nFile: ${currentFile.name}`;
      }
      setMessages(prev => [...prev, { content: fileMessageContent, role: "user", id: traceId }]);
    } else {
      setMessages(prev => [...prev, { content: messageText, role: "user", id: traceId }]);
    }
    
    setQuestion("");
    setFile(null);

    try {
      const response = await fetch("http://localhost:8000/query", {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        throw new Error("Network response was not ok");
      }

      const result = await response.json();
      if (result.session_id) {
        setSessionID(result.session_id);
      }
      setMessages(prev => [...prev, { content: result.answer, role: "assistant", id: uuidv4() }]);
    } catch (error) {
      console.error("Error processing message:", error);
      setMessages(prev => [...prev, { content: "Sorry, there was an error processing your message.", role: "assistant", id: uuidv4() }]);
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <div className="flex flex-col min-w-0 h-dvh bg-background">
      <Header/>
      <div className="flex flex-col min-w-0 gap-6 flex-1 overflow-y-scroll pt-4" ref={messagesContainerRef}>
        {messages.length > 0 && (
          <button
            onClick={clearMessages}
            className="self-end mr-4 px-3 py-1 text-sm bg-red-500 text-white rounded hover:bg-red-600 transition-colors"
          >
            Clear Messages
          </button>
        )}
        {messages.length == 0 && <Overview />}
        {messages.map((message, index) => (
          <PreviewMessage key={index} message={message} />
        ))}
        {isLoading && <ThinkingMessage />}
        <div ref={messagesEndRef} className="shrink-0 min-w-[24px] min-h-[24px]"/>
      </div>
      <div className="flex mx-auto px-4 bg-background pb-4 md:pb-6 gap-2 w-full md:max-w-3xl">
        <ChatInput  
          question={question}
          setQuestion={setQuestion}
          onSubmit={handleSubmit}
          isLoading={isLoading}
          file={file}
          setFile={setFile}
        />
      </div>
    </div>
  );
};