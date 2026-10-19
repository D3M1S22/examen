import { describe, expect, it } from "bun:test";
import {
  bucketTone,
  formatDuration,
  historyBadge,
  isRecovered,
  mergeProgress,
  presetRange,
  toApiIso,
  toLocalInput,
} from "./backfill";
import { BackfillProgress, CoverageBucket, HistoryTelemetry } from "@/types/schemas";

const bucket = (live: number, backfill: number, gap: number): CoverageBucket => ({
  start: "2026-10-19T09:00:00",
  end: "2026-10-19T10:00:00",
  live_seconds: live,
  backfill_seconds: backfill,
  gap_seconds: gap,
});

const progress = (over: Partial<BackfillProgress> = {}): BackfillProgress => ({
  run_id: "r1",
  trigger: "manual",
  status: "replaying",
  window_from: "2026-10-18T13:00:00",
  window_to: "2026-10-18T20:00:00",
  processed: 42,
  selected: 100,
  qualified: 4,
  failed: 0,
  events: 1,
  progress: 0.42,
  ...over,
});

describe("backfill - time helpers", () => {
  it("formats datetime-local values and API timestamps", () => {
    const d = new Date(2026, 9, 19, 9, 5);
    expect(toLocalInput(d)).toBe("2026-10-19T09:05");
    expect(toApiIso("2026-10-19T09:05")).toBe("2026-10-19T09:05:00");
    expect(toApiIso("2026-10-19T09:05:30.123Z")).toBe("2026-10-19T09:05:30");
  });

  it("ends presets at the start of the live connection", () => {
    const now = new Date(2026, 9, 19, 12, 0);
    const live = new Date(2026, 9, 19, 10, 30);
    expect(presetRange("24h", now, toApiIso(toLocalInput(live)))).toEqual({
      from: "2026-10-18T10:30",
      to: "2026-10-19T10:30",
    });
    expect(presetRange("3d", now).from).toBe("2026-10-16T12:00");
  });

  it("formats durations compactly", () => {
    expect(formatDuration(0)).toBe("0s");
    expect(formatDuration(45)).toBe("45s");
    expect(formatDuration(90)).toBe("1m 30s");
    expect(formatDuration(6 * 3600 + 53 * 60)).toBe("6h 53m");
    expect(formatDuration(2 * 86400 + 3600)).toBe("2d 1h");
  });
});

describe("backfill - coverage strip", () => {
  it("classifies buckets", () => {
    expect(bucketTone(bucket(3600, 0, 0))).toBe("live");
    expect(bucketTone(bucket(600, 3000, 0))).toBe("backfill");
    expect(bucketTone(bucket(3000, 0, 600))).toBe("mixed");
    expect(bucketTone(bucket(600, 0, 3000))).toBe("gap");
    expect(bucketTone(bucket(0, 0, 0))).toBe("empty");
  });
});

describe("backfill - badges and progress", () => {
  const history: HistoryTelemetry = {
    coverage: { last_gap: { start: "a", end: "b", seconds: 24780 }, uncovered_seconds_7d: 24780 },
    backfill: { enabled: true, active_run: null, queued: 0 },
  };

  it("derives the dock badge", () => {
    expect(historyBadge(undefined)).toEqual({ label: "OFF", tone: "off" });
    expect(historyBadge(history)).toEqual({ label: "GAP 6h 53m", tone: "gap" });
    expect(historyBadge(history, progress())).toEqual({ label: "RECOVERING 42%", tone: "running" });
    expect(historyBadge(history, progress({ status: "completed" }))).toEqual({ label: "GAP 6h 53m", tone: "gap" });
    expect(
      historyBadge({ coverage: { last_gap: null, uncovered_seconds_7d: 0 }, backfill: history.backfill })
    ).toEqual({ label: "SYNCED", tone: "ok" });
  });

  it("merges SSE progress only for the same run", () => {
    const merged = mergeProgress(progress(), progress({ processed: 80, progress: 0.8 }));
    expect(merged.processed).toBe(80);
    expect(mergeProgress(progress(), progress({ run_id: "r2", processed: 1 })).run_id).toBe("r2");
  });

  it("flags recovered entities", () => {
    expect(isRecovered({ ingest_source: "backfill" })).toBe(true);
    expect(isRecovered({ ingest_source: "live" })).toBe(false);
    expect(isRecovered(undefined)).toBe(false);
  });
});
