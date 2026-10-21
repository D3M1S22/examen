import { describe, expect, test } from "bun:test";
import {
  applyIncidentEvent,
  buildChangeSet,
  formatBytes,
  formatTokens,
  Incident,
  inputError,
  parseInput,
  prependEvents,
  shareOf,
  SettingRow,
  sortIncidents,
  testsNeeded,
  usageBars,
} from "./admin";

const row = (over: Partial<SettingRow>): SettingRow => ({
  key: "k", env: "K", group: "g", label: "l", apply: "hot", type: "str", optional: false,
  effective: "a", source: "default", env_value: "a", ...over,
});

describe("settings editing", () => {
  test("parses inputs by type", () => {
    expect(parseInput(row({ type: "int" }), "12.7")).toBe(12);
    expect(parseInput(row({ type: "float" }), "0.25")).toBe(0.25);
    expect(parseInput(row({ type: "bool" }), 1)).toBe(true);
    expect(parseInput(row({ type: "str", optional: true }), "  ")).toBeNull();
    expect(parseInput(row({ type: "choice", choices: [256, 512] }), "512")).toBe(512);
    expect(Number.isNaN(parseInput(row({ type: "int" }), ""))).toBe(true);
  });

  test("checks constraints", () => {
    const n = row({ type: "int", minimum: 1, maximum: 10 });
    expect(inputError(n, 0)).toBe("At least 1");
    expect(inputError(n, 11)).toBe("At most 10");
    expect(inputError(n, 5)).toBeNull();
    expect(inputError(row({ choices: ["proxy", "cli"] }), "pigeon")).toBe("Not an allowed value");
    expect(inputError(row({ pattern: "^https://" }), "http://x")).toBe("Invalid format");
    expect(inputError(row({ optional: false }), null)).toBe("A value is required");
  });

  test("builds a change set with real changes only, and the tests it needs", () => {
    const rows = [
      row({ key: "gatekeeper_model_id", effective: "m1", tests: ["gatekeeper"] }),
      row({ key: "backfill_lookback_days", type: "float", effective: 2 }),
    ];
    const changes = buildChangeSet(rows, { gatekeeper_model_id: "m2", backfill_lookback_days: 2 });
    expect(changes).toEqual({ gatekeeper_model_id: "m2" });
    expect(testsNeeded(rows, changes)).toEqual(["gatekeeper"]);
    expect(testsNeeded(rows, { backfill_lookback_days: 3 })).toEqual([]);
  });
});

const inc = (over: Partial<Incident>): Incident => ({
  id: "inc_1", code: "c", component: "system", severity: "warning", title: "t", status: "open", count: 1,
  first_seen: "2026-10-21T10:00:00+00:00", last_seen: "2026-10-21T10:00:00+00:00", ...over,
});

describe("incidents and events", () => {
  test("sorts open before resolved, then by severity and recency", () => {
    const sorted = sortIncidents([
      inc({ id: "a", status: "resolved", severity: "critical" }),
      inc({ id: "b", severity: "warning", last_seen: "2026-10-21T11:00:00+00:00" }),
      inc({ id: "c", severity: "error" }),
    ]);
    expect(sorted.map((i) => i.id)).toEqual(["c", "b", "a"]);
  });

  test("applies SSE updates", () => {
    const list = [inc({ id: "a" })];
    const updated = applyIncidentEvent(list, "incident_updated", inc({ id: "a", count: 7 }));
    expect(updated[0].count).toBe(7);
    expect(applyIncidentEvent(updated, "incident_resolved", inc({ id: "a", status: "resolved" }))).toEqual([]);
    expect(applyIncidentEvent(list, "incident_opened", inc({ id: "z", severity: "critical" }))[0].id).toBe("z");
  });

  test("prepends live events without duplicates", () => {
    const e = (ref: string) => ({ ref, at: "", level: "warning" as const, code: "x", component: "y", message: "" });
    const out = prependEvents([e("1"), e("2")], [e("3"), e("1")], 3);
    expect(out.map((x) => x.ref)).toEqual(["3", "1", "2"]);
  });

  test("formats bytes", () => {
    expect(formatBytes(1536)).toBe("1.5 KB");
    expect(formatBytes(null)).toBe("—");
    expect(formatBytes(3 * 1024 ** 3)).toBe("3.0 GB");
  });
});

describe("token usage", () => {
  test("formats token counts and shares", () => {
    expect(formatTokens(950)).toBe("950");
    expect(formatTokens(12_300)).toBe("12.3k");
    expect(formatTokens(4_500_000)).toBe("4.5M");
    expect(formatTokens(null)).toBe("—");
    expect(shareOf(0.4567)).toBe("46%");
    expect(shareOf(0.004)).toBe("<1%");
    expect(shareOf(0)).toBe("0%");
  });

  test("builds hourly bars with empty hours", () => {
    const now = new Date(Date.UTC(2026, 9, 21, 12, 30));
    const bars = usageBars([
      { hour: "2026-10-21T12:00:00+00:00", tokens: 100 },
      { hour: "2026-10-21T10:00:00+00:00", tokens: 50 },
    ], 4, now);
    expect(bars).toEqual([0, 0.5, 0, 1]);
    expect(usageBars([], 3, now)).toEqual([0, 0, 0]);
  });
});
