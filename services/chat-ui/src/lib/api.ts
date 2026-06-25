/**
 * API Client — SSE streaming interface for the Agents Service.
 *
 * SRP: Only handles HTTP communication. No UI logic here.
 * DIP: Chat UI depends on this abstraction, not on fetch internals.
 * OWASP A02: API URL is a same-origin proxy path — never a hardcoded host,
 *            never baked into the client bundle via NEXT_PUBLIC_.
 * OWASP A01: All protected calls use authFetch (auto-attaches JWT + refreshes).
 *
 * WHY /api/backend instead of NEXT_PUBLIC_API_URL?
 * NEXT_PUBLIC_ variables are compiled into the JS bundle at startup, so
 * "localhost:8003" gets shipped to every browser — including a director's
 * laptop where localhost points to their own machine, not the dev server.
 * Using a same-origin path (/api/backend) routes through the Next.js proxy
 * (next.config.ts rewrites), which forwards server-side to FastAPI.
 * This works from any device on any network with zero .env changes.
 */

import { authFetch, authHeaders } from "@/lib/auth";

// Same-origin proxy path — Next.js rewrites this to BACKEND_URL server-side.
// Works from any device; no cross-origin requests, no CORS required.
const API_BASE = "/api/backend";


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

// ── Template Types ───────────────────────────────────────────────

export interface TemplateField {
  field_name: string;
  field_type: "acroform" | "bracket" | "underscore" | "mustache";
  page_number: number;
  current_value?: string | null;
}

export interface TemplateAnalyzeResponse {
  file_id: string;
  filename: string;
  total_fields: number;
  fields: TemplateField[];
}

export interface TemplateStatusEvent {
  stage: "opening" | "analyzing" | "filling" | "writing" | "saving";
  message: string;
  progress?: number;
  total?: number;
}

export interface TemplateFieldEvent {
  field_name: string;
  status: "filled" | "failed";
  value?: string;
  confidence?: number;
  error?: string;
}

export interface TemplateFillError {
  field_name: string;
  reason: string;
}

export interface TemplateCompleteEvent {
  file_id: string;
  filename: string;
  fields_filled: number;
  fields_failed: number;
  field_errors: TemplateFillError[];
  download_url: string;
  status: "completed" | "completed_with_errors";
}

export interface TemplateErrorEvent {
  message: string;
}

export type TemplateSSEEvent =
  | { type: "status"; data: TemplateStatusEvent }
  | { type: "field"; data: TemplateFieldEvent }
  | { type: "complete"; data: TemplateCompleteEvent }
  | { type: "error"; data: TemplateErrorEvent }
  | { type: "done"; data: {} };

// ── Template API (auth required) ──────────────────────────────────

export async function analyzeTemplate(file: File): Promise<TemplateAnalyzeResponse | null> {
  try {
    const formData = new FormData();
    formData.append("file", file);
    const res = await authFetch(`${API_BASE}/templates/analyze`, {
      method: "POST",
      body: formData,
    });
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

export async function* streamFillTemplate(
  fileId: string,
  fields?: string[],
  signal?: AbortSignal
): AsyncGenerator<TemplateSSEEvent> {
  let res: Response;
  try {
    res = await authFetch(`${API_BASE}/templates/fill`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...authHeaders(),
      },
      body: JSON.stringify({
        file_id: fileId,
        fields: fields || null,
      }),
      signal,
    });
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : "Network error";
    yield { type: "error", data: { message: msg } };
    return;
  }

  if (!res.ok) {
    const status = res.status;
    const message = status === 401
      ? "Session expired. Please log in again."
      : `Server error (${status})`;
    yield { type: "error", data: { message } };
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
          yield { type: eventType, data: JSON.parse(eventData) } as TemplateSSEEvent;
        } catch { /* skip malformed */ }
      }
    }
  }
}

export async function downloadTemplate(fileId: string): Promise<Blob | null> {
  try {
    const res = await authFetch(`${API_BASE}/templates/download/${encodeURIComponent(fileId)}`);
    if (!res.ok) return null;
    return await res.blob();
  } catch {
    return null;
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
