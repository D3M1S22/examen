import React, { useState } from "react";
import { PlannedTask, VerifiedAction } from "@/types/schemas";
import { TranscriptExcerpt } from "./TranscriptExcerpt";
import { displayActionTitle } from "@/utils/curation";

type ReviewKind = "action" | "task";

interface ReviewTrayProps {
  kind: ReviewKind;
  items: (VerifiedAction | PlannedTask)[];
  onAccept: (kind: ReviewKind, id: string) => Promise<void>;
  onDismiss: (kind: ReviewKind, id: string) => Promise<void>;
}

const titleOf = (kind: ReviewKind, item: VerifiedAction | PlannedTask) =>
  kind === "action" ? displayActionTitle((item as VerifiedAction).action_type) : (item as PlannedTask).title;

const transcriptOf = (kind: ReviewKind, item: VerifiedAction | PlannedTask) =>
  kind === "action" ? (item as VerifiedAction).raw_statement : (item as PlannedTask).raw_statement || "";

const timeOf = (kind: ReviewKind, item: VerifiedAction | PlannedTask) => {
  const iso = kind === "action" ? (item as VerifiedAction).timestamp : (item as PlannedTask).created_at;
  return iso && iso.length >= 16 ? iso.replace("T", " ").substring(0, 16) : undefined;
};

/** Results of speech Bee did not attribute to anyone: they count only once the owner confirms them
 *  (docs/next_steps/speaker_review/03 §4). */
export function ReviewTray({ kind, items, onAccept, onDismiss }: ReviewTrayProps) {
  const [open, setOpen] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  if (items.length === 0) return null;

  const run = async (id: string, fn: () => Promise<void>) => {
    setBusy(id);
    try {
      await fn();
    } finally {
      setBusy(null);
    }
  };

  const acceptAll = async () => {
    setBusy("all");
    try {
      for (const item of items) await onAccept(kind, item.id);
    } finally {
      setBusy(null);
    }
  };

  const noun = kind === "action" ? "action" : "routine";
  return (
    <section className="rounded-2xl border border-amber-500/30 bg-amber-950/10 p-space-lg" aria-label="To confirm">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="flex items-center gap-2 font-mono text-[11px] tracking-widest uppercase text-amber-300"
          aria-expanded={open}
        >
          <span>{open ? "▾" : "▸"}</span>
          <span>To confirm ({items.length})</span>
        </button>
        <p className="font-sans text-[12px] text-secondary flex-1 min-w-[220px]">
          Bee did not recognise who said these. They count as yours only once you confirm them.
        </p>
        {items.length > 1 && (
          <button
            type="button"
            disabled={busy !== null}
            onClick={acceptAll}
            className="px-3 py-1.5 rounded-lg border border-emerald-500/40 bg-emerald-950/30 hover:bg-emerald-950/60 text-emerald-300 font-mono text-[9px] tracking-widest uppercase disabled:opacity-40"
          >
            {busy === "all" ? "…" : "✔ Accept all"}
          </button>
        )}
      </div>

      {open && (
        <ul className="mt-4 space-y-3">
          {items.map((item) => {
            const transcript = transcriptOf(kind, item);
            return (
              <li key={item.id} className="rounded-xl border border-white/5 bg-[#121419] p-4">
                <div className="flex flex-wrap items-start justify-between gap-3 mb-3">
                  <div>
                    <div className="font-serif text-[20px] text-primary capitalize leading-tight">{titleOf(kind, item)}</div>
                    <div className="font-mono text-[9px] text-secondary tracking-widest uppercase mt-1">
                      ◌ Voice not identified{timeOf(kind, item) ? ` · ${timeOf(kind, item)}` : ""}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      disabled={busy !== null}
                      onClick={() => run(item.id, () => onAccept(kind, item.id))}
                      className="px-3 py-1.5 rounded-lg border border-emerald-500/40 bg-emerald-950/30 hover:bg-emerald-950/60 text-emerald-300 font-mono text-[9px] tracking-widest uppercase disabled:opacity-40"
                      aria-label={`Confirm this ${noun} is yours`}
                    >
                      {busy === item.id ? "…" : "✔ Mine"}
                    </button>
                    <button
                      type="button"
                      disabled={busy !== null}
                      onClick={() => run(item.id, () => onDismiss(kind, item.id))}
                      className="px-3 py-1.5 rounded-lg border border-rose-500/30 hover:bg-rose-950/40 text-rose-300 font-mono text-[9px] tracking-widest uppercase disabled:opacity-40"
                      aria-label={`Discard this ${noun}: not yours`}
                    >
                      ✕ Not mine
                    </button>
                  </div>
                </div>
                {transcript && <TranscriptExcerpt label="Heard" text={transcript} />}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
