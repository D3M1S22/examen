import React from "react";
import { SpeakerAttribution } from "@/types/schemas";

/**
 * Who said the sentence an action or task came from (Bee `tagged-utterance`, docs/next_steps/08).
 * Shown only when Bee recognised a voice; untagged speech (most of it) shows nothing.
 */
export function SpeakerBadge({ speaker }: { speaker?: SpeakerAttribution | null }) {
  if (!speaker || speaker.role === "unknown") return null;
  const voice = speaker.source === "bee_voice_id" || speaker.source === "bee_name";
  const score = typeof speaker.score === "number" ? ` · ${Math.round(speaker.score * 100)}%` : "";
  if (speaker.role === "user") {
    if (!voice) return null; // simulator or history name: no voice match to show
    return (
      <span
        className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full bg-emerald-950/70 border border-emerald-500/40 text-emerald-300 font-mono text-[8px] tracking-wider uppercase shrink-0"
        title={`Bee recognised your voice${score}`}
      >
        🎙 Your voice{score}
      </span>
    );
  }
  return (
    <span
      className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full bg-amber-950/70 border border-amber-500/40 text-amber-300 font-mono text-[8px] tracking-wider uppercase shrink-0"
      title="Said by another person: it does not count as your own confirmation"
    >
      🗣 {speaker.name || "Someone else"}
    </span>
  );
}
