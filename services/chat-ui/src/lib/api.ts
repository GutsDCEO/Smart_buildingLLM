/**
 * API Client — SSE streaming interface for the Agents Service.
 *
 * SRP: Only handles HTTP communication. No UI logic here.
 * DIP: Chat UI depends on this abstraction, not on fetch internals.
 * OWASP A02: API URL from env var — never hardcoded.
 * OWASP A01: All protected calls use authFetch (auto-attaches JWT + refreshes).
 */

import { authFetch, authHeaders } from "@/lib/auth";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8003";


// ── Event Types ──────────────────────────────────────────────────

export interface StatusEvent {
  stage: "guardrail" | "router" | "retrieval" | "generating";
  message: string;
}
export interface TokenEvent { text: string; }
export interface CitationData {
  source_file: string;
  page_number: number | null;
  chunk_index: number;
  relevance_score: number;
}
export interface DoneEvent { answered_at: string; intent?: string; }
export interface ErrorEvent { stage: string; message: string; }

export type ChatSSEEvent =
  | { type: "status";    data: StatusEvent }
  | { type: "token";     data: TokenEvent }
  | { type: "citations"; data: CitationData[] }
  | { type: "done";      data: DoneEvent }
  | { type: "error";     data: ErrorEvent };

// ── Health Check ─────────────────────────────────────────────────

export interface HealthStatus {
  status: string;
  service: string;
  version: string;
  ollama_reachable: boolean;
  qdrant_reachable: boolean;
}

export async function fetchHealth(): Promise<HealthStatus | null> {
  try {
    // Health is public — no auth required
    const res = await fetch(`${API_BASE}/health`, { cache: "no-store" });
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

// ── Document Types ───────────────────────────────────────────────

export interface DocumentInfo {
  id: number;
  filename: string;
  file_type: string;
  chunk_count: number;
  file_size_bytes: number;
  created_at: string;
}

export interface DocumentListResponse {
  documents: DocumentInfo[];
  total: number;
}

// ── Document API (auth required) ──────────────────────────────────

export async function fetchDocuments(fileType?: string): Promise<DocumentListResponse> {
  try {
    const url = fileType
      ? `${API_BASE}/documents?file_type=${encodeURIComponent(fileType)}`
      : `${API_BASE}/documents`;
    const res = await authFetch(url, { cache: "no-store" });
    if (!res.ok) return { documents: [], total: 0 };
    return await res.json();
  } catch {
    return { documents: [], total: 0 };
  }
}

export async function uploadDocument(file: File): Promise<{ success: boolean; error?: string }> {
  try {
    const formData = new FormData();
    formData.append("file", file);
    // Note: Don't set Content-Type — browser sets multipart boundary automatically
    const res = await authFetch(`${API_BASE}/ingest`, {
      method: "POST",
      body: formData,
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({ detail: "Upload failed" }));
      return { success: false, error: data.detail || `Error ${res.status}` };
    }
    return { success: true };
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : "Network error";
    return { success: false, error: msg };
  }
}

export async function deleteDocument(docId: number): Promise<{ success: boolean; error?: string }> {
  try {
    const res = await authFetch(`${API_BASE}/documents/${docId}`, { method: "DELETE" });
    if (!res.ok) {
      const data = await res.json().catch(() => ({ detail: "Delete failed" }));
      return { success: false, error: data.detail || `Error ${res.status}` };
    }
    return { success: true };
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : "Network error";
    return { success: false, error: msg };
  }
}

export interface SyncResponse {
  status: string;
  total_files_found: number;
  already_indexed: number;
  newly_ingested: number;
  failed: number;
  errors: string[];
}

export async function syncFolder(): Promise<{ success: boolean; data?: SyncResponse; error?: string }> {
  try {
    const res = await authFetch(`${API_BASE}/sync`, { method: "POST" });
    if (!res.ok) {
      const data = await res.json().catch(() => ({ detail: "Sync failed" }));
      return { success: false, error: data.detail || `Error ${res.status}` };
    }
    return { success: true, data: await res.json() };
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : "Network error";
    return { success: false, error: msg };
  }
}

// ── Chat History (auth required) ──────────────────────────────────

export interface HistoryMessage {
  id: number;
  role: "user" | "assistant";
  content: string;
  created_at: string;
}

export async function fetchHistory(sessionId: string): Promise<HistoryMessage[]> {
  try {
    const res = await authFetch(
      `${API_BASE}/history/${encodeURIComponent(sessionId)}`,
      { cache: "no-store" }
    );
    if (!res.ok) return [];
    const data = await res.json();
    return data.messages || [];
  } catch {
    return [];
  }
}

// ── SSE Streaming (auth required) ────────────────────────────────

/**
 * Connect to /chat (POST) and yield structured SSE events.
 *
 * WHY fetch + ReadableStream instead of EventSource?
 * EventSource only supports GET. Our /chat needs POST to send
 * the question body. authFetch handles the JWT + refresh cycle.
 */
export async function* streamChat(
  question: string,
  signal?: AbortSignal,
  sessionId?: string,
  enableThinking?: boolean
): AsyncGenerator<ChatSSEEvent> {
  let res: Response;
  try {
    res = await authFetch(`${API_BASE}/chat`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...authHeaders(),
      },
      body: JSON.stringify({
        question,
        session_id: sessionId,
        enable_thinking: enableThinking ?? false,
      }),
      signal,
    });
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : "Network error";
    yield { type: "error", data: { stage: "error", message: msg } };
    return;
  }

  if (!res.ok) {
    const status = res.status;
    const message = status === 401
      ? "Session expired. Please log in again."
      : `Server error (${status})`;
    yield { type: "error", data: { stage: "error", message } };
    return;
  }

  const reader = res.body?.getReader();
  if (!reader) return;

  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const blocks = buffer.split("\n\n");
    buffer = blocks.pop() ?? "";

    for (const block of blocks) {
      const lines = block.split("\n");
      let eventType = "";
      let eventData = "";
      for (const line of lines) {
        if (line.startsWith("event: ")) eventType = line.slice(7).trim();
        else if (line.startsWith("data: ")) eventData = line.slice(6);
      }
      if (eventType && eventData) {
        try {
          yield { type: eventType, data: JSON.parse(eventData) } as ChatSSEEvent;
        } catch { /* skip malformed */ }
      }
    }
  }
}

// ── Sessions API (auth required) ──────────────────────────────────

export interface SessionInfo {
  session_id: string;
  title: string;
  last_active: string;
  message_count: number;
}

export async function fetchSessions(): Promise<SessionInfo[]> {
  try {
    const res = await authFetch(`${API_BASE}/sessions`, { cache: "no-store" });
    if (!res.ok) return [];
    const data = await res.json();
    return data.sessions || [];
  } catch {
    return [];
  }
}

export async function deleteSession(sessionId: string): Promise<boolean> {
  try {
    const res = await authFetch(
      `${API_BASE}/sessions/${encodeURIComponent(sessionId)}`,
      { method: "DELETE" }
    );
    return res.ok;
  } catch {
    return false;
  }
}
