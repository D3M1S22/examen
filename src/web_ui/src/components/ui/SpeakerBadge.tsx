import React from "react";
import { SpeakerAttribution } from "@/types/schemas";

const CHIP = "inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full border font-mono text-[8px] tracking-wider uppercase shrink-0";

/**
 * Who said the sentence an action or task came from (Bee `tagged-utterance`, docs/next_steps/08 §5).
 * - green  "Your voice":       Bee recognised the owner's voice
 * - blue   "Asked by …":       someone asked the owner to do it ("Damiano, remember to …")
 * - grey   "Voice not verified": no Bee tag, probably the owner
 * - amber  name:               said by another person
 * Manual entries and simulator data (no attribution, or source "internal") show nothing.
 */
export function SpeakerBadge({ speaker }: { speaker?: SpeakerAttribution | null }) {
  if (!speaker || speaker.source === "internal") return null;
  const voice = speaker.source === "bee_voice_id" || speaker.source === "bee_name";
  const score = voice && typeof speaker.score === "number" ? ` · ${Math.round(speaker.score * 100)}%` : "";

  if (speaker.addressed_to_user) {
    const who = speaker.name || "someone";
    const verified = speaker.role === "contact" && voice;
    return (
      <span
        className={`${CHIP} bg-sky-950/70 border-sky-500/40 text-sky-300`}
        title={verified ? `${who} asked you; Bee recognised their voice${score}` : `${who} asked you; the speaker's voice was not verified`}
      >
        📣 Asked by {who}
        {verified ? score : " · unverified"}
      </span>
    );
  }
  if (speaker.role === "user") {
    if (speaker.source === "history_name") {
      return (
        <span className={`${CHIP} bg-emerald-950/40 border-emerald-500/25 text-emerald-300/80`} title="Bee history names you as the speaker (no voice score)">
          🎙 You · Bee history
        </span>
      );
    }
    return (
      <span className={`${CHIP} bg-emerald-950/70 border-emerald-500/40 text-emerald-300`} title={`Bee recognised your voice${score}`}>
        🎙 Your voice{score}
      </span>
    );
  }
  if (speaker.role === "contact") {
    return (
      <span className={`${CHIP} bg-amber-950/70 border-amber-500/40 text-amber-300`} title="Said by another person: it does not count as your own confirmation">
        🗣 {speaker.name || "Someone else"}
      </span>
    );
  }
  return (
    <span
      className={`${CHIP} bg-zinc-900/70 border-zinc-500/40 text-zinc-400`}
      title="Bee did not tag this sentence: probably you, but your voice was not verified"
    >
      ◌ Voice not verified
    </span>
  );
}
