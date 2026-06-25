/**
 * Auth Client — Token management for JWT authentication.
 *
 * SRP: Only handles token storage, retrieval, refresh, and API calls.
 * OWASP A02: Tokens stored in localStorage (acceptable for this local-network
 *            deployment; httpOnly cookies require a BFF proxy).
 * DIP: All other modules depend on this abstraction, not on localStorage directly.
 *
 * DESIGN NOTE — Redirect-loop prevention:
 *   getStoredUser() verifies BOTH user data AND access token exist.
 *   If either is missing the entire auth state is cleared, guaranteeing
 *   that the login page will never see stale data and bounce back to "/".
 *
 * DESIGN NOTE — Same-origin API proxy:
 *   API calls use /api/backend (proxied by Next.js) instead of a direct
 *   backend URL. This eliminates CORS entirely and prevents localhost from
 *   being baked into the JS bundle — the root cause of the demo network error.
 */

// Same-origin proxy path — Next.js rewrites /api/backend/:path* to BACKEND_URL.
// Works identically from localhost, a local IP, or any other device.
const API_BASE = "/api/backend";

// ── Storage Keys — named constants (no magic strings) ─────────────
const ACCESS_TOKEN_KEY = "sb_access_token";
const REFRESH_TOKEN_KEY = "sb_refresh_token";
const USER_KEY = "sb_user";

// ── Types ─────────────────────────────────────────────────────────

export interface AuthUser {
  id: number;
  username: string;
  email: string;
  role: "admin" | "viewer";
  is_active: boolean;
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

// ── Token Storage ─────────────────────────────────────────────────

export function getAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(ACCESS_TOKEN_KEY);
}

export function getRefreshToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(REFRESH_TOKEN_KEY);
}

/**
 * Returns the cached user ONLY if both user data AND an access token
 * exist in localStorage. If either is missing, clears everything to
 * prevent redirect loops between "/" and "/login".
 */
export function getStoredUser(): AuthUser | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = localStorage.getItem(USER_KEY);
    const token = localStorage.getItem(ACCESS_TOKEN_KEY);
    // Both must exist; if either is missing, the session is invalid
    if (!raw || !token) {
      clearAuth();
      return null;
    }
    return JSON.parse(raw) as AuthUser;
  } catch {
    clearAuth();
    return null;
  }
}

function storeTokens(tokens: TokenResponse): void {
  localStorage.setItem(ACCESS_TOKEN_KEY, tokens.access_token);
  localStorage.setItem(REFRESH_TOKEN_KEY, tokens.refresh_token);
}

/**
 * Nuke all auth state from localStorage.
 * Exported so pages can explicitly invalidate sessions.
 */
export function clearAuth(): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

// ── Auth Headers Helper ────────────────────────────────────────────

export function authHeaders(): Record<string, string> {
  const token = getAccessToken();
  if (!token) return {};
  return { Authorization: `Bearer ${token}` };
}

// ── API Calls ─────────────────────────────────────────────────────

function parseDetailError(detail: any, defaultMsg: string): string {
  if (!detail) return defaultMsg;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const first = detail[0];
    if (first && first.msg) {
      const field = first.loc ? first.loc[first.loc.length - 1] : "";
      return field ? `${field}: ${first.msg}` : first.msg;
    }
  }
  return defaultMsg;
}

export async function apiRegister(
  username: string,
  email: string,
  password: string
): Promise<{ user?: AuthUser; error?: string }> {
  try {
    const res = await fetch(`${API_BASE}/auth/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, email, password }),
    });
    const data = await res.json();
    if (!res.ok) return { error: parseDetailError(data.detail, "Registration failed.") };
    return { user: data as AuthUser };
  } catch {
    return { error: "Network error. Please try again." };
  }
}

export async function apiLogin(
  username: string,
  password: string
): Promise<{ user?: AuthUser; error?: string }> {
  try {
    const res = await fetch(`${API_BASE}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    const data = await res.json();
    if (!res.ok) return { error: parseDetailError(data.detail, "Invalid username or password.") };

    // Store tokens then fetch the user profile
    storeTokens(data as TokenResponse);
    const user = await apiGetMe();
    if (user) {
      localStorage.setItem(USER_KEY, JSON.stringify(user));
    }
    return { user: user ?? undefined };
  } catch {
    return { error: "Network error. Please try again." };
  }
}

/**
 * Fetch the current user profile from the server.
 * Uses plain fetch (NOT authFetch) to avoid circular dependency.
 * On any auth failure, nukes localStorage to prevent stale-session loops.
 */
export async function apiGetMe(): Promise<AuthUser | null> {
  const token = getAccessToken();
  if (!token) return null;
  try {
    const res = await fetch(`${API_BASE}/auth/me`, {
      headers: { Authorization: `Bearer ${token}` },
    });

    if (res.status === 401) {
      // Token expired — try refresh once
      const refreshed = await apiRefreshToken();
      if (!refreshed) {
        clearAuth();
        return null;
      }
      // Retry with the fresh token
      const retryToken = getAccessToken();
      if (!retryToken) {
        clearAuth();
        return null;
      }
      const retryRes = await fetch(`${API_BASE}/auth/me`, {
        headers: { Authorization: `Bearer ${retryToken}` },
      });
      if (!retryRes.ok) {
        clearAuth();
        return null;
      }
      return await retryRes.json();
    }

    if (!res.ok) {
      clearAuth();
      return null;
    }
    return await res.json();
  } catch {
    return null;
  }
}

/**
 * Validate the current session against the server.
 * Returns the fresh user if valid, null if invalid.
 * Always clears localStorage on failure — the single source of truth
 * for "should we redirect to login?".
 */
export async function validateSession(): Promise<AuthUser | null> {
  const user = await apiGetMe();
  if (user) {
    // Refresh the cached user with latest server data
    localStorage.setItem(USER_KEY, JSON.stringify(user));
    return user;
  }
  // Session is dead — ensure localStorage is clean
  clearAuth();
  return null;
}

/**
 * Refresh the access token using the stored refresh token.
 * Returns true if successful, false if the session has expired.
 */
export async function apiRefreshToken(): Promise<boolean> {
  const refreshToken = getRefreshToken();
  if (!refreshToken) return false;
  try {
    const res = await fetch(`${API_BASE}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
    if (!res.ok) {
      clearAuth();
      return false;
    }
    storeTokens(await res.json());
    return true;
  } catch {
    return false;
  }
}

export async function apiLogout(): Promise<void> {
  const token = getAccessToken();
  if (token) {
    // Best-effort revoke on server — don't block on failure
    fetch(`${API_BASE}/auth/logout`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
    }).catch(() => {});
  }
  clearAuth();
}

/**
 * Authenticated fetch wrapper with automatic 401 → refresh → retry.
 * Use this for all protected API calls instead of raw fetch().
 */
export async function authFetch(
  url: string,
  options: RequestInit = {}
): Promise<Response> {
  const headers = {
    ...(options.headers as Record<string, string> ?? {}),
    ...authHeaders(),
  };

  let res = await fetch(url, { ...options, headers });

  // Access token expired — try to refresh once and retry
  if (res.status === 401) {
    const refreshed = await apiRefreshToken();
    if (refreshed) {
      const newHeaders = {
        ...(options.headers as Record<string, string> ?? {}),
        ...authHeaders(),
      };
      res = await fetch(url, { ...options, headers: newHeaders });
    }
  }

  return res;
}
