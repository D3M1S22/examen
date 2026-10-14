"use client";

import React, { useState, useEffect, useCallback, useMemo } from "react";
import { createPortal } from "react-dom";
import useSWR from "swr";
import {
  PlannedTask,
  VerifiedAction,
  SocialEntity,
  BriefingReport,
  DemoUser,
  EchoNotification,
} from "@/types/schemas";
import { speakAlexaReassurance, playAcousticVerificationTone } from "@/utils/audioEffects";
import { getApiBaseUrl } from "@/utils/api";

export interface EchoShowModalProps {
  isOpen: boolean;
  onClose: () => void;
  initialTab?: string;
  initialTemplate?: string;
  statusData?: any;
  routinesData?: { tasks: PlannedTask[] };
  actionsData?: { actions: VerifiedAction[] };
  socialData?: { contacts: SocialEntity[] };
  topicsData?: { topics: BriefingReport[] };
  currentUser?: DemoUser | null;
  onOpenLoginModal?: () => void;
  onLogout?: () => void;
  onDisconnectBee?: () => void;
  onToggleRoutine?: (task: PlannedTask) => void | Promise<void>;
  handleAddRoutine?: (
    title: string,
    domain: string,
    scheduled_time: string,
    recurrence?: string
  ) => Promise<void>;
  handleDeleteRoutine?: (taskId: string) => Promise<void>;
  handleAddAction?: (statement: string) => Promise<void>;
  handleEnrichContact?: (contactId: string) => Promise<void>;
  handleToggleCommitment?: (
    commitmentId: string,
    action: "fulfill" | "cancel"
  ) => Promise<void>;
  simText?: string;
  setSimText?: (text: string) => void;
  simRunning?: boolean;
  runSimulation?: () => Promise<void> | void;
  simResult?: any;
  echoNotification?: EchoNotification | null;
  onDismissNotification?: () => void;
  updatedTabs?: Record<string, number | boolean>;
  onClearTabBadge?: (tabId: string) => void;
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

// Specular Echo Show Tabs matching the Web UI tabs
export const ECHO_TABS = [
  { id: "overview", label: "OVERVIEW HUB", icon: "🌐" },
  { id: "peace", label: "PEACE OF MIND", icon: "🛡️" },
  { id: "routines", label: "DAILY ROUTINES", icon: "📋" },
  { id: "social", label: "SOCIAL ROLODEX", icon: "👥" },
  { id: "topics", label: "TOPIC DOSSIERS", icon: "📚" },
  { id: "simulator", label: "AMBIENT SIMULATOR", icon: "⚡" },
];

export function EchoShowModal({
  isOpen,
  onClose,
  initialTab,
  initialTemplate,
  statusData,
  routinesData,
  actionsData,
  socialData,
  topicsData,
  currentUser,
  onOpenLoginModal,
  onLogout,
  onDisconnectBee,
  onToggleRoutine,
  handleAddRoutine,
  handleDeleteRoutine,
  handleAddAction,
  handleEnrichContact,
  handleToggleCommitment,
  simText = "",
  setSimText,
  simRunning = false,
  runSimulation,
  simResult,
  echoNotification,
  onDismissNotification,
  updatedTabs,
  onClearTabBadge,
}: EchoShowModalProps) {
  const [mounted, setMounted] = useState(false);
  const [profileMenuOpen, setProfileMenuOpen] = useState(false);
  const profileMenuRef = React.useRef<HTMLDivElement>(null);
  const lastSpokenNotifId = React.useRef<string | null>(null);

  // Map legacy template names or initialTab to specular tabs
  const resolveInitialTab = useCallback(() => {
    if (initialTemplate) {
      if (initialTemplate === "ACTION_VERIFIED_BADGE") return "peace";
      if (["DAILY_ACTIONS_RECAP", "UPCOMING_TASKS_VIEWER"].includes(initialTemplate)) return "routines";
      if (["SOCIAL_PROFILE_CARD", "SOCIAL_COMMITMENTS_CARD"].includes(initialTemplate)) return "social";
      if (["DEEP_BRIEFING_VIEWER", "SESSION_DOSSIER_VIEWER"].includes(initialTemplate)) return "topics";
    }
    if (initialTab && ["overview", "peace", "routines", "social", "topics", "simulator"].includes(initialTab)) {
      return initialTab;
    }
    return "overview";
  }, [initialTab, initialTemplate]);

  const [activeTab, setActiveTab] = useState(resolveInitialTab);
  const [echoTime, setEchoTime] = useState("");
  const [feedbackMsg, setFeedbackMsg] = useState<string | null>(null);

  // Local fallback states for sub-views if not passed via props
  const [localSimText, setLocalSimText] = useState(simText || "I just unplugged the clothes iron from the wall outlet.");
  const [localSimRunning, setLocalSimRunning] = useState(false);
  const [localSimResult, setLocalSimResult] = useState<any>(simResult || null);
  const [selectedContactIndex, setSelectedContactIndex] = useState(0);
  const [selectedTopicIndex, setSelectedTopicIndex] = useState(0);
  const [quickRoutineTitle, setQuickRoutineTitle] = useState("");
  const [routineFilter, setRoutineFilter] = useState<"ALL" | "PENDING" | "COMPLETED">("ALL");

  useEffect(() => {
    setMounted(true);
  }, []);

  // Update active tab when props change or modal opens
  useEffect(() => {
    if (isOpen) {
      setActiveTab(resolveInitialTab());
    }
  }, [isOpen, resolveInitialTab]);

  // Audio tone and voice announcement on new notification arrival
  useEffect(() => {
    if (isOpen && echoNotification && lastSpokenNotifId.current !== echoNotification.id) {
      lastSpokenNotifId.current = echoNotification.id;
      playAcousticVerificationTone();
      speakAlexaReassurance(`Notification: ${echoNotification.title}. ${echoNotification.message}`);
    }
  }, [isOpen, echoNotification]);

  // Auto-dismiss notification modal after 8 seconds
  useEffect(() => {
    if (!isOpen || !echoNotification) return;
    const timer = setTimeout(() => {
      onDismissNotification?.();
    }, 8000);
    return () => clearTimeout(timer);
  }, [isOpen, echoNotification, onDismissNotification]);

  // Close profile menu on outside click
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (profileMenuRef.current && !profileMenuRef.current.contains(event.target as Node)) {
        setProfileMenuOpen(false);
      }
    }
    if (profileMenuOpen) {
      document.addEventListener("mousedown", handleClickOutside);
      return () => document.removeEventListener("mousedown", handleClickOutside);
    }
  }, [profileMenuOpen]);

  // SWR Fallbacks if data not passed as props
  const { data: swrStatus, mutate: mutateStatus } = useSWR(
    isOpen && !statusData ? "/api/status" : null,
    fetcher
  );
  const { data: swrRoutines, mutate: mutateRoutines } = useSWR<{ tasks: PlannedTask[] }>(
    isOpen && !routinesData ? "/api/routines" : null,
    fetcher
  );
  const { data: swrActions, mutate: mutateActions } = useSWR<{ actions: VerifiedAction[] }>(
    isOpen && !actionsData ? "/api/actions?limit=50" : null,
    fetcher
  );
  const { data: swrSocial, mutate: mutateSocial } = useSWR<{ contacts: SocialEntity[] }>(
    isOpen && !socialData ? "/api/contacts" : null,
    fetcher
  );
  const { data: swrTopics, mutate: mutateTopics } = useSWR<{ topics: BriefingReport[] }>(
    isOpen && !topicsData ? "/api/topics?limit=20" : null,
    fetcher
  );

  const effStatus = statusData || swrStatus;
  const effRoutines = routinesData || swrRoutines;
  const effActions = actionsData || swrActions;
  const effSocial = socialData || swrSocial;
  const effTopics = topicsData || swrTopics;

  const tasks = effRoutines?.tasks || [];
  const actions = effActions?.actions || [];
  const contacts = effSocial?.contacts || [];
  const topics = effTopics?.topics || [];

  const completedTasks = tasks.filter((t) => t.status === "completed").length;
  const pendingTasks = tasks.filter((t) => t.status !== "completed").length;

  const showFeedback = useCallback((msg: string) => {
    setFeedbackMsg(msg);
    setTimeout(() => setFeedbackMsg(null), 3000);
  }, []);

  // Echo System Clock and Keyboard Listener
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

  const beeDevice = effStatus?.telemetry?.bee_device;
  const isBeeConnected = !!currentUser?.bee_connected || !!beeDevice?.connected || beeDevice?.status === "STREAMING";

  // Handlers
  const handleTabSelect = (tabId: string) => {
    setActiveTab(tabId);
    if (onClearTabBadge) {
      onClearTabBadge(tabId);
    }
  };

  const handleToggleRoutineClick = async (task: PlannedTask) => {
    if (onToggleRoutine) {
      await onToggleRoutine(task);
    } else {
      try {
        const baseUrl = getApiBaseUrl();
        await fetch(`${baseUrl}/api/routines/${task.id}/toggle`, { method: "POST" });
        if (mutateRoutines) mutateRoutines();
        if (mutateStatus) mutateStatus();
      } catch (e) {
        console.error(e);
      }
    }
    const newStatus = task.status === "completed" ? "pending" : "completed";
    speakAlexaReassurance(`Routine '${task.title}' marked ${newStatus}.`);
    showFeedback(`Routine updated!`);
  };

  const handleCreateRoutineQuick = async (title: string, time: string = "09:00", domain: string = "routine") => {
    if (!title.trim()) return;
    try {
      if (handleAddRoutine) {
        await handleAddRoutine(title.trim(), domain, time, "daily");
      } else {
        const baseUrl = getApiBaseUrl();
        await fetch(`${baseUrl}/api/routines`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ title: title.trim(), domain, scheduled_time: time, recurrence: "daily" }),
        });
        if (mutateRoutines) mutateRoutines();
        if (mutateStatus) mutateStatus();
      }
      speakAlexaReassurance(`New routine '${title}' scheduled for ${time}.`);
      showFeedback(`Routine added!`);
      setQuickRoutineTitle("");
    } catch (e) {
      showFeedback("Failed to add routine.");
    }
  };

  const handleCorroborateActionQuick = async (statement: string) => {
    try {
      if (handleAddAction) {
        await handleAddAction(statement);
      } else {
        const baseUrl = getApiBaseUrl();
        await fetch(`${baseUrl}/api/simulate`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ transcript_chunk: statement }),
        });
        if (mutateActions) mutateActions();
        if (mutateRoutines) mutateRoutines();
        if (mutateStatus) mutateStatus();
      }
      speakAlexaReassurance(`Action corroborated: "${statement}"`);
      showFeedback("Action corroborated into acoustic ledger!");
    } catch (e) {
      showFeedback("Failed to corroborate action.");
    }
  };

  const handleEnrichContactClick = async (contactId: string, name?: string) => {
    try {
      showFeedback(`Enriching ${name || "contact"}...`);
      if (handleEnrichContact) {
        await handleEnrichContact(contactId);
      } else {
        const baseUrl = getApiBaseUrl();
        await fetch(`${baseUrl}/api/contacts/${encodeURIComponent(contactId)}/enrich`, {
          method: "POST",
        });
        if (mutateSocial) mutateSocial();
        if (mutateStatus) mutateStatus();
      }
      speakAlexaReassurance(`Executive AI web profile refreshed for ${name || "contact"}.`);
      showFeedback("Contact profile enriched!");
    } catch (e) {
      showFeedback("Enrichment failed.");
    }
  };

  const handleToggleCommitmentClick = async (commitmentId: string, action: "fulfill" | "cancel") => {
    try {
      if (handleToggleCommitment) {
        await handleToggleCommitment(commitmentId, action);
      } else {
        const baseUrl = getApiBaseUrl();
        await fetch(`${baseUrl}/api/commitments/${encodeURIComponent(commitmentId)}/${action}`, {
          method: "POST",
        });
        if (mutateSocial) mutateSocial();
        if (mutateStatus) mutateStatus();
      }
      speakAlexaReassurance(`Commitment marked ${action === "fulfill" ? "fulfilled" : "cancelled"}.`);
      showFeedback(`Commitment updated!`);
    } catch (e) {
      showFeedback("Failed to update commitment.");
    }
  };

  const handleRunSimulationClick = async () => {
    const textToSim = simText || localSimText;
    if (!textToSim.trim()) return;

    if (runSimulation) {
      await runSimulation();
    } else {
      setLocalSimRunning(true);
      try {
        const baseUrl = getApiBaseUrl();
        const res = await fetch(`${baseUrl}/api/simulate`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ transcript_chunk: textToSim }),
        });
        const data = await res.json();
        setLocalSimResult(data);
        if (mutateActions) mutateActions();
        if (mutateRoutines) mutateRoutines();
        if (mutateSocial) mutateSocial();
        if (mutateTopics) mutateTopics();
        if (mutateStatus) mutateStatus();
        speakAlexaReassurance("Simulation pipeline executed successfully across ambient channels.");
        showFeedback("Simulation completed!");
      } catch (e) {
        showFeedback("Simulation failed.");
      } finally {
        setLocalSimRunning(false);
      }
    }
  };

  const selectedContact = contacts[selectedContactIndex] || contacts[0] || null;
  const selectedTopic = topics[selectedTopicIndex] || topics[0] || null;
  const latestAction = actions[0] || null;

  return createPortal(
    <div
      className="fixed inset-0 z-[9999] overflow-y-auto bg-black/90 backdrop-blur-md flex items-center justify-center p-2 sm:p-4 md:p-6"
      onClick={onClose}
      aria-modal="true"
      role="dialog"
    >
      <div
        className="relative w-full max-w-5xl my-auto animate-in fade-in zoom-in-95 duration-150"
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
              <span className="font-mono text-[10px] text-emerald-400 tracking-wider bg-emerald-950/80 border border-emerald-500/30 px-2 py-0.5 rounded animate-in fade-in">
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
        <div className="bg-[#101216] border-4 border-[#242833] rounded-3xl p-3 sm:p-5 md:p-6 shadow-[0_25px_60px_-15px_rgba(0,0,0,0.95)] relative">
          {/* Echo Camera Notch */}
          <div className="absolute top-2 left-1/2 -translate-x-1/2 flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-[#0a0b0d] border border-white/10"></span>
            <span className="w-1.5 h-1.5 rounded-full bg-red-900/30"></span>
          </div>

          {/* Glass Display Screen */}
          <div className="bg-[#08090b] border border-white/10 rounded-2xl overflow-hidden min-h-[580px] flex flex-col relative text-zinc-100">
            {/* Multimodal Modal Notification on Echo Show */}
            {echoNotification && (
              <div className="absolute inset-4 z-40 rounded-2xl bg-[#0d121d]/95 backdrop-blur-2xl border-2 border-cyan-400/80 shadow-[0_0_60px_rgba(6,182,212,0.6)] p-6 flex flex-col justify-between animate-in zoom-in-95 duration-200">
                <div className="flex items-center justify-between pb-3 border-b border-white/10">
                  <div className="flex items-center gap-2">
                    <span className="w-2.5 h-2.5 rounded-full bg-cyan-400 animate-ping" />
                    <span className="font-mono text-[10px] text-cyan-300 tracking-[0.2em] uppercase font-bold">
                      ⚡ ALEXA+ AMBIENT INTELLIGENCE NOTIFICATION // {echoNotification.category.toUpperCase()}
                    </span>
                  </div>
                  {onDismissNotification && (
                    <button
                      onClick={onDismissNotification}
                      className="text-zinc-400 hover:text-white font-mono text-sm px-2 py-0.5 rounded hover:bg-white/10 cursor-pointer"
                    >
                      ✕
                    </button>
                  )}
                </div>

                <div className="my-auto py-4 space-y-3">
                  <h3 className="font-serif text-2xl sm:text-3xl text-white font-bold">
                    {echoNotification.title}
                  </h3>
                  <div className="p-4 rounded-xl bg-black/60 border border-cyan-500/30 text-zinc-200 font-sans text-sm sm:text-base leading-relaxed italic">
                    "{echoNotification.message}"
                  </div>
                  <div className="flex items-center justify-between font-mono text-[10px] text-zinc-400">
                    <span>TIME: {echoNotification.timestamp}</span>
                    <span className="text-cyan-400">STATUS: PROCESSED BY BEDROCK AGENTCORE</span>
                  </div>
                </div>

                <div className="flex items-center justify-end gap-3 pt-3 border-t border-white/10">
                  {onDismissNotification && (
                    <button
                      onClick={onDismissNotification}
                      className="px-4 py-2 rounded-xl bg-zinc-800 hover:bg-zinc-700 text-zinc-300 font-mono text-xs uppercase tracking-wider transition-colors cursor-pointer"
                    >
                      Dismiss
                    </button>
                  )}
                  {echoNotification.targetTab && (
                    <button
                      onClick={() => {
                        const targetTabId = echoNotification.targetTab!;
                        const targetTabObj = ECHO_TABS.find((t) => t.id === targetTabId);
                        handleTabSelect(targetTabId);
                        if (onDismissNotification) onDismissNotification();
                        speakAlexaReassurance(`Switching to ${targetTabObj?.label || targetTabId}.`);
                      }}
                      className="px-5 py-2 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-black font-mono text-xs uppercase tracking-wider font-bold shadow-lg shadow-cyan-500/30 transition-all flex items-center gap-2 cursor-pointer"
                    >
                      <span>Inspect in Echo</span>
                      <span>→</span>
                    </button>
                  )}
                </div>
              </div>
            )}

            {/* Echo System Bar with Login & Profile Integration */}
            <div className="bg-black/70 px-4 sm:px-6 py-2.5 flex items-center justify-between border-b border-white/10 gap-2">
              <div className="flex items-center gap-3">
                <div className="font-mono text-sm sm:text-base font-bold text-white tracking-wider">
                  {echoTime || "12:00"}
                </div>
                <div className="hidden sm:flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-cyan-950/60 border border-cyan-500/40 text-cyan-300 font-mono text-[9px] tracking-widest uppercase">
                  <span className="w-1.5 h-1.5 rounded-full bg-cyan-400"></span>
                  <span>Alexa+ Ambient Ext-App</span>
                </div>
              </div>

              {/* User Profile & Login on Echo Show */}
              <div className="relative flex items-center gap-2 sm:gap-3" ref={profileMenuRef}>
                {currentUser ? (
                  <>
                    <button
                      onClick={() => setProfileMenuOpen((prev) => !prev)}
                      className="flex items-center gap-2 px-2.5 py-1 rounded-xl bg-zinc-900/90 hover:bg-zinc-800 border border-cyan-500/40 text-white transition-all shadow-sm cursor-pointer"
                      title="Manage Echo Show Profile & Bee Device"
                    >
                      <div className="w-5 h-5 rounded-full bg-cyan-500/20 border border-cyan-400 text-cyan-300 font-mono text-[9px] font-bold flex items-center justify-center">
                        {currentUser.handle ? currentUser.handle.charAt(0).toUpperCase() : "U"}
                      </div>
                      <div className="text-left text-xs font-sans font-medium text-white max-w-[110px] truncate hidden xs:block">
                        {currentUser.handle}
                      </div>
                      <div className="flex items-center gap-1 font-mono text-[8px] text-zinc-400">
                        <span
                          className={`w-1.5 h-1.5 rounded-full ${
                            currentUser.bee_connected || isBeeConnected ? "bg-emerald-400" : "bg-zinc-500"
                          }`}
                        />
                        <span className="hidden md:inline">
                          {currentUser.bee_connected || isBeeConnected ? "BEE LINKED" : "DEMO USER"}
                        </span>
                      </div>
                      <span className={`text-[10px] text-zinc-400 transition-transform ${profileMenuOpen ? "rotate-180" : ""}`}>
                        ▾
                      </span>
                    </button>

                    {/* Echo Touch Profile Menu Dropdown */}
                    {profileMenuOpen && (
                      <div className="absolute right-0 top-full mt-2 w-72 rounded-2xl bg-[#0d121d]/95 backdrop-blur-2xl border border-cyan-500/40 shadow-[0_20px_50px_rgba(0,0,0,0.95)] p-4 z-50 text-left space-y-3 animate-in fade-in zoom-in-95 duration-150">
                        <div className="pb-2.5 border-b border-white/10">
                          <div className="flex items-center justify-between">
                            <span className="font-mono text-[9px] uppercase tracking-widest text-zinc-400 font-semibold">
                              ECHO SHOW SESSION
                            </span>
                            <span className="font-mono text-[8px] px-1.5 py-0.5 rounded bg-cyan-950 text-cyan-300 border border-cyan-500/30 font-bold uppercase">
                              GDPR ART. 25
                            </span>
                          </div>
                          <div className="font-sans text-sm font-semibold text-white mt-1">
                            {currentUser.handle}
                          </div>
                          <div className="font-mono text-[9px] text-zinc-400 flex items-center gap-1 mt-0.5">
                            <span>ID:</span>
                            <span className="text-cyan-300 truncate">{currentUser.user_id}</span>
                          </div>
                        </div>

                        {/* Bee Wearable Status & Pairing */}
                        <div className="p-2.5 rounded-xl bg-black/60 border border-white/10 space-y-2">
                          <div className="flex items-center justify-between">
                            <span className="text-xs font-sans text-white font-medium flex items-center gap-1.5">
                              <span>🐝</span>
                              <span>Bee Wearable AI</span>
                            </span>
                            <span
                              className={`font-mono text-[8px] px-2 py-0.5 rounded-full uppercase font-bold ${
                                isBeeConnected
                                  ? "bg-emerald-950 text-emerald-300 border border-emerald-500/40"
                                  : "bg-zinc-800 text-zinc-400"
                              }`}
                            >
                              {isBeeConnected ? "LINKED" : "STANDBY"}
                            </span>
                          </div>
                          {isBeeConnected && onDisconnectBee ? (
                            <button
                              onClick={() => {
                                onDisconnectBee();
                                setProfileMenuOpen(false);
                              }}
                              className="w-full py-1.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-300 hover:text-white font-mono text-[10px] uppercase tracking-wider transition-colors border border-white/10 text-center cursor-pointer"
                            >
                              Disconnect Bee Device
                            </button>
                          ) : (
                            onOpenLoginModal && (
                              <button
                                onClick={() => {
                                  onOpenLoginModal();
                                  setProfileMenuOpen(false);
                                }}
                                className="w-full py-1.5 rounded-lg bg-cyan-950/80 hover:bg-cyan-900 text-cyan-300 border border-cyan-500/40 font-mono text-[10px] uppercase tracking-wider transition-colors text-center cursor-pointer"
                              >
                                Connect Bee Device →
                              </button>
                            )
                          )}
                        </div>

                        {/* Profile switch and Logout actions */}
                        <div className="space-y-1.5 pt-1">
                          {onOpenLoginModal && (
                            <button
                              onClick={() => {
                                onOpenLoginModal();
                                setProfileMenuOpen(false);
                              }}
                              className="w-full py-1.5 px-2.5 rounded-lg hover:bg-white/5 text-zinc-200 hover:text-white text-xs font-sans flex items-center justify-between transition-colors cursor-pointer"
                            >
                              <span>Switch / Manage Profile</span>
                              <span className="text-zinc-500 font-mono text-xs">→</span>
                            </button>
                          )}
                          {onLogout && (
                            <button
                              onClick={() => {
                                onLogout();
                                setProfileMenuOpen(false);
                              }}
                              className="w-full py-1.5 px-2.5 rounded-lg hover:bg-red-950/40 text-red-400 hover:text-red-300 text-xs font-sans flex items-center justify-between transition-colors border border-red-500/20 cursor-pointer"
                            >
                              <span>Sign Out</span>
                              <span>🚪</span>
                            </button>
                          )}
                        </div>
                      </div>
                    )}
                  </>
                ) : (
                  <button
                    onClick={onOpenLoginModal}
                    className="flex items-center gap-1.5 px-2.5 py-1 rounded-xl bg-cyan-950/70 hover:bg-cyan-900 border border-cyan-500/40 text-cyan-300 font-mono text-[10px] tracking-wider transition-colors shadow-sm cursor-pointer"
                    title="Sign In to Echo Show"
                  >
                    <span>👤</span>
                    <span>Sign In</span>
                  </button>
                )}

                <div className="flex items-center gap-2 text-zinc-400 text-[10px] sm:text-xs font-mono">
                  <span className="hidden sm:inline">📶 5G MESH</span>
                  <span className="hidden sm:inline opacity-40">•</span>
                  <span className={isBeeConnected ? "text-emerald-400 font-semibold" : "text-zinc-500"}>
                    {isBeeConnected ? "🐝 BEE LINKED" : "BEE STANDBY"}
                  </span>
                </div>
              </div>
            </div>

            {/* Specular Tabs Bar matching Web UI sections */}
            <div className="bg-[#121419] px-3 sm:px-4 py-2 border-b border-white/5 flex items-center gap-1.5 sm:gap-2 overflow-x-auto hide-scrollbar">
              {ECHO_TABS.map((tab) => {
                const isSelected = activeTab === tab.id;
                const rawVal = updatedTabs?.[tab.id];
                const count = typeof rawVal === "number" ? rawVal : rawVal ? 1 : 0;
                const hasUpdate = count > 0 && !isSelected;
                return (
                  <button
                    key={tab.id}
                    onClick={() => handleTabSelect(tab.id)}
                    className={`relative px-3 py-1.5 rounded-lg font-mono text-[10px] sm:text-[11px] tracking-wider whitespace-nowrap transition-all uppercase flex items-center gap-1.5 cursor-pointer ${
                      isSelected
                        ? "bg-cyan-500 text-black font-bold shadow-md shadow-cyan-500/20"
                        : "text-zinc-400 hover:text-white hover:bg-white/5"
                    }`}
                  >
                    <span>{tab.icon}</span>
                    <span>{tab.label}</span>
                    {hasUpdate && (
                      count > 1 ? (
                        <span
                          className="relative inline-flex items-center justify-center px-1.5 py-0.2 min-w-[16px] h-4 text-[9px] font-mono font-bold leading-none text-black bg-cyan-400 rounded-full shadow-[0_0_8px_rgba(6,182,212,0.9)]"
                          title={`${count} updates`}
                        >
                          {count}
                        </span>
                      ) : (
                        <span className="relative flex h-2 w-2 ml-0.5 shrink-0" title="New update received">
                          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-75"></span>
                          <span className="relative inline-flex rounded-full h-2 w-2 bg-cyan-400 shadow-[0_0_8px_rgba(6,182,212,0.9)]"></span>
                        </span>
                      )
                    )}
                  </button>
                );
              })}
            </div>

            {/* Main Specular Touch Canvas */}
            <div className="p-4 sm:p-6 md:p-8 flex-1 flex flex-col justify-between overflow-y-auto">
              {/* TAB 1: OVERVIEW HUB */}
              {activeTab === "overview" && (
                <div className="space-y-6 flex-1 flex flex-col justify-between animate-in fade-in duration-150">
                  <div>
                    {/* Top Status Banner */}
                    <div className="bg-gradient-to-r from-emerald-950/40 via-black/40 to-cyan-950/30 border border-emerald-500/30 rounded-2xl p-4 sm:p-5 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
                      <div className="flex items-center gap-3.5">
                        <div className="w-10 h-10 rounded-full border-4 border-emerald-400 flex items-center justify-center shrink-0 shadow-lg shadow-emerald-950/60">
                          <div className="w-3 h-3 rounded-full bg-emerald-400 animate-ping"></div>
                        </div>
                        <div>
                          <div className="font-mono text-[9px] text-emerald-400 tracking-[0.2em] uppercase font-bold">
                            DOMESTIC POSTURE // ALL CLEAR
                          </div>
                          <div className="font-serif text-xl sm:text-2xl text-white font-bold leading-tight">
                            All Anchors Calibrated & Synchronized
                          </div>
                        </div>
                      </div>

                      <div className="flex flex-wrap gap-2 text-[10px] font-mono uppercase">
                        <button
                          onClick={() => handleTabSelect("peace")}
                          className="px-2.5 py-1 rounded-lg bg-emerald-950/60 border border-emerald-500/30 text-emerald-300 hover:bg-emerald-900 transition-colors"
                        >
                          🛡️ {actions.length} Verified Anchors
                        </button>
                        <button
                          onClick={() => handleTabSelect("routines")}
                          className="px-2.5 py-1 rounded-lg bg-amber-950/60 border border-amber-500/30 text-amber-300 hover:bg-amber-900 transition-colors"
                        >
                          📋 {pendingTasks} Pending Checks
                        </button>
                        <button
                          onClick={() => handleTabSelect("social")}
                          className="px-2.5 py-1 rounded-lg bg-cyan-950/60 border border-cyan-500/30 text-cyan-300 hover:bg-cyan-900 transition-colors"
                        >
                          👥 {contacts.length} Social Contacts
                        </button>
                        <button
                          onClick={() => handleTabSelect("topics")}
                          className="px-2.5 py-1 rounded-lg bg-purple-950/60 border border-purple-500/30 text-purple-300 hover:bg-purple-900 transition-colors"
                        >
                          📚 {topics.length} Dossiers
                        </button>
                      </div>
                    </div>

                    {/* 4 Multimodal Echo Touch Cards Grid */}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
                      {/* Peace of Mind Card */}
                      <div className="p-4 rounded-xl bg-[#12141a] border border-white/10 hover:border-emerald-500/40 transition-colors space-y-2.5">
                        <div className="flex items-center justify-between">
                          <span className="font-mono text-[9px] text-emerald-400 tracking-wider uppercase font-bold flex items-center gap-1.5">
                            <span className="w-2 h-2 rounded-full bg-emerald-400" />
                            PEACE OF MIND ANCHOR
                          </span>
                          <span className="font-mono text-[9px] text-zinc-500">
                            {latestAction?.elapsed_time_human || "RECENT"}
                          </span>
                        </div>
                        <h4 className="font-serif text-lg text-white font-medium truncate">
                          {latestAction?.action_type?.replace(/_/g, " ").toUpperCase() || "UNPLUG CLOTHES IRON"}
                        </h4>
                        <p className="text-xs text-zinc-300 font-sans italic line-clamp-2 bg-black/40 p-2 rounded border border-white/5">
                          "{latestAction?.raw_statement || "Ho appena staccato il ferro da stiro prima di uscire."}"
                        </p>
                        <div className="flex items-center justify-between pt-1">
                          <span className="font-mono text-[9px] text-emerald-400">
                            {Math.round((latestAction?.confidence || 0.98) * 100)}% CONFIDENCE
                          </span>
                          <button
                            onClick={() => handleTabSelect("peace")}
                            className="text-xs font-mono text-cyan-400 hover:underline flex items-center gap-1"
                          >
                            <span>Inspect Peace Ledger</span>
                            <span>→</span>
                          </button>
                        </div>
                      </div>

                      {/* Daily Routines Card */}
                      <div className="p-4 rounded-xl bg-[#12141a] border border-white/10 hover:border-amber-500/40 transition-colors space-y-2.5">
                        <div className="flex items-center justify-between">
                          <span className="font-mono text-[9px] text-amber-400 tracking-wider uppercase font-bold flex items-center gap-1.5">
                            <span className="w-2 h-2 rounded-full bg-amber-400" />
                            DAILY ROUTINES CHECKLIST
                          </span>
                          <span className="font-mono text-[9px] text-zinc-400">
                            {completedTasks} / {tasks.length} DONE
                          </span>
                        </div>
                        {tasks.length > 0 ? (
                          <div className="space-y-1.5">
                            {tasks.slice(0, 2).map((task) => (
                              <div
                                key={task.id}
                                className="flex items-center justify-between p-2 rounded bg-black/40 border border-white/5 text-xs"
                              >
                                <div className="flex items-center gap-2 truncate">
                                  <button
                                    onClick={() => handleToggleRoutineClick(task)}
                                    className={`w-4 h-4 rounded flex items-center justify-center font-mono text-[10px] border transition-colors ${
                                      task.status === "completed"
                                        ? "bg-emerald-500 border-emerald-400 text-black font-bold"
                                        : "border-white/30 hover:border-white"
                                    }`}
                                  >
                                    {task.status === "completed" ? "✓" : ""}
                                  </button>
                                  <span className={`truncate ${task.status === "completed" ? "line-through text-zinc-500" : "text-zinc-200"}`}>
                                    {task.title}
                                  </span>
                                </div>
                                <span className="font-mono text-[9px] text-amber-400 shrink-0">
                                  {task.scheduled_time || "SCHEDULED"}
                                </span>
                              </div>
                            ))}
                          </div>
                        ) : (
                          <div className="text-zinc-500 font-mono text-xs py-3 text-center">
                            No monitored routines active.
                          </div>
                        )}
                        <div className="flex items-center justify-end pt-1">
                          <button
                            onClick={() => handleTabSelect("routines")}
                            className="text-xs font-mono text-amber-400 hover:underline flex items-center gap-1"
                          >
                            <span>View All Routines</span>
                            <span>→</span>
                          </button>
                        </div>
                      </div>

                      {/* Social Rolodex Card */}
                      <div className="p-4 rounded-xl bg-[#12141a] border border-white/10 hover:border-cyan-500/40 transition-colors space-y-2.5">
                        <div className="flex items-center justify-between">
                          <span className="font-mono text-[9px] text-cyan-400 tracking-wider uppercase font-bold flex items-center gap-1.5">
                            <span className="w-2 h-2 rounded-full bg-cyan-400" />
                            SOCIAL ROLODEX PROFILE
                          </span>
                          <span className="font-mono text-[9px] text-zinc-500">
                            {contacts.length} CONTACTS
                          </span>
                        </div>
                        {selectedContact ? (
                          <div className="space-y-1.5">
                            <div className="flex items-center gap-2">
                              <div className="w-7 h-7 rounded-full bg-cyan-500/20 border border-cyan-400 text-cyan-300 font-mono text-xs font-bold flex items-center justify-center">
                                {selectedContact.name ? selectedContact.name.charAt(0).toUpperCase() : "C"}
                              </div>
                              <div>
                                <h4 className="font-serif text-base text-white font-medium leading-tight">
                                  {selectedContact.name}
                                </h4>
                                <div className="text-[10px] font-mono text-zinc-400 truncate">
                                  {selectedContact.company_or_role || selectedContact.web_profile?.headline || "Executive Contact"}
                                </div>
                              </div>
                            </div>
                            <div className="text-xs text-zinc-300 font-sans line-clamp-1">
                              {selectedContact.web_profile?.bio_summary || "Autonomous web profile indexed."}
                            </div>
                          </div>
                        ) : (
                          <div className="text-zinc-500 font-mono text-xs py-3 text-center">
                            No contacts indexed yet.
                          </div>
                        )}
                        <div className="flex items-center justify-end pt-1">
                          <button
                            onClick={() => handleTabSelect("social")}
                            className="text-xs font-mono text-cyan-400 hover:underline flex items-center gap-1"
                          >
                            <span>Open Social Rolodex</span>
                            <span>→</span>
                          </button>
                        </div>
                      </div>

                      {/* Topic Dossiers Card */}
                      <div className="p-4 rounded-xl bg-[#12141a] border border-white/10 hover:border-purple-500/40 transition-colors space-y-2.5">
                        <div className="flex items-center justify-between">
                          <span className="font-mono text-[9px] text-purple-400 tracking-wider uppercase font-bold flex items-center gap-1.5">
                            <span className="w-2 h-2 rounded-full bg-purple-400" />
                            SYNTHESIZED TOPIC DOSSIER
                          </span>
                          <span className="font-mono text-[9px] text-zinc-500">
                            {topics.length} COMPILED
                          </span>
                        </div>
                        {selectedTopic ? (
                          <div className="space-y-1.5">
                            <h4 className="font-serif text-base text-white font-medium truncate">
                              {selectedTopic.topic_title}
                            </h4>
                            <p className="text-xs text-zinc-300 font-sans line-clamp-2 bg-black/40 p-2 rounded border border-white/5">
                              {selectedTopic.explanatory_synthesis || selectedTopic.executive_summary?.[0] || "Synthesized analysis recorded."}
                            </p>
                          </div>
                        ) : (
                          <div className="text-zinc-500 font-mono text-xs py-3 text-center">
                            No technical briefings recorded yet.
                          </div>
                        )}
                        <div className="flex items-center justify-end pt-1">
                          <button
                            onClick={() => handleTabSelect("topics")}
                            className="text-xs font-mono text-purple-400 hover:underline flex items-center gap-1"
                          >
                            <span>Read Deep Briefing</span>
                            <span>→</span>
                          </button>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Alexa Voice Speech Output Footer */}
                  <div className="mt-4 pt-3 border-t border-white/10 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
                    <div className="flex items-center gap-2.5">
                      <div className="w-8 h-8 rounded-full bg-cyan-500/20 border border-cyan-400/40 flex items-center justify-center text-cyan-300 shrink-0">
                        💬
                      </div>
                      <div>
                        <div className="font-mono text-[8px] text-zinc-400 tracking-widest uppercase">
                          Alexa Voice Output
                        </div>
                        <div className="font-sans text-xs text-zinc-200 italic max-w-xl truncate">
                          "EXAMEN Status: Domestic posture is all clear. {actions.length} verified actions, {completedTasks}/{tasks.length} routines completed."
                        </div>
                      </div>
                    </div>

                    <div className="flex flex-wrap gap-1.5">
                      <button
                        onClick={() => {
                          speakAlexaReassurance("Yes, your clothes iron is confirmed unplugged and cold.");
                          handleTabSelect("peace");
                        }}
                        className="px-2.5 py-1 rounded-full bg-zinc-800/80 hover:bg-zinc-700 text-zinc-300 font-mono text-[9px] tracking-wider transition-colors"
                      >
                        "Did I unplug iron?"
                      </button>
                      <button
                        onClick={() => {
                          speakAlexaReassurance(`You have ${pendingTasks} pending routines remaining today.`);
                          handleTabSelect("routines");
                        }}
                        className="px-2.5 py-1 rounded-full bg-zinc-800/80 hover:bg-zinc-700 text-zinc-300 font-mono text-[9px] tracking-wider transition-colors"
                      >
                        "Routine Check"
                      </button>
                      <button
                        onClick={() => {
                          speakAlexaReassurance("Opening speech simulator on Echo Show.");
                          handleTabSelect("simulator");
                        }}
                        className="px-2.5 py-1 rounded-full bg-cyan-950/80 border border-cyan-500/40 text-cyan-300 font-mono text-[9px] tracking-wider transition-colors"
                      >
                        "Run Simulator"
                      </button>
                    </div>
                  </div>
                </div>
              )}

              {/* TAB 2: PEACE OF MIND */}
              {activeTab === "peace" && (
                <div className="space-y-4 flex-1 flex flex-col justify-between animate-in fade-in duration-150">
                  <div className="space-y-4">
                    {/* Primary Highlighted Verified Action Card */}
                    <div className="p-5 rounded-2xl bg-gradient-to-r from-emerald-950/40 via-black/60 to-black/80 border-2 border-emerald-500/50 space-y-3">
                      <div className="flex items-center justify-between">
                        <span className="flex items-center gap-2 font-mono text-xs font-bold tracking-wider text-emerald-400 uppercase">
                          <span className="w-2.5 h-2.5 rounded-full bg-emerald-400 animate-ping" />
                          ACOUSTICALLY VERIFIED ANCHOR // DOMESTIC SAFETY
                        </span>
                        <span className="font-mono text-xs text-zinc-400">
                          {latestAction?.elapsed_time_human || "just now"}
                        </span>
                      </div>

                      <div className="font-serif text-2xl sm:text-3xl text-white font-bold">
                        {latestAction?.action_type?.replace(/_/g, " ").toUpperCase() || "UNPLUG CLOTHES IRON"}
                      </div>

                      <div className="p-3.5 rounded-xl bg-black/60 border border-emerald-500/20 font-sans italic text-sm text-zinc-200">
                        "{latestAction?.raw_statement || "Ho appena staccato il ferro da stiro prima di uscire."}"
                      </div>

                      <div className="flex items-center justify-between pt-2 border-t border-white/10 text-xs font-mono">
                        <span className="text-zinc-400">ACOUSTIC CERTAINTY:</span>
                        <span className="text-emerald-400 font-bold">
                          {Math.round((latestAction?.confidence || 0.98) * 100)}% CONFIDENCE // GROUNDED
                        </span>
                      </div>
                    </div>

                    {/* Quick Domestic Reassurance Check Buttons */}
                    <div className="space-y-2">
                      <div className="font-mono text-[9px] text-zinc-400 tracking-widest uppercase">
                        Ask Alexa Peace Reassurance:
                      </div>
                      <div className="flex flex-wrap gap-2">
                        {[
                          { q: "Clothes Iron", statement: "I just unplugged the clothes iron from the wall outlet." },
                          { q: "Kitchen Stove", statement: "The gas stovetop burners are completely off and cold." },
                          { q: "Front Door Lock", statement: "I double locked the front deadbolt lock." },
                          { q: "Evening Medication", statement: "I just took my evening medication pills." },
                        ].map((item, i) => (
                          <button
                            key={i}
                            onClick={() => handleCorroborateActionQuick(item.statement)}
                            className="px-3.5 py-2 rounded-xl bg-black/50 hover:bg-emerald-950/60 border border-white/10 hover:border-emerald-500/40 text-zinc-200 font-mono text-xs tracking-wider transition-all flex items-center gap-2 cursor-pointer"
                          >
                            <span>🛡️</span>
                            <span>{item.q} Check</span>
                          </button>
                        ))}
                      </div>
                    </div>

                    {/* Recent Acoustic Ledger List */}
                    <div className="space-y-2 pt-2 border-t border-white/10">
                      <div className="font-mono text-[9px] text-zinc-400 tracking-widest uppercase">
                        Recent Verified Ledger Entries ({actions.length}):
                      </div>
                      <div className="space-y-1.5 max-h-[160px] overflow-y-auto pr-1">
                        {actions.map((act) => (
                          <div
                            key={act.id}
                            className="p-2.5 rounded-lg bg-black/40 border border-white/5 flex items-center justify-between text-xs font-sans gap-2"
                          >
                            <div className="truncate flex-1">
                              <span className="font-semibold text-white mr-2">
                                {act.action_type.replace(/_/g, " ").toUpperCase()}:
                              </span>
                              <span className="text-zinc-300 italic">"{act.raw_statement}"</span>
                            </div>
                            <span className="font-mono text-[9px] text-emerald-400 shrink-0">
                              {act.elapsed_time_human || "VERIFIED"}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>

                  <div className="pt-3 border-t border-white/10 flex items-center justify-between">
                    <span className="text-xs font-mono text-zinc-400">
                      Acoustic Sensor Mesh: <strong className="text-emerald-400">ONLINE</strong>
                    </span>
                    <button
                      onClick={() =>
                        speakAlexaReassurance(
                          `Alexa reassurance: ${latestAction?.action_type || "Clothes iron"} is verified completed with ${Math.round((latestAction?.confidence || 0.98) * 100)} percent certainty.`
                        )
                      }
                      className="px-4 py-1.5 rounded-full bg-emerald-500/20 hover:bg-emerald-500/30 border border-emerald-400/40 text-emerald-300 font-mono text-xs uppercase tracking-wider font-bold transition-colors"
                    >
                      🔊 Speak Acoustic Confirmation
                    </button>
                  </div>
                </div>
              )}

              {/* TAB 3: DAILY ROUTINES */}
              {activeTab === "routines" && (
                <div className="space-y-4 flex-1 flex flex-col justify-between animate-in fade-in duration-150">
                  <div className="space-y-4">
                    {/* 4 Summary Stats */}
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-center">
                      <div className="p-2.5 rounded-xl bg-black/40 border border-white/10">
                        <div className="font-mono text-xl font-bold text-white">{tasks.length}</div>
                        <div className="font-mono text-[8px] text-zinc-400 uppercase tracking-wider">PLANNED TOTAL</div>
                      </div>
                      <div className="p-2.5 rounded-xl bg-black/40 border border-white/10">
                        <div className="font-mono text-xl font-bold text-emerald-400">{completedTasks}</div>
                        <div className="font-mono text-[8px] text-zinc-400 uppercase tracking-wider">COMPLETED</div>
                      </div>
                      <div className="p-2.5 rounded-xl bg-black/40 border border-white/10">
                        <div className="font-mono text-xl font-bold text-amber-400">{pendingTasks}</div>
                        <div className="font-mono text-[8px] text-zinc-400 uppercase tracking-wider">PENDING</div>
                      </div>
                      <div className="p-2.5 rounded-xl bg-black/40 border border-white/10">
                        <div className="font-mono text-xl font-bold text-cyan-400">{actions.length}</div>
                        <div className="font-mono text-[8px] text-zinc-400 uppercase tracking-wider">SPONTANEOUS</div>
                      </div>
                    </div>

                    {/* Filter Pills */}
                    <div className="flex items-center gap-2 pb-1 border-b border-white/5">
                      {(["ALL", "PENDING", "COMPLETED"] as const).map((f) => (
                        <button
                          key={f}
                          onClick={() => setRoutineFilter(f)}
                          className={`px-3 py-1 rounded-lg font-mono text-[10px] uppercase tracking-wider transition-colors ${
                            routineFilter === f
                              ? "bg-amber-400 text-black font-bold"
                              : "bg-black/40 text-zinc-400 hover:text-white"
                          }`}
                        >
                          {f} ({f === "ALL" ? tasks.length : f === "PENDING" ? pendingTasks : completedTasks})
                        </button>
                      ))}
                    </div>

                    {/* Monitored Routines Checklist */}
                    <div className="space-y-2 max-h-[220px] overflow-y-auto pr-1">
                      {tasks
                        .filter((t) => {
                          if (routineFilter === "PENDING") return t.status !== "completed";
                          if (routineFilter === "COMPLETED") return t.status === "completed";
                          return true;
                        })
                        .map((task) => {
                          const isComp = task.status === "completed";
                          return (
                            <div
                              key={task.id}
                              className="p-3 rounded-xl bg-black/40 border border-white/10 flex items-center justify-between gap-3 hover:border-white/20 transition-colors"
                            >
                              <div className="flex items-center gap-3 truncate flex-1">
                                <button
                                  onClick={() => handleToggleRoutineClick(task)}
                                  className={`w-6 h-6 rounded-lg flex items-center justify-center font-mono text-xs border transition-colors shrink-0 ${
                                    isComp
                                      ? "bg-emerald-500 border-emerald-400 text-black font-bold"
                                      : "border-white/30 hover:border-emerald-400 text-transparent"
                                  }`}
                                  title="Toggle routine completion"
                                >
                                  ✓
                                </button>
                                <div className="truncate min-w-0">
                                  <div className={`text-sm font-sans truncate font-medium ${isComp ? "line-through text-zinc-500" : "text-zinc-100"}`}>
                                    {task.title}
                                  </div>
                                  <div className="text-[10px] font-mono text-zinc-400 flex items-center gap-2">
                                    <span className="uppercase text-cyan-400">{task.domain}</span>
                                    <span>•</span>
                                    <span>{task.scheduled_time || "DAILY"}</span>
                                  </div>
                                </div>
                              </div>

                              <div className="flex items-center gap-2 shrink-0">
                                <span
                                  className={`font-mono text-[9px] uppercase font-bold px-2 py-0.5 rounded ${
                                    isComp
                                      ? "bg-emerald-950 text-emerald-300 border border-emerald-500/30"
                                      : "bg-amber-950 text-amber-300 border border-amber-500/30"
                                  }`}
                                >
                                  {task.status}
                                </span>
                              </div>
                            </div>
                          );
                        })}
                    </div>

                    {/* Quick Add Routine Presets */}
                    <div className="pt-2 border-t border-white/10 flex flex-wrap items-center gap-2">
                      <span className="font-mono text-[9px] text-zinc-400 tracking-widest uppercase">Quick Add:</span>
                      {[
                        { title: "Turn off garden irrigation", time: "18:00" },
                        { title: "Evening vitamins & water", time: "21:00" },
                        { title: "Lock patio & garage doors", time: "22:30" },
                      ].map((preset, i) => (
                        <button
                          key={i}
                          onClick={() => handleCreateRoutineQuick(preset.title, preset.time)}
                          className="px-2.5 py-1 rounded-lg bg-zinc-800/80 hover:bg-zinc-700 text-zinc-300 font-mono text-[10px] transition-colors"
                        >
                          + {preset.title}
                        </button>
                      ))}
                    </div>
                  </div>

                  <div className="pt-3 border-t border-white/10 flex items-center justify-between">
                    <span className="text-xs font-mono text-zinc-400">
                      Echo Show Monitored Cadence: <strong className="text-amber-400">ACTIVE</strong>
                    </span>
                    <button
                      onClick={() =>
                        speakAlexaReassurance(
                          `Alexa routines update: You have completed ${completedTasks} of ${tasks.length} daily routines.`
                        )
                      }
                      className="px-4 py-1.5 rounded-full bg-amber-500/20 hover:bg-amber-500/30 border border-amber-400/40 text-amber-300 font-mono text-xs uppercase tracking-wider font-bold transition-colors"
                    >
                      🔊 Speak Daily Recap
                    </button>
                  </div>
                </div>
              )}

              {/* TAB 4: SOCIAL ROLODEX */}
              {activeTab === "social" && (
                <div className="space-y-4 flex-1 flex flex-col justify-between animate-in fade-in duration-150">
                  <div className="space-y-4">
                    {/* Contact Carousel Selector */}
                    {contacts.length > 0 && (
                      <div className="flex items-center gap-2 overflow-x-auto hide-scrollbar pb-1">
                        {contacts.map((c, idx) => (
                          <button
                            key={c.id || idx}
                            onClick={() => setSelectedContactIndex(idx)}
                            className={`px-3 py-1.5 rounded-xl font-mono text-xs whitespace-nowrap transition-all flex items-center gap-2 ${
                              selectedContactIndex === idx
                                ? "bg-cyan-500 text-black font-bold shadow-md"
                                : "bg-black/40 text-zinc-400 hover:text-white border border-white/10"
                            }`}
                          >
                            <span className="w-4 h-4 rounded-full bg-white/20 flex items-center justify-center text-[9px]">
                              {c.name ? c.name.charAt(0) : "C"}
                            </span>
                            <span>{c.name}</span>
                          </button>
                        ))}
                      </div>
                    )}

                    {selectedContact ? (
                      <div className="p-5 rounded-2xl bg-[#12141a] border border-white/10 space-y-4">
                        <div className="flex items-start justify-between gap-3">
                          <div className="flex items-center gap-3">
                            <div className="w-12 h-12 rounded-2xl bg-cyan-500/20 border-2 border-cyan-400 text-cyan-300 font-serif text-xl font-bold flex items-center justify-center shrink-0">
                              {selectedContact.name ? selectedContact.name.charAt(0).toUpperCase() : "C"}
                            </div>
                            <div>
                              <h3 className="font-serif text-2xl text-white font-bold leading-tight">
                                {selectedContact.name}
                              </h3>
                              <div className="text-xs font-mono text-zinc-400 uppercase tracking-wider">
                                {selectedContact.company_or_role || selectedContact.web_profile?.headline || "Executive Contact"}
                              </div>
                            </div>
                          </div>

                          <button
                            onClick={() => handleEnrichContactClick(selectedContact.id || selectedContact.name, selectedContact.name)}
                            className="px-3 py-1.5 rounded-xl bg-cyan-950/80 hover:bg-cyan-900 border border-cyan-500/40 text-cyan-300 font-mono text-[10px] uppercase tracking-wider shrink-0 transition-colors"
                          >
                            🔍 Enrich Profile
                          </button>
                        </div>

                        {/* Bio summary */}
                        <div className="text-sm font-sans text-zinc-200 leading-relaxed bg-black/40 p-3 rounded-xl border border-white/5">
                          {selectedContact.web_profile?.bio_summary ||
                            "Autonomous executive intelligence profile corroborated via live web search."}
                        </div>

                        {/* Expertise tags */}
                        {selectedContact.web_profile?.areas_of_expertise && selectedContact.web_profile.areas_of_expertise.length > 0 && (
                          <div className="flex flex-wrap gap-1.5">
                            {selectedContact.web_profile.areas_of_expertise.map((tag, i) => (
                              <span
                                key={i}
                                className="px-2 py-0.5 rounded bg-cyan-950/60 border border-cyan-500/20 text-cyan-300 font-mono text-[9px] uppercase"
                              >
                                #{tag}
                              </span>
                            ))}
                          </div>
                        )}

                        {/* Bilateral Commitments for this contact */}
                        {selectedContact.commitments && selectedContact.commitments.length > 0 && (
                          <div className="space-y-2 pt-2 border-t border-white/10">
                            <div className="font-mono text-[9px] text-zinc-400 tracking-widest uppercase">
                              Bilateral Commitments ({selectedContact.commitments.length}):
                            </div>
                            <div className="space-y-1.5">
                              {selectedContact.commitments.map((cmt, i) => {
                                const isObj = typeof cmt === "object" && cmt !== null;
                                const desc = isObj ? cmt.description : String(cmt);
                                const debtor = isObj ? cmt.debtor : "user";
                                const status = isObj ? cmt.status : "open";
                                const cmtId = isObj ? cmt.id : `cmt-${i}`;
                                return (
                                  <div
                                    key={cmtId || i}
                                    className="p-2.5 rounded-lg bg-black/60 border border-white/5 flex items-center justify-between text-xs font-sans gap-2"
                                  >
                                    <div className="flex items-center gap-2 truncate">
                                      <span>{debtor === "user" ? "📤" : "📥"}</span>
                                      <span className="text-zinc-200 truncate">{desc}</span>
                                    </div>
                                    <div className="flex items-center gap-2 shrink-0">
                                      <span className="font-mono text-[9px] text-cyan-400 uppercase">
                                        {debtor === "user" ? "You Promised" : "They Promised"}
                                      </span>
                                      {isObj && status === "open" && (
                                        <button
                                          onClick={() => handleToggleCommitmentClick(cmt.id, "fulfill")}
                                          className="px-2 py-0.5 rounded bg-emerald-950/80 hover:bg-emerald-900 border border-emerald-500/40 text-emerald-300 font-mono text-[9px] uppercase transition-colors"
                                        >
                                          ✓ Fulfill
                                        </button>
                                      )}
                                    </div>
                                  </div>
                                );
                              })}
                            </div>
                          </div>
                        )}
                      </div>
                    ) : (
                      <div className="text-center py-12 text-zinc-500 font-mono text-sm">
                        No contacts recorded in social rolodex.
                      </div>
                    )}
                  </div>

                  <div className="pt-3 border-t border-white/10 flex items-center justify-between">
                    <span className="text-xs font-mono text-zinc-400">
                      CRM Ledger: <strong className="text-cyan-400">SYNCHRONIZED</strong>
                    </span>
                    {selectedContact && (
                      <button
                        onClick={() =>
                          speakAlexaReassurance(
                            `Executive profile for ${selectedContact.name}: ${selectedContact.web_profile?.bio_summary || "profile indexed."}`
                          )
                        }
                        className="px-4 py-1.5 rounded-full bg-cyan-500/20 hover:bg-cyan-500/30 border border-cyan-400/40 text-cyan-300 font-mono text-xs uppercase tracking-wider font-bold transition-colors"
                      >
                        🔊 Read Profile Aloud
                      </button>
                    )}
                  </div>
                </div>
              )}

              {/* TAB 5: TOPIC DOSSIERS */}
              {activeTab === "topics" && (
                <div className="space-y-4 flex-1 flex flex-col justify-between animate-in fade-in duration-150">
                  <div className="space-y-4">
                    {/* Topics Pill Selector */}
                    {topics.length > 0 && (
                      <div className="flex items-center gap-2 overflow-x-auto hide-scrollbar pb-1">
                        {topics.map((t, idx) => (
                          <button
                            key={t.id || idx}
                            onClick={() => setSelectedTopicIndex(idx)}
                            className={`px-3 py-1.5 rounded-xl font-mono text-xs whitespace-nowrap transition-all ${
                              selectedTopicIndex === idx
                                ? "bg-purple-500 text-white font-bold shadow-md shadow-purple-500/30"
                                : "bg-black/40 text-zinc-400 hover:text-white border border-white/10"
                            }`}
                          >
                            {t.topic_title}
                          </button>
                        ))}
                      </div>
                    )}

                    {selectedTopic ? (
                      <div className="p-5 rounded-2xl bg-[#12141a] border border-white/10 space-y-4">
                        <div className="flex items-center justify-between">
                          <span className="px-2.5 py-0.5 rounded bg-purple-950/80 border border-purple-500/30 text-purple-300 font-mono text-[9px] uppercase font-bold tracking-wider">
                            {selectedTopic.context_type || "TECH STACK"}
                          </span>
                          <span className="font-mono text-[9px] text-zinc-500">
                            {selectedTopic.created_at?.substring(0, 10) || "LIVE"}
                          </span>
                        </div>

                        <h3 className="font-serif text-2xl text-white font-bold">
                          {selectedTopic.topic_title}
                        </h3>

                        {/* Synthesis */}
                        {selectedTopic.explanatory_synthesis && (
                          <div className="p-3.5 rounded-xl bg-amber-950/20 border border-amber-500/30 text-amber-200 font-sans text-sm leading-relaxed">
                            ⚡ <strong className="font-mono text-[10px] tracking-wider uppercase text-amber-300 mr-1">Thesis:</strong>
                            {selectedTopic.explanatory_synthesis}
                          </div>
                        )}

                        {/* Bullets */}
                        {selectedTopic.executive_summary && selectedTopic.executive_summary.length > 0 && (
                          <div className="space-y-1.5">
                            <div className="font-mono text-[9px] text-zinc-400 tracking-widest uppercase">Key Insights:</div>
                            <ul className="space-y-1 text-xs text-zinc-200 font-sans">
                              {selectedTopic.executive_summary.map((b, i) => (
                                <li key={i} className="flex items-start gap-2">
                                  <span className="text-cyan-400 font-bold">•</span>
                                  <span>{b}</span>
                                </li>
                              ))}
                            </ul>
                          </div>
                        )}

                        {/* Web Sources */}
                        {selectedTopic.web_sources && selectedTopic.web_sources.length > 0 && (
                          <div className="pt-2 border-t border-white/10 flex flex-wrap gap-2">
                            <span className="font-mono text-[9px] text-zinc-400 uppercase tracking-wider">Sources:</span>
                            {selectedTopic.web_sources.slice(0, 3).map((src, i) => (
                              <a
                                key={i}
                                href={src}
                                target="_blank"
                                rel="noreferrer"
                                className="text-[10px] font-mono text-purple-300 hover:underline truncate max-w-xs"
                              >
                                🔗 {src}
                              </a>
                            ))}
                          </div>
                        )}
                      </div>
                    ) : (
                      <div className="text-center py-12 text-zinc-500 font-mono text-sm">
                        No technical research dossiers compiled yet.
                      </div>
                    )}
                  </div>

                  <div className="pt-3 border-t border-white/10 flex items-center justify-between">
                    <span className="text-xs font-mono text-zinc-400">
                      Research Engine: <strong className="text-purple-400">AWS BEDROCK + DUCKDUCKGO</strong>
                    </span>
                    {selectedTopic && (
                      <button
                        onClick={() =>
                          speakAlexaReassurance(
                            `Briefing for ${selectedTopic.topic_title}: ${selectedTopic.explanatory_synthesis || selectedTopic.executive_summary?.[0] || "Analysis complete."}`
                          )
                        }
                        className="px-4 py-1.5 rounded-full bg-purple-500/20 hover:bg-purple-500/30 border border-purple-400/40 text-purple-300 font-mono text-xs uppercase tracking-wider font-bold transition-colors"
                      >
                        🔊 Read Dossier Aloud
                      </button>
                    )}
                  </div>
                </div>
              )}

              {/* TAB 6: AMBIENT SIMULATOR */}
              {activeTab === "simulator" && (
                <div className="space-y-4 flex-1 flex flex-col justify-between animate-in fade-in duration-150">
                  <div className="space-y-4">
                    {/* Presets Bar */}
                    <div className="space-y-2">
                      <div className="font-mono text-[9px] text-zinc-400 tracking-widest uppercase">
                        Select Demo Scenario Preset:
                      </div>
                      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-2">
                        {[
                          {
                            label: "Iron & Gas Safety",
                            icon: "🛡️",
                            text: "I just unplugged the clothes iron from the wall outlet and styled my hair — all good. Gas stovetop is cold and switched off.",
                          },
                          {
                            label: "Task Scheduler",
                            icon: "⏱️",
                            text: "Remind me to turn off the garden irrigation valve in an hour before leaving for dinner.",
                          },
                          {
                            label: "Bilateral Promises",
                            icon: "🤝",
                            text: "Nice to meet you Giulia Verdi, Senior Director at CloudOps. I will send you our architecture pitch deck tomorrow at 10 AM.",
                          },
                          {
                            label: "Executive CRM",
                            icon: "👤",
                            text: "Pleased to meet you, I'm Dr. Elena Rostova, VP of AI Research at CloudScale. Let's discuss distributed consensus algorithms.",
                          },
                          {
                            label: "Topic Synthesis",
                            icon: "📚",
                            text: "In today's meeting we evaluated AWS Bedrock AgentCore Runtime microVM execution and sub-second state persistence.",
                          },
                        ].map((preset, i) => (
                          <button
                            key={i}
                            onClick={() => {
                              if (setSimText) setSimText(preset.text);
                              setLocalSimText(preset.text);
                            }}
                            className="p-2.5 rounded-xl bg-black/40 hover:bg-cyan-950/40 border border-white/10 hover:border-cyan-500/40 text-left transition-colors cursor-pointer"
                          >
                            <div className="text-base mb-1">{preset.icon}</div>
                            <div className="text-[11px] font-mono font-bold text-white leading-tight">
                              {preset.label}
                            </div>
                          </button>
                        ))}
                      </div>
                    </div>

                    {/* Speech Transcript Input Box */}
                    <div className="space-y-1.5">
                      <div className="font-mono text-[9px] text-zinc-400 tracking-widest uppercase">
                        Ambient Utterance Transcript Stream:
                      </div>
                      <textarea
                        value={simText || localSimText}
                        onChange={(e) => {
                          if (setSimText) setSimText(e.target.value);
                          setLocalSimText(e.target.value);
                        }}
                        rows={3}
                        className="w-full p-3 rounded-xl bg-black/60 border border-white/15 text-zinc-100 font-sans text-xs focus:outline-none focus:border-cyan-400 resize-none"
                        placeholder="Enter simulated spoken transcript..."
                      />
                    </div>

                    {/* Simulation Execution Trigger */}
                    <div className="flex items-center justify-between">
                      <div className="text-[10px] font-mono text-zinc-400">
                        TARGET: <span className="text-cyan-400 font-semibold">AWS Bedrock AgentCore Runtime</span>
                      </div>
                      <button
                        onClick={handleRunSimulationClick}
                        disabled={simRunning || localSimRunning}
                        className="px-5 py-2.5 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-black font-mono text-xs uppercase tracking-wider font-bold shadow-lg shadow-cyan-500/30 transition-all flex items-center gap-2 cursor-pointer disabled:opacity-50"
                      >
                        <span>{simRunning || localSimRunning ? "⚡ Processing..." : "⚡ Run Pipeline Ingestion"}</span>
                      </button>
                    </div>

                    {/* Simulation Output Card */}
                    {(simResult || localSimResult) && (
                      <div className="p-4 rounded-xl bg-black/60 border border-cyan-500/30 space-y-2">
                        <div className="flex items-center justify-between">
                          <span className="font-mono text-[9px] text-emerald-400 uppercase font-bold">
                            ✓ Ingestion Successful
                          </span>
                          <span className="font-mono text-[9px] text-zinc-500">
                            AgentCore Latency: ~1.2s
                          </span>
                        </div>
                        <pre className="font-mono text-[10px] text-zinc-300 max-h-32 overflow-y-auto hide-scrollbar bg-black/80 p-2.5 rounded">
                          {JSON.stringify(simResult || localSimResult, null, 2)}
                        </pre>
                      </div>
                    )}
                  </div>

                  <div className="pt-3 border-t border-white/10 flex items-center justify-between">
                    <span className="text-xs font-mono text-zinc-400">
                      Echo Simulator: <strong className="text-cyan-400">REAL-TIME BRIDGE</strong>
                    </span>
                    <button
                      onClick={() =>
                        speakAlexaReassurance("Simulation complete. All domain ledgers updated on Echo Show.")
                      }
                      className="px-4 py-1.5 rounded-full bg-cyan-500/20 hover:bg-cyan-500/30 border border-cyan-400/40 text-cyan-300 font-mono text-xs uppercase tracking-wider font-bold transition-colors"
                    >
                      🔊 Test Echo Audio
                    </button>
                  </div>
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
