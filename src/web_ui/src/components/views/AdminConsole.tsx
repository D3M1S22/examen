"use client";

// Admin console (docs/next_steps/admin_console/04 §2): accounts, runtime settings, service log and
// health. Admins manage the service: nothing here shows a user's data.

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AdminSection } from "@/components/ui/AdminSection";
import {
  ackIncident,
  adminEventsUrl,
  APPLY_LABEL,
  applyIncidentEvent,
  buildChangeSet,
  ChangeSet,
  formatBytes,
  formatTokens,
  getAudit,
  getHealth,
  getIncident,
  getIncidents,
  getLogs,
  getSettings,
  getSettingsHistory,
  getUsage,
  Incident,
  inputError,
  parseInput,
  prependEvents,
  ProbeResult,
  resetAllSettings,
  resetSetting,
  resolveIncident,
  revertChange,
  saveSettings,
  ServiceEvent,
  SettingRow,
  SettingsPayload,
  shareOf,
  sortIncidents,
  sourceLabel,
  testSettings,
  testsNeeded,
  totalTokens,
  UsagePayload,
  UsageRange,
  usageBars,
} from "@/utils/admin";

type Tab = "accounts" | "settings" | "logs" | "health";
type Message = { kind: "ok" | "error"; text: string } | null;

const card = "p-4 rounded-2xl bg-zinc-900/60 border border-white/10";
const btn = "px-3 py-1.5 rounded-lg text-[11px] font-semibold transition-colors disabled:opacity-40";
const btnGhost = `${btn} bg-white/5 hover:bg-white/10 border border-white/10 text-zinc-200`;
const btnPrimary = `${btn} bg-cyan-500 hover:bg-cyan-400 text-zinc-950`;
const btnDanger = `${btn} bg-red-950/50 hover:bg-red-900/60 border border-red-500/40 text-red-200`;
const input = "w-full px-2.5 py-1.5 rounded-lg bg-black/50 border border-white/15 text-white text-xs focus:outline-none focus:border-cyan-400";
const SEVERITY: Record<string, string> = {
  critical: "bg-red-600/30 border-red-400/60 text-red-100",
  error: "bg-red-950/60 border-red-500/40 text-red-200",
  warning: "bg-amber-950/50 border-amber-500/40 text-amber-200",
  info: "bg-zinc-800 border-white/10 text-zinc-300",
};
const ts = (iso?: string | null) => (iso ? iso.slice(0, 19).replace("T", " ") : "—");
const fmt = (v: any) => (v === null || v === undefined || v === "" ? "—" : typeof v === "boolean" ? (v ? "on" : "off") : String(v));

export function AdminConsole({ selfId }: { selfId: string }) {
  const [tab, setTab] = useState<Tab>("settings");
  const [message, setMessage] = useState<Message>(null);
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [liveEvents, setLiveEvents] = useState<ServiceEvent[]>([]);
  const [health, setHealth] = useState<any>(null);
  const [live, setLive] = useState(false);

  // Admin-only SSE channel: service events, incidents, health snapshots
  useEffect(() => {
    if (typeof window === "undefined" || typeof EventSource === "undefined") return;
    const es = new EventSource(adminEventsUrl(), { withCredentials: true });
    es.addEventListener("hello", () => setLive(true));
    es.addEventListener("service_event", (e: MessageEvent) => {
      try {
        setLiveEvents((prev) => prependEvents(prev, [JSON.parse(e.data)], 200));
      } catch { /* ignore malformed frames */ }
    });
    for (const type of ["incident_opened", "incident_updated", "incident_resolved"]) {
      es.addEventListener(type, (e: MessageEvent) => {
        try {
          setIncidents((prev) => applyIncidentEvent(prev, type, JSON.parse(e.data)));
        } catch { /* ignore */ }
      });
    }
    es.addEventListener("health", (e: MessageEvent) => {
      try {
        setHealth(JSON.parse(e.data));
      } catch { /* ignore */ }
    });
    es.onerror = () => setLive(false);
    return () => es.close();
  }, []);

  const refreshIncidents = useCallback(() => {
    getIncidents("active").then((r) => setIncidents(sortIncidents(r.incidents))).catch(() => undefined);
  }, []);
  useEffect(() => { refreshIncidents(); }, [refreshIncidents]);

  const openCount = incidents.filter((i) => i.status !== "resolved").length;
  const tabs: { id: Tab; label: string }[] = [
    { id: "settings", label: "Settings" },
    { id: "logs", label: `Logs${openCount ? ` · ${openCount}` : ""}` },
    { id: "health", label: "Health" },
    { id: "accounts", label: "Accounts" },
  ];

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="font-serif text-[28px] text-primary">Admin console</h1>
          <p className="text-xs text-zinc-400">
            Service settings, health and errors. Users&apos; data is never shown here.
          </p>
        </div>
        <div className="flex items-center gap-2 text-[11px] text-zinc-400">
          <span className={`w-2 h-2 rounded-full ${live ? "bg-emerald-400 animate-pulse" : "bg-zinc-600"}`} />
          {live ? "Live" : "Offline"}
        </div>
      </div>

      <div role="tablist" className="flex gap-1 p-1 rounded-xl bg-black/40 border border-white/10 w-fit">
        {tabs.map((t) => (
          <button key={t.id} role="tab" aria-selected={tab === t.id} onClick={() => { setTab(t.id); setMessage(null); }}
            className={`px-4 py-1.5 rounded-lg text-xs font-semibold ${tab === t.id ? "bg-cyan-500/20 text-cyan-200 border border-cyan-400/50" : "text-zinc-400 hover:text-zinc-200"}`}>
            {t.label}
          </button>
        ))}
      </div>

      {message && (
        <div role="status" className={`p-3 rounded-xl text-xs ${message.kind === "ok" ? "bg-emerald-950/50 border border-emerald-500/30 text-emerald-200" : "bg-red-950/60 border border-red-500/40 text-red-300"}`}>
          {message.text}
        </div>
      )}

      {tab === "settings" && <SettingsTab setMessage={setMessage} />}
      {tab === "logs" && (
        <LogsTab incidents={incidents} setIncidents={setIncidents} refreshIncidents={refreshIncidents}
          liveEvents={liveEvents} setMessage={setMessage} />
      )}
      {tab === "health" && <HealthTab health={health} setHealth={setHealth} />}
      {tab === "accounts" && <AccountsTab selfId={selfId} setMessage={setMessage} />}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Settings
// ---------------------------------------------------------------------------

function SettingInput({ row, value, onChange }: { row: SettingRow; value: any; onChange: (v: any) => void }) {
  if (row.type === "bool") {
    return (
      <label className="inline-flex items-center gap-2 text-xs text-zinc-200">
        <input type="checkbox" checked={Boolean(value)} onChange={(e) => onChange(e.target.checked)} />
        {value ? "on" : "off"}
      </label>
    );
  }
  if (row.choices && row.choices.length) {
    return (
      <select className={input} value={String(value ?? "")} onChange={(e) => onChange(parseInput(row, e.target.value))}>
        {row.choices.map((c) => <option key={String(c)} value={String(c)}>{String(c)}</option>)}
      </select>
    );
  }
  const numeric = row.type === "int" || row.type === "float";
  return (
    <input className={input} type={numeric ? "number" : "text"} value={value ?? ""}
      step={row.type === "float" ? "any" : 1} min={row.minimum ?? undefined} max={row.maximum ?? undefined}
      placeholder={row.optional ? "empty = not set" : undefined}
      onChange={(e) => onChange(numeric ? (e.target.value === "" ? "" : e.target.value) : e.target.value)} />
  );
}

function SettingsTab({ setMessage }: { setMessage: (m: Message) => void }) {
  const [data, setData] = useState<SettingsPayload | null>(null);
  const [raw, setRaw] = useState<Record<string, any>>({});
  const [tests, setTests] = useState<ProbeResult[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [history, setHistory] = useState<ChangeSet[] | null>(null);
  const [open, setOpen] = useState<Record<string, boolean>>({ "AI models": true });

  const load = useCallback(() => {
    getSettings().then((d) => { setData(d); setRaw({}); setTests(null); })
      .catch((e) => setMessage({ kind: "error", text: e.message }));
  }, [setMessage]);
  useEffect(() => { load(); }, [load]);

  const rows = data?.settings || [];
  const edits = useMemo(() => {
    const out: Record<string, any> = {};
    for (const row of rows) if (row.key in raw) out[row.key] = parseInput(row, raw[row.key]);
    return out;
  }, [rows, raw]);
  const changes = useMemo(() => buildChangeSet(rows, edits), [rows, edits]);
  const errors = useMemo(() => {
    const out: Record<string, string> = {};
    rows.forEach((r) => {
      if (r.key in changes) {
        const err = inputError(r, changes[r.key]);
        if (err) out[r.key] = err;
      }
    });
    return out;
  }, [rows, changes]);
  const needed = testsNeeded(rows, changes);
  const passed = tests !== null && tests.every((t) => t.ok) && needed.every((g) => tests.some((t) => t.group === g && t.ok));
  const pending = Object.keys(changes);
  const groups = useMemo(() => {
    const map = new Map<string, SettingRow[]>();
    rows.forEach((r) => map.set(r.group, [...(map.get(r.group) || []), r]));
    return Array.from(map.entries());
  }, [rows]);

  const runTest = async () => {
    setBusy(true);
    setMessage(null);
    try {
      const r = await testSettings(changes);
      setTests(r.results);
      setMessage(r.ok ? { kind: "ok", text: "Test passed: you can save." } : { kind: "error", text: "Test failed: check the results below." });
    } catch (e: any) {
      setMessage({ kind: "error", text: e.message });
    } finally {
      setBusy(false);
    }
  };

  const save = async (force = false) => {
    if (force && !confirm("Save without a passing test? The change is flagged in the history and the log.")) return;
    setBusy(true);
    setMessage(null);
    try {
      const r = await saveSettings(changes, { force, base_version: data?.version });
      setMessage({ kind: "ok", text: `Saved ${r.applied.length} setting(s)${r.rebuilt_runtimes ? `; ${r.rebuilt_runtimes} user runtime(s) restarted` : ""}.` });
      load();
    } catch (e: any) {
      const detail = e.errors ? Object.entries(e.errors).map(([k, v]) => `${k}: ${v}`).join(" · ") : "";
      setMessage({ kind: "error", text: `${e.message}${detail ? ` (${detail})` : ""}` });
      if (e.code === "settings_changed_meanwhile") load();
    } finally {
      setBusy(false);
    }
  };

  const act = async (fn: () => Promise<any>, ok: string) => {
    setBusy(true);
    try {
      await fn();
      setMessage({ kind: "ok", text: ok });
      load();
      if (history) setHistory((await getSettingsHistory()).history);
    } catch (e: any) {
      setMessage({ kind: "error", text: e.message });
    } finally {
      setBusy(false);
    }
  };

  if (!data) return <p className="text-xs text-zinc-400">Loading settings…</p>;

  return (
    <div className="space-y-4">
      {pending.length > 0 && (
        <div className="sticky top-2 z-10 p-3 rounded-2xl bg-cyan-950/80 border border-cyan-500/40 backdrop-blur space-y-2">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-xs text-cyan-100">
              {pending.length} pending change(s): {pending.map((k) => rows.find((r) => r.key === k)?.env).join(", ")}
            </p>
            <div className="flex gap-2">
              {needed.length > 0 && (
                <button className={btnGhost} disabled={busy || Object.keys(errors).length > 0} onClick={runTest}>
                  Test {needed.join(", ")}
                </button>
              )}
              <button className={btnPrimary} disabled={busy || Object.keys(errors).length > 0 || (needed.length > 0 && !passed)}
                onClick={() => save(false)}>Save</button>
              {needed.length > 0 && !passed && (
                <button className={btnDanger} disabled={busy || Object.keys(errors).length > 0} onClick={() => save(true)}>
                  Save without test
                </button>
              )}
              <button className={btnGhost} disabled={busy} onClick={() => { setRaw({}); setTests(null); }}>Discard</button>
            </div>
          </div>
          {tests && (
            <ul className="space-y-1">
              {tests.map((t) => (
                <li key={t.group} className={`text-[11px] ${t.ok ? "text-emerald-300" : "text-red-300"}`}>
                  {t.ok ? "✓" : "✗"} {t.group} · {t.latency_ms} ms{t.message ? ` · ${t.message}` : ""}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      <div className="flex flex-wrap gap-2">
        <button className={btnGhost} onClick={async () => setHistory(history ? null : (await getSettingsHistory()).history)}>
          {history ? "Hide history" : "History"}
        </button>
        <button className={btnDanger} disabled={busy || !rows.some((r) => r.source === "override")}
          onClick={() => confirm("Remove every override and go back to the .env values?") && act(resetAllSettings, "All settings reset to their defaults.")}>
          Reset all to defaults
        </button>
      </div>

      {history && (
        <div className={`${card} space-y-2`}>
          <h3 className="text-xs font-semibold text-zinc-200">Change history</h3>
          {history.length === 0 && <p className="text-[11px] text-zinc-500">No changes yet.</p>}
          {history.map((h) => (
            <div key={h.change_id} className="flex items-start justify-between gap-3 py-2 border-t border-white/5 text-[11px]">
              <div className="min-w-0">
                <p className="text-zinc-300">{ts(h.at)} · {h.by_email || h.by_user}{h.note ? ` · ${h.note}` : ""}
                  {h.test_result?.forced && <span className="ml-1 text-amber-300">(saved without test)</span>}</p>
                {h.changes.map((c) => (
                  <p key={c.key} className="font-mono text-zinc-400 truncate">
                    {rows.find((r) => r.key === c.key)?.env || c.key}: {fmt(c.old)} → {c.new === null ? "default" : fmt(c.new)}
                  </p>
                ))}
              </div>
              <button className={btnGhost} disabled={busy}
                onClick={() => confirm("Revert this change?") && act(() => revertChange(h.change_id), "Change reverted.")}>Revert</button>
            </div>
          ))}
        </div>
      )}

      {groups.map(([group, items]) => (
        <section key={group} className={card}>
          <button className="w-full flex items-center justify-between text-left" onClick={() => setOpen((o) => ({ ...o, [group]: !o[group] }))}>
            <h3 className="text-sm font-semibold text-zinc-100">{group}</h3>
            <span className="text-[11px] text-zinc-400">
              {items.filter((r) => r.source === "override").length ? `${items.filter((r) => r.source === "override").length} overridden · ` : ""}
              {open[group] ? "▾" : "▸"}
            </span>
          </button>
          {open[group] && (
            <div className="mt-3 divide-y divide-white/5">
              {items.map((row) => {
                const value = row.key in raw ? raw[row.key] : row.effective;
                const changed = row.key in changes;
                return (
                  <div key={row.key} className="py-2.5 grid grid-cols-1 md:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)_auto] gap-2 items-center">
                    <div className="min-w-0">
                      <p className="text-xs text-zinc-100">{row.label} <span className="font-mono text-[10px] text-zinc-500">{row.env}</span></p>
                      <p className="text-[10px] text-zinc-500">
                        <span className={row.source === "override" ? "text-cyan-300" : ""}>{sourceLabel(row)}</span>
                        {row.source === "override" && <> · default {fmt(row.env_value)}</>}
                        {" · "}{APPLY_LABEL[row.apply]}{row.help ? ` · ${row.help}` : ""}
                      </p>
                      {row.risk && changed && <p className="text-[10px] text-amber-300">⚠ {row.risk}</p>}
                      {errors[row.key] && <p className="text-[10px] text-red-300">{errors[row.key]}</p>}
                    </div>
                    <SettingInput row={row} value={value} onChange={(v) => setRaw((r) => ({ ...r, [row.key]: v }))} />
                    <div className="flex gap-1 justify-end">
                      {row.source === "override" && (
                        <button className={btnGhost} disabled={busy} title="Back to the .env value"
                          onClick={() => act(() => resetSetting(row.key), `${row.env} reset to its default.`)}>Reset</button>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </section>
      ))}

      <section className={card}>
        <h3 className="text-sm font-semibold text-zinc-100 mb-2">Secrets (environment only)</h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          {data.secrets.map((s) => (
            <p key={s.key} className="text-xs text-zinc-300 font-mono">
              {s.env}: <span className={s.status === "missing" ? "text-red-300" : "text-emerald-300"}>{s.status}</span>
            </p>
          ))}
        </div>
      </section>
      <section className={card}>
        <h3 className="text-sm font-semibold text-zinc-100 mb-2">Read-only (needs a server restart)</h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-1">
          {data.read_only.map((r) => (
            <p key={r.key} className="text-[11px] text-zinc-400 font-mono truncate">{r.env} = {fmt(r.effective)}</p>
          ))}
        </div>
      </section>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Logs
// ---------------------------------------------------------------------------

function LogsTab({ incidents, setIncidents, refreshIncidents, liveEvents, setMessage }: {
  incidents: Incident[];
  setIncidents: (f: (prev: Incident[]) => Incident[]) => void;
  refreshIncidents: () => void;
  liveEvents: ServiceEvent[];
  setMessage: (m: Message) => void;
}) {
  const [events, setEvents] = useState<ServiceEvent[]>([]);
  const [filters, setFilters] = useState({ level: "warning", component: "", q: "" });
  const [paused, setPaused] = useState(false);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [detail, setDetail] = useState<{ incident: Incident; events: ServiceEvent[] } | null>(null);
  const seenLive = useRef(0);

  const load = useCallback((before?: number) => {
    getLogs({ ...filters, before_id: before, limit: 100 })
      .then((r) => setEvents((prev) => (before ? [...prev, ...r.events] : r.events)))
      .catch((e) => setMessage({ kind: "error", text: e.message }));
  }, [filters, setMessage]);
  useEffect(() => { load(); }, [load]);

  // Live events (already level ≥ warning) when not paused and matching the component filter
  useEffect(() => {
    if (paused || liveEvents.length === seenLive.current) return;
    const fresh = liveEvents.slice(0, liveEvents.length - seenLive.current)
      .filter((e) => !filters.component || e.component === filters.component)
      .filter((e) => !filters.q || e.message.toLowerCase().includes(filters.q.toLowerCase()));
    seenLive.current = liveEvents.length;
    if (fresh.length) setEvents((prev) => prependEvents(prev, fresh));
  }, [liveEvents, paused, filters]);

  const lifecycle = async (fn: () => Promise<{ incident: Incident }>) => {
    try {
      const r = await fn();
      setIncidents((prev) => applyIncidentEvent(prev, r.incident.status === "resolved" ? "incident_resolved" : "incident_updated", r.incident));
    } catch (e: any) {
      setMessage({ kind: "error", text: e.message });
    }
  };

  const exportJson = () => {
    const blob = new Blob([JSON.stringify(events, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `examen-service-log-${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };

  const components = ["", "bee", "orchestrator", "gatekeeper", "pipeline", "llm", "event_engine", "backfill", "storage", "auth", "serving", "settings", "system"];

  return (
    <div className="space-y-5">
      <section className={card}>
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold text-zinc-100">Incidents</h3>
          <button className={btnGhost} onClick={refreshIncidents}>Refresh</button>
        </div>
        {incidents.length === 0 && <p className="text-xs text-emerald-300">No open incidents.</p>}
        <div className="space-y-2">
          {incidents.map((inc) => (
            <div key={inc.id} className={`p-3 rounded-xl border ${SEVERITY[inc.severity] || SEVERITY.info}`}>
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="text-xs font-semibold">{inc.title}</p>
                  <p className="text-[10px] opacity-80 font-mono">
                    {inc.code} · {inc.component}{inc.user_email ? ` · ${inc.user_email}` : ""} · ×{inc.count} · first {ts(inc.first_seen)} · last {ts(inc.last_seen)}
                    {inc.status === "acknowledged" && " · acknowledged"}
                  </p>
                </div>
                <div className="flex gap-1.5 shrink-0">
                  <button className={btnGhost} onClick={async () => setDetail(detail?.incident.id === inc.id ? null : await getIncident(inc.id))}>Details</button>
                  {inc.change_id && (
                    <button className={btnDanger} onClick={async () => {
                      if (!confirm("Revert the settings change linked to this incident?")) return;
                      try {
                        await revertChange(inc.change_id!);
                        setMessage({ kind: "ok", text: "Settings change reverted." });
                      } catch (e: any) {
                        setMessage({ kind: "error", text: e.message });
                      }
                    }}>Revert settings change</button>
                  )}
                  {inc.status === "open" && <button className={btnGhost} onClick={() => lifecycle(() => ackIncident(inc.id))}>Acknowledge</button>}
                  <button className={btnGhost} onClick={() => lifecycle(() => resolveIncident(inc.id))}>Resolve</button>
                </div>
              </div>
              {detail?.incident.id === inc.id && (
                <div className="mt-2 space-y-1">
                  {detail.events.length === 0 && <p className="text-[10px] opacity-80">Raised by a health check ({JSON.stringify(inc.details || {})}).</p>}
                  {detail.events.slice(0, 10).map((e) => (
                    <p key={e.ref} className="text-[10px] font-mono opacity-80 truncate">{ts(e.at)} {e.message}</p>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      </section>

      <section className={card}>
        <div className="flex flex-wrap items-end gap-2 mb-3">
          <h3 className="text-sm font-semibold text-zinc-100 mr-auto">Service log</h3>
          <select className={`${input} w-auto`} value={filters.level} onChange={(e) => setFilters((f) => ({ ...f, level: e.target.value }))}>
            {["info", "warning", "error", "critical"].map((l) => <option key={l} value={l}>{l}+</option>)}
          </select>
          <select className={`${input} w-auto`} value={filters.component} onChange={(e) => setFilters((f) => ({ ...f, component: e.target.value }))}>
            {components.map((c) => <option key={c} value={c}>{c || "all components"}</option>)}
          </select>
          <input className={`${input} w-48`} placeholder="Search messages" value={filters.q}
            onChange={(e) => setFilters((f) => ({ ...f, q: e.target.value }))} />
          <button className={btnGhost} onClick={() => setPaused((p) => !p)}>{paused ? "Resume live" : "Pause live"}</button>
          <button className={btnGhost} onClick={exportJson} disabled={!events.length}>Export</button>
        </div>
        <div className="divide-y divide-white/5">
          {events.length === 0 && <p className="text-xs text-zinc-500">No events.</p>}
          {events.map((e) => (
            <div key={e.ref} className="py-1.5">
              <button className="w-full text-left flex items-start gap-2" onClick={() => setExpanded(expanded === e.ref ? null : e.ref)}>
                <span className={`shrink-0 px-1.5 rounded border text-[9px] uppercase ${SEVERITY[e.level] || SEVERITY.info}`}>{e.level}</span>
                <span className="shrink-0 font-mono text-[10px] text-zinc-500">{ts(e.at)}</span>
                <span className="shrink-0 font-mono text-[10px] text-cyan-300">{e.code}</span>
                <span className="text-[11px] text-zinc-300 truncate">{e.message}</span>
              </button>
              {expanded === e.ref && (
                <div className="mt-1 ml-2 p-2 rounded-lg bg-black/40 font-mono text-[10px] text-zinc-400 space-y-0.5">
                  <p>component {e.component}{e.user_email ? ` · user ${e.user_email}` : ""} · ref {e.ref}</p>
                  {e.error_type && <p>error {e.error_type}</p>}
                  {e.location && <p>at {e.location}</p>}
                  {e.context && Object.keys(e.context).length > 0 && <p>context {JSON.stringify(e.context)}</p>}
                  <p className="whitespace-pre-wrap break-all text-zinc-300">{e.message}</p>
                </div>
              )}
            </div>
          ))}
        </div>
        {events.length >= 100 && (
          <button className={`${btnGhost} mt-3`} onClick={() => load(events[events.length - 1]?.id)}>Load older</button>
        )}
      </section>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Health
// ---------------------------------------------------------------------------

function Stat({ label, value, warn }: { label: string; value: React.ReactNode; warn?: boolean }) {
  return (
    <div className={card}>
      <p className="text-[10px] uppercase tracking-wider text-zinc-500">{label}</p>
      <p className={`mt-1 text-lg font-semibold ${warn ? "text-amber-300" : "text-zinc-100"}`}>{value}</p>
    </div>
  );
}

function HealthTab({ health, setHealth }: { health: any; setHealth: (h: any) => void }) {
  const [error, setError] = useState<string | null>(null);
  const refresh = useCallback(() => {
    getHealth().then(setHealth).catch((e) => setError(e.message));
  }, [setHealth]);
  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 30000);
    return () => clearInterval(t);
  }, [refresh]);

  if (error && !health) return <p className="text-xs text-red-300">{error}</p>;
  if (!health) return <p className="text-xs text-zinc-400">Loading health…</p>;
  const mem = health.memory || {};
  const disk = health.disk || {};
  const llm = health.llm || {};
  const memShare = mem.rss_bytes && mem.limit_bytes ? mem.rss_bytes / mem.limit_bytes : null;
  const incidentsOpen = Object.values(health.incidents_open || {}).reduce((a: number, b: any) => a + Number(b), 0);
  const uptime = health.uptime_s ?? 0;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <Stat label="Uptime" value={`${Math.floor(uptime / 3600)} h ${Math.floor((uptime % 3600) / 60)} min`} />
        <Stat label="Memory" value={`${formatBytes(mem.rss_bytes)} / ${formatBytes(mem.limit_bytes)}`} warn={memShare !== null && memShare > 0.75} />
        <Stat label="Disk free" value={formatBytes(disk.free_bytes)} />
        <Stat label="Open incidents" value={incidentsOpen} warn={incidentsOpen > 0} />
        <Stat label="Live Bee streams" value={`${health.streams?.active ?? 0} / ${health.streams?.max ?? "—"}`} />
        <Stat label="LLM slots" value={`${llm.slots_in_use ?? 0} / ${llm.slots_max ?? "—"}`} />
        <Stat label="Gatekeeper fallbacks (15 min)"
          value={llm.gatekeeper_fallback_rate == null ? "—" : `${Math.round(llm.gatekeeper_fallback_rate * 100)}% of ${llm.gatekeeper_calls_15m}`}
          warn={(llm.gatekeeper_fallback_rate || 0) >= 0.2} />
        <Stat label="Gatekeeper p95" value={llm.gatekeeper_p95_ms == null ? "—" : `${llm.gatekeeper_p95_ms} ms`} />
        <Stat label="Errors (15 min)" value={health.errors_15m ?? 0} warn={(health.errors_15m || 0) > 0} />
        <Stat label="Warnings (15 min)" value={health.warnings_15m ?? 0} />
        <Stat label="Pipeline dispatches (15 min)" value={llm.pipeline_dispatches_15m ?? 0} />
        <Stat label="Settings version" value={health.settings_version ?? 0} />
        <Stat label="Tokens (24 h)"
          value={health.tokens_24h ? formatTokens(health.tokens_24h.tokens) : "—"} />
      </div>

      <TokenUsageCard />

      <section className={card}>
        <h3 className="text-sm font-semibold text-zinc-100 mb-2">Bee streams</h3>
        {(health.streams?.users || []).length === 0 && <p className="text-xs text-zinc-500">No linked Bee accounts.</p>}
        <div className="divide-y divide-white/5">
          {(health.streams?.users || []).map((s: any) => (
            <div key={s.user_id} className="py-2 grid grid-cols-2 sm:grid-cols-5 gap-2 text-[11px] text-zinc-300">
              <span className="truncate">{s.user_email || s.user_id}</span>
              <span className={s.streaming ? "text-emerald-300" : "text-zinc-500"}>{s.streaming ? "listening" : "not running"}</span>
              <span>{s.transport || "—"}</span>
              <span>{s.last_frame_age_s == null ? "no frame yet" : `last frame ${Math.round(s.last_frame_age_s / 60)} min ago`}</span>
              <span className={s.capacity_wait_s ? "text-amber-300" : ""}>{s.capacity_wait_s ? `waiting ${Math.round(s.capacity_wait_s / 60)} min` : s.link_state}</span>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Token usage (admin_console/03 §8): counts only, never content
// ---------------------------------------------------------------------------

const RANGE_HOURS: Record<UsageRange, number> = { "1h": 1, "24h": 24, "7d": 24 * 7, "30d": 24 * 30 };
const ROLE_LABEL: Record<string, string> = {
  gatekeeper: "gatekeeper", extraction: "extraction", reasoner: "reasoner", topic_judge: "topic judge",
  embeddings: "embeddings", probe: "console tests", other: "other",
};

function TokenUsageCard() {
  const [range, setRange] = useState<UsageRange>("24h");
  const [byUser, setByUser] = useState(false);
  const [data, setData] = useState<UsagePayload | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    getUsage(range).then((d) => { setData(d); setError(null); }).catch((e) => setError(e.message));
  }, [range]);
  useEffect(() => {
    load();
    const t = setInterval(load, 60000);
    return () => clearInterval(t);
  }, [load]);

  // The chart groups 30 days by 6-hour bars so it stays readable
  const barHours = range === "30d" ? RANGE_HOURS[range] / 6 : Math.min(RANGE_HOURS[range], 168);
  const bars = useMemo(() => {
    if (!data) return [];
    if (range !== "30d") return usageBars(data.series, barHours);
    const hourly = usageBars(data.series, RANGE_HOURS[range]);
    const grouped = Array.from({ length: barHours }, (_, i) => hourly.slice(i * 6, i * 6 + 6).reduce((a, b) => a + b, 0));
    const max = Math.max(...grouped, 0);
    return grouped.map((v) => (max ? v / max : 0));
  }, [data, range, barHours]);

  const totals = data?.totals;
  return (
    <section className={card}>
      <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
        <div>
          <h3 className="text-sm font-semibold text-zinc-100">Token usage</h3>
          <p className="text-[10px] text-zinc-500">
            Counted at every model call{data?.tracking_since ? ` · since ${ts(data.tracking_since)} UTC` : ""}.
            Input includes cached tokens.
          </p>
        </div>
        <div className="flex items-center gap-1">
          {(Object.keys(RANGE_HOURS) as UsageRange[]).map((r) => (
            <button key={r} onClick={() => setRange(r)}
              className={`${btn} ${range === r ? "bg-cyan-500/20 text-cyan-200 border border-cyan-400/50" : "text-zinc-400 hover:text-zinc-200"}`}>
              {r}
            </button>
          ))}
          <button className={`${btnGhost} ml-2`} onClick={() => setByUser((v) => !v)}>{byUser ? "By model" : "By user"}</button>
        </div>
      </div>

      {error && <p className="text-xs text-red-300">{error}</p>}
      {data && totals && (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-2 mb-3 text-[11px]">
            <p className="text-zinc-400">Total <span className="block text-base text-zinc-100 font-semibold">{formatTokens(totalTokens(totals))}</span></p>
            <p className="text-zinc-400">Input <span className="block text-base text-zinc-100">{formatTokens(totals.input_tokens)}</span></p>
            <p className="text-zinc-400">Output <span className="block text-base text-zinc-100">{formatTokens(totals.output_tokens)}</span></p>
            <p className="text-zinc-400">Cache read / write <span className="block text-base text-zinc-100">{formatTokens(totals.cache_read_tokens)} / {formatTokens(totals.cache_write_tokens)}</span></p>
            <p className="text-zinc-400">Calls <span className="block text-base text-zinc-100">{formatTokens(totals.calls)}</span></p>
          </div>

          <svg viewBox={`0 0 ${Math.max(bars.length, 1)} 20`} preserveAspectRatio="none" className="w-full h-12 mb-3" role="img"
            aria-label={`Tokens per ${range === "30d" ? "6 hours" : "hour"}`}>
            {bars.map((h, i) => (
              <rect key={i} x={i + 0.1} width={0.8} y={20 - Math.max(h * 20, h ? 0.6 : 0)} height={Math.max(h * 20, h ? 0.6 : 0)}
                className="fill-cyan-400/70" />
            ))}
          </svg>

          {!byUser ? (
            <div className="overflow-x-auto">
              <table className="w-full text-[11px] text-zinc-300">
                <thead className="text-zinc-500 text-left">
                  <tr><th className="py-1 pr-3">Model</th><th className="pr-3">Provider</th><th className="pr-3">Roles</th>
                    <th className="pr-3 text-right">Calls</th><th className="pr-3 text-right">Input</th><th className="pr-3 text-right">Output</th>
                    <th className="pr-3 text-right">Cache</th><th className="pr-3 text-right">Total</th><th className="text-right">Share</th></tr>
                </thead>
                <tbody className="divide-y divide-white/5">
                  {data.by_model.length === 0 && <tr><td colSpan={9} className="py-2 text-zinc-500">No model calls in this range.</td></tr>}
                  {data.by_model.map((m) => (
                    <tr key={`${m.provider}:${m.model_id}`}>
                      <td className="py-1.5 pr-3 font-mono text-zinc-100 break-all">{m.model_id}</td>
                      <td className="pr-3">{m.provider}</td>
                      <td className="pr-3 text-zinc-400">
                        {Object.entries(m.roles).map(([role, c]) => `${ROLE_LABEL[role] || role} ${formatTokens(totalTokens(c))}`).join(" · ")}
                      </td>
                      <td className="pr-3 text-right">{formatTokens(m.calls)}</td>
                      <td className="pr-3 text-right">{formatTokens(m.input_tokens)}</td>
                      <td className="pr-3 text-right">{formatTokens(m.output_tokens)}</td>
                      <td className="pr-3 text-right">{formatTokens(m.cache_read_tokens + m.cache_write_tokens)}</td>
                      <td className="pr-3 text-right text-zinc-100">{formatTokens(totalTokens(m))}</td>
                      <td className="text-right">{shareOf(m.share)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="divide-y divide-white/5">
              {data.by_user.length === 0 && <p className="py-2 text-[11px] text-zinc-500">No model calls in this range.</p>}
              {data.by_user.map((u) => (
                <div key={u.user_id || "system"} className="py-1.5 grid grid-cols-4 gap-2 text-[11px] text-zinc-300">
                  <span className="truncate">{u.user_id ? (u.user_email || u.user_id) : "System (no user)"}</span>
                  <span className="text-right">{formatTokens(u.calls)} calls</span>
                  <span className="text-right text-zinc-100">{formatTokens(totalTokens(u))} tokens</span>
                  <span className="text-right">{shareOf(u.share)}</span>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Accounts
// ---------------------------------------------------------------------------

function AccountsTab({ selfId, setMessage }: { selfId: string; setMessage: (m: Message) => void }) {
  const [audit, setAudit] = useState<any[] | null>(null);
  useEffect(() => {
    getAudit().then((r) => setAudit(r.audit)).catch(() => setAudit([]));
  }, []);
  return (
    <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
      <section className={card}>
        <h3 className="text-sm font-semibold text-zinc-100 mb-3">Accounts</h3>
        <AdminSection selfId={selfId} setMessage={setMessage} />
      </section>
      <section className={card}>
        <h3 className="text-sm font-semibold text-zinc-100 mb-3">Security log</h3>
        {!audit && <p className="text-xs text-zinc-400">Loading…</p>}
        {audit && audit.length === 0 && <p className="text-xs text-zinc-500">No entries.</p>}
        <div className="divide-y divide-white/5 max-h-[520px] overflow-y-auto">
          {(audit || []).map((a) => (
            <p key={a.id} className="py-1.5 text-[11px] text-zinc-300 font-mono truncate">
              {ts(a.at)} · {a.event}{a.user_email ? ` · ${a.user_email}` : ""}{a.actor_email && a.actor_email !== a.user_email ? ` · by ${a.actor_email}` : ""}
            </p>
          ))}
        </div>
      </section>
    </div>
  );
}
