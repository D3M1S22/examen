import { AccountToken, AdminUser, BeeLinkInfo, SessionUser } from "@/types/schemas";
import { getApiBaseUrl } from "@/utils/api";

/**
 * Multi-user authentication client (docs/next_steps/multi_user/04 §4).
 *
 * The server keeps the session in an HttpOnly cookie: nothing about the user is stored in the browser.
 * `installAuthFetch()` makes every API call send the cookie (also from `next dev` on another port), adds
 * the CSRF header to state-changing requests and reports 401 responses through `AUTH_EXPIRED_EVENT`.
 */

export const CSRF_HEADER = "X-Requested-With";
export const CSRF_VALUE = "examen";
export const AUTH_EXPIRED_EVENT = "examen:unauthenticated";

let installed = false;

const isApiRequest = (url: string): boolean => {
  const base = getApiBaseUrl();
  const path = base && url.startsWith(base) ? url.slice(base.length) : url;
  return path.startsWith("/api/") || path.startsWith("/mcp");
};

export const installAuthFetch = (): void => {
  if (installed || typeof window === "undefined") return;
  installed = true;
  const nativeFetch = window.fetch.bind(window);
  window.fetch = async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
    if (!isApiRequest(url)) return nativeFetch(input, init);
    const method = (init.method || (input instanceof Request ? input.method : "GET")).toUpperCase();
    const headers = new Headers(init.headers || (input instanceof Request ? input.headers : undefined));
    if (!["GET", "HEAD", "OPTIONS"].includes(method)) headers.set(CSRF_HEADER, CSRF_VALUE);
    const res = await nativeFetch(input, { ...init, headers, credentials: "include" });
    if (res.status === 401 && !url.includes("/api/auth/")) {
      window.dispatchEvent(new Event(AUTH_EXPIRED_EVENT));
    }
    return res;
  };
};

const api = (path: string): string => `${getApiBaseUrl()}${path}`;

const jsonRequest = async <T>(path: string, method: string, body?: unknown): Promise<T> => {
  const res = await fetch(api(path), {
    method,
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data?.message || data?.error || `Request failed (${res.status})`);
  }
  return data as T;
};

interface SessionResponse {
  authenticated: boolean;
  user: {
    user_id: string;
    username: string;
    display_name?: string | null;
    is_admin: boolean;
    timezone?: string | null;
    created_at: string;
  } | null;
  bee_link: BeeLinkInfo | null;
  /** Whether the sign-in page offers "Create account" (server `AUTH_ALLOW_SIGNUP`). */
  signup_enabled?: boolean;
}

export interface SessionState {
  user: SessionUser | null;
  signupEnabled: boolean;
}

export const toSessionUser = (data: SessionResponse): SessionUser | null => {
  if (!data.authenticated || !data.user) return null;
  const link = data.bee_link;
  return {
    user_id: data.user.user_id,
    username: data.user.username,
    handle: data.user.display_name || data.user.username,
    is_admin: data.user.is_admin,
    created_at: data.user.created_at,
    bee_link: link,
    bee_connected: link?.state === "linked",
    bee_account: link?.state === "linked" ? link.bee_first_name ?? null : null,
  };
};

export const toSessionState = (data: SessionResponse): SessionState => ({
  user: toSessionUser(data),
  signupEnabled: Boolean(data.signup_enabled),
});

export const fetchSessionState = async (): Promise<SessionState> => {
  const res = await fetch(api("/api/auth/session"));
  if (!res.ok) return { user: null, signupEnabled: false };
  return toSessionState(await res.json());
};

export const fetchSession = async (): Promise<SessionUser | null> => (await fetchSessionState()).user;

export const login = async (username: string, password: string): Promise<SessionUser> => {
  const data = await jsonRequest<SessionResponse & { success: boolean }>("/api/auth/login", "POST", {
    username: username.trim(),
    password,
  });
  const user = toSessionUser({ ...data, authenticated: true });
  if (!user) throw new Error("Sign-in failed");
  return user;
};

/** Ends this browser session only: the Bee link and live ingestion keep running. */
/** Self-registration: the server creates a non-admin account and sets the session cookie. */
export const signup = async (username: string, password: string, displayName?: string): Promise<SessionUser> => {
  const data = await jsonRequest<SessionResponse & { success: boolean }>("/api/auth/signup", "POST", {
    username: username.trim(),
    password,
    display_name: displayName?.trim() || undefined,
  });
  const user = toSessionUser({ ...data, authenticated: true });
  if (!user) throw new Error("Registration failed");
  return user;
};

/** Client-side mirror of the server rules (src/serving/auth.py); the server stays authoritative. */
export const USERNAME_PATTERN = /^[A-Za-z0-9._-]{3,32}$/;
export const MIN_PASSWORD_LENGTH = 12;

export const signupFormError = (username: string, password: string, confirm: string): string | null => {
  if (!USERNAME_PATTERN.test(username.trim())) return "Username: 3-32 letters, digits, '.', '_' or '-'";
  if (password.length < MIN_PASSWORD_LENGTH) return `Password must be at least ${MIN_PASSWORD_LENGTH} characters`;
  if (password !== confirm) return "Passwords do not match";
  return null;
};

export const logout = async (): Promise<void> => {
  await jsonRequest("/api/auth/logout", "POST").catch(() => undefined);
};

export const logoutEverywhere = async (): Promise<void> => {
  await jsonRequest("/api/auth/sessions/revoke-all", "POST");
};

export const changePassword = async (currentPassword: string, newPassword: string): Promise<void> => {
  await jsonRequest("/api/auth/password", "POST", { current_password: currentPassword, new_password: newPassword });
};

// --- Bee account link -------------------------------------------------------

export const startBeePairing = async (): Promise<BeeLinkInfo> =>
  (await jsonRequest<{ bee_link: BeeLinkInfo }>("/api/bee/link", "POST")).bee_link;

/** Re-checks the Bee token; completes an approved pairing and starts live ingestion. */
export const refreshBeeLink = async (): Promise<BeeLinkInfo> =>
  (await jsonRequest<{ bee_link: BeeLinkInfo }>("/api/bee/link", "GET")).bee_link;

export const unlinkBee = async (): Promise<BeeLinkInfo> =>
  (await jsonRequest<{ bee_link: BeeLinkInfo }>("/api/bee/unlink", "POST")).bee_link;

// --- Account ------------------------------------------------------------------

/** GDPR Art. 17: erases the signed-in user's data, Bee link and account (password required). */
export const eraseAccount = async (password: string): Promise<void> => {
  await jsonRequest("/api/account/erase", "POST", { password });
};

export const listTokens = async (): Promise<AccountToken[]> =>
  (await jsonRequest<{ tokens: AccountToken[] }>("/api/account/tokens", "GET")).tokens;

export const createToken = async (name: string): Promise<{ token: string; info: AccountToken }> =>
  jsonRequest("/api/account/tokens", "POST", { name });

export const revokeToken = async (tokenId: string): Promise<void> => {
  await jsonRequest(`/api/account/tokens/${encodeURIComponent(tokenId)}`, "DELETE");
};

// --- Admin (accounts only) ------------------------------------------------------

export const listUsers = async (): Promise<AdminUser[]> =>
  (await jsonRequest<{ users: AdminUser[] }>("/api/admin/users", "GET")).users;

export const createUser = async (
  username: string,
  isAdmin: boolean
): Promise<{ user: AdminUser; initial_password: string | null }> =>
  jsonRequest("/api/admin/users", "POST", { username, is_admin: isAdmin });

export const setUserStatus = async (userId: string, status: "active" | "disabled"): Promise<void> => {
  await jsonRequest(`/api/admin/users/${encodeURIComponent(userId)}/status`, "POST", { status });
};

export const resetUserPassword = async (userId: string): Promise<string> =>
  (await jsonRequest<{ initial_password: string }>(`/api/admin/users/${encodeURIComponent(userId)}/reset-password`, "POST"))
    .initial_password;

/**
 * GDPR Art. 20 Data Portability: downloads the user's telemetry snapshot as JSON.
 */
export const exportUserDataJson = (user: SessionUser, telemetryData?: unknown): void => {
  if (typeof window === "undefined") return;
  const exportPayload = {
    export_metadata: {
      framework: "EU General Data Protection Regulation (GDPR) Art. 20 - Data Portability",
      exported_at: new Date().toISOString(),
      system: "EXAMEN Ambient Intelligence Platform",
    },
    user_profile: { user_id: user.user_id, username: user.username, bee_account: user.bee_account },
    ambient_telemetry_snapshot: telemetryData || null,
  };
  const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(exportPayload, null, 2));
  const anchor = document.createElement("a");
  anchor.setAttribute("href", dataStr);
  anchor.setAttribute("download", `examen-gdpr-export-${user.username}.json`);
  anchor.click();
};
