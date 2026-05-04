"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { authFetch, apiLogout } from "@/lib/auth";
import type { AuthUser } from "@/lib/auth";
import { useRouter } from "next/navigation";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8003";

// ── Types ─────────────────────────────────────────────────────────

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
  user: AuthUser | null;
}

// ── Component ─────────────────────────────────────────────────────

export default function Sidebar({
  activeTab,
  onTabChange,
  activeSessionId,
  onSessionSelect,
  onNewChat,
  user,
}: SidebarProps) {
  const router = useRouter();
  const [sessions, setSessions] = useState<SessionInfo[]>([]);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [isLoggingOut, setIsLoggingOut] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  // ── Load sessions ─────────────────────────────────────────────

  const loadSessions = useCallback(async () => {
    try {
      const res = await authFetch(`${API_BASE}/sessions`, { cache: "no-store" });
      if (!res.ok) return;
      const data = await res.json();
      setSessions(data.sessions || []);
    } catch {
      // Silently degrade — sidebar still works without session list
    }
  }, []);

  useEffect(() => {
    loadSessions();
  }, [loadSessions, activeSessionId]);

  // ── Close menu on outside click ───────────────────────────────

  useEffect(() => {
    if (!menuOpen) return;
    const handleClickOutside = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [menuOpen]);

  // ── Handlers ──────────────────────────────────────────────────

  const handleDelete = async (e: React.MouseEvent, sessionId: string) => {
    e.stopPropagation();
    setDeletingId(sessionId);
    try {
      await authFetch(
        `${API_BASE}/sessions/${encodeURIComponent(sessionId)}`,
        { method: "DELETE" }
      );
      setSessions((prev) => prev.filter((s) => s.session_id !== sessionId));
      if (sessionId === activeSessionId) onNewChat();
    } catch {
      // Fail silently
    } finally {
      setDeletingId(null);
    }
  };

  const handleLogout = async () => {
    setIsLoggingOut(true);
    setMenuOpen(false);
    await apiLogout();
    router.replace("/login");
  };

  const handleDocsClick = () => {
    setMenuOpen(false);
    onTabChange(activeTab === "knowledge" ? "chat" : "knowledge");
  };

  // ── Helpers ───────────────────────────────────────────────────

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

  const avatarLetter = (user?.username ?? "?")[0].toUpperCase();
  const isAdmin = user?.role === "admin";

  // ── Render ────────────────────────────────────────────────────

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
      <div className="conversation-list">
        {sessions.length > 0 && (
          <div className="sidebar-section-label">Recent</div>
        )}
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

      {/* ── Bottom Profile ───────────────────────────────────── */}
      {user && (
        <div className="sidebar-profile" ref={menuRef}>
          {/* Popup Menu (above profile) */}
          {menuOpen && (
            <div className="profile-menu" id="profile-menu">
              <button
                className="profile-menu-item"
                id="menu-docs"
                onClick={handleDocsClick}
              >
                <span className="profile-menu-icon">📚</span>
                <span>Knowledge Base</span>
                {activeTab === "knowledge" && (
                  <span className="profile-menu-check">✓</span>
                )}
              </button>
              <div className="profile-menu-divider" />
              <div className="profile-menu-info">
                <span className="profile-menu-email">{user.email}</span>
                <span className={`profile-menu-role profile-menu-role--${user.role}`}>
                  {isAdmin ? "⚙️ Admin" : "👁 Viewer"}
                </span>
              </div>
              <div className="profile-menu-divider" />
              <button
                className="profile-menu-item profile-menu-item--danger"
                id="menu-logout"
                onClick={handleLogout}
                disabled={isLoggingOut}
              >
                <span className="profile-menu-icon">↪</span>
                <span>{isLoggingOut ? "Signing out..." : "Sign out"}</span>
              </button>
            </div>
          )}

          {/* Profile Button */}
          <button
            className={`profile-btn ${menuOpen ? "profile-btn--active" : ""}`}
            id="profile-btn"
            onClick={() => setMenuOpen((v) => !v)}
            aria-expanded={menuOpen}
            aria-haspopup="true"
          >
            <div className="profile-avatar">{avatarLetter}</div>
            <div className="profile-info">
              <span className="profile-name">{user.username}</span>
            </div>
            <span className={`profile-chevron ${menuOpen ? "profile-chevron--open" : ""}`}>
              ···
            </span>
          </button>
        </div>
      )}
    </nav>
  );
}
