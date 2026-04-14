"use client";

import { useRef, useEffect } from "react";
import type { CitationData } from "@/lib/api";
import CitationCard from "./CitationCard";

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations?: CitationData[];
  timestamp: Date;
  isStreaming?: boolean;
}

interface ChatMessageProps {
  message: Message;
}

export default function ChatMessage({ message }: ChatMessageProps) {
  const contentRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom as new tokens arrive
  useEffect(() => {
    if (message.isStreaming && contentRef.current) {
      contentRef.current.scrollIntoView({ behavior: "smooth", block: "end" });
    }
  }, [message.content, message.isStreaming]);

  const isUser = message.role === "user";
  const time = message.timestamp.toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });

  const copyToClipboard = () => {
    navigator.clipboard.writeText(message.content);
  };

  return (
    <div className={`message-row ${isUser ? "message-row--user" : "message-row--ai"}`}>
      <div className={`message-bubble ${isUser ? "message-bubble--user" : "message-bubble--ai"}`}>
        {/* Avatar */}
        <div className="message-avatar">
          {isUser ? "👤" : "🏗️"}
        </div>

        <div className="message-content-wrap">
          {/* Header */}
          <div className="message-header">
            <span className="message-sender">{isUser ? "You" : "Smart Building AI"}</span>
            <span className="message-time">{time}</span>
          </div>

          {/* Content */}
          <div ref={contentRef} className="message-text">
            {message.content}
            {message.isStreaming && <span className="cursor-blink">▌</span>}
          </div>

          {/* Citations */}
          {!isUser && message.citations && message.citations.length > 0 && (
            <div className="message-citations">
              <div className="citations-label">📚 Sources</div>
              <div className="citations-list">
                {message.citations.map((c, i) => (
                  <CitationCard key={`${c.source_file}-${c.chunk_index}`} citation={c} index={i} />
                ))}
              </div>
            </div>
          )}

          {/* Copy button (only for complete AI messages) */}
          {!isUser && !message.isStreaming && message.content && (
            <button className="copy-btn" onClick={copyToClipboard} title="Copy answer">
              📋
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
