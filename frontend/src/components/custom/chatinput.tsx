import { Textarea } from "../ui/textarea";
import { cx } from 'classix';
import { Button } from "../ui/button";
import { ArrowUpIcon, PaperclipIcon, CrossIcon } from "./icons"
import { toast } from 'sonner';
import { motion } from 'framer-motion';
import { useState, useRef } from 'react';

interface ChatInputProps {
    question: string;
    setQuestion: (question: string) => void;
    onSubmit: (text?: string, file?: File) => void;
    isLoading: boolean;
    file: File | null;
    setFile: (file: File | null) => void;
}

const suggestedActions = [
    {
        title: 'How is the weather',
        label: 'in Vienna?',
        action: 'How is the weather in Vienna today?',
    },
    {
        title: 'Tell me a fun fact',
        label: 'about pandas',
        action: 'Tell me an interesting fact about pandas',
    },
];

export const ChatInput = ({ question, setQuestion, onSubmit, isLoading, file, setFile }: ChatInputProps) => {
    const [showSuggestions, setShowSuggestions] = useState(true);
    const fileInputRef = useRef<HTMLInputElement>(null);

    const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
        const files = event.target.files;
        if (files && files.length > 0) {
            setFile(files[0]);
        }
    };

    const handleButtonClick = () => {
        fileInputRef.current?.click();
    };

    return(
    <div className="relative w-full flex flex-col gap-4">
        {showSuggestions && !file && (
            <div className="hidden md:grid sm:grid-cols-2 gap-2 w-full">
                {suggestedActions.map((suggestedAction, index) => (
                    <motion.div
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: 20 }}
                    transition={{ delay: 0.05 * index }}
                    key={index}
                    className={index > 1 ? 'hidden sm:block' : 'block'}
                    >
                        <Button
                            variant="ghost"
                            onClick={ () => {
                                const text = suggestedAction.action;
                                onSubmit(text);
                                setShowSuggestions(false);
                            }}
                            className="text-left border rounded-xl px-4 py-3.5 text-sm flex-1 gap-1 sm:flex-col w-full h-auto justify-start items-start"
                        >
                            <span className="font-medium">{suggestedAction.title}</span>
                            <span className="text-muted-foreground">
                            {suggestedAction.label}
                            </span>
                        </Button>
                    </motion.div>
                ))}
            </div>
        )}
        <input
            type="file"
            ref={fileInputRef}
            className="hidden"
            onChange={handleFileChange}
            multiple={false}
            tabIndex={-1}
        />
        {file && (
            <div className="flex items-center justify-between bg-muted p-2 rounded-md">
                <span>{file.name}</span>
                <Button variant="ghost" size="icon" onClick={() => setFile(null)}>
                    <CrossIcon size={16} />
                </Button>
            </div>
        )}
        <div className="relative flex items-center">
            <Button 
                variant="ghost" 
                size="icon" 
                className="absolute left-2"
                onClick={handleButtonClick}
            >
                <PaperclipIcon size={16} />
            </Button>
            <Textarea
                placeholder="Send a message..."
                className={cx(
                    'min-h-[24px] max-h-[calc(75dvh)] overflow-hidden resize-none rounded-xl text-base bg-muted pl-10',
                )}
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                onKeyDown={(event) => {
                    if (event.key === 'Enter' && !event.shiftKey) {
                        event.preventDefault();

                        if (isLoading) {
                            toast.error('Please wait for the model to finish its response!');
                        } else {
                            setShowSuggestions(false);
                            onSubmit(question, file ?? undefined);
                        }
                    }
                }}
                rows={1}
                autoFocus
            />

            <Button 
                className="rounded-full p-1.5 h-fit absolute bottom-2 right-2 m-0.5 border dark:border-zinc-600"
                onClick={() => onSubmit(question, file ?? undefined)}
                disabled={(question.length === 0 && !file) || isLoading}
            >
                <ArrowUpIcon size={14} />
            </Button>
        </div>
    </div>
    );
}