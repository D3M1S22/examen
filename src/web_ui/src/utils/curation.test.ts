import { describe, expect, it } from "bun:test";
import { displayActionTitle, excerptLabels, formatCascade, normalizeActionTitle } from "./curation";
import { PlannedTask } from "@/types/schemas";

const task = (over: Partial<PlannedTask>): PlannedTask => ({
  id: "t1",
  title: "check stove",
  domain: "safety",
  status: "pending",
  recurrence: "daily",
  created_at: "2026-10-22T08:00:00",
  ...over,
});

describe("formatCascade", () => {
  it("lists what goes with the deleted item", () => {
    expect(formatCascade({ commitments: 2, tasks: 1 })).toBe("Also deletes 2 commitments and 1 routine.");
    expect(formatCascade({ commitments: 1, tasks: 2, briefings: 3 })).toBe(
      "Also deletes 1 commitment, 2 routines and 3 briefings."
    );
  });

  it("is null when nothing else is deleted", () => {
    expect(formatCascade({})).toBeNull();
    expect(formatCascade({ commitments: 0, tasks: 0 })).toBeNull();
  });
});

describe("action titles", () => {
  it("normalises like the server and displays with spaces", () => {
    expect(normalizeActionTitle("  Gas Stove   OFF ")).toBe("gas_stove_off");
    expect(displayActionTitle("gas_stove_off")).toBe("gas stove off");
  });
});

describe("excerptLabels", () => {
  it("shows where a voice routine came from and what completed it", () => {
    const excerpts = excerptLabels(
      task({
        origin: "ambient_voice",
        raw_statement: "remind me to check the stove at nine",
        status: "completed",
        completed_at: "2026-10-22T21:04:10",
        completion_statement: "I checked the stove",
      })
    );
    expect(excerpts).toEqual([
      { label: "Heard", text: "remind me to check the stove at nine" },
      { label: "Completed by", text: "I checked the stove", meta: "21:04" },
    ]);
  });

  it("labels commitment routines and hides stale completions", () => {
    const excerpts = excerptLabels(
      task({ origin: "social_commitment", raw_statement: "Send the deck", completion_statement: "old" })
    );
    expect(excerpts).toEqual([{ label: "Promised", text: "Send the deck" }]);
  });

  it("is empty for a manual routine never completed", () => {
    expect(excerptLabels(task({ origin: "manual" }))).toEqual([]);
  });
});
