// Manual curation helpers (docs/next_steps/manual_curation/04): pure, covered by curation.test.ts
import type { PlannedTask } from "@/types/schemas";

export interface CascadeCounts {
  commitments?: number;
  tasks?: number;
  briefings?: number;
}

const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;

const joinList = (parts: string[]) =>
  parts.length <= 1 ? parts.join("") : `${parts.slice(0, -1).join(", ")} and ${parts[parts.length - 1]}`;

/** "Also deletes 2 commitments and 1 routine." — null when nothing else goes. */
export function formatCascade(counts: CascadeCounts): string | null {
  const parts: string[] = [];
  if (counts.commitments) parts.push(plural(counts.commitments, "commitment"));
  if (counts.tasks) parts.push(plural(counts.tasks, "routine"));
  if (counts.briefings) parts.push(plural(counts.briefings, "briefing"));
  return parts.length ? `Also deletes ${joinList(parts)}.` : null;
}

/** Mirrors rules.normalize_action_type on the server: trimmed, lower case, "_" between words. */
export function normalizeActionTitle(text: string): string {
  return text.trim().toLowerCase().replace(/\s+/g, "_").slice(0, 80);
}

/** How an action title is shown ("stove_off" -> "stove off"). */
export function displayActionTitle(actionType: string): string {
  return actionType.replace(/_/g, " ");
}

export interface Excerpt {
  label: string;
  text: string;
  meta?: string;
}

const clock = (iso?: string | null) => (iso && iso.length >= 16 ? iso.substring(11, 16) : undefined);

/** Transcript excerpts of a routine card: where it came from, and what completed it. */
export function excerptLabels(task: PlannedTask): Excerpt[] {
  const out: Excerpt[] = [];
  const origin = task.raw_statement?.trim();
  if (origin) {
    const label = task.origin === "social_commitment" ? "Promised" : task.origin === "ambient_voice" ? "Heard" : "Note";
    out.push({ label, text: origin });
  }
  const completion = task.completion_statement?.trim();
  if (task.status === "completed" && completion) {
    out.push({ label: "Completed by", text: completion, meta: clock(task.completed_at) });
  }
  return out;
}
