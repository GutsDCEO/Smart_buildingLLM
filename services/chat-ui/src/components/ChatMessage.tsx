"use client";

import { useRef, useEffect, useState, type ReactNode } from "react";
import type { CitationData } from "@/lib/api";
import CitationCard from "./CitationCard";
import MermaidDiagram, { MermaidSkeleton } from "./MermaidDiagram";

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

// ── Mermaid fence parser ─────────────────────────────────────────
// Splits message text into plain text spans and MermaidDiagram
// components. During streaming, shows a skeleton if a fence is open.

const MERMAID_FENCE_RE = /(```mermaid\n[\s\S]*?```)/g;

export function renderContent(text: string, isStreaming?: boolean): ReactNode[] {
  const elements: ReactNode[] = [];

  // Split on complete ```mermaid ... ``` blocks
  const parts = text.split(MERMAID_FENCE_RE);

  for (let i = 0; i < parts.length; i++) {
    const part = parts[i];
    if (!part) continue;

    if (part.startsWith("```mermaid\n")) {
      // It's a COMPLETE mermaid block
      if (isStreaming) {
        // Never render the actual diagram during streaming to avoid race conditions
        elements.push(<MermaidSkeleton key={`mmd-skel-${i}`} />);
      } else {
        const code = part.slice(10, -3).trim();
        if (code) {
          elements.push(<MermaidDiagram key={`mmd-${i}`} code={code} />);
        }
      }
    } else {
      // It's text, but check if it contains an UNCLOSED mermaid fence at the end
      if (isStreaming && i === parts.length - 1 && part.includes("```mermaid\n")) {
        const textBeforeFence = part.split("```mermaid\n")[0];
        if (textBeforeFence) {
          elements.push(<span key={`txt-${i}`}>{textBeforeFence}</span>);
        }
        elements.push(<MermaidSkeleton key={`mmd-skel-open`} />);
      } else {
        elements.push(<span key={`txt-${i}`}>{part}</span>);
      }
    }
  }

  return elements;
}

export default function ChatMessage({ message }: ChatMessageProps) {
  const contentRef = useRef<HTMLDivElement>(null);
  const [copied, setCopied] = useState(false);

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
    navigator.clipboard.writeText(message.content).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    });
  };

  return (
    <div className={`message-row ${isUser ? "message-row--user" : "message-row--ai"}`}>
      <div className="message-inner">
        {/* Avatar */}
        <div className={`message-avatar ${isUser ? "message-avatar--user" : "message-avatar--ai"}`}>
          {isUser ? "👤" : "SB"}
        </div>

        <div className="message-content-wrap">
          {/* Header */}
          <div className="message-header">
            <span className="message-sender">{isUser ? "You" : "Smart Building AI"}</span>
            <span className="message-time">{time}</span>
          </div>

          {/* Content — with mermaid detection */}
          <div ref={contentRef} className="message-text">
            {isUser
              ? message.content
              : renderContent(message.content, message.isStreaming)}
            {message.isStreaming && <span className="cursor-blink">▌</span>}
          </div>

          {/* Citations */}
          {!isUser && message.citations && message.citations.length > 0 && (
            <div className="message-citations">
              <div className="citations-label">Sources</div>
              <div className="citations-list">
                {message.citations.map((c, i) => (
                  <CitationCard
                    key={`${c.source_file}-${c.chunk_index}`}
                    citation={c}
                    index={i}
                  />
                ))}
              </div>
            </div>
          )}

          {/* Actions — fade in on hover */}
          {!isUser && !message.isStreaming && message.content && (
            <div className="msg-actions">
              <button
                className="action-btn"
                onClick={copyToClipboard}
                title="Copy answer"
                id={`copy-${message.id}`}
              >
                {copied ? "✓ Copied" : "Copy"}
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
