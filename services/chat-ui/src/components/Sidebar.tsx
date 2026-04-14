"use client";

export type SidebarTab = "chat" | "knowledge";

interface SidebarProps {
  activeTab: SidebarTab;
  onTabChange: (tab: SidebarTab) => void;
}

export default function Sidebar({ activeTab, onTabChange }: SidebarProps) {
  return (
    <nav className="sidebar" id="main-sidebar">
      <div className="sidebar-brand">
        <span className="sidebar-logo">🏗️</span>
        <span className="sidebar-title">Smart Building AI</span>
      </div>

      <div className="sidebar-nav">
        <button
          id="sidebar-tab-chat"
          className={`sidebar-item ${activeTab === "chat" ? "sidebar-item--active" : ""}`}
          onClick={() => onTabChange("chat")}
        >
          <span className="sidebar-item-icon">💬</span>
          <span className="sidebar-item-label">Chat</span>
        </button>

        <button
          id="sidebar-tab-knowledge"
          className={`sidebar-item ${activeTab === "knowledge" ? "sidebar-item--active" : ""}`}
          onClick={() => onTabChange("knowledge")}
        >
          <span className="sidebar-item-icon">📚</span>
          <span className="sidebar-item-label">Knowledge Base</span>
        </button>
      </div>

      <div className="sidebar-footer">
        <span className="sidebar-version">v0.2.0 · Phase 4</span>
      </div>
    </nav>
  );
}
