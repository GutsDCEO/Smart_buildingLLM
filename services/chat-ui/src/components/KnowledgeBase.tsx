"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import {
  fetchDocuments,
  uploadDocument,
  deleteDocument,
  syncFolder,
  type DocumentInfo,
} from "@/lib/api";

// ── File type filter options ─────────────────────────────────────

const FILE_TYPE_FILTERS = [
  { label: "All", value: "" },
  { label: "PDF", value: "PDF" },
  { label: "Word", value: "Word" },
  { label: "Text", value: "Text" },
];

// ── File type icons ──────────────────────────────────────────────

const FILE_ICONS: Record<string, string> = {
  PDF: "📄",
  Word: "📝",
  HTML: "🌐",
  Text: "📋",
  Unknown: "📎",
};

// ── Format file size ─────────────────────────────────────────────

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

// ── Format date ──────────────────────────────────────────────────

function formatDate(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

// ── Component ────────────────────────────────────────────────────

export default function KnowledgeBase() {
  const [docs, setDocs] = useState<DocumentInfo[]>([]);
  const [filter, setFilter] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isUploading, setIsUploading] = useState(false);
  const [isSyncing, setIsSyncing] = useState(false);
  const [actionStatus, setActionStatus] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const loadDocs = useCallback(async () => {
    setIsLoading(true);
    const data = await fetchDocuments(filter || undefined);
    setDocs(data.documents);
    setIsLoading(false);
  }, [filter]);

  useEffect(() => {
    loadDocs();
  }, [loadDocs]);

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setIsUploading(true);
    setActionStatus(null);

    const result = await uploadDocument(file);
    if (result.success) {
      setActionStatus(`✅ "${file.name}" uploaded successfully!`);
      await loadDocs();
    } else {
      setActionStatus(`❌ ${result.error}`);
    }

    setIsUploading(false);
    // Reset file input
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const handleSync = async () => {
    setIsSyncing(true);
    setActionStatus("⏳ Scanning ingest folder...");

    const result = await syncFolder();
    if (result.success && result.data) {
      const summary = result.data;
      if (summary.newly_ingested > 0) {
        setActionStatus(`✅ Synced: ${summary.newly_ingested} new files ingested. (${summary.already_indexed} skipped)`);
        await loadDocs();
      } else if (summary.failed > 0) {
        setActionStatus(`⚠️ Failed to sync ${summary.failed} files. Check logs.`);
      } else {
        setActionStatus(`✅ Folder is up to date. (${summary.total_files_found} files tracked)`);
      }
    } else {
      setActionStatus(`❌ Sync failed: ${result.error}`);
    }

    setIsSyncing(false);
  };

  const handleDelete = async (doc: DocumentInfo) => {
    if (!confirm(`Delete "${doc.filename}" and all its chunks from the AI's knowledge?`)) return;

    setDeletingId(doc.id);
    const result = await deleteDocument(doc.id);

    if (result.success) {
      setDocs((prev) => prev.filter((d) => d.id !== doc.id));
    } else {
      alert(`Failed to delete: ${result.error}`);
    }
    setDeletingId(null);
  };

  return (
    <div className="kb-container">
      {/* Header */}
      <div className="kb-header">
        <h2 className="kb-title">📚 Knowledge Base</h2>
        <p className="kb-subtitle">{docs.length} document{docs.length !== 1 ? "s" : ""} indexed</p>
      </div>

      {/* Upload & Sync Area */}
      <div className="kb-upload-area">
        <div style={{ display: "flex", gap: "12px", alignItems: "center" }}>
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.docx,.doc,.txt"
            onChange={handleUpload}
            className="kb-file-input"
            id="kb-file-upload"
            disabled={isUploading || isSyncing}
          />
          <label htmlFor="kb-file-upload" className={`kb-upload-btn ${isUploading || isSyncing ? "kb-upload-btn--disabled" : ""}`}>
            {isUploading ? "⏳ Uploading..." : "📤 Upload Document"}
          </label>
          <button
            className={`kb-upload-btn ${isUploading || isSyncing ? "kb-upload-btn--disabled" : ""}`}
            style={{ background: "transparent", border: "1px solid var(--border)", color: "var(--text-primary)" }}
            onClick={handleSync}
            disabled={isUploading || isSyncing}
          >
            {isSyncing ? "⏳ Syncing..." : "🔄 Sync Folder"}
          </button>
        </div>
        {actionStatus && (
          <p className="kb-upload-status">{actionStatus}</p>
        )}
      </div>

      {/* Filter Bar */}
      <div className="kb-filter-bar">
        {FILE_TYPE_FILTERS.map((f) => (
          <button
            key={f.value}
            className={`kb-filter-btn ${filter === f.value ? "kb-filter-btn--active" : ""}`}
            onClick={() => setFilter(f.value)}
          >
            {f.label}
          </button>
        ))}
      </div>

      {/* Document List */}
      <div className="kb-doc-list">
        {isLoading ? (
          <div className="kb-loading">Loading documents...</div>
        ) : docs.length === 0 ? (
          <div className="kb-empty">
            <p>No documents found.</p>
            <p className="kb-empty-hint">Upload a PDF or Word file to get started.</p>
          </div>
        ) : (
          docs.map((doc) => (
            <div key={doc.id} className="kb-doc-card">
              <div className="kb-doc-icon">{FILE_ICONS[doc.file_type] || FILE_ICONS.Unknown}</div>
              <div className="kb-doc-info">
                <span className="kb-doc-name" title={doc.filename}>{doc.filename}</span>
                <div className="kb-doc-meta">
                  <span className="kb-doc-type">{doc.file_type}</span>
                  <span className="kb-doc-sep">·</span>
                  <span>{doc.chunk_count} chunks</span>
                  <span className="kb-doc-sep">·</span>
                  <span>{formatSize(doc.file_size_bytes)}</span>
                  <span className="kb-doc-sep">·</span>
                  <span>{formatDate(doc.created_at)}</span>
                </div>
              </div>
              <button
                className="kb-doc-delete"
                onClick={() => handleDelete(doc)}
                disabled={deletingId === doc.id}
                title="Delete document"
              >
                {deletingId === doc.id ? "⏳" : "🗑️"}
              </button>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
