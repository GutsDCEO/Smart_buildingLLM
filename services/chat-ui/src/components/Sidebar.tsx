"use client";

import { useState, useEffect, useCallback } from "react";

export type SidebarTab = "chat" | "knowledge";

export interface SessionInfo {
  session_id: string;
  title: string;
  last_active: string;
  message_count: number;
}

interface SidebarProps {
  activeTab: SidebarTab;
  onTabChange: (tab: SidebarTab) => void;
  activeSessionId: string;
  onSessionSelect: (sessionId: string) => void;
  onNewChat: () => void;
}



export default function Sidebar({
  activeTab,
  onTabChange,
  activeSessionId,
  onSessionSelect,
  onNewChat,
}: SidebarProps) {
  const [sessions, setSessions] = useState<SessionInfo[]>([]);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const loadSessions = useCallback(async () => {
    try {
      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8003"}/sessions`,
        { cache: "no-store" }
      );
      if (!res.ok) return;
      const data = await res.json();
      setSessions(data.sessions || []);
    } catch {
      // Silently degrade — sidebar still works without session list
    }
  }, []);

  useEffect(() => {
    loadSessions();
  }, [loadSessions, activeSessionId]); // Refresh when session changes

  const handleDelete = async (e: React.MouseEvent, sessionId: string) => {
    e.stopPropagation(); // Don't trigger session select
    setDeletingId(sessionId);
    try {
      await fetch(
        `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8003"}/sessions/${encodeURIComponent(sessionId)}`,
        { method: "DELETE" }
      );
      setSessions((prev) => prev.filter((s) => s.session_id !== sessionId));
      // If we deleted the active session, start a new chat
      if (sessionId === activeSessionId) {
        onNewChat();
      }
    } catch {
      // Fail silently
    } finally {
      setDeletingId(null);
    }
  };

  const formatRelativeTime = (isoString: string): string => {
    const date = new Date(isoString);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    if (diffMins < 1) return "Just now";
    if (diffMins < 60) return `${diffMins}m ago`;
    const diffHours = Math.floor(diffMins / 60);
    if (diffHours < 24) return `${diffHours}h ago`;
    return `${Math.floor(diffHours / 24)}d ago`;
  };

  return (
    <nav className="sidebar" id="main-sidebar">
      {/* Brand */}
      <div className="sidebar-brand">
        <span className="sidebar-logo">🏗️</span>
        <span className="sidebar-title">Smart Building AI</span>
      </div>

      {/* New Chat */}
      <button className="new-chat-btn" id="new-chat-btn" onClick={onNewChat}>
        <span className="new-chat-icon">✏️</span>
        <span>New Chat</span>
      </button>

      {/* Conversation List */}
      {sessions.length > 0 && (
        <>
          <div className="sidebar-section-label">Recent</div>
          <div className="conversation-list">
            {sessions.map((session) => (
              <div
                key={session.session_id}
                id={`conv-${session.session_id.slice(-6)}`}
                className={`conv-item ${session.session_id === activeSessionId ? "conv-item--active" : ""}`}
                onClick={() => onSessionSelect(session.session_id)}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => e.key === "Enter" && onSessionSelect(session.session_id)}
              >
                <span className="conv-icon">💬</span>
                <div className="conv-info">
                  <span className="conv-title">{session.title}</span>
                  <span className="conv-meta">
                    {formatRelativeTime(session.last_active)} · {Math.floor(session.message_count / 2)} msg
                  </span>
                </div>
                <button
                  className="conv-delete"
                  onClick={(e) => handleDelete(e, session.session_id)}
                  disabled={deletingId === session.session_id}
                  title="Delete conversation"
                  aria-label={`Delete ${session.title}`}
                >
                  🗑
                </button>
              </div>
            ))}
          </div>
        </>
      )}

      {/* Footer Tabs */}
      <div className="sidebar-footer">
        <button
          id="sidebar-tab-chat"
          className={`sidebar-footer-tab ${activeTab === "chat" ? "sidebar-footer-tab--active" : ""}`}
          onClick={() => onTabChange("chat")}
        >
          <span>💬</span>
          <span>Chat</span>
        </button>
        <button
          id="sidebar-tab-knowledge"
          className={`sidebar-footer-tab ${activeTab === "knowledge" ? "sidebar-footer-tab--active" : ""}`}
          onClick={() => onTabChange("knowledge")}
        >
          <span>📚</span>
          <span>Docs</span>
        </button>
        <span className="sidebar-version">v0.5.0</span>
      </div>
    </nav>
  );
}
