// Admin console client (docs/next_steps/admin_console/04): runtime settings, service log,
// incidents, health and the admin-only SSE channel. Pure helpers below are unit-tested (admin.test.ts).

import { getApiBaseUrl } from "@/utils/api";

export type ApplyMode = "hot" | "runtime" | "boot";
export type SettingSource = "default" | "env" | "override";

export interface SettingRow {
  key: string;
  env: string;
  group: string;
  label: string;
  help?: string;
  apply: ApplyMode;
  type: "bool" | "int" | "float" | "str" | "choice";
  optional: boolean;
  choices?: (string | number)[] | null;
  minimum?: number | null;
  maximum?: number | null;
  pattern?: string | null;
  tests?: string[] | null;
  risk?: string | null;
  effective: any;
  source: SettingSource;
  env_value: any;
  override_by?: string | null;
  override_at?: string | null;
}

export interface SettingsPayload {
  version: number;
  settings: SettingRow[];
  read_only: { key: string; env: string; effective: any; apply: "boot" }[];
  secrets: { key: string; env: string; status: "configured" | "missing" | "derived" | "not set" }[];
}

export interface ProbeResult {
  group: string;
  ok: boolean;
  latency_ms: number;
  error_type?: string | null;
  message?: string | null;
}

export interface ServiceEvent {
  id?: number;
  ref: string;
  at: string;
  level: "info" | "warning" | "error" | "critical";
  code: string;
  component: string;
  user_id?: string | null;
  user_email?: string | null;
  message: string;
  context?: Record<string, any>;
  error_type?: string | null;
  location?: string | null;
}

export interface Incident {
  id: string;
  code: string;
  component: string;
  severity: "warning" | "error" | "critical";
  title: string;
  user_id?: string | null;
  user_email?: string | null;
  status: "open" | "acknowledged" | "resolved";
  count: number;
  first_seen: string;
  last_seen: string;
  resolved_at?: string | null;
  change_id?: string | null;
  details?: Record<string, any>;
}

export interface ChangeSet {
  change_id: string;
  at: string;
  by_user: string;
  by_email?: string | null;
  note?: string | null;
  test_result?: { forced?: boolean; untested?: string[] } | null;
  changes: { key: string; old: any; new: any }[];
}

export class AdminApiError extends Error {
  status: number;
  code?: string;
  errors?: Record<string, string>;
  constructor(message: string, status: number, code?: string, errors?: Record<string, string>) {
    super(message);
    this.status = status;
    this.code = code;
    this.errors = errors;
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
    throw new AdminApiError(data?.message || data?.error || `Request failed (${res.status})`, res.status, data?.error, data?.errors);
  }
  return data as T;
}

const send = <T = any>(method: string, path: string, body?: any) =>
  call<T>(path, { method, body: body === undefined ? undefined : JSON.stringify(body) });

const query = (params: Record<string, any>) => {
  const q = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "") q.set(k, String(v));
  });
  const s = q.toString();
  return s ? `?${s}` : "";
};

// ---------------------------------------------------------------------------
// API
// ---------------------------------------------------------------------------

export const getSettings = () => call<SettingsPayload>("/api/admin/settings");
export const testSettings = (changes: Record<string, any>) =>
  send<{ ok: boolean; results: ProbeResult[] }>("POST", "/api/admin/settings/test", { changes });
export const saveSettings = (changes: Record<string, any>, opts: { force?: boolean; base_version?: number; note?: string } = {}) =>
  send<{ change_id: string; applied: string[]; rebuilt_runtimes: number; forced_untested: string[] }>(
    "PUT", "/api/admin/settings", { changes, ...opts });
export const resetSetting = (key: string) => send("DELETE", `/api/admin/settings/${encodeURIComponent(key)}`);
export const resetAllSettings = () => send("POST", "/api/admin/settings/reset-all");
export const getSettingsHistory = () => call<{ history: ChangeSet[] }>("/api/admin/settings/history");
export const revertChange = (change_id: string) => send("POST", "/api/admin/settings/revert", { change_id });

export const getLogs = (filters: { level?: string; component?: string; code?: string; user_id?: string; q?: string; before_id?: number; limit?: number }) =>
  call<{ events: ServiceEvent[] }>(`/api/admin/logs${query(filters)}`);
export const getIncidents = (status = "active") => call<{ incidents: Incident[] }>(`/api/admin/incidents${query({ status })}`);
export const getIncident = (id: string) => call<{ incident: Incident; events: ServiceEvent[] }>(`/api/admin/incidents/${id}`);
export const ackIncident = (id: string) => send<{ incident: Incident }>("POST", `/api/admin/incidents/${id}/ack`);
export const resolveIncident = (id: string) => send<{ incident: Incident }>("POST", `/api/admin/incidents/${id}/resolve`);
export const getHealth = () => call<any>("/api/admin/health");
export const getAudit = () => call<{ audit: any[] }>("/api/admin/audit");
export const adminEventsUrl = () => `${getApiBaseUrl()}/api/admin/events`;

// ---------------------------------------------------------------------------
// Pure helpers
// ---------------------------------------------------------------------------

/** Converts what the admin typed into the value the API expects (null = remove the override). */
export const parseInput = (row: SettingRow, raw: any): any => {
  if (row.type === "bool") return Boolean(raw);
  if (row.type === "int" || row.type === "float") {
    if (raw === "" || raw === null || raw === undefined) return NaN;
    const n = Number(raw);
    return row.type === "int" ? Math.trunc(n) : n;
  }
  if (row.type === "choice" && row.choices && typeof row.choices[0] === "number") return Number(raw);
  const text = String(raw ?? "").trim();
  return text === "" && row.optional ? null : text;
};

/** Client-side check mirroring the registry constraints (the server stays authoritative). */
export const inputError = (row: SettingRow, value: any): string | null => {
  if (row.type === "int" || row.type === "float") {
    if (typeof value !== "number" || Number.isNaN(value)) return "Enter a number";
    if (row.minimum != null && value < row.minimum) return `At least ${row.minimum}`;
    if (row.maximum != null && value > row.maximum) return `At most ${row.maximum}`;
  }
  if (row.choices && row.choices.length && value !== null && !row.choices.includes(value)) return "Not an allowed value";
  if (row.pattern && typeof value === "string" && value && !new RegExp(row.pattern).test(value)) return "Invalid format";
  if (value === null && !row.optional) return "A value is required";
  return null;
};

/** Pending edits → the change set to send: only keys whose value differs from the effective one. */
export const buildChangeSet = (rows: SettingRow[], edits: Record<string, any>): Record<string, any> => {
  const out: Record<string, any> = {};
  for (const row of rows) {
    if (!(row.key in edits)) continue;
    const value = edits[row.key];
    if (value !== row.effective) out[row.key] = value;
  }
  return out;
};

/** Probe groups needed by a change set (keys that declare tests). */
export const testsNeeded = (rows: SettingRow[], changes: Record<string, any>): string[] => {
  const groups = new Set<string>();
  rows.filter((r) => r.key in changes).forEach((r) => (r.tests || []).forEach((g) => groups.add(g)));
  return Array.from(groups).sort();
};

export const sourceLabel = (row: SettingRow): string =>
  row.source === "override" ? `override${row.override_at ? ` · ${row.override_at.slice(0, 16).replace("T", " ")}` : ""}` : row.source;

export const APPLY_LABEL: Record<ApplyMode, string> = {
  hot: "instant",
  runtime: "restarts runtimes",
  boot: "needs server restart",
};

const SEVERITY_RANK: Record<string, number> = { critical: 3, error: 2, warning: 1 };

/** Open incidents first, then by severity and last seen. */
export const sortIncidents = (items: Incident[]): Incident[] =>
  [...items].sort((a, b) => {
    const open = (i: Incident) => (i.status === "resolved" ? 0 : 1);
    return open(b) - open(a)
      || (SEVERITY_RANK[b.severity] || 0) - (SEVERITY_RANK[a.severity] || 0)
      || b.last_seen.localeCompare(a.last_seen);
  });

/** Applies an incident message from the admin SSE channel to the list. */
export const applyIncidentEvent = (items: Incident[], type: string, incident: Incident, showResolved = false): Incident[] => {
  const rest = items.filter((i) => i.id !== incident.id);
  if (type === "incident_resolved" && !showResolved) return sortIncidents(rest);
  return sortIncidents([incident, ...rest]);
};

/** Prepends live events, keeping the list bounded. */
export const prependEvents = (items: ServiceEvent[], incoming: ServiceEvent[], max = 500): ServiceEvent[] => {
  const seen = new Set(items.map((e) => e.ref));
  return [...incoming.filter((e) => !seen.has(e.ref)), ...items].slice(0, max);
};

export const formatBytes = (n?: number | null): string => {
  if (n == null) return "—";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let v = n;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i++;
  }
  return `${v.toFixed(v >= 10 || i === 0 ? 0 : 1)} ${units[i]}`;
};
