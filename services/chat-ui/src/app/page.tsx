"use client";

import { useState, useRef, useEffect, useCallback, KeyboardEvent } from "react";
import { useRouter } from "next/navigation";
import { streamChat, fetchHealth, fetchHistory } from "@/lib/api";
import { getStoredUser, validateSession, clearAuth } from "@/lib/auth";
import type { AuthUser } from "@/lib/auth";
import type { CitationData, HealthStatus } from "@/lib/api";
import ChatMessage from "@/components/ChatMessage";
import type { Message } from "@/components/ChatMessage";
import PipelineStatus from "@/components/PipelineStatus";
import type { Stage as PipelineStage } from "@/components/PipelineStatus";
import Sidebar from "@/components/Sidebar";
import type { SidebarTab } from "@/components/Sidebar";
import KnowledgeBase from "@/components/KnowledgeBase";

// ── Session helpers ───────────────────────────────────────────────

const SESSION_KEY = "sb_session_id";
const SESSION_LIST_KEY = "sb_session_list";

function generateSessionId(): string {
  return `session-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function getOrCreateSessionId(): string {
  if (typeof window === "undefined") return generateSessionId();
  let id = localStorage.getItem(SESSION_KEY);
  if (!id) {
    id = generateSessionId();
    localStorage.setItem(SESSION_KEY, id);
  }
  return id;
}

let msgIdCounter = 0;
const newId = () => `msg-${++msgIdCounter}`;

// ── Starter prompt chips ─────────────────────────────────────────

const STARTER_CHIPS = [
  "What maintenance tasks are due this month?",
  "Explain BACnet MSTP network topology",
  "What are the HVAC seasonal changeover steps?",
  "List the GSA Smart Buildings implementation phases",
];

// ── Main Page Component ──────────────────────────────────────────

export default function ChatPage() {
  const router = useRouter();
  const [user, setUser] = useState<AuthUser | null>(null);
  const [authChecked, setAuthChecked] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [pipelineStage, setPipelineStage] = useState<PipelineStage>("idle");
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [activeTab, setActiveTab] = useState<SidebarTab>("chat");
  const [historyLoaded, setHistoryLoaded] = useState(false);
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);
  const [thinkingEnabled, setThinkingEnabled] = useState(false);
  const [sessionId, setSessionId] = useState<string>(getOrCreateSessionId);

  const abortRef = useRef<AbortController | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const redirectingRef = useRef(false); // Prevent double-redirect

  // ── Auth Guard ────────────────────────────────────────────────
  //
  // Strategy: show nothing until server validates the session.
  // 1. Quick check: if no local data at all → instant redirect (no flash).
  // 2. If local data exists → validate with server.
  //    - Server says OK → render the app.
  //    - Server says invalid → clearAuth() THEN redirect.
  //    clearAuth() runs synchronously BEFORE router.replace(),
  //    so by the time /login mounts its useEffect, localStorage is clean.

  useEffect(() => {
    // Guard against StrictMode double-invoke or repeated calls
    if (redirectingRef.current) return;

    const cached = getStoredUser();
    if (!cached) {
      // No local data at all — go to login immediately
      redirectingRef.current = true;
      router.replace("/login");
      return;
    }

    // Optimistically show cached user while we verify with server
    setUser(cached);

    validateSession().then((freshUser) => {
      if (!freshUser) {
        // Token expired and refresh failed — session is dead.
        // clearAuth() already called inside validateSession().
        redirectingRef.current = true;
        router.replace("/login");
      } else {
        setUser(freshUser);
        setAuthChecked(true);
      }
    });
  }, [router]);

  // ── Health check (gated — runs after auth confirmed) ─────────

  useEffect(() => {
    if (!authChecked) return;
    fetchHealth().then(setHealth);
  }, [authChecked]);

  // ── Load chat history when session changes ────────────────────

  useEffect(() => {
    if (!authChecked) return;  // Don't fetch until auth confirmed
    setHistoryLoaded(false);
    setMessages([]);
    setIsLoadingHistory(true);

    fetchHistory(sessionId).then((historyMessages) => {
      if (historyMessages.length > 0) {
        const restored: Message[] = historyMessages.map((hm) => ({
          id: newId(),
          role: hm.role as "user" | "assistant",
          content: hm.content,
          timestamp: new Date(hm.created_at),
        }));
        setMessages(restored);
      }
      setHistoryLoaded(true);
      setIsLoadingHistory(false);
    });
  }, [sessionId, authChecked]);

  // ── Auto-scroll ───────────────────────────────────────────────

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // ── Keyboard shortcuts ────────────────────────────────────────

  useEffect(() => {
    const handler = (e: globalThis.KeyboardEvent) => {
      if (e.ctrlKey && e.key === "k") {
        e.preventDefault();
        inputRef.current?.focus();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  // ── New Chat ──────────────────────────────────────────────────

  const handleNewChat = useCallback(() => {
    const newSessionId = generateSessionId();
    localStorage.setItem(SESSION_KEY, newSessionId);
    setSessionId(newSessionId);
    setMessages([]);
    setHistoryLoaded(false);
    setThinkingEnabled(false);
    setActiveTab("chat");
    inputRef.current?.focus();
  }, []);

  // ── Switch to existing session ────────────────────────────────

  const handleSessionSelect = useCallback((id: string) => {
    if (id === sessionId) return;
    localStorage.setItem(SESSION_KEY, id);
    setSessionId(id);
    setActiveTab("chat");
  }, [sessionId]);

  // ── Send message ──────────────────────────────────────────────

  const handleSend = useCallback(async (questionOverride?: string) => {
    const q = (questionOverride ?? input).trim();
    if (!q || isStreaming) return;

    const userMsg: Message = {
      id: newId(), role: "user", content: q, timestamp: new Date(),
    };
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
      for await (const event of streamChat(q, controller.signal, sessionId, thinkingEnabled)) {
        switch (event.type) {
          case "status":
            setPipelineStage(event.data.stage as PipelineStage);
            break;
          case "token":
            accumulatedText += event.data.text;
            setMessages((prev) =>
              prev.map((m) => m.id === aiId ? { ...m, content: accumulatedText } : m)
            );
            break;
          case "citations":
            finalCitations = event.data;
            break;
          case "error":
            accumulatedText = accumulatedText || event.data.message;
            setMessages((prev) =>
              prev.map((m) => m.id === aiId ? { ...m, content: accumulatedText } : m)
            );
            break;
          case "done":
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
  }, [input, isStreaming, sessionId, thinkingEnabled]);

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
    if (e.key === "Escape" && isStreaming) {
      abortRef.current?.abort();
    }
  };

  const handleStop = () => abortRef.current?.abort();

  // ── Status dot color ──────────────────────────────────────────

  const statusColor = health
    ? health.ollama_reachable && health.qdrant_reachable ? "#48bb78" : "#ed8936"
    : "#718096";

  const showEmpty = historyLoaded && messages.length === 0 && !isLoadingHistory;

  // ── Early return AFTER all hooks (Rules of Hooks compliant) ──

  if (!authChecked) return null;

  // ── Render ────────────────────────────────────────────────────

  return (
    <div className="app-layout">
      {/* Sidebar */}
      <Sidebar
        activeTab={activeTab}
        onTabChange={setActiveTab}
        activeSessionId={sessionId}
        onSessionSelect={handleSessionSelect}
        onNewChat={handleNewChat}
        user={user}
      />

      {/* Main */}
      <div className="app-main">
        {activeTab === "chat" ? (
          <div className="chat-container">
            {/* Header */}
            <header className="header">
              <div className="header-left">
                <div>
                  <div className="header-title">Smart Building AI</div>
                  <div className="header-sub">RAG · Qwen3-32B · BGE-base-768</div>
                </div>
              </div>
              <div className="header-status">
                <span className="status-dot" style={{ background: statusColor }} />
                <span>{health ? `${health.service} v${health.version}` : "Connecting..."}</span>
              </div>
            </header>

            {/* Message list */}
            <main className="messages" id="chat-messages">
              {/* Skeleton while loading history */}
              {isLoadingHistory && (
                <div className="skeleton">
                  <div className="skeleton-line" style={{ width: "60%" }} />
                  <div className="skeleton-line" style={{ width: "85%" }} />
                  <div className="skeleton-line" style={{ width: "45%" }} />
                </div>
              )}

              {/* Empty state */}
              {showEmpty && (
                <div className="empty-state">
                  <div className="empty-icon">🏗️</div>
                  <div className="empty-title">Smart Building AI</div>
                  <div className="empty-sub">
                    Ask anything about your building — HVAC, BMS, BACnet, maintenance, or equipment specs.
                  </div>
                  <div className="empty-chips">
                    {STARTER_CHIPS.map((chip) => (
                      <button
                        key={chip}
                        className="empty-chip"
                        onClick={() => handleSend(chip)}
                        disabled={isStreaming}
                      >
                        {chip}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {messages.map((msg) => (
                <ChatMessage key={msg.id} message={msg} />
              ))}
              <div ref={bottomRef} />
            </main>

            {/* Pipeline status */}
            <PipelineStatus activeStage={pipelineStage} />

            {/* Input area */}
            <div className="input-area">
              {/* Persistent thinking warning */}
              {thinkingEnabled && (
                <div className="thinking-badge" id="thinking-badge">
                  <span className="thinking-badge-dot" />
                  <span>🧠 Deep thinking active — uses ~3× more quota per message</span>
                </div>
              )}

              <div className="input-box">
                <textarea
                  ref={inputRef}
                  id="chat-input"
                  className="input-field"
                  placeholder="Message Smart Building AI..."
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  rows={1}
                  disabled={isStreaming}
                  autoFocus
                />
                <div className="input-toolbar">
                  <div className="input-tools-left">
                    {/* Thinking toggle */}
                    <button
                      id="thinking-toggle"
                      className={`think-toggle ${thinkingEnabled ? "think-toggle--active" : ""}`}
                      onClick={() => setThinkingEnabled((v) => !v)}
                      title={thinkingEnabled ? "Disable deep thinking (saves quota)" : "Enable deep thinking (CoT reasoning)"}
                    >
                      <span className="think-icon">🧠</span>
                      <span>{thinkingEnabled ? "Thinking ON" : "Think"}</span>
                    </button>
                  </div>

                  <div className="input-actions">
                    {isStreaming ? (
                      <button className="send-btn send-btn--stop" onClick={handleStop} title="Stop (Esc)" id="stop-btn">
                        ⏹
                      </button>
                    ) : (
                      <button
                        className="send-btn"
                        id="send-btn"
                        onClick={() => handleSend()}
                        disabled={!input.trim()}
                        title="Send (Enter)"
                      >
                        ↑
                      </button>
                    )}
                  </div>
                </div>
              </div>

              <p className="input-hint">
                Enter to send · Shift+Enter for newline · Ctrl+K to focus · Esc to stop
              </p>
            </div>
          </div>
        ) : (
          <KnowledgeBase />
        )}
      </div>
    </div>
  );
}
