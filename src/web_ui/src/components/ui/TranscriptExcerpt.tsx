import React, { useState } from "react";

interface TranscriptExcerptProps {
  label: string;
  text: string;
  /** Right-aligned detail of the label row (e.g. the time) */
  meta?: string;
  /** Lines shown before "Show more" */
  clampLines?: number;
}

/** A quoted piece of the Bee transcript a result came from (Peace of Mind, Daily Routines). */
export function TranscriptExcerpt({ label, text, meta, clampLines = 4 }: TranscriptExcerptProps) {
  const [expanded, setExpanded] = useState(false);
  const long = text.length > clampLines * 70;
  return (
    <div className="bg-[#121419] border border-surface-container-highest rounded-xl p-4">
      <div className="flex items-center justify-between font-mono text-[8px] text-secondary tracking-widest uppercase mb-1">
        <span>{label}</span>
        {meta && <span>{meta}</span>}
      </div>
      <p
        className="font-sans text-body-md text-primary leading-relaxed italic"
        style={
          expanded || !long
            ? undefined
            : { display: "-webkit-box", WebkitLineClamp: clampLines, WebkitBoxOrient: "vertical", overflow: "hidden" }
        }
      >
        &ldquo;{text}&rdquo;
      </p>
      {long && (
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="mt-1 font-mono text-[9px] tracking-widest uppercase text-secondary hover:text-primary"
        >
          {expanded ? "Show less" : "Show more"}
        </button>
      )}
    </div>
  );
}
