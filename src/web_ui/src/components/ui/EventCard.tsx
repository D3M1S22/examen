import React, { useState } from "react";
import useSWR from "swr";
import {
  BriefingReport,
  EventDetail,
  EventSummary,
  EventTransitionLog,
  SessionSegment,
} from "@/types/schemas";
import { getApiBaseUrl } from "@/utils/api";
import { speakAlexaReassurance } from "@/utils/audioEffects";
import { RecoveredBadge } from "./RecoveredBadge";
import { ConfirmDialog } from "./ConfirmDialog";
import { formatCascade } from "@/utils/curation";

const fetcher = (url: string) => fetch(`${getApiBaseUrl()}${url}`).then((res) => res.json());

export type EventAction = "pause" | "resume" | "conclude" | "split" | "merge" | "delete";

interface EventCardProps {
  event: EventSummary;
  previousEvent?: EventSummary | null;
  tHardSeconds?: number;
  onAction: (action: EventAction, event: EventSummary, extra?: Record<string, any>) => Promise<void>;
  onOpenBriefing: (briefing: BriefingReport) => void;
  defaultExpanded?: boolean;
}

const hhmm = (iso?: string | null) => {
  if (!iso) return "…";
  const d = new Date(iso);
  return isNaN(d.getTime()) ? "…" : d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
};

const hhmmss = (iso?: string | null) => {
  if (!iso) return "";
  const d = new Date(iso);
  return isNaN(d.getTime()) ? iso : d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
};

const minutesBetween = (a?: string | null, b?: string | null) => {
  if (!a || !b) return 0;
  return Math.round((new Date(b).getTime() - new Date(a).getTime()) / 60000);
};

function EventStatusChip({ event, tHardSeconds }: { event: EventSummary; tHardSeconds?: number }) {
  if (event.status === "active") {
    return (
      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-emerald-950/60 border border-emerald-500/50 text-emerald-300 font-mono text-[9px] tracking-widest font-bold">
        <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
        LIVE
      </span>
    );
  }
  if (event.status === "paused" || event.status === "finalizing") {
    let deadline = event.hard_close_deadline;
    if (!deadline && event.paused_at && tHardSeconds) {
      deadline = new Date(new Date(event.paused_at).getTime() + tHardSeconds * 1000).toISOString();
    }
    return (
      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-amber-950/60 border border-amber-500/50 text-amber-300 font-mono text-[9px] tracking-widest font-bold">
        ⏸ PAUSED{deadline ? ` · RESUMES UNTIL ${hhmm(deadline)}` : ""}
      </span>
    );
  }
  if (event.final_status === "pending" || event.final_status === "synthesizing") {
    return (
      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-cyan-950/60 border border-cyan-500/50 text-cyan-300 font-mono text-[9px] tracking-widest font-bold">
        <span className="w-2.5 h-2.5 border-2 border-cyan-300 border-t-transparent rounded-full animate-spin" />
        FINAL PENDING
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-zinc-900 border border-zinc-600/60 text-zinc-300 font-mono text-[9px] tracking-widest font-bold">
      ✓ CONCLUDED
    </span>
  );
}

function SegmentStatus({ seg }: { seg: SessionSegment }) {
  const map: Record<string, { label: string; cls: string }> = {
    open: { label: "● RECORDING", cls: "text-emerald-300 border-emerald-500/40 bg-emerald-950/40" },
    closed: { label: "QUEUED", cls: "text-zinc-300 border-zinc-600/40 bg-zinc-900" },
    synthesizing: { label: "SYNTHESIZING…", cls: "text-cyan-300 border-cyan-500/40 bg-cyan-950/40" },
    synthesized: { label: "✓ BRIEFING", cls: "text-amber-300 border-amber-500/40 bg-amber-950/40" },
    skipped: { label: "TOO SHORT · IN FINAL", cls: "text-zinc-400 border-zinc-700 bg-zinc-900" },
    failed: { label: "FAILED", cls: "text-rose-300 border-rose-500/40 bg-rose-950/40" },
  };
  const s = map[seg.status] || map.closed;
  return <span className={`px-2 py-0.5 rounded border font-mono text-[8px] tracking-widest ${s.cls}`}>{s.label}</span>;
}

const RULE_LABELS: Record<string, string> = {
  R0: "OPEN",
  R1: "SOFT PAUSE",
  R2: "CUE PAUSE",
  R3: "CHECKPOINT",
  R4: "RESUME",
  R5: "HARD CLOSE",
  R6: "LOCATION",
  R7: "NEW TOPIC",
  R8: "MANUAL",
  R9: "TOPIC DRIFT",
  MANUAL: "MANUAL",
};

function DecisionLog({ transitions }: { transitions: EventTransitionLog[] }) {
  return (
    <div className="bg-[#0d0e12] border border-white/5 rounded-xl p-4 space-y-2 max-h-[260px] overflow-y-auto">
      <div className="font-mono text-[9px] text-secondary tracking-[0.2em] uppercase font-bold mb-1">
        🧭 DECISION AUDIT TRAIL
      </div>
      {transitions.length === 0 && <div className="font-mono text-[10px] text-zinc-500">No transitions recorded.</div>}
      {transitions.map((t, i) => (
        <div key={i} className="flex items-start gap-3 text-[11px]">
          <span className="font-mono text-[9px] text-zinc-500 w-[64px] shrink-0 pt-0.5">{hhmmss(t.at)}</span>
          <span className="font-mono text-[8px] px-1.5 py-0.5 rounded bg-white/5 border border-white/10 text-cyan-300 shrink-0 w-[88px] text-center">
            {t.rule} · {RULE_LABELS[t.rule] || t.rule}
          </span>
          <div className="min-w-0">
            <div className="font-mono text-[9px] text-zinc-300 uppercase tracking-wider">
              {(t.from_status || "∅").toUpperCase()} → {t.to_status.toUpperCase()}
              <span className="text-zinc-500 normal-case"> · {t.reason.replace(/_/g, " ")}</span>
            </div>
            {t.detail && <div className="font-sans text-[11px] text-zinc-400 leading-snug">{t.detail}</div>}
          </div>
        </div>
      ))}
    </div>
  );
}

export function EventCard({
  event,
  previousEvent,
  tHardSeconds,
  onAction,
  onOpenBriefing,
  defaultExpanded = false,
}: EventCardProps) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const [showLog, setShowLog] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const isOpen = event.status === "active" || event.status === "paused" || event.status === "finalizing";
  const { data: detail } = useSWR<EventDetail>(
    expanded || showLog ? `/api/sessions/${event.session_id}` : null,
    fetcher,
    { refreshInterval: isOpen || event.final_status === "pending" || event.final_status === "synthesizing" ? 5000 : 0 }
  );

  const segments: SessionSegment[] = detail?.segments || event.segments;
  const finalBriefing = detail?.briefing_report || null;
  const isPlaceholder = !event.title || event.title.startsWith("Ongoing session");
  const title = event.final_title || (isPlaceholder ? null : event.title);

  const run = async (action: EventAction, extra?: Record<string, any>) => {
    setBusy(action);
    try {
      await onAction(action, event, extra);
    } finally {
      setBusy(null);
    }
  };

  const openFinal = async () => {
    if (finalBriefing) {
      onOpenBriefing(finalBriefing);
      return;
    }
    try {
      const res = await fetch(`${getApiBaseUrl()}/api/sessions/${event.session_id}`);
      const data: EventDetail = await res.json();
      if (data.briefing_report) onOpenBriefing(data.briefing_report);
    } catch (err) {
      console.error(err);
    }
  };

  const speak = () => {
    if (detail?.spoken_summary) speakAlexaReassurance(detail.spoken_summary);
  };

  const accent =
    event.status === "active" ? "border-emerald-500/40" : event.status === "concluded" ? "border-surface-container-highest" : "border-amber-500/40";

  return (
    <div className={`card-elevated bg-surface-container-low border ${accent} rounded-2xl p-space-lg flex flex-col gap-4 transition-all`}>
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2 mb-2">
            <EventStatusChip event={event} tHardSeconds={tHardSeconds} />
            <RecoveredBadge entity={event} />
            <span className="px-2 py-1 rounded bg-[#1c1f26] border border-white/5 font-mono text-[9px] text-secondary tracking-widest uppercase">
              {event.domain === "general" ? "EVENT" : event.domain.replace(/_/g, " ")}
            </span>
            <span className="font-mono text-[9px] text-zinc-500 tracking-widest uppercase">
              {hhmm(event.start_time)} → {event.concluded_at ? hhmm(event.concluded_at) : isOpen ? "NOW" : "…"}
              {event.location_name ? ` · 📍 ${event.location_name}` : ""}
            </span>
          </div>
          <h3 className="font-serif text-[26px] text-primary leading-tight">
            {title || <span className="text-zinc-400 italic">Recording — title after the first synthesis</span>}
          </h3>
          {event.top_terms?.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mt-2">
              {event.top_terms.map((t) => (
                <span key={t} className="px-2 py-0.5 rounded-full bg-white/5 border border-white/10 font-mono text-[9px] text-zinc-300">
                  {t}
                </span>
              ))}
            </div>
          )}
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <span className="font-mono text-[9px] text-secondary tracking-widest uppercase">
            {segments.length} PART{segments.length === 1 ? "" : "S"} · {event.micro_events_count} MICRO-EVENTS
          </span>
          <button
            onClick={() => setExpanded((v) => !v)}
            className="px-3 py-1.5 rounded-lg border border-surface-container-highest hover:bg-surface-container text-secondary hover:text-primary font-mono text-[9px] tracking-widest uppercase"
          >
            {expanded ? "COLLAPSE" : "EXPAND"}
          </button>
        </div>
      </div>

      {/* Final consolidated briefing */}
      {event.final_status === "ready" && (
        <div className="bg-gradient-to-r from-amber-950/40 to-[#121419] border border-amber-500/40 rounded-xl p-4 flex flex-col md:flex-row md:items-center justify-between gap-3">
          <div className="min-w-0">
            <div className="font-mono text-[9px] text-amber-300 tracking-[0.2em] uppercase font-bold mb-1">
              ★ CONSOLIDATED EVENT BRIEFING
            </div>
            <div className="font-serif text-lg text-primary truncate">{event.final_title || "Final briefing"}</div>
            {expanded && finalBriefing?.explanatory_synthesis && (
              <p className="font-sans text-xs text-amber-100/80 leading-relaxed mt-2 line-clamp-4">
                {finalBriefing.explanatory_synthesis}
              </p>
            )}
          </div>
          <button
            onClick={openFinal}
            className="px-4 py-2 rounded-lg border border-amber-500/50 bg-amber-500/10 hover:bg-amber-500/20 text-amber-300 font-mono text-[9px] tracking-[0.2em] font-bold uppercase shrink-0 disabled:opacity-50"
          >
            📖 OPEN FINAL
          </button>
        </div>
      )}

      {/* Segment timeline */}
      {expanded && (
        <div className="relative pl-4 border-l border-white/10 space-y-3">
          {segments.map((seg, i) => {
            const prev = i > 0 ? segments[i - 1] : null;
            const gap = prev ? minutesBetween(prev.end_time, seg.start_time) : 0;
            return (
              <React.Fragment key={seg.segment_id}>
                {prev && gap >= 1 && (
                  <div className="font-mono text-[9px] text-zinc-500 tracking-widest uppercase -ml-4 pl-4 flex items-center gap-2">
                    <span>☕</span>
                    <span>BREAK · {gap} MIN</span>
                  </div>
                )}
                <div className="bg-[#121419] border border-white/5 rounded-xl p-3 flex flex-col md:flex-row md:items-center justify-between gap-2">
                  <div className="flex items-center gap-3 min-w-0">
                    <div className="w-7 h-7 rounded-full bg-surface-container-highest flex items-center justify-center font-mono text-[11px] font-bold text-primary shrink-0">
                      {seg.index}
                    </div>
                    <div className="min-w-0">
                      <div className="font-sans text-sm text-primary truncate">
                        {seg.title || (seg.status === "open" ? "Recording…" : "Awaiting synthesis")}
                      </div>
                      <div className="font-mono text-[9px] text-zinc-500 tracking-wider">
                        {seg.time_range} · {seg.word_count} WORDS
                        {seg.kind === "checkpoint" ? " · CHECKPOINT" : ""}
                        {seg.close_reason ? ` · ${seg.close_reason.replace(/_/g, " ").toUpperCase()}` : ""}
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <SegmentStatus seg={seg} />
                    {seg.briefing && (
                      <button
                        onClick={() => onOpenBriefing(seg.briefing as BriefingReport)}
                        className="px-2.5 py-1 rounded border border-amber-500/40 text-amber-300 hover:bg-amber-500/10 font-mono text-[8px] tracking-widest uppercase"
                      >
                        OPEN
                      </button>
                    )}
                    {seg.index > 1 && (
                      <button
                        disabled={busy !== null}
                        onClick={() => run("split", { at_time: seg.start_time })}
                        title="Move this part and everything after it into a new event"
                        className="px-2.5 py-1 rounded border border-white/10 text-zinc-400 hover:text-white hover:bg-white/5 font-mono text-[8px] tracking-widest uppercase disabled:opacity-40"
                      >
                        ✂ SPLIT HERE
                      </button>
                    )}
                  </div>
                </div>
              </React.Fragment>
            );
          })}
          {event.status === "paused" && (
            <div className="font-mono text-[9px] text-amber-400/80 tracking-widest uppercase flex items-center gap-2">
              <span>⏸</span>
              <span>PAUSED SINCE {hhmm(event.paused_at)} — WAITING FOR THE SAME SUBJECT TO RESUME</span>
            </div>
          )}
        </div>
      )}

      {/* Micro-events */}
      {expanded && event.linked_micro_events?.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {event.linked_micro_events.slice(0, 8).map((m) => (
            <span key={`${m.event_type}-${m.record_id}`} className="px-2.5 py-1 rounded-lg bg-[#121419] border border-white/5 font-sans text-[11px] text-zinc-300">
              {m.event_type === "action" ? "🛡️" : m.event_type === "social_contact" ? "👤" : m.event_type === "task_scheduled" ? "⏱️" : "🤝"}{" "}
              {m.headline}
            </span>
          ))}
        </div>
      )}

      {/* Actions */}
      <div className="flex flex-wrap items-center gap-2 pt-3 border-t border-white/5">
        {event.status === "active" && (
          <button
            disabled={busy !== null}
            onClick={() => run("pause")}
            className="px-3 py-1.5 rounded-lg border border-cyan-500/40 bg-cyan-950/30 hover:bg-cyan-950/60 text-cyan-300 font-mono text-[9px] tracking-widest uppercase disabled:opacity-40"
          >
            {busy === "pause" ? "…" : "⚡ SYNTHESIZE NOW"}
          </button>
        )}
        {event.status === "paused" && (
          <button
            disabled={busy !== null}
            onClick={() => run("resume")}
            className="px-3 py-1.5 rounded-lg border border-emerald-500/40 bg-emerald-950/30 hover:bg-emerald-950/60 text-emerald-300 font-mono text-[9px] tracking-widest uppercase disabled:opacity-40"
          >
            {busy === "resume" ? "…" : "▶ RESUME"}
          </button>
        )}
        {isOpen && (
          <button
            disabled={busy !== null}
            onClick={() => run("conclude")}
            className="px-3 py-1.5 rounded-lg border border-white/10 hover:bg-white/5 text-zinc-300 font-mono text-[9px] tracking-widest uppercase disabled:opacity-40"
          >
            {busy === "conclude" ? "…" : "🏁 CONCLUDE"}
          </button>
        )}
        {previousEvent && (
          <button
            disabled={busy !== null}
            onClick={() => run("merge", { with: previousEvent.session_id })}
            title={`Merge with "${previousEvent.final_title || previousEvent.title || "previous event"}"`}
            className="px-3 py-1.5 rounded-lg border border-white/10 hover:bg-white/5 text-zinc-300 font-mono text-[9px] tracking-widest uppercase disabled:opacity-40"
          >
            {busy === "merge" ? "…" : "⇡ MERGE WITH PREVIOUS"}
          </button>
        )}
        <button
          onClick={() => setShowLog((v) => !v)}
          className="px-3 py-1.5 rounded-lg border border-white/10 hover:bg-white/5 text-zinc-400 font-mono text-[9px] tracking-widest uppercase"
        >
          🧭 {showLog ? "HIDE" : "WHY?"} ({event.transitions_count})
        </button>
        {detail?.spoken_summary && (
          <button
            onClick={speak}
            className="px-3 py-1.5 rounded-lg border border-amber-500/30 hover:bg-amber-500/10 text-amber-300 font-mono text-[9px] tracking-widest uppercase"
          >
            🔊 ALEXA RECAP
          </button>
        )}
        <button
          disabled={busy !== null}
          onClick={() => setConfirmDelete(true)}
          className="px-3 py-1.5 rounded-lg border border-rose-500/30 hover:bg-rose-950/40 text-rose-300 font-mono text-[9px] tracking-widest uppercase disabled:opacity-40"
          title="Delete this event, its transcript log and its briefings"
        >
          {busy === "delete" ? "…" : "🗑️ DELETE"}
        </button>
        {event.last_transition && !showLog && (
          <span className="font-mono text-[9px] text-zinc-500 ml-auto truncate max-w-[420px]" title={event.last_transition.detail || ""}>
            LAST: {event.last_transition.rule} · {event.last_transition.reason.replace(/_/g, " ")} · {hhmm(event.last_transition.at)}
          </span>
        )}
      </div>

      {showLog && <DecisionLog transitions={detail?.transitions || []} />}

      <ConfirmDialog
        isOpen={confirmDelete}
        title={`Delete "${title || "this event"}"?`}
        body="Its transcript log and briefings are deleted. The actions, contacts and routines found in it are kept."
        consequences={formatCascade({ briefings: segments.filter((s) => s.briefing_id).length + (event.final_briefing_id ? 1 : 0) })}
        onConfirm={() => run("delete")}
        onClose={() => setConfirmDelete(false)}
      />
    </div>
  );
}
