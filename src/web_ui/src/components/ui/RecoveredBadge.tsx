import React from "react";
import { IngestSource } from "@/types/schemas";
import { isRecovered } from "@/utils/backfill";

/** "⏪ Recovered" provenance chip for entities produced by the history backfill. */
export function RecoveredBadge({ entity }: { entity?: { ingest_source?: IngestSource | string | null } | null }) {
  if (!isRecovered(entity)) return null;
  return (
    <span
      className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full bg-sky-950/70 border border-sky-500/40 text-sky-300 font-mono text-[8px] tracking-wider uppercase shrink-0"
      title="Recovered from Bee history: recorded while EXAMEN was offline"
    >
      ⏪ Recovered
    </span>
  );
}
