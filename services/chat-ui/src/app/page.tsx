"use client";

import { useState, useRef, useEffect, useCallback, KeyboardEvent } from "react";
import { streamChat, fetchHealth, fetchHistory } from "@/lib/api";
import type { CitationData, HealthStatus } from "@/lib/api";
import ChatMessage from "@/components/ChatMessage";
import type { Message } from "@/components/ChatMessage";
import PipelineStatus from "@/components/PipelineStatus";
import type { Stage as PipelineStage } from "@/components/PipelineStatus";
import Sidebar from "@/components/Sidebar";
import type { SidebarTab } from "@/components/Sidebar";
import KnowledgeBase from "@/components/KnowledgeBase";

// ── Session Management ───────────────────────────────────────────

function getSessionId(): string {
  if (typeof window === "undefined") return "default-session";
  let id = localStorage.getItem("sb_session_id");
  if (!id) {
    id = `session-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    localStorage.setItem("sb_session_id", id);
  }
  return id;
}

let msgIdCounter = 0;
const newId = () => `msg-${++msgIdCounter}`;

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [pipelineStage, setPipelineStage] = useState<PipelineStage>("idle");
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [activeTab, setActiveTab] = useState<SidebarTab>("chat");
  const [historyLoaded, setHistoryLoaded] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const sessionId = useRef(getSessionId());

  // Poll /health on mount for welcome message
  useEffect(() => {
    fetchHealth().then((h) => {
      setHealth(h);
    });
  }, []);

  // Load chat history on mount
  useEffect(() => {
    if (historyLoaded) return;
    fetchHistory(sessionId.current).then((historyMessages) => {
      if (historyMessages.length > 0) {
        const restored: Message[] = historyMessages.map((hm) => ({
          id: newId(),
          role: hm.role as "user" | "assistant",
          content: hm.content,
          timestamp: new Date(hm.created_at),
        }));
        setMessages(restored);
      } else if (health) {
        // Only show welcome if no history exists
        setMessages([{
          id: newId(),
          role: "assistant",
          content: `👋 Connected to **Smart Building AI** (v${health.version}).\n\n`
            + `LLM: ${health.ollama_reachable ? "✅ Ready" : "⚠️ Offline"} · `
            + `Vector DB: ${health.qdrant_reachable ? "✅ Ready" : "⚠️ Offline"}\n\n`
            + `Ask me anything about your building — HVAC schedules, maintenance logs, equipment specs, and more.`,
          timestamp: new Date(),
        }]);
      }
      setHistoryLoaded(true);
    });
  }, [health, historyLoaded]);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Keyboard shortcut: Ctrl+K to focus input
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.ctrlKey && e.key === "k") {
        e.preventDefault();
        inputRef.current?.focus();
      }
    };
    window.addEventListener("keydown", handler as unknown as EventListener);
    return () => window.removeEventListener("keydown", handler as unknown as EventListener);
  }, []);

  const handleSend = useCallback(async () => {
    const q = input.trim();
    if (!q || isStreaming) return;

    // Add user message
    const userMsg: Message = {
      id: newId(), role: "user", content: q, timestamp: new Date(),
    };

    // Placeholder AI message (will fill in with streaming tokens)
    const aiId = newId();
    const aiMsg: Message = {
      id: aiId, role: "assistant", content: "", timestamp: new Date(), isStreaming: true,
    };

    setMessages((prev) => [...prev, userMsg, aiMsg]);
    setInput("");
    setIsStreaming(true);
    setPipelineStage("guardrail");

    const controller = new AbortController();
    abortRef.current = controller;

    let accumulatedText = "";
    let finalCitations: CitationData[] = [];

    try {
      for await (const event of streamChat(q, controller.signal, sessionId.current)) {
        switch (event.type) {
          case "status":
            setPipelineStage(event.data.stage as PipelineStage);
            break;

          case "token":
            accumulatedText += event.data.text;
            setMessages((prev) =>
              prev.map((m) =>
                m.id === aiId ? { ...m, content: accumulatedText } : m
              )
            );
            break;

          case "citations":
            finalCitations = event.data;
            break;

          case "error":
            accumulatedText = accumulatedText || event.data.message;
            setMessages((prev) =>
              prev.map((m) =>
                m.id === aiId ? { ...m, content: accumulatedText } : m
              )
            );
            break;

          case "done":
            // Finalize message — remove isStreaming, add citations
            setMessages((prev) =>
              prev.map((m) =>
                m.id === aiId
                  ? { ...m, content: accumulatedText, citations: finalCitations, isStreaming: false }
                  : m
              )
            );
            break;
        }
      }
    } catch {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === aiId
            ? { ...m, content: accumulatedText || "Connection error. Please try again.", isStreaming: false }
            : m
        )
      );
    } finally {
      setIsStreaming(false);
      setPipelineStage("done");
      setTimeout(() => setPipelineStage("idle"), 800);
      abortRef.current = null;
    }
  }, [input, isStreaming]);

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
    if (e.key === "Escape" && isStreaming) {
      abortRef.current?.abort();
    }
  };

  const handleStop = () => {
    abortRef.current?.abort();
  };

  const statusColor = health
    ? health.ollama_reachable && health.qdrant_reachable
      ? "#22c55e"
      : "#f59e0b"
    : "#6b7280";

  return (
    <div className="app-layout">
      {/* ── Sidebar ── */}
      <Sidebar activeTab={activeTab} onTabChange={setActiveTab} />

      {/* ── Main Area ── */}
      <div className="app-main">
        {activeTab === "chat" ? (
          <div className="app">
            {/* ── Header ── */}
            <header className="header">
              <div className="header-brand">
                <span className="header-logo">🏗️</span>
                <div>
                  <h1 className="header-title">Smart Building AI</h1>
                  <p className="header-sub">RAG-Powered Local Assistant</p>
                </div>
              </div>
              <div className="header-status">
                <span className="status-dot" style={{ background: statusColor }} />
                <span className="status-text">
                  {health ? `${health.service} v${health.version}` : "Connecting..."}
                </span>
              </div>
            </header>

            {/* ── Message List ── */}
            <main className="messages">
              {messages.map((msg) => (
                <ChatMessage key={msg.id} message={msg} />
              ))}
              <div ref={bottomRef} />
            </main>

            {/* ── Pipeline Status Bar ── */}
            <PipelineStatus activeStage={pipelineStage} />

            {/* ── Input Bar ── */}
            <footer className="input-bar">
              <div className="input-wrap">
                <textarea
                  ref={inputRef}
                  id="chat-input"
                  className="input-field"
                  placeholder="Ask about HVAC, maintenance, equipment... (↵ send · Shift+↵ newline · Ctrl+K focus)"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  rows={1}
                  disabled={isStreaming}
                  autoFocus
                />
                {isStreaming ? (
                  <button className="send-btn send-btn--stop" onClick={handleStop} title="Stop (Esc)">
                    ⏹
                  </button>
                ) : (
                  <button
                    className="send-btn"
                    onClick={handleSend}
                    disabled={!input.trim()}
                    title="Send (Enter)"
                  >
                    ➤
                  </button>
                )}
              </div>
              <p className="input-hint">
                Ctrl+K to focus · Esc to stop streaming · Shift+Enter for newline
              </p>
            </footer>
          </div>
        ) : (
          <KnowledgeBase />
        )}
      </div>
    </div>
  );
}
