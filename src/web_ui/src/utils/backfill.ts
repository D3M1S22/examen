// Pure helpers for the History Sync UI (docs/next_steps/historical_backfill/04 §4).
// The backend stores naive *local* ISO timestamps ("2026-10-19T09:00:00"), so every value sent to the
// API is formatted in local time without a zone suffix.

import { BackfillProgress, CoverageBucket, HistoryTelemetry, IngestSource } from "@/types/schemas";

export type RangePreset = "24h" | "3d" | "7d";

const pad = (n: number) => n.toString().padStart(2, "0");

/** Date -> "YYYY-MM-DDTHH:mm" for <input type="datetime-local">. */
export function toLocalInput(date: Date): string {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(
    date.getMinutes()
  )}`;
}

/** "YYYY-MM-DDTHH:mm" (or a full ISO) -> naive local ISO with seconds, as the API expects. */
export function toApiIso(value: string): string {
  if (!value) return value;
  return value.length === 16 ? `${value}:00` : value.replace(/Z$/, "").split(".")[0];
}

/** Window for a preset. The end never goes past the start of the current live connection. */
export function presetRange(preset: RangePreset, now: Date, liveSince?: string | null): { from: string; to: string } {
  const hours = preset === "24h" ? 24 : preset === "3d" ? 72 : 168;
  let end = now;
  if (liveSince) {
    const since = new Date(liveSince);
    if (!Number.isNaN(since.getTime()) && since < now) end = since;
  }
  const start = new Date(end.getTime() - hours * 3600 * 1000);
  return { from: toLocalInput(start), to: toLocalInput(end) };
}

/** 23400 -> "6h 30m", 90 -> "1m 30s", 2 days -> "2d 0h". */
export function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds) || seconds <= 0) return "0s";
  const s = Math.round(seconds);
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (d > 0) return `${d}d ${h}h`;
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m${s % 60 ? ` ${s % 60}s` : ""}`;
  return `${s}s`;
}

export type BucketTone = "live" | "backfill" | "gap" | "mixed" | "empty";

/** Colour class of one coverage-strip bucket. */
export function bucketTone(bucket: CoverageBucket): BucketTone {
  const covered = bucket.live_seconds + bucket.backfill_seconds;
  const total = covered + bucket.gap_seconds;
  if (total <= 0) return "empty";
  if (bucket.gap_seconds / total > 0.5) return "gap";
  if (bucket.gap_seconds > 0) return "mixed";
  return bucket.backfill_seconds > bucket.live_seconds ? "backfill" : "live";
}

export const BUCKET_CLASS: Record<BucketTone, string> = {
  live: "bg-emerald-500/80",
  backfill: "bg-sky-500/80",
  gap: "bg-rose-500/70",
  mixed: "bg-amber-400/80",
  empty: "bg-zinc-800",
};

export type HistoryTone = "ok" | "gap" | "running" | "off";

/** Dock / card badge for the history coverage state. */
export function historyBadge(history?: HistoryTelemetry | null, live?: BackfillProgress | null): {
  label: string;
  tone: HistoryTone;
} {
  if (!history?.backfill?.enabled) return { label: "OFF", tone: "off" };
  const active = live && !isTerminal(live.status) ? live : history.backfill.active_run;
  if (active) return { label: `RECOVERING ${Math.round((active.progress || 0) * 100)}%`, tone: "running" };
  const uncovered = history.coverage?.uncovered_seconds_7d || 0;
  if (history.coverage?.last_gap && uncovered > 0) return { label: `GAP ${formatDuration(uncovered)}`, tone: "gap" };
  return { label: "SYNCED", tone: "ok" };
}

export function isTerminal(status?: string | null): boolean {
  return status === "completed" || status === "partial" || status === "failed" || status === "cancelled";
}

export function isRecovered(entity?: { ingest_source?: IngestSource | string | null } | null): boolean {
  return entity?.ingest_source === "backfill";
}

/** "18 Oct 13:02 → 19:55" (date repeated only when the day changes). */
export function formatRange(fromIso: string, toIso: string): string {
  const a = new Date(fromIso);
  const b = new Date(toIso);
  if (Number.isNaN(a.getTime()) || Number.isNaN(b.getTime())) return `${fromIso} → ${toIso}`;
  const day = (d: Date) => d.toLocaleDateString("en-GB", { day: "2-digit", month: "short" });
  const time = (d: Date) => `${pad(d.getHours())}:${pad(d.getMinutes())}`;
  return a.toDateString() === b.toDateString()
    ? `${day(a)} ${time(a)} → ${time(b)}`
    : `${day(a)} ${time(a)} → ${day(b)} ${time(b)}`;
}

/** Merges an SSE backfill_* payload into the tracked progress (ignores stale runs). */
export function mergeProgress(
  current: BackfillProgress | null,
  incoming: BackfillProgress
): BackfillProgress {
  if (!current || current.run_id !== incoming.run_id) return incoming;
  return { ...current, ...incoming };
}
