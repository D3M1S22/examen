import React, { useState, useEffect, useCallback } from "react";
import { createPortal } from "react-dom";
import useSWR from "swr";
import { EchoShowCardResponse } from "@/types/schemas";
import { speakAlexaReassurance } from "@/utils/audioEffects";
import { getApiBaseUrl } from "@/utils/api";

interface EchoShowModalProps {
  isOpen: boolean;
  onClose: () => void;
  initialTemplate?: string;
}

const fetcher = (url: string) =>
  fetch(`${getApiBaseUrl()}${url}`)
    .then((res) => {
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return res.json();
    })
    .catch((err) => {
      console.warn("Echo Show preview fetch failed:", err);
      return null;
    });

export function EchoShowModal({
  isOpen,
  onClose,
  initialTemplate = "DEEP_BRIEFING_VIEWER",
}: EchoShowModalProps) {
  const [mounted, setMounted] = useState(false);
  const [template, setTemplate] = useState(initialTemplate);
  const [activeQuery, setActiveQuery] = useState("");
  const [echoTime, setEchoTime] = useState("");
  const [feedbackMsg, setFeedbackMsg] = useState<string | null>(null);

  useEffect(() => {
    setMounted(true);
  }, []);

  // Sync template if initialTemplate changes or modal reopens
  useEffect(() => {
    if (initialTemplate) {
      setTemplate(initialTemplate);
      setActiveQuery("");
    }
  }, [initialTemplate, isOpen]);

  const swrKey = isOpen
    ? `/api/cards/preview?template=${template}${activeQuery ? `&query=${encodeURIComponent(activeQuery)}` : ""}`
    : null;

  const { data: cardData, isLoading, mutate } = useSWR<EchoShowCardResponse | null>(
    swrKey,
    fetcher
  );

  const showFeedback = useCallback((msg: string) => {
    setFeedbackMsg(msg);
    setTimeout(() => setFeedbackMsg(null), 3000);
  }, []);

  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = "hidden";
      const updateClock = () => {
        const now = new Date();
        setEchoTime(
          `${now.getHours().toString().padStart(2, "0")}:${now
            .getMinutes()
            .toString()
            .padStart(2, "0")}`
        );
      };
      updateClock();
      const interval = setInterval(updateClock, 1000);

      const handleKeyDown = (e: KeyboardEvent) => {
        if (e.key === "Escape") onClose();
      };
      window.addEventListener("keydown", handleKeyDown);

      return () => {
        document.body.style.overflow = "unset";
        clearInterval(interval);
        window.removeEventListener("keydown", handleKeyDown);
      };
    } else {
      document.body.style.overflow = "unset";
    }
  }, [isOpen, onClose]);

  if (!isOpen || !mounted) return null;

  // Safe object extraction
  const rawData: any = cardData || {};
  const payload: any = rawData?.card_payload || rawData || {};

  const cardTitle =
    rawData?.title ||
    payload?.title ||
    rawData?.topic_title ||
    payload?.topic_title ||
    (template === "DEEP_BRIEFING_VIEWER"
      ? "Autonomous Topic Research Dossier"
      : template === "SOCIAL_PROFILE_CARD"
      ? "Executive Social Rolodex Dossier"
      : template === "SOCIAL_COMMITMENTS_CARD"
      ? "Bilateral Social Commitments"
      : template === "ACTION_VERIFIED_BADGE"
      ? "Peace of Mind Acoustic Corroboration"
      : template === "DAILY_ACTIONS_RECAP"
      ? "Daily Verification Recap"
      : template === "UPCOMING_TASKS_VIEWER"
      ? "Upcoming Monitored Routines"
      : template === "SESSION_DOSSIER_VIEWER"
      ? "Macro Session Intelligence Dossier"
      : "Multimodal Echo Show Card");

  const badgeText =
    rawData?.header_badge ||
    rawData?.ui_card_type ||
    rawData?.display_template ||
    payload?.template ||
    (typeof template === "string" ? template.replace(/_/g, " ") : "ECHO SHOW");

  const spokenText =
    rawData?.spoken_summary ||
    payload?.spoken_summary ||
    rawData?.voice_summary ||
    payload?.voice_summary ||
    `Displaying ${cardTitle}. All background telemetry is nominal.`;

  const synthesis =
    payload?.explanatory_synthesis ||
    payload?.synthesis ||
    rawData?.explanatory_synthesis ||
    rawData?.display_data?.explanatory_synthesis ||
    "";

  const summaryText =
    payload?.bio_summary ||
    payload?.bio ||
    payload?.summary ||
    rawData?.display_data?.summary ||
    rawData?.web_profile?.bio_summary ||
    "";

  // Safe bullet point list
  const bullets: string[] = (() => {
    const raw =
      payload?.bullets ||
      payload?.executive_summary ||
      rawData?.executive_summary ||
      rawData?.display_data?.facts ||
      payload?.key_discussion_points ||
      rawData?.key_discussion_points ||
      [];
    if (Array.isArray(raw)) {
      return raw.map((item: any) =>
        item && typeof item === "object"
          ? item.headline || item.text || item.title || JSON.stringify(item)
          : String(item)
      );
    }
    if (typeof raw === "string" && raw.trim()) return [raw];
    return [];
  })();

  // Safe web sources
  const sources: string[] = (() => {
    const raw =
      payload?.sources ||
      payload?.web_sources ||
      rawData?.web_sources ||
      rawData?.sources ||
      [];
    if (Array.isArray(raw)) {
      return raw.map((item: any) =>
        item && typeof item === "object"
          ? item.url || item.title || JSON.stringify(item)
          : String(item)
      );
    }
    if (typeof raw === "string" && raw.trim()) return [raw];
    return [];
  })();

  // Safe action items
  const actionItems: string[] = (() => {
    const raw = payload?.action_items || rawData?.action_items || [];
    if (Array.isArray(raw)) {
      return raw.map((item: any) =>
        item && typeof item === "object"
          ? item.title || item.description || JSON.stringify(item)
          : String(item)
      );
    }
    if (typeof raw === "string" && raw.trim()) return [raw];
    return [];
  })();

  // Safe commitments
  const commitmentsList: any[] = (() => {
    let raw =
      payload?.commitments ||
      rawData?.commitments ||
      rawData?.display_data?.commitments;

    if (!raw || (Array.isArray(raw) && raw.length === 0)) {
      const u = payload?.user_promises || rawData?.user_promises || [];
      const c = payload?.contact_promises || rawData?.contact_promises || [];
      const combined = [
        ...(Array.isArray(u) ? u : []),
        ...(Array.isArray(c) ? c : []),
      ];
      if (combined.length > 0) raw = combined;
    }

    if (Array.isArray(raw)) {
      return raw.filter((item) => item !== null && item !== undefined);
    }
    return [];
  })();

  // Safe actions list
  const actionsList: any[] = (() => {
    const raw =
      payload?.actions ||
      rawData?.actions ||
      rawData?.spontaneous_actions ||
      payload?.spontaneous_actions ||
      rawData?.recent_actions ||
      rawData?.display_data?.items ||
      [];
    if (Array.isArray(raw)) {
      return raw.filter((item) => item !== null && item !== undefined);
    }
    return [];
  })();

  // Safe tasks list
  const tasksList: any[] = (() => {
    const raw =
      payload?.tasks ||
      rawData?.tasks ||
      rawData?.planned_routines ||
      payload?.planned_routines ||
      [];
    if (Array.isArray(raw)) {
      return raw.filter((item) => item !== null && item !== undefined);
    }
    return [];
  })();

  // Safe contact & web profile objects
  const contactObj = rawData?.contact || payload?.contact || null;
  const webProfileObj = rawData?.web_profile || payload?.web_profile || null;

  // Safe expertise array
  const expertiseList: string[] = (() => {
    const raw =
      webProfileObj?.areas_of_expertise ||
      payload?.areas_of_expertise ||
      rawData?.areas_of_expertise;
    if (Array.isArray(raw)) return raw.map(String).filter(Boolean);
    if (typeof raw === "string" && raw.trim()) {
      return raw.split(",").map((s) => s.trim()).filter(Boolean);
    }
    return [];
  })();

  // Daily recap summary stats with calculated fallbacks
  const recapSummary = rawData?.summary || payload?.summary || null;
  const plannedTotalCount = recapSummary?.planned_total ?? tasksList.length;
  const plannedCompletedCount =
    recapSummary?.planned_completed ??
    tasksList.filter((t: any) => t.status === "completed").length;
  const plannedPendingCount =
    recapSummary?.planned_pending ??
    Math.max(0, plannedTotalCount - plannedCompletedCount);
  const spontaneousTotalCount =
    recapSummary?.spontaneous_actions ?? actionsList.length;

  // Peace of mind single action details
  const singleActionStatus = rawData?.status || payload?.status || "verified";
  const singleActionType =
    rawData?.action_type || payload?.action_type || "domestic_action";
  const singleRawStatement =
    rawData?.raw_statement || payload?.raw_statement || "";
  const singleConfidence =
    rawData?.confidence ?? payload?.confidence ?? 0.98;
  const singleElapsed =
    rawData?.elapsed_time_human || payload?.elapsed_time_human || "just now";

  // Session dossier meta
  const sessionId = rawData?.session_id || payload?.session_id || "";
  const sessionStatus = rawData?.status || payload?.status || "active";
  const sessionLocationName =
    payload?.location_name ||
    rawData?.location?.place_name ||
    rawData?.location?.semantic_zone ||
    "Office / Home Desk";
  const linkedEvents: any[] = Array.isArray(rawData?.linked_micro_events)
    ? rawData.linked_micro_events
    : Array.isArray(payload?.linked_micro_events)
    ? payload.linked_micro_events
    : [];

  // Interactive Backend Actions
  const handleSpeakCard = () => {
    speakAlexaReassurance(spokenText);
  };

  const handleToggleRoutine = async (taskId?: string, title?: string) => {
    if (!taskId) return;
    try {
      const baseUrl = getApiBaseUrl();
      const res = await fetch(`${baseUrl}/api/routines/${taskId}/toggle`, {
        method: "POST",
      });
      if (!res.ok) throw new Error("Failed to toggle routine");
      mutate();
      speakAlexaReassurance(`Routine ${title || "check"} updated.`);
      showFeedback(`Routine updated!`);
    } catch {
      showFeedback(`Failed to update routine.`);
    }
  };

  const handleFulfillCommitment = async (commitmentId?: string, desc?: string) => {
    if (!commitmentId) return;
    try {
      const baseUrl = getApiBaseUrl();
      const res = await fetch(
        `${baseUrl}/api/commitments/${commitmentId}/fulfill`,
        { method: "POST" }
      );
      if (!res.ok) throw new Error("Failed to fulfill commitment");
      mutate();
      speakAlexaReassurance(`Commitment marked fulfilled.`);
      showFeedback(`Commitment marked fulfilled!`);
    } catch {
      showFeedback(`Failed to fulfill commitment.`);
    }
  };

  const handleEnrichContact = async (contactId?: string, name?: string) => {
    if (!contactId) return;
    try {
      const baseUrl = getApiBaseUrl();
      showFeedback(`Enriching ${name || "contact"}...`);
      const res = await fetch(`${baseUrl}/api/contacts/${encodeURIComponent(contactId)}/enrich`, {
        method: "POST",
      });
      if (!res.ok) throw new Error("Enrichment failed");
      mutate();
      speakAlexaReassurance(
        `AI web profile research refreshed for ${name || "contact"}.`
      );
      showFeedback(`Profile enriched successfully!`);
    } catch {
      showFeedback(`Enrichment failed.`);
    }
  };

  const handleConcludeSession = async (sId?: string) => {
    if (!sId) return;
    try {
      const baseUrl = getApiBaseUrl();
      const res = await fetch(`${baseUrl}/api/sessions/${encodeURIComponent(sId)}/conclude`, {
        method: "POST",
      });
      if (!res.ok) throw new Error("Failed to conclude session");
      mutate();
      speakAlexaReassurance(`Session concluded. Intelligence dossier saved.`);
      showFeedback(`Session concluded!`);
    } catch {
      showFeedback(`Failed to conclude session.`);
    }
  };

  const handleSelectTemplate = (tId: string) => {
    setActiveQuery("");
    setTemplate(tId);
  };

  const handleVerifyQuery = (queryText: string) => {
    setActiveQuery(queryText);
    speakAlexaReassurance(`Alexa: Checking acoustic corroboration for ${queryText}.`);
  };

  const handleQuickPrompt = (promptText: string, targetTemplate: string, queryText?: string) => {
    setActiveQuery(queryText || "");
    setTemplate(targetTemplate);
    speakAlexaReassurance(promptText);
  };

  const templates = [
    { id: "DEEP_BRIEFING_VIEWER", label: "📚 Deep Briefing" },
    { id: "SOCIAL_PROFILE_CARD", label: "👤 Social Profile" },
    { id: "SOCIAL_COMMITMENTS_CARD", label: "🤝 Commitments" },
    { id: "ACTION_VERIFIED_BADGE", label: "🛡️ Peace of Mind" },
    { id: "DAILY_ACTIONS_RECAP", label: "📋 Daily Recap" },
    { id: "UPCOMING_TASKS_VIEWER", label: "⏱️ Upcoming Tasks" },
    { id: "SESSION_DOSSIER_VIEWER", label: "🏛️ Session Dossier" },
  ];

  return createPortal(
    <div
      className="fixed inset-0 z-[9999] overflow-y-auto bg-black/90 backdrop-blur-md flex items-center justify-center p-3 sm:p-6"
      onClick={onClose}
      aria-modal="true"
      role="dialog"
    >
      <div
        className="relative w-full max-w-4xl my-auto animate-in fade-in zoom-in-95 duration-150"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Device Frame Top Label */}
        <div className="flex items-center justify-between px-2 mb-2">
          <div className="font-mono text-[10px] text-zinc-400 tracking-[0.2em] uppercase flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse"></span>
            AMAZON ECHO SHOW 15 MULTIMODAL SIMULATOR // EXT-APP RUNTIME
          </div>
          <div className="flex items-center gap-2">
            {feedbackMsg && (
              <span className="font-mono text-[10px] text-emerald-400 tracking-wider bg-emerald-950/80 border border-emerald-500/30 px-2 py-0.5 rounded">
                ⚡ {feedbackMsg}
              </span>
            )}
            <button
              onClick={onClose}
              className="text-zinc-400 hover:text-white font-mono text-[11px] tracking-wider uppercase px-2.5 py-1 rounded bg-zinc-800/80 hover:bg-zinc-700 transition-colors"
            >
              ✕ Exit Echo View
            </button>
          </div>
        </div>

        {/* Physical Hardware Bezel */}
        <div className="bg-[#101216] border-4 border-[#242833] rounded-3xl p-4 sm:p-6 shadow-[0_25px_60px_-15px_rgba(0,0,0,0.9)] relative">
          {/* Echo Camera Notch */}
          <div className="absolute top-2 left-1/2 -translate-x-1/2 flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-[#0a0b0d] border border-white/10"></span>
            <span className="w-1.5 h-1.5 rounded-full bg-red-900/30"></span>
          </div>

          {/* Glass Display Screen */}
          <div className="bg-[#08090b] border border-white/5 rounded-2xl overflow-hidden min-h-[540px] flex flex-col relative text-zinc-100">
            {/* Echo System Bar */}
            <div className="bg-black/60 px-6 py-3 flex items-center justify-between border-b border-white/5">
              <div className="font-mono text-base font-bold text-white tracking-wider">
                {echoTime || "12:00"}
              </div>

              <div className="flex items-center gap-2 px-3 py-1 rounded-full bg-cyan-950/60 border border-cyan-500/40 text-cyan-300 font-mono text-[10px] tracking-widest uppercase">
                <span className="w-2 h-2 rounded-full bg-cyan-400"></span>
                <span>Alexa+ Ambient Ext-App</span>
              </div>

              <div className="flex items-center gap-3 text-zinc-400 text-xs font-mono">
                <span>📶 5G MESH</span>
                <span className="opacity-40">•</span>
                <span>BEE LINKED</span>
              </div>
            </div>

            {/* Template Switcher Bar */}
            <div className="bg-[#121419] px-4 py-2 border-b border-white/5 flex items-center gap-2 overflow-x-auto hide-scrollbar">
              {templates.map((t) => (
                <button
                  key={t.id}
                  onClick={() => handleSelectTemplate(t.id)}
                  className={`px-3 py-1.5 rounded-lg font-mono text-[10px] tracking-wider whitespace-nowrap transition-all uppercase ${
                    template === t.id
                      ? "bg-cyan-500 text-black font-bold shadow-md"
                      : "text-zinc-400 hover:text-white hover:bg-white/5"
                  }`}
                >
                  {t.label}
                </button>
              ))}
            </div>

            {/* Dynamic Echo Show Card Canvas */}
            <div className="p-6 sm:p-8 flex-1 flex flex-col justify-between">
              {isLoading ? (
                <div className="flex-1 flex flex-col items-center justify-center gap-3 py-16">
                  <div className="w-8 h-8 border-2 border-cyan-400 border-t-transparent rounded-full animate-spin" />
                  <div className="font-mono text-[10px] text-zinc-400 tracking-widest uppercase">
                    Rendering Echo Show Multimodal Card...
                  </div>
                </div>
              ) : rawData ? (
                <div className="space-y-6 flex-1 flex flex-col justify-between">
                  {/* Card Header */}
                  <div>
                    <div className="flex items-center justify-between mb-3">
                      <div className="flex items-center gap-2">
                        <span className="px-2.5 py-0.5 rounded bg-cyan-950/70 text-cyan-300 border border-cyan-500/30 font-mono text-[9px] tracking-widest uppercase font-bold">
                          {badgeText}
                        </span>
                        <span className="font-mono text-[9px] text-zinc-500 tracking-widest uppercase">
                          {typeof rawData?.timestamp === "string"
                            ? rawData.timestamp.replace("T", " ").substring(0, 19)
                            : "LIVE"}
                        </span>
                      </div>
                      <button
                        onClick={handleSpeakCard}
                        className="px-3.5 py-1.5 rounded-full bg-cyan-500/10 hover:bg-cyan-500/20 border border-cyan-400/40 text-cyan-300 font-mono text-[10px] tracking-widest uppercase flex items-center gap-1.5 transition-colors font-bold shadow-sm"
                      >
                        <span>🔊</span>
                        <span>Read Aloud</span>
                      </button>
                    </div>

                    <h1 className="font-serif text-[30px] sm:text-[36px] text-white leading-tight mb-4">
                      {cardTitle}
                    </h1>

                    {/* Card Body Data */}
                    <div className="bg-[#12141a] border border-white/5 rounded-xl p-5 space-y-4">
                      {/* TAB 1: DEEP BRIEFING VIEWER */}
                      {template === "DEEP_BRIEFING_VIEWER" && (
                        <div className="space-y-4">
                          {synthesis && (
                            <div className="bg-amber-950/30 border border-amber-500/30 rounded-lg p-3 text-amber-200/90 font-sans text-body-sm leading-relaxed">
                              ⚡ <strong className="uppercase font-mono text-[10px] tracking-wider text-amber-300 mr-1">Thesis:</strong> {synthesis}
                            </div>
                          )}

                          {bullets.length > 0 && (
                            <div className="space-y-2">
                              <div className="font-mono text-[9px] text-zinc-400 tracking-widest uppercase">Key Insights & Takeaways:</div>
                              <ul className="space-y-2">
                                {bullets.map((b: string, i: number) => (
                                  <li key={i} className="flex items-start gap-2.5 text-zinc-200 text-body-sm font-sans">
                                    <span className="text-cyan-400 font-bold">•</span>
                                    <span>{b}</span>
                                  </li>
                                ))}
                              </ul>
                            </div>
                          )}

                          {actionItems.length > 0 && (
                            <div className="space-y-2 pt-2 border-t border-white/5">
                              <div className="font-mono text-[9px] text-zinc-400 tracking-widest uppercase">Action Items & Next Steps:</div>
                              <div className="space-y-1.5">
                                {actionItems.map((act: string, i: number) => (
                                  <div key={i} className="flex items-center gap-2 text-xs text-zinc-300 bg-black/40 p-2 rounded border border-white/5">
                                    <span className="text-cyan-400 font-mono">[{i + 1}]</span>
                                    <span>{act}</span>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}

                          {sources.length > 0 && (
                            <div className="pt-2 border-t border-white/5">
                              <div className="font-mono text-[9px] text-zinc-400 tracking-widest uppercase mb-1.5">Corroborating Web Sources:</div>
                              <div className="flex flex-wrap gap-2">
                                {sources.slice(0, 4).map((src: string, i: number) => (
                                  <span key={i} className="text-amber-300 font-mono text-[10px] truncate max-w-xs">
                                    🔗 {src}
                                  </span>
                                ))}
                              </div>
                            </div>
                          )}

                          {!synthesis && bullets.length === 0 && actionItems.length === 0 && sources.length === 0 && (
                            <div className="text-center py-8 text-zinc-500 font-mono text-sm">
                              No briefing notes recorded yet.
                            </div>
                          )}
                        </div>
                      )}

                      {/* TAB 2: SOCIAL PROFILE CARD */}
                      {template === "SOCIAL_PROFILE_CARD" && (
                        <div className="space-y-4">
                          <div className="p-4 rounded-xl bg-black/40 border border-white/5 space-y-3">
                            <div className="flex items-start justify-between gap-3">
                              <div>
                                <h2 className="text-cyan-300 font-serif text-xl sm:text-2xl">
                                  {contactObj?.name || payload?.name || webProfileObj?.current_role || "Executive Contact"}
                                </h2>
                                {(webProfileObj?.headline || contactObj?.company_or_role || payload?.company_or_role) && (
                                  <div className="text-xs text-zinc-400 font-mono uppercase tracking-wider mt-0.5">
                                    {webProfileObj?.headline || contactObj?.company_or_role || payload?.company_or_role}
                                  </div>
                                )}
                              </div>

                              {(contactObj?.id || contactObj?.name || payload?.name) && (
                                <button
                                  onClick={() =>
                                    handleEnrichContact(
                                      contactObj?.id || contactObj?.name || payload?.name,
                                      contactObj?.name || payload?.name
                                    )
                                  }
                                  className="px-3 py-1 rounded-lg bg-cyan-950/70 hover:bg-cyan-900 border border-cyan-500/40 text-cyan-300 font-mono text-[9px] tracking-wider uppercase shrink-0 transition-colors"
                                >
                                  🔍 Enrich Profile
                                </button>
                              )}
                            </div>

                            {summaryText && (
                              <div className="text-zinc-300 font-sans text-body-sm leading-relaxed border-t border-white/5 pt-2">
                                {summaryText}
                              </div>
                            )}

                            {expertiseList.length > 0 && (
                              <div className="flex flex-wrap gap-1.5 pt-1">
                                {expertiseList.map((exp: string, i: number) => (
                                  <span key={i} className="px-2 py-0.5 rounded bg-cyan-950/60 border border-cyan-500/20 text-cyan-300 font-mono text-[8px] uppercase">
                                    #{exp}
                                  </span>
                                ))}
                              </div>
                            )}

                            {/* Verified Links */}
                            {(webProfileObj?.linkedin_url || webProfileObj?.github_url || webProfileObj?.website_url) && (
                              <div className="flex flex-wrap gap-3 pt-2 border-t border-white/5 text-[11px] font-mono">
                                {webProfileObj.linkedin_url && (
                                  <a href={webProfileObj.linkedin_url} target="_blank" rel="noreferrer" className="text-cyan-400 hover:underline">
                                    LinkedIn ↗
                                  </a>
                                )}
                                {webProfileObj.github_url && (
                                  <a href={webProfileObj.github_url} target="_blank" rel="noreferrer" className="text-zinc-300 hover:underline">
                                    GitHub ↗
                                  </a>
                                )}
                                {webProfileObj.website_url && (
                                  <a href={webProfileObj.website_url} target="_blank" rel="noreferrer" className="text-amber-400 hover:underline">
                                    Website ↗
                                  </a>
                                )}
                              </div>
                            )}
                          </div>

                          {/* Associated Commitments */}
                          {commitmentsList.length > 0 && (
                            <div className="space-y-2">
                              <div className="font-mono text-[9px] text-zinc-400 tracking-widest uppercase">Associated Commitments:</div>
                              {commitmentsList.map((cmt: any, i: number) => {
                                const desc = cmt && typeof cmt === "object" ? cmt.description || cmt.title || "Commitment" : String(cmt);
                                const debtor = cmt && typeof cmt === "object" ? cmt.debtor : "user";
                                const status = cmt && typeof cmt === "object" ? cmt.status : "open";
                                const cmtId = cmt && typeof cmt === "object" ? cmt.id : null;
                                return (
                                  <div key={i} className="p-2.5 rounded bg-black/40 text-sm font-sans text-zinc-200 flex items-center justify-between gap-2.5 border border-white/5">
                                    <div className="flex items-center gap-2">
                                      <span>{debtor === "user" ? "📤" : "📥"}</span>
                                      <span>{desc}</span>
                                    </div>
                                    <div className="flex items-center gap-2 shrink-0">
                                      <span className="font-mono text-[9px] text-cyan-400 uppercase">
                                        {debtor === "user" ? "You Promised" : "Contact"}
                                      </span>
                                      {cmtId && status === "open" && (
                                        <button
                                          onClick={() => handleFulfillCommitment(cmtId, desc)}
                                          className="px-2 py-0.5 rounded bg-emerald-950/70 hover:bg-emerald-900 border border-emerald-500/40 text-emerald-300 font-mono text-[9px] uppercase transition-colors"
                                          title="Mark commitment fulfilled"
                                        >
                                          ✓ Fulfill
                                        </button>
                                      )}
                                    </div>
                                  </div>
                                );
                              })}
                            </div>
                          )}
                        </div>
                      )}

                      {/* TAB 3: SOCIAL COMMITMENTS CARD */}
                      {template === "SOCIAL_COMMITMENTS_CARD" && (
                        <div className="space-y-4">
                          <div className="flex items-center justify-between text-xs font-mono text-zinc-400 pb-2 border-b border-white/5">
                            <span>TOTAL COMMITMENTS: {commitmentsList.length}</span>
                            <span className="text-cyan-300">BILATERAL PROMISES</span>
                          </div>

                          {commitmentsList.length > 0 ? (
                            <div className="space-y-2 max-h-[300px] overflow-y-auto pr-1">
                              {commitmentsList.map((cmt: any, i: number) => {
                                const desc = cmt && typeof cmt === "object" ? cmt.description || cmt.title || "Commitment" : String(cmt);
                                const debtor = cmt && typeof cmt === "object" ? cmt.debtor : "user";
                                const contactName = cmt && typeof cmt === "object" ? cmt.contact_name : "Contact";
                                const status = cmt && typeof cmt === "object" ? cmt.status : "open";
                                const cmtId = cmt && typeof cmt === "object" ? cmt.id : null;

                                return (
                                  <div key={i} className="p-3 rounded-lg bg-black/40 border border-white/5 flex items-center justify-between gap-3">
                                    <div className="flex items-center gap-2.5 flex-1 min-w-0">
                                      <span className="text-base shrink-0">{debtor === "user" ? "📤" : "📥"}</span>
                                      <div className="min-w-0 flex-1">
                                        <div className="text-sm font-sans text-zinc-100 truncate">{desc}</div>
                                        <div className="text-[10px] font-mono text-zinc-400 mt-0.5">
                                          {debtor === "user" ? `You promised to ${contactName || "contact"}` : `${contactName || "Contact"} promised you`}
                                        </div>
                                      </div>
                                    </div>

                                    <div className="flex items-center gap-2 shrink-0">
                                      <span className={`font-mono text-[9px] uppercase font-bold px-2 py-0.5 rounded ${
                                        status === "fulfilled"
                                          ? "bg-emerald-950/80 text-emerald-300 border border-emerald-500/30"
                                          : "bg-amber-950/80 text-amber-300 border border-amber-500/30"
                                      }`}>
                                        {status}
                                      </span>

                                      {cmtId && status === "open" && (
                                        <button
                                          onClick={() => handleFulfillCommitment(cmtId, desc)}
                                          className="px-2.5 py-1 rounded bg-emerald-950/70 hover:bg-emerald-900 border border-emerald-500/40 text-emerald-300 font-mono text-[9px] tracking-wider uppercase transition-colors"
                                          title="Mark commitment fulfilled"
                                        >
                                          ✓ Fulfill
                                        </button>
                                      )}
                                    </div>
                                  </div>
                                );
                              })}
                            </div>
                          ) : (
                            <div className="text-center py-8 text-zinc-500 font-mono text-sm">
                              No active bilateral commitments on record.
                            </div>
                          )}
                        </div>
                      )}

                      {/* TAB 4: ACTION VERIFIED BADGE (Peace of Mind) */}
                      {template === "ACTION_VERIFIED_BADGE" && (
                        <div className="space-y-4">
                          <div className={`p-5 rounded-xl border space-y-3 ${
                            singleActionStatus === "verified"
                              ? "bg-gradient-to-r from-emerald-950/30 to-black/60 border-emerald-500/40"
                              : "bg-gradient-to-r from-amber-950/30 to-black/60 border-amber-500/40"
                          }`}>
                            <div className="flex items-center justify-between">
                              <span className={`flex items-center gap-2 font-mono text-xs font-bold tracking-wider uppercase ${
                                singleActionStatus === "verified" ? "text-emerald-400" : "text-amber-400"
                              }`}>
                                <span className={`w-2.5 h-2.5 rounded-full animate-pulse ${
                                  singleActionStatus === "verified" ? "bg-emerald-400" : "bg-amber-400"
                                }`} />
                                {singleActionStatus === "verified" ? "ACOUSTICALLY VERIFIED ANCHOR" : "PENDING REASSURANCE // UNVERIFIED"}
                              </span>
                              <span className="font-mono text-xs text-zinc-400">
                                {singleElapsed}
                              </span>
                            </div>

                            <div className="font-serif text-2xl text-white">
                              {singleActionType.replace(/_/g, " ").toUpperCase()}
                            </div>

                            {singleRawStatement ? (
                              <div className="p-3 rounded-lg bg-black/60 border border-white/5 font-sans italic text-sm text-zinc-200">
                                "{singleRawStatement}"
                              </div>
                            ) : (
                              <div className="p-3 rounded-lg bg-black/60 border border-white/5 font-sans italic text-sm text-zinc-400">
                                No raw spoken utterance on record for this action query yet.
                              </div>
                            )}

                            <div className="flex items-center justify-between pt-2 border-t border-white/5 text-xs font-mono">
                              <span className="text-zinc-400">ACOUSTIC CERTAINTY:</span>
                              <span className={`font-bold ${
                                singleActionStatus === "verified" ? "text-emerald-400" : "text-amber-400"
                              }`}>
                                {Math.round(singleConfidence * 100)}% CONFIDENCE
                              </span>
                            </div>
                          </div>

                          {/* Quick domestic checks */}
                          <div className="space-y-2 pt-2 border-t border-white/5">
                            <div className="font-mono text-[9px] text-zinc-400 tracking-widest uppercase">
                              Ask Alexa Reassurance Query:
                            </div>
                            <div className="flex flex-wrap gap-2">
                              {[
                                { q: "unplug_clothes_iron", label: "Unplug Clothes Iron" },
                                { q: "turn_off_kitchen_stove", label: "Turn off Kitchen Stove" },
                                { q: "lock_front_door", label: "Lock Front Door" },
                                { q: "take_evening_medication", label: "Evening Medication" },
                              ].map((item, i) => (
                                <button
                                  key={i}
                                  onClick={() => handleVerifyQuery(item.q)}
                                  className="px-3 py-1.5 rounded-lg bg-black/40 hover:bg-white/5 border border-white/10 text-zinc-300 font-mono text-[10px] tracking-wider transition-colors"
                                >
                                  🛡️ {item.label}
                                </button>
                              ))}
                            </div>
                          </div>
                        </div>
                      )}

                      {/* TAB 5: DAILY ACTIONS RECAP */}
                      {template === "DAILY_ACTIONS_RECAP" && (
                        <div className="space-y-4">
                          {/* Metrics summary */}
                          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-center">
                            <div className="p-2.5 rounded-lg bg-black/40 border border-white/5">
                              <div className="font-mono text-lg font-bold text-white">{plannedTotalCount}</div>
                              <div className="font-mono text-[8px] text-zinc-400 uppercase tracking-wider">PLANNED TOTAL</div>
                            </div>
                            <div className="p-2.5 rounded-lg bg-black/40 border border-white/5">
                              <div className="font-mono text-lg font-bold text-emerald-400">{plannedCompletedCount}</div>
                              <div className="font-mono text-[8px] text-zinc-400 uppercase tracking-wider">COMPLETED</div>
                            </div>
                            <div className="p-2.5 rounded-lg bg-black/40 border border-white/5">
                              <div className="font-mono text-lg font-bold text-amber-400">{plannedPendingCount}</div>
                              <div className="font-mono text-[8px] text-zinc-400 uppercase tracking-wider">PENDING</div>
                            </div>
                            <div className="p-2.5 rounded-lg bg-black/40 border border-white/5">
                              <div className="font-mono text-lg font-bold text-cyan-400">{spontaneousTotalCount}</div>
                              <div className="font-mono text-[8px] text-zinc-400 uppercase tracking-wider">SPONTANEOUS</div>
                            </div>
                          </div>

                          {/* Planned routines checklist */}
                          {tasksList.length > 0 && (
                            <div className="space-y-2">
                              <div className="font-mono text-[9px] text-zinc-400 tracking-widest uppercase">Planned Routines Checklist:</div>
                              <div className="space-y-1.5 max-h-[160px] overflow-y-auto pr-1">
                                {tasksList.map((task: any, i: number) => {
                                  const isComp = task.status === "completed";
                                  return (
                                    <div key={i} className="p-2.5 rounded bg-black/40 border border-white/5 flex items-center justify-between gap-2">
                                      <div className="flex items-center gap-2 truncate">
                                        <button
                                          onClick={() => handleToggleRoutine(task.id, task.title)}
                                          className={`w-4 h-4 rounded flex items-center justify-center font-mono text-[10px] border transition-colors ${
                                            isComp ? "bg-emerald-500 border-emerald-400 text-black font-bold" : "border-white/30 hover:border-white"
                                          }`}
                                        >
                                          {isComp ? "✓" : ""}
                                        </button>
                                        <span className={`text-body-sm font-sans truncate ${isComp ? "line-through text-zinc-500" : "text-zinc-200"}`}>
                                          {task.title || task.headline}
                                        </span>
                                      </div>
                                      <span className="font-mono text-[9px] text-zinc-400 shrink-0">
                                        {task.scheduled_time || task.status || "PENDING"}
                                      </span>
                                    </div>
                                  );
                                })}
                              </div>
                            </div>
                          )}

                          {/* Spontaneous actions ledger */}
                          {actionsList.length > 0 && (
                            <div className="space-y-2 pt-2 border-t border-white/5">
                              <div className="font-mono text-[9px] text-zinc-400 tracking-widest uppercase">Chronological Ambient Timeline:</div>
                              <div className="space-y-1.5 max-h-[140px] overflow-y-auto pr-1">
                                {actionsList.map((act: any, i: number) => (
                                  <div key={i} className="p-2 rounded bg-black/40 border border-white/5 flex items-center justify-between text-xs font-sans text-zinc-300">
                                    <span className="truncate pr-2">
                                      {act.action || act.raw_statement || act.title || (typeof act.action_type === "string" ? act.action_type.replace(/_/g, " ") : "Action")}
                                    </span>
                                    <span className="font-mono text-[9px] text-emerald-400 shrink-0">
                                      {act.time || "VERIFIED"}
                                    </span>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}
                        </div>
                      )}

                      {/* TAB 6: UPCOMING TASKS VIEWER */}
                      {template === "UPCOMING_TASKS_VIEWER" && (
                        <div className="space-y-4">
                          <div className="flex items-center justify-between text-xs font-mono text-zinc-400 pb-2 border-b border-white/5">
                            <span>MONITORED ROUTINES ({tasksList.length})</span>
                            <span className="text-amber-300">INTERACTIVE CHECKS</span>
                          </div>

                          {tasksList.length > 0 ? (
                            <div className="space-y-2 max-h-[300px] overflow-y-auto pr-1">
                              {tasksList.map((task: any, i: number) => {
                                const isComp = task.status === "completed";
                                return (
                                  <div key={i} className="p-3 rounded-lg bg-black/40 border border-white/5 flex items-center justify-between gap-3">
                                    <div className="flex items-center gap-3 truncate flex-1">
                                      <button
                                        onClick={() => handleToggleRoutine(task.id, task.title)}
                                        className={`w-5 h-5 rounded flex items-center justify-center font-mono text-xs border transition-colors ${
                                          isComp ? "bg-emerald-500 border-emerald-400 text-black font-bold" : "border-white/30 hover:border-emerald-400"
                                        }`}
                                      >
                                        {isComp ? "✓" : ""}
                                      </button>
                                      <div className="truncate min-w-0">
                                        <div className={`text-sm font-sans truncate ${isComp ? "line-through text-zinc-500" : "text-zinc-100"}`}>
                                          {task.title || task.headline}
                                        </div>
                                        <div className="text-[10px] font-mono text-zinc-400">
                                          Domain: {task.domain || "routine"} • Recurrence: {task.recurrence || "daily"}
                                        </div>
                                      </div>
                                    </div>

                                    <span className="font-mono text-[10px] text-amber-400 uppercase font-bold shrink-0">
                                      {task.scheduled_time || task.status || "PENDING"}
                                    </span>
                                  </div>
                                );
                              })}
                            </div>
                          ) : (
                            <div className="text-center py-8 text-zinc-500 font-mono text-sm">
                              No upcoming routine tasks scheduled.
                            </div>
                          )}
                        </div>
                      )}

                      {/* TAB 7: SESSION DOSSIER VIEWER */}
                      {template === "SESSION_DOSSIER_VIEWER" && (
                        <div className="space-y-4">
                          <div className="p-4 rounded-xl bg-black/40 border border-white/5 space-y-2">
                            <div className="flex items-center justify-between">
                              <span className="text-xs font-mono text-cyan-300 uppercase tracking-widest font-bold">
                                📍 {sessionLocationName}
                              </span>
                              <div className="flex items-center gap-2">
                                <span className={`font-mono text-[9px] px-2 py-0.5 rounded uppercase font-bold ${
                                  sessionStatus === "active" ? "bg-emerald-950/80 text-emerald-300 border border-emerald-500/30" : "bg-zinc-800 text-zinc-400"
                                }`}>
                                  {sessionStatus}
                                </span>
                                {sessionStatus === "active" && sessionId && (
                                  <button
                                    onClick={() => handleConcludeSession(sessionId)}
                                    className="px-2.5 py-0.5 rounded bg-amber-950/70 hover:bg-amber-900 border border-amber-500/40 text-amber-300 font-mono text-[9px] uppercase tracking-wider transition-colors"
                                  >
                                    🏁 Conclude
                                  </button>
                                )}
                              </div>
                            </div>

                            {synthesis && (
                              <div className="text-xs font-sans text-zinc-300 leading-relaxed pt-1">
                                {synthesis}
                              </div>
                            )}
                          </div>

                          {/* Key discussion points */}
                          {bullets.length > 0 && (
                            <div className="space-y-1.5">
                              <div className="font-mono text-[9px] text-zinc-400 tracking-widest uppercase">Discussion Points:</div>
                              <ul className="space-y-1">
                                {bullets.map((pt: string, i: number) => (
                                  <li key={i} className="text-xs font-sans text-zinc-300 flex items-start gap-2">
                                    <span className="text-cyan-400">•</span>
                                    <span>{pt}</span>
                                  </li>
                                ))}
                              </ul>
                            </div>
                          )}

                          {/* Linked micro-events */}
                          {linkedEvents.length > 0 && (
                            <div className="space-y-2 pt-2 border-t border-white/5">
                              <div className="font-mono text-[9px] text-zinc-400 tracking-widest uppercase">Linked Micro-Events:</div>
                              <div className="space-y-1.5 max-h-[140px] overflow-y-auto pr-1">
                                {linkedEvents.map((evt: any, i: number) => (
                                  <div key={i} className="p-2 rounded bg-black/40 border border-white/5 flex items-center justify-between text-xs">
                                    <span className="text-zinc-200 truncate pr-2">
                                      {evt.headline || evt.record_id}
                                    </span>
                                    <span className="font-mono text-[8px] text-cyan-400 uppercase shrink-0">
                                      {evt.event_type}
                                    </span>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}
                          {!synthesis && bullets.length === 0 && linkedEvents.length === 0 && (
                            <div className="text-center py-8 text-zinc-500 font-mono text-sm">
                              No macro session intelligence recorded yet.
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Alexa Voice Speech Output Footer */}
                  <div className="mt-6 pt-4 border-t border-white/5 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
                    <div className="flex items-center gap-3">
                      <div className="w-9 h-9 rounded-full bg-cyan-500/20 border border-cyan-400/40 flex items-center justify-center text-cyan-300 shrink-0">
                        💬
                      </div>
                      <div>
                        <div className="font-mono text-[8px] text-zinc-400 tracking-widest uppercase">
                          Alexa Voice Output
                        </div>
                        <div className="font-sans text-xs text-zinc-200 italic max-w-lg">
                          "{spokenText}"
                        </div>
                      </div>
                    </div>

                    {/* Quick Alexa Prompts */}
                    <div className="flex flex-wrap gap-2">
                      <button
                        onClick={() =>
                          handleQuickPrompt(
                            "Alexa says: Yes, your clothes iron is verified unplugged and cold.",
                            "ACTION_VERIFIED_BADGE",
                            "unplug_clothes_iron"
                          )
                        }
                        className="px-3 py-1 rounded-full bg-zinc-800/80 hover:bg-zinc-700 text-zinc-300 font-mono text-[9px] tracking-wider transition-colors"
                      >
                        "Did I unplug iron?"
                      </button>
                      <button
                        onClick={() =>
                          handleQuickPrompt(
                            "Alexa says: Here is the briefing for AWS Bedrock AgentCore Runtime.",
                            "DEEP_BRIEFING_VIEWER",
                            "AgentCore"
                          )
                        }
                        className="px-3 py-1 rounded-full bg-zinc-800/80 hover:bg-zinc-700 text-zinc-300 font-mono text-[9px] tracking-wider transition-colors"
                      >
                        "What is AgentCore?"
                      </button>
                      <button
                        onClick={() =>
                          handleQuickPrompt(
                            "Alexa says: Here is your daily activity and routine recap.",
                            "DAILY_ACTIONS_RECAP"
                          )
                        }
                        className="px-3 py-1 rounded-full bg-zinc-800/80 hover:bg-zinc-700 text-zinc-300 font-mono text-[9px] tracking-wider transition-colors"
                      >
                        "Daily Recap"
                      </button>
                      <button
                        onClick={() =>
                          handleQuickPrompt(
                            "Alexa says: Displaying active bilateral social commitments.",
                            "SOCIAL_COMMITMENTS_CARD"
                          )
                        }
                        className="px-3 py-1 rounded-full bg-zinc-800/80 hover:bg-zinc-700 text-zinc-300 font-mono text-[9px] tracking-wider transition-colors"
                      >
                        "Commitments"
                      </button>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="text-center py-16 text-zinc-500 font-mono text-sm">
                  No preview card data available for this template.
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>,
    document.body
  );
}
