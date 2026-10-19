// Accounts, sessions and Bee pairing (docs/13_multi_user_accounts.md).
//
// The session lives in an HttpOnly cookie set by the server: nothing about the user (no email, no
// token, no profile) is stored in localStorage. Every API call is sent with credentials
// (see installCredentialedFetch in utils/api.ts), so each request only ever sees the signed-in
// user's own data.

import { DemoUser, BeePairingInfo } from "@/types/schemas";
import { getApiBaseUrl } from "@/utils/api";

export interface AccountUser {
  id: string | null;
  email: string | null;
  display_name?: string | null;
  created_at?: string;
  last_login_at?: string | null;
  privacy_consent_version?: string | null;
  privacy_consent_at?: string | null;
}

export interface SessionInfo {
  auth_enabled: boolean;
  authenticated: boolean;
  user: AccountUser | null;
  consent_required?: boolean;
  privacy_notice_version?: string;
  bee_device?: any;
  bee?: { pairing?: BeePairingInfo; linked?: boolean | null };
}

export interface AuthConfig {
  auth_enabled: boolean;
  min_password_length: number;
  privacy_notice_version: string;
}

export interface ApiTokenInfo {
  id: string;
  name: string;
  prefix: string;
  created_at: string;
  last_used_at?: string | null;
  token?: string; // only right after creation
}

export class ApiError extends Error {
  status: number;
  code?: string;
  constructor(message: string, status: number, code?: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

async function call<T = any>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`${getApiBaseUrl()}${path}`, {
    ...init,
    credentials: "include",
    headers: { "Content-Type": "application/json", ...(init.headers || {}) },
  });
  let data: any = null;
  try {
    data = await res.json();
  } catch {
    data = null;
  }
  if (!res.ok) {
    throw new ApiError(data?.message || data?.error || `Request failed (${res.status})`, res.status, data?.error);
  }
  return data as T;
}

const post = <T = any>(path: string, body?: any) =>
  call<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });

// ---------------------------------------------------------------------------
// Session
// ---------------------------------------------------------------------------

export const fetchAuthConfig = () => call<AuthConfig>("/api/auth/config");

export const fetchSession = () => call<SessionInfo>("/api/auth/session");

export const registerAccount = (input: {
  email: string;
  password: string;
  display_name?: string;
  privacy_consent: boolean;
}) => post<{ authenticated: boolean; user: AccountUser }>("/api/auth/register", input);

export const loginAccount = (email: string, password: string) =>
  post<{ authenticated: boolean; user: AccountUser; consent_required?: boolean }>("/api/auth/login", {
    email,
    password,
  });

/** Signs out of this browser. The Bee keeps listening for the user (disconnect it explicitly). */
export const logoutUser = async (): Promise<void> => {
  try {
    await post("/api/auth/logout");
  } catch (err) {
    console.warn("Logout request error:", err);
  }
};

export const acceptPrivacyNotice = () =>
  call<{ user: AccountUser }>("/api/account", { method: "PATCH", body: JSON.stringify({ privacy_consent: true }) });

/** Maps the signed-in account to the view model the dashboard components already use. */
export const toUiUser = (session: SessionInfo | null): DemoUser | null => {
  if (!session?.authenticated || !session.user) return null;
  const u = session.user;
  const pairing = session.bee?.pairing;
  const linked = !!session.bee?.linked || !!session.bee_device?.account;
  return {
    user_id: u.id || "local",
    handle: u.display_name || u.email || "Local user",
    email: u.email,
    avatar_seed: u.id || "local",
    created_at: u.created_at || new Date().toISOString(),
    last_active: u.last_login_at || undefined,
    gdpr_compliant: true,
    privacy_framework: "EU GDPR",
    data_retention: "until account deletion",
    bee_connected: linked,
    bee_account: session.bee_device?.account || pairing?.account || null,
    bee_pairing: pairing || null,
  };
};

// ---------------------------------------------------------------------------
// Account (GDPR)
// ---------------------------------------------------------------------------

export const fetchAccount = () =>
  call<{ user: AccountUser; tokens: ApiTokenInfo[]; bee: any; privacy_notice_version: string }>("/api/account");

export const updateDisplayName = (display_name: string) =>
  call<{ user: AccountUser }>("/api/account", { method: "PATCH", body: JSON.stringify({ display_name }) });

export const changePassword = (current_password: string, new_password: string) =>
  post<{ success: boolean; other_sessions_signed_out: number }>("/api/account/password", {
    current_password,
    new_password,
  });

/** GDPR Art. 17: permanently deletes the account, the Bee login and every stored record. */
export const deleteAccount = (password: string) =>
  call<{ success: boolean }>("/api/account", { method: "DELETE", body: JSON.stringify({ password }) });

/** GDPR Art. 15 / 20: downloads every record the server holds about the user. */
export const exportUserDataJson = async (_user?: DemoUser | null, _unused?: any): Promise<void> => {
  if (typeof window === "undefined") return;
  const res = await fetch(`${getApiBaseUrl()}/api/account/export`, { credentials: "include" });
  if (!res.ok) throw new ApiError(`Export failed (${res.status})`, res.status);
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `examen-export-${new Date().toISOString().slice(0, 10)}.json`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
};

export const listApiTokens = () => call<{ tokens: ApiTokenInfo[] }>("/api/account/tokens");

export const createApiToken = (name: string) =>
  post<{ token: ApiTokenInfo; message: string }>("/api/account/tokens", { name });

export const revokeApiToken = (id: string) =>
  call<{ success: boolean }>(`/api/account/tokens/${encodeURIComponent(id)}`, { method: "DELETE" });

// ---------------------------------------------------------------------------
// Bee pairing (per user)
// ---------------------------------------------------------------------------

export const startBeePairing = () => post<{ bee_pairing: BeePairingInfo }>("/api/bee/pair");

export const getBeePairing = () => call<{ bee_pairing: BeePairingInfo }>("/api/bee/pair");

export const cancelBeePairing = () => call<{ bee_pairing: BeePairingInfo }>("/api/bee/pair", { method: "DELETE" });

/** Removes this user's Bee login and stops their ambient ingestion. Stored data is kept. */
export const disconnectBee = async (): Promise<boolean> => {
  try {
    const res = await post<{ success: boolean }>("/api/bee/disconnect");
    return !!res.success;
  } catch {
    return false;
  }
};
