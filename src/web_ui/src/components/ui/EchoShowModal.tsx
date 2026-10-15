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
  EventSummary,
  EventEngineStatus,
  DossierFolderDef,
  DossierBreadcrumbItem,
  DEFAULT_DOSSIER_FOLDERS,
} from "@/types/schemas";
import { speakAlexaReassurance, playAcousticVerificationTone } from "@/utils/audioEffects";
import { getApiBaseUrl } from "@/utils/api";
import { MarkdownRenderer } from "./MarkdownRenderer";
import { DossierBreadcrumbs } from "./DossierBreadcrumbs";
import { DossierFolderCard } from "./DossierFolderCard";
import {
  generateTopicMarkdown,
  downloadTextFile,
  sanitizeFilename,
} from "@/utils/dossierExport";

interface EchoSubfolderItem {
  id: string;
  label: string;
  count: number;
  topicFilter?: (t: BriefingReport) => boolean;
  eventFilter?: (e: EventSummary) => boolean;
}

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
  sessionsData?: { sessions: EventSummary[] };
  engineStatus?: EventEngineStatus;
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

class EchoShowErrorBoundary extends React.Component<
  { children: React.ReactNode },
  { hasError: boolean; error: Error | null }
> {
  constructor(props: { children: React.ReactNode }) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.warn("EchoShowModal recovered from render error:", error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="p-8 text-center space-y-4 my-auto flex-1 flex flex-col items-center justify-center">
          <div className="text-amber-400 text-3xl">⚠️</div>
          <h3 className="font-serif text-xl text-white font-bold">
            Echo Show View Display Recovered
          </h3>
          <p className="font-mono text-xs text-zinc-400 max-w-md">
            The active tab encountered an unexpected format and safely reset to stable telemetry.
          </p>
          <div className="pt-2">
            <button
              onClick={() => this.setState({ hasError: false, error: null })}
              className="px-4 py-2 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-black font-mono text-xs uppercase font-bold tracking-wider cursor-pointer"
            >
              Resume Echo Display
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
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

const KIND_BADGES: Record<string, { label: string; cls: string }> = {
  final: { label: "★ EVENT FINAL", cls: "text-amber-300 border-amber-500/50 bg-amber-950/40" },
  segment: { label: "EVENT PART", cls: "text-cyan-300 border-cyan-500/40 bg-cyan-950/30" },
  checkpoint: { label: "CHECKPOINT", cls: "text-cyan-300 border-cyan-500/40 bg-cyan-950/30" },
  standalone: { label: "STANDALONE", cls: "text-zinc-300 border-white/10 bg-[#1c1f26]" },
};

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
  sessionsData,
  engineStatus,
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
  const [selectedEventIndex, setSelectedEventIndex] = useState(0);
  const [topicSubView, setTopicSubView] = useState<"events" | "briefings">(
    initialTemplate === "SESSION_DOSSIER_VIEWER" ? "events" : "briefings"
  );
  const [quickRoutineTitle, setQuickRoutineTitle] = useState("");
  const [routineFilter, setRoutineFilter] = useState<"ALL" | "PENDING" | "COMPLETED">("ALL");
  const [echoTopicCategory, setEchoTopicCategory] = useState<string>("ALL");

  // Topic Dossiers folder hierarchy states on Echo Show
  const [echoTopicViewMode, setEchoTopicViewMode] = useState<"folders" | "all_feed">("folders");
  const [echoFolderId, setEchoFolderId] = useState<string | null>(
    initialTemplate === "SESSION_DOSSIER_VIEWER" ? "event_sessions" : null
  );
  const [echoSubfolderId, setEchoSubfolderId] = useState<string | null>(null);
  const [echoFocusedTopicId, setEchoFocusedTopicId] = useState<string | null>(null);
  const [echoSelectedSessionId, setEchoSelectedSessionId] = useState<string | null>(null);

  useEffect(() => {
    setMounted(true);
  }, []);

  // Update active tab when props change or modal opens
  useEffect(() => {
    if (isOpen) {
      setActiveTab(resolveInitialTab());
      if (initialTemplate === "SESSION_DOSSIER_VIEWER") {
        setEchoTopicViewMode("folders");
        setEchoFolderId("event_sessions");
        setTopicSubView("events");
      }
    }
  }, [isOpen, resolveInitialTab, initialTemplate]);

  // Audio tone and voice announcement on new notification arrival
  useEffect(() => {
    if (isOpen && echoNotification && lastSpokenNotifId.current !== echoNotification.id) {
      lastSpokenNotifId.current = echoNotification.id;
      playAcousticVerificationTone();
      speakAlexaReassurance(`Notification: ${echoNotification.title || "Alert"}. ${echoNotification.message || ""}`);
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
  const { data: swrSessions, mutate: mutateSessions } = useSWR<{ sessions: EventSummary[] }>(
    isOpen && !sessionsData ? "/api/sessions?events_only=true&limit=20" : null,
    fetcher
  );
  const { data: swrEngine, mutate: mutateEngine } = useSWR<EventEngineStatus>(
    isOpen && !engineStatus ? "/api/event-engine/status" : null,
    fetcher
  );

  const effStatus = statusData || swrStatus;
  const effRoutines = routinesData || swrRoutines;
  const effActions = actionsData || swrActions;
  const effSocial = socialData || swrSocial;
  const effTopics = topicsData || swrTopics;
  const effSessions = sessionsData || swrSessions;
  const effEngine = engineStatus || swrEngine;

  // Defensive array extractions guaranteeing no undefined crashes
  const tasks: PlannedTask[] = useMemo(() => {
    const raw = Array.isArray(effRoutines)
      ? effRoutines
      : Array.isArray(effRoutines?.tasks)
      ? effRoutines.tasks
      : [];
    return raw.filter((t): t is PlannedTask => Boolean(t && typeof t === "object"));
  }, [effRoutines]);

  const actions: VerifiedAction[] = useMemo(() => {
    const raw = Array.isArray(effActions)
      ? effActions
      : Array.isArray(effActions?.actions)
      ? effActions.actions
      : [];
    return raw.filter((a): a is VerifiedAction => Boolean(a && typeof a === "object"));
  }, [effActions]);

  const contacts: SocialEntity[] = useMemo(() => {
    const raw = Array.isArray(effSocial)
      ? effSocial
      : Array.isArray(effSocial?.contacts)
      ? effSocial.contacts
      : [];
    return raw.filter((c): c is SocialEntity => Boolean(c && typeof c === "object"));
  }, [effSocial]);

  const topics: BriefingReport[] = useMemo(() => {
    const raw = Array.isArray(effTopics)
      ? effTopics
      : Array.isArray(effTopics?.topics)
      ? effTopics.topics
      : [];
    return raw.filter((t): t is BriefingReport => Boolean(t && typeof t === "object"));
  }, [effTopics]);

  const events: EventSummary[] = useMemo(() => {
    const raw = Array.isArray(effSessions)
      ? effSessions
      : Array.isArray(effSessions?.sessions)
      ? effSessions.sessions
      : [];
    return raw.filter((e): e is EventSummary => Boolean(e && typeof e === "object"));
  }, [effSessions]);

  const liveEvent = effEngine?.active_event || null;

  const completedTasks = tasks.filter((t) => t?.status === "completed").length;
  const pendingTasks = tasks.filter((t) => t?.status !== "completed").length;

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

  // Topic Categories Filter Options (defensive against undefined/null objects)
  const topicCategories = useMemo(() => {
    if (!Array.isArray(topics)) return ["ALL"];
    const cats = new Set<string>();
    topics.forEach((t) => {
      if (t && typeof t.context_type === "string" && t.context_type.trim()) {
        cats.add(t.context_type.trim());
      }
    });
    return ["ALL", ...Array.from(cats)];
  }, [topics]);

  // Filtered topics array with guaranteed array typing
  const echoFilteredTopics = useMemo(() => {
    if (!Array.isArray(topics)) return [];
    const valid = topics.filter((t): t is BriefingReport => Boolean(t && typeof t === "object"));
    if (echoTopicCategory === "ALL") return valid;
    return valid.filter((t) => t.context_type === echoTopicCategory);
  }, [topics, echoTopicCategory]);

  // Complete list of folders including any dynamic / custom context types on Echo Show
  const echoAllFolders: DossierFolderDef[] = useMemo(() => {
    const knownTypes = new Set(DEFAULT_DOSSIER_FOLDERS.flatMap((f) => f.contextTypes));
    const dynamicFolders: DossierFolderDef[] = [];

    topics.forEach((t) => {
      if (t.context_type && !knownTypes.has(t.context_type)) {
        knownTypes.add(t.context_type);
        const folderId = `custom_${t.context_type}`;
        dynamicFolders.push({
          id: folderId,
          name: t.context_type.replace(/_/g, " ").toUpperCase(),
          icon: "📁",
          accent: "zinc",
          description: `Synthesized research topics tagged under ${t.context_type.replace(/_/g, " ")}`,
          contextTypes: [t.context_type],
        });
      }
    });

    return [...DEFAULT_DOSSIER_FOLDERS, ...dynamicFolders];
  }, [topics]);

  // Active folder object
  const echoActiveFolder = useMemo(
    () => echoAllFolders.find((f) => f.id === echoFolderId) || null,
    [echoAllFolders, echoFolderId]
  );

  // Filter topics for the active folder
  const echoFolderTopics = useMemo(() => {
    if (!echoActiveFolder || echoActiveFolder.isEventFolder) return [];
    return topics.filter((t) => echoActiveFolder.contextTypes.includes(t.context_type));
  }, [echoActiveFolder, topics]);

  // Focused topic dossier object (Level 3 drill-down)
  const echoFocusedTopic = useMemo(() => {
    if (!echoFocusedTopicId) return null;
    return topics.find((t) => t.id === echoFocusedTopicId) || null;
  }, [topics, echoFocusedTopicId]);

  // Focused event session object
  const echoFocusedEvent = useMemo(() => {
    if (!echoSelectedSessionId) return null;
    return events.find((e) => e.session_id === echoSelectedSessionId) || null;
  }, [events, echoSelectedSessionId]);

  // Subfolders definition for active folder
  const echoSubfolders: EchoSubfolderItem[] = useMemo(() => {
    if (!echoActiveFolder) return [];

    if (echoActiveFolder.isEventFolder) {
      return [
        { id: "all", label: "ALL SESSIONS", count: events.length },
        {
          id: "active",
          label: "LIVE RECORDING",
          count: events.filter((e) => e.status === "active").length,
          eventFilter: (e: EventSummary) => e.status === "active",
        },
        {
          id: "paused",
          label: "PAUSED / IN BREAK",
          count: events.filter((e) => e.status === "paused" || e.status === "finalizing").length,
          eventFilter: (e: EventSummary) => e.status === "paused" || e.status === "finalizing",
        },
        {
          id: "concluded",
          label: "CONCLUDED",
          count: events.filter((e) => e.status === "concluded").length,
          eventFilter: (e: EventSummary) => e.status === "concluded",
        },
      ];
    }

    if (echoActiveFolder.id === "academic") {
      return [
        { id: "all", label: "ALL ACADEMIC", count: echoFolderTopics.length },
        {
          id: "lectures",
          label: "LECTURES & SYLLABI",
          count: echoFolderTopics.filter((t) => t.kind !== "final").length,
          topicFilter: (t: BriefingReport) => t.kind !== "final",
        },
        {
          id: "final",
          label: "FINAL SYNTHESES",
          count: echoFolderTopics.filter((t) => t.kind === "final").length,
          topicFilter: (t: BriefingReport) => t.kind === "final",
        },
        {
          id: "sources",
          label: "WITH CITATIONS",
          count: echoFolderTopics.filter((t) => Boolean(t.web_sources && t.web_sources.length > 0)).length,
          topicFilter: (t: BriefingReport) => Boolean(t.web_sources && t.web_sources.length > 0),
        },
      ];
    }

    if (echoActiveFolder.id === "tech_stack") {
      return [
        { id: "all", label: "ALL TECH TOPICS", count: echoFolderTopics.length },
        {
          id: "deep_dive",
          label: "DEEP RESEARCH MARKDOWN",
          count: echoFolderTopics.filter((t) => Boolean(t.deep_dive_markdown)).length,
          topicFilter: (t: BriefingReport) => Boolean(t.deep_dive_markdown),
        },
        {
          id: "citations",
          label: "WITH CITATIONS",
          count: echoFolderTopics.filter((t) => Boolean(t.web_sources && t.web_sources.length > 0)).length,
          topicFilter: (t: BriefingReport) => Boolean(t.web_sources && t.web_sources.length > 0),
        },
        {
          id: "actions",
          label: "ACTION ITEMS",
          count: echoFolderTopics.filter((t) => Boolean(t.action_items && t.action_items.length > 0)).length,
          topicFilter: (t: BriefingReport) => Boolean(t.action_items && t.action_items.length > 0),
        },
      ];
    }

    if (echoActiveFolder.id === "engineering") {
      return [
        { id: "all", label: "ALL PRODUCT TOPICS", count: echoFolderTopics.length },
        {
          id: "features",
          label: "FEATURE PROPOSALS",
          count: echoFolderTopics.filter((t) => t.context_type === "feature_discussion").length,
          topicFilter: (t: BriefingReport) => t.context_type === "feature_discussion",
        },
        {
          id: "incidents",
          label: "BUGS & INCIDENTS",
          count: echoFolderTopics.filter(
            (t) => t.context_type === "bug" || t.context_type === "system_incident"
          ).length,
          topicFilter: (t: BriefingReport) =>
            t.context_type === "bug" || t.context_type === "system_incident",
        },
        {
          id: "sources",
          label: "WITH CITATIONS",
          count: echoFolderTopics.filter((t) => Boolean(t.web_sources && t.web_sources.length > 0)).length,
          topicFilter: (t: BriefingReport) => Boolean(t.web_sources && t.web_sources.length > 0),
        },
      ];
    }

    if (echoActiveFolder.id === "business") {
      return [
        { id: "all", label: "ALL BUSINESS", count: echoFolderTopics.length },
        {
          id: "actions",
          label: "WITH ACTION ITEMS",
          count: echoFolderTopics.filter((t) => Boolean(t.action_items && t.action_items.length > 0)).length,
          topicFilter: (t: BriefingReport) => Boolean(t.action_items && t.action_items.length > 0),
        },
        {
          id: "briefs",
          label: "EXECUTIVE BRIEFS",
          count: echoFolderTopics.filter((t) => Boolean(t.executive_summary && t.executive_summary.length > 0)).length,
          topicFilter: (t: BriefingReport) => Boolean(t.executive_summary && t.executive_summary.length > 0),
        },
      ];
    }

    return [
      { id: "all", label: "ALL ITEMS", count: echoFolderTopics.length },
      {
        id: "citations",
        label: "WITH CITATIONS",
        count: echoFolderTopics.filter((t) => Boolean(t.web_sources && t.web_sources.length > 0)).length,
        topicFilter: (t: BriefingReport) => Boolean(t.web_sources && t.web_sources.length > 0),
      },
    ];
  }, [echoActiveFolder, echoFolderTopics, events]);

  // Topics displayed inside active folder after subfolder filter
  const echoDisplayedFolderTopics = useMemo(() => {
    let result = echoFolderTopics;
    if (echoSubfolderId && echoSubfolderId !== "all") {
      const sub = echoSubfolders.find((s) => s.id === echoSubfolderId);
      if (sub && sub.topicFilter) {
        result = result.filter(sub.topicFilter);
      }
    }
    return result;
  }, [echoFolderTopics, echoSubfolderId, echoSubfolders]);

  // Event sessions displayed inside event folder after subfolder filter
  const echoDisplayedEvents = useMemo(() => {
    let result = events;
    if (echoActiveFolder?.isEventFolder && echoSubfolderId && echoSubfolderId !== "all") {
      const sub = echoSubfolders.find((s) => s.id === echoSubfolderId);
      if (sub && sub.eventFilter) {
        result = result.filter(sub.eventFilter);
      }
    }
    return result;
  }, [events, echoActiveFolder, echoSubfolderId, echoSubfolders]);

  // Breadcrumbs Generation for Echo Show
  const echoBreadcrumbItems: DossierBreadcrumbItem[] = useMemo(() => {
    const items: DossierBreadcrumbItem[] = [
      {
        id: "root",
        label: "DOSSIERS REPOSITORY",
        icon: "📁",
        count: topics.length,
      },
    ];

    if (echoTopicViewMode === "all_feed") {
      items.push({
        id: "all_feed",
        label: "ALL BRIEFINGS FEED",
        icon: "📚",
        count: topics.length,
      });
      return items;
    }

    if (echoActiveFolder) {
      items.push({
        id: echoActiveFolder.id,
        label: echoActiveFolder.name,
        icon: echoActiveFolder.icon,
        count: echoActiveFolder.isEventFolder ? events.length : echoFolderTopics.length,
      });

      if (echoSubfolderId && echoSubfolderId !== "all") {
        const sub = echoSubfolders.find((s) => s.id === echoSubfolderId);
        if (sub) {
          items.push({
            id: sub.id,
            label: sub.label,
            icon: "📂",
            count: sub.count,
          });
        }
      }

      if (echoSelectedSessionId && echoActiveFolder.isEventFolder) {
        const ev = events.find((e) => e.session_id === echoSelectedSessionId);
        items.push({
          id: echoSelectedSessionId,
          label: ev?.final_title || ev?.title || "EVENT SESSION",
          icon: "🏛️",
        });
      }

      if (echoFocusedTopic) {
        items.push({
          id: echoFocusedTopic.id,
          label: echoFocusedTopic.topic_title,
          icon: "📄",
        });
      }
    }

    return items;
  }, [
    echoTopicViewMode,
    echoActiveFolder,
    echoSubfolderId,
    echoSubfolders,
    echoSelectedSessionId,
    events,
    echoFocusedTopic,
    topics.length,
    echoFolderTopics.length,
  ]);

  const echoCurrentPathString = useMemo(() => {
    if (echoTopicViewMode === "all_feed") return "~/echo/dossiers/all_feed/";
    if (!echoActiveFolder) return "~/echo/dossiers/";
    let base = `~/echo/dossiers/${echoActiveFolder.id}/`;
    if (echoSubfolderId && echoSubfolderId !== "all") {
      base += `${echoSubfolderId}/`;
    }
    if (echoActiveFolder.isEventFolder && echoSelectedSessionId) {
      base += `${echoSelectedSessionId.substring(0, 8)}/`;
    }
    if (echoFocusedTopic) {
      const slug = echoFocusedTopic.topic_title
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "-")
        .replace(/(^-|-$)/g, "");
      base += `${slug.substring(0, 20)}/`;
    }
    return base;
  }, [echoTopicViewMode, echoActiveFolder, echoSubfolderId, echoSelectedSessionId, echoFocusedTopic]);

  const handleEchoNavigateBreadcrumb = (item: DossierBreadcrumbItem) => {
    if (item.id === "root") {
      setEchoFolderId(null);
      setEchoSubfolderId(null);
      setEchoFocusedTopicId(null);
      setEchoSelectedSessionId(null);
      setEchoTopicViewMode("folders");
    } else if (item.id === "all_feed") {
      setEchoTopicViewMode("all_feed");
    } else if (echoActiveFolder && item.id === echoActiveFolder.id) {
      setEchoSubfolderId(null);
      setEchoFocusedTopicId(null);
      setEchoSelectedSessionId(null);
    } else if (item.id === echoSubfolderId) {
      setEchoFocusedTopicId(null);
      setEchoSelectedSessionId(null);
    }
  };

  const handleEchoBack = () => {
    if (echoFocusedTopicId) {
      setEchoFocusedTopicId(null);
    } else if (echoSelectedSessionId) {
      setEchoSelectedSessionId(null);
    } else if (echoSubfolderId && echoSubfolderId !== "all") {
      setEchoSubfolderId(null);
    } else if (echoFolderId) {
      setEchoFolderId(null);
    } else if (echoTopicViewMode !== "folders") {
      setEchoTopicViewMode("folders");
    }
  };

  const handleOpenEchoFolder = (folderId: string) => {
    setEchoTopicViewMode("folders");
    setEchoFolderId(folderId);
    setEchoSubfolderId(null);
    setEchoFocusedTopicId(null);
    setEchoSelectedSessionId(null);
  };

  const getEchoFolderForTopic = useCallback((topic: BriefingReport): DossierFolderDef => {
    if (!topic.context_type) return echoAllFolders[0];
    const found = echoAllFolders.find(
      (f) => !f.isEventFolder && f.contextTypes.includes(topic.context_type)
    );
    return found || echoAllFolders[0];
  }, [echoAllFolders]);

  const handleSelectEchoTopic = (topic: BriefingReport) => {
    const parentFolder = getEchoFolderForTopic(topic);
    setEchoFolderId(parentFolder.id);
    setEchoFocusedTopicId(topic.id);
    setEchoTopicViewMode("folders");
  };

  // Pager navigation for focused topic on Echo Show
  const echoFocusedIndex = useMemo(() => {
    if (!echoFocusedTopic) return -1;
    return echoDisplayedFolderTopics.findIndex((t) => t.id === echoFocusedTopic.id);
  }, [echoDisplayedFolderTopics, echoFocusedTopic]);

  const echoPrevTopic = echoFocusedIndex > 0 ? echoDisplayedFolderTopics[echoFocusedIndex - 1] : null;
  const echoNextTopic =
    echoFocusedIndex >= 0 && echoFocusedIndex < echoDisplayedFolderTopics.length - 1
      ? echoDisplayedFolderTopics[echoFocusedIndex + 1]
      : null;

  // Defensive active selections
  const selectedContact = (contacts && contacts[selectedContactIndex]) || (contacts && contacts[0]) || null;
  const selectedTopic = (echoFilteredTopics && echoFilteredTopics[selectedTopicIndex]) || (echoFilteredTopics && echoFilteredTopics[0]) || null;
  const selectedEvent = (events && events[selectedEventIndex]) || (events && events[0]) || null;
  const latestAction = (actions && actions[0]) || null;

  // Clamp selection indices if list length shrinks
  useEffect(() => {
    if (selectedTopicIndex >= echoFilteredTopics.length && echoFilteredTopics.length > 0) {
      setSelectedTopicIndex(0);
    }
  }, [echoFilteredTopics.length, selectedTopicIndex]);

  useEffect(() => {
    if (selectedContactIndex >= contacts.length && contacts.length > 0) {
      setSelectedContactIndex(0);
    }
  }, [contacts.length, selectedContactIndex]);

  useEffect(() => {
    if (selectedEventIndex >= events.length && events.length > 0) {
      setSelectedEventIndex(0);
    }
  }, [events.length, selectedEventIndex]);

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
    if (!task || !task.id) return;
    if (onToggleRoutine) {
      await onToggleRoutine(task);
    } else {
      try {
        const baseUrl = getApiBaseUrl();
        await fetch(`${baseUrl}/api/routines/${encodeURIComponent(task.id)}/toggle`, { method: "POST" });
        if (mutateRoutines) mutateRoutines();
        if (mutateStatus) mutateStatus();
      } catch (e) {
        console.error(e);
      }
    }
    const newStatus = task.status === "completed" ? "pending" : "completed";
    speakAlexaReassurance(`Routine '${task.title || "Routine"}' marked ${newStatus}.`);
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

  const handleDownloadEchoTopic = (t: BriefingReport) => {
    const md = generateTopicMarkdown(t);
    const fname = sanitizeFilename(t.topic_title || "topic_briefing", ".md");
    downloadTextFile(md, fname);
    showFeedback("Dossier downloaded as .md");
  };

  const liveSegmentsCount = Array.isArray(liveEvent?.segments)
    ? liveEvent.segments.length
    : typeof liveEvent?.segments === "number"
    ? liveEvent.segments
    : 0;

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
              className="text-zinc-400 hover:text-white font-mono text-[11px] tracking-wider uppercase px-2.5 py-1 rounded bg-zinc-800/80 hover:bg-zinc-700 transition-colors cursor-pointer"
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
                      ⚡ ALEXA+ AMBIENT INTELLIGENCE NOTIFICATION // {(echoNotification.category || "UPDATE").toUpperCase()}
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
                    {echoNotification.title || "Ambient Notification"}
                  </h3>
                  <div className="p-4 rounded-xl bg-black/60 border border-cyan-500/30 text-zinc-200 font-sans text-sm sm:text-base leading-relaxed italic">
                    "{echoNotification.message || ""}"
                  </div>
                  <div className="flex items-center justify-between font-mono text-[10px] text-zinc-400">
                    <span>TIME: {echoNotification.timestamp || "RECENT"}</span>
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
                        {typeof currentUser.handle === "string" && currentUser.handle ? currentUser.handle.charAt(0).toUpperCase() : "U"}
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
                            {currentUser.handle || "User"}
                          </div>
                          <div className="font-mono text-[9px] text-zinc-400 flex items-center gap-1 mt-0.5">
                            <span>ID:</span>
                            <span className="text-cyan-300 truncate">{currentUser.user_id || "demo-user"}</span>
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

            {/* Main Specular Touch Canvas Protected by Error Boundary */}
            <div className="p-4 sm:p-6 md:p-8 flex-1 flex flex-col justify-between overflow-y-auto">
              <EchoShowErrorBoundary key={activeTab}>
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
                            className="px-2.5 py-1 rounded-lg bg-emerald-950/60 border border-emerald-500/30 text-emerald-300 hover:bg-emerald-900 transition-colors cursor-pointer"
                          >
                            🛡️ {actions.length} Verified Anchors
                          </button>
                          <button
                            onClick={() => handleTabSelect("routines")}
                            className="px-2.5 py-1 rounded-lg bg-amber-950/60 border border-amber-500/30 text-amber-300 hover:bg-amber-900 transition-colors cursor-pointer"
                          >
                            📋 {pendingTasks} Pending Checks
                          </button>
                          <button
                            onClick={() => handleTabSelect("social")}
                            className="px-2.5 py-1 rounded-lg bg-cyan-950/60 border border-cyan-500/30 text-cyan-300 hover:bg-cyan-900 transition-colors cursor-pointer"
                          >
                            👥 {contacts.length} Social Contacts
                          </button>
                          <button
                            onClick={() => {
                              setEchoTopicViewMode("folders");
                              setEchoFolderId(null);
                              setEchoFocusedTopicId(null);
                              setEchoSelectedSessionId(null);
                              handleTabSelect("topics");
                            }}
                            className="px-2.5 py-1 rounded-lg bg-purple-950/60 border border-purple-500/30 text-purple-300 hover:bg-purple-900 transition-colors cursor-pointer"
                          >
                            📚 {topics.length} Dossiers
                          </button>
                          {events.length > 0 && (
                            <button
                              onClick={() => {
                                setTopicSubView("events");
                                setEchoFolderId("event_sessions");
                                setEchoTopicViewMode("folders");
                                handleTabSelect("topics");
                              }}
                              className="px-2.5 py-1 rounded-lg bg-cyan-950/60 border border-cyan-500/30 text-cyan-300 hover:bg-cyan-900 transition-colors cursor-pointer"
                            >
                              🏛️ {events.length} Events
                            </button>
                          )}
                        </div>
                      </div>

                      {/* Live lecture / meeting banner (Deep Topic Event Engine) */}
                      {liveEvent && (
                        <div
                          onClick={() => {
                            setTopicSubView("events");
                            setEchoFolderId("event_sessions");
                            setEchoTopicViewMode("folders");
                            handleTabSelect("topics");
                          }}
                          className={`rounded-xl p-3.5 mt-3 border cursor-pointer flex items-center justify-between gap-3 transition-colors ${
                            liveEvent.status === "active"
                              ? "bg-emerald-950/40 border-emerald-500/40 hover:border-emerald-400"
                              : "bg-amber-950/40 border-amber-500/40 hover:border-amber-400"
                          }`}
                        >
                          <div className="flex items-center gap-3 min-w-0">
                            <span className={`w-2.5 h-2.5 rounded-full shrink-0 ${liveEvent.status === "active" ? "bg-emerald-400 animate-pulse" : "bg-amber-400"}`} />
                            <div className="min-w-0">
                              <div className={`font-mono text-[8px] tracking-[0.2em] uppercase font-bold ${liveEvent.status === "active" ? "text-emerald-300" : "text-amber-300"}`}>
                                {liveEvent.status === "active" ? "LIVE EVENT // RECORDING" : "LIVE EVENT // PAUSED"}
                              </div>
                              <div className="font-serif text-sm sm:text-base text-white font-bold truncate">
                                {typeof liveEvent.title === "string" && liveEvent.title.startsWith("Ongoing session") ? "Lecture / meeting in progress" : (liveEvent.title || "Live Lecture")}
                              </div>
                            </div>
                          </div>
                          <div className="flex items-center gap-3 font-mono text-[9px] text-zinc-400 tracking-widest uppercase shrink-0">
                            <span>{liveSegmentsCount} PART(S)</span>
                            <span className="text-cyan-400 font-bold">OPEN TIMELINE →</span>
                          </div>
                        </div>
                      )}

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
                            {latestAction?.action_type ? latestAction.action_type.replace(/_/g, " ").toUpperCase() : "UNPLUG CLOTHES IRON"}
                          </h4>
                          <p className="text-xs text-zinc-300 font-sans italic line-clamp-2 bg-black/40 p-2 rounded border border-white/5">
                            "{latestAction?.raw_statement || "Ho appena staccato il ferro da stiro prima di uscire."}"
                          </p>
                          <div className="flex items-center justify-between pt-1">
                            <span className="font-mono text-[9px] text-emerald-400">
                              {Math.round((latestAction?.confidence ?? 0.98) * 100)}% CONFIDENCE
                            </span>
                            <button
                              onClick={() => handleTabSelect("peace")}
                              className="text-xs font-mono text-cyan-400 hover:underline flex items-center gap-1 cursor-pointer"
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
                              {tasks.slice(0, 2).map((task, i) => (
                                <div
                                  key={task.id || i}
                                  className="flex items-center justify-between p-2 rounded bg-black/40 border border-white/5 text-xs"
                                >
                                  <div className="flex items-center gap-2 truncate">
                                    <button
                                      onClick={() => handleToggleRoutineClick(task)}
                                      className={`w-4 h-4 rounded flex items-center justify-center font-mono text-[10px] border transition-colors cursor-pointer ${
                                        task.status === "completed"
                                          ? "bg-emerald-500 border-emerald-400 text-black font-bold"
                                          : "border-white/30 hover:border-white"
                                      }`}
                                    >
                                      {task.status === "completed" ? "✓" : ""}
                                    </button>
                                    <span className={`truncate ${task.status === "completed" ? "line-through text-zinc-500" : "text-zinc-200"}`}>
                                      {task.title || "Routine"}
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
                              className="text-xs font-mono text-amber-400 hover:underline flex items-center gap-1 cursor-pointer"
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
                                  {typeof selectedContact.name === "string" && selectedContact.name ? selectedContact.name.charAt(0).toUpperCase() : "C"}
                                </div>
                                <div>
                                  <h4 className="font-serif text-base text-white font-medium leading-tight">
                                    {selectedContact.name || "Executive Contact"}
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
                              className="text-xs font-mono text-cyan-400 hover:underline flex items-center gap-1 cursor-pointer"
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
                                {selectedTopic.explanatory_synthesis || (Array.isArray(selectedTopic.executive_summary) ? selectedTopic.executive_summary[0] : null) || "Synthesized analysis recorded."}
                              </p>
                            </div>
                          ) : (
                            <div className="text-zinc-500 font-mono text-xs py-3 text-center">
                              No technical briefings recorded yet.
                            </div>
                          )}
                          <div className="flex items-center justify-end pt-1">
                            <button
                              onClick={() => {
                                if (selectedTopic) {
                                  handleSelectEchoTopic(selectedTopic);
                                }
                                handleTabSelect("topics");
                              }}
                              className="text-xs font-mono text-purple-400 hover:underline flex items-center gap-1 cursor-pointer"
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
                          className="px-2.5 py-1 rounded-full bg-zinc-800/80 hover:bg-zinc-700 text-zinc-300 font-mono text-[9px] tracking-wider transition-colors cursor-pointer"
                        >
                          "Did I unplug iron?"
                        </button>
                        <button
                          onClick={() => {
                            speakAlexaReassurance(`You have ${pendingTasks} pending routines remaining today.`);
                            handleTabSelect("routines");
                          }}
                          className="px-2.5 py-1 rounded-full bg-zinc-800/80 hover:bg-zinc-700 text-zinc-300 font-mono text-[9px] tracking-wider transition-colors cursor-pointer"
                        >
                          "Routine Check"
                        </button>
                        <button
                          onClick={() => {
                            speakAlexaReassurance("Opening speech simulator on Echo Show.");
                            handleTabSelect("simulator");
                          }}
                          className="px-2.5 py-1 rounded-full bg-cyan-950/80 border border-cyan-500/40 text-cyan-300 font-mono text-[9px] tracking-wider transition-colors cursor-pointer"
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
                          {latestAction?.action_type ? latestAction.action_type.replace(/_/g, " ").toUpperCase() : "UNPLUG CLOTHES IRON"}
                        </div>

                        <div className="p-3.5 rounded-xl bg-black/60 border border-emerald-500/20 font-sans italic text-sm text-zinc-200">
                          "{latestAction?.raw_statement || "Ho appena staccato il ferro da stiro prima di uscire."}"
                        </div>

                        <div className="flex items-center justify-between pt-2 border-t border-white/10 text-xs font-mono">
                          <span className="text-zinc-400">ACOUSTIC CERTAINTY:</span>
                          <span className="text-emerald-400 font-bold">
                            {Math.round((latestAction?.confidence ?? 0.98) * 100)}% CONFIDENCE // GROUNDED
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
                          {actions.map((act, idx) => (
                            <div
                              key={act.id || idx}
                              className="p-2.5 rounded-lg bg-black/40 border border-white/5 flex items-center justify-between text-xs font-sans gap-2"
                            >
                              <div className="truncate flex-1">
                                <span className="font-semibold text-white mr-2">
                                  {act.action_type ? act.action_type.replace(/_/g, " ").toUpperCase() : "ACTION"}:
                                </span>
                                <span className="text-zinc-300 italic">"{act.raw_statement || ""}"</span>
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
                            `Alexa reassurance: ${latestAction?.action_type || "Clothes iron"} is verified completed with ${Math.round((latestAction?.confidence ?? 0.98) * 100)} percent certainty.`
                          )
                        }
                        className="px-4 py-1.5 rounded-full bg-emerald-500/20 hover:bg-emerald-500/30 border border-emerald-400/40 text-emerald-300 font-mono text-xs uppercase tracking-wider font-bold transition-colors cursor-pointer"
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
                            className={`px-3 py-1 rounded-lg font-mono text-[10px] uppercase tracking-wider transition-colors cursor-pointer ${
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
                            if (!t) return false;
                            if (routineFilter === "PENDING") return t.status !== "completed";
                            if (routineFilter === "COMPLETED") return t.status === "completed";
                            return true;
                          })
                          .map((task, idx) => {
                            const isComp = task.status === "completed";
                            return (
                              <div
                                key={task.id || idx}
                                className="p-3 rounded-xl bg-black/40 border border-white/10 flex items-center justify-between gap-3 hover:border-white/20 transition-colors"
                              >
                                <div className="flex items-center gap-3 truncate flex-1">
                                  <button
                                    onClick={() => handleToggleRoutineClick(task)}
                                    className={`w-6 h-6 rounded-lg flex items-center justify-center font-mono text-xs border transition-colors shrink-0 cursor-pointer ${
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
                                      {task.title || "Routine"}
                                    </div>
                                    <div className="text-[10px] font-mono text-zinc-400 flex items-center gap-2">
                                      <span className="uppercase text-cyan-400">{task.domain || "routine"}</span>
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
                                    {task.status || "pending"}
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
                            className="px-2.5 py-1 rounded-lg bg-zinc-800/80 hover:bg-zinc-700 text-zinc-300 font-mono text-[10px] transition-colors cursor-pointer"
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
                        className="px-4 py-1.5 rounded-full bg-amber-500/20 hover:bg-amber-500/30 border border-amber-400/40 text-amber-300 font-mono text-xs uppercase tracking-wider font-bold transition-colors cursor-pointer"
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
                              className={`px-3 py-1.5 rounded-xl font-mono text-xs whitespace-nowrap transition-all flex items-center gap-2 cursor-pointer ${
                                selectedContactIndex === idx
                                  ? "bg-cyan-500 text-black font-bold shadow-md"
                                  : "bg-black/40 text-zinc-400 hover:text-white border border-white/10"
                              }`}
                            >
                              <span className="w-4 h-4 rounded-full bg-white/20 flex items-center justify-center text-[9px]">
                                {typeof c.name === "string" && c.name ? c.name.charAt(0) : "C"}
                              </span>
                              <span>{c.name || "Contact"}</span>
                            </button>
                          ))}
                        </div>
                      )}

                      {selectedContact ? (
                        <div className="p-5 rounded-2xl bg-[#12141a] border border-white/10 space-y-4">
                          <div className="flex items-start justify-between gap-3">
                            <div className="flex items-center gap-3">
                              <div className="w-12 h-12 rounded-2xl bg-cyan-500/20 border-2 border-cyan-400 text-cyan-300 font-serif text-xl font-bold flex items-center justify-center shrink-0">
                                {typeof selectedContact.name === "string" && selectedContact.name ? selectedContact.name.charAt(0).toUpperCase() : "C"}
                              </div>
                              <div>
                                <h3 className="font-serif text-2xl text-white font-bold leading-tight">
                                  {selectedContact.name || "Executive Contact"}
                                </h3>
                                <div className="text-xs font-mono text-zinc-400 uppercase tracking-wider">
                                  {selectedContact.company_or_role || selectedContact.web_profile?.headline || "Executive Contact"}
                                </div>
                              </div>
                            </div>

                            <button
                              onClick={() => handleEnrichContactClick(selectedContact.id || selectedContact.name, selectedContact.name)}
                              className="px-3 py-1.5 rounded-xl bg-cyan-950/80 hover:bg-cyan-900 border border-cyan-500/40 text-cyan-300 font-mono text-[10px] uppercase tracking-wider shrink-0 transition-colors cursor-pointer"
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
                          {Array.isArray(selectedContact.web_profile?.areas_of_expertise) && selectedContact.web_profile.areas_of_expertise.length > 0 && (
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
                          {Array.isArray(selectedContact.commitments) && selectedContact.commitments.length > 0 && (
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
                                            className="px-2 py-0.5 rounded bg-emerald-950/80 hover:bg-emerald-900 border border-emerald-500/40 text-emerald-300 font-mono text-[9px] uppercase transition-colors cursor-pointer"
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
                              `Executive profile for ${selectedContact.name || "contact"}: ${selectedContact.web_profile?.bio_summary || "profile indexed."}`
                            )
                          }
                          className="px-4 py-1.5 rounded-full bg-cyan-500/20 hover:bg-cyan-500/30 border border-cyan-400/40 text-cyan-300 font-mono text-xs uppercase tracking-wider font-bold transition-colors cursor-pointer"
                        >
                          🔊 Read Profile Aloud
                        </button>
                      )}
                    </div>
                  </div>
                )}

                {/* TAB 5: TOPIC DOSSIERS & EVENT SESSIONS - HIERARCHICAL FOLDERS & SPECULAR FEED */}
                {activeTab === "topics" && (
                  <div className="space-y-4 flex-1 flex flex-col justify-between animate-in fade-in duration-150">
                    <div className="space-y-4">
                      {/* Top Bar: Sub-Toggle between Folders, All Briefings, and Event Sessions */}
                      <div className="flex flex-wrap items-center justify-between gap-3 pb-1">
                        <div className="flex items-center gap-1.5 p-1 rounded-full bg-black/60 border border-white/10">
                          <button
                            onClick={() => {
                              setEchoTopicViewMode("folders");
                              setEchoFolderId(null);
                              setEchoFocusedTopicId(null);
                              setEchoSelectedSessionId(null);
                            }}
                            className={`px-3.5 py-1.5 rounded-full font-mono text-[10px] font-bold tracking-wider transition-colors cursor-pointer flex items-center gap-1.5 ${
                              echoTopicViewMode === "folders" && echoFolderId !== "event_sessions"
                                ? "bg-amber-500 text-black shadow-sm font-bold"
                                : "text-zinc-400 hover:text-white"
                            }`}
                          >
                            <span>📁</span>
                            <span>FOLDERS</span>
                          </button>
                          <button
                            onClick={() => {
                              setEchoTopicViewMode("all_feed");
                              setEchoFocusedTopicId(null);
                              setEchoSelectedSessionId(null);
                            }}
                            className={`px-3.5 py-1.5 rounded-full font-mono text-[10px] font-bold tracking-wider transition-colors cursor-pointer flex items-center gap-1.5 ${
                              echoTopicViewMode === "all_feed"
                                ? "bg-purple-500 text-white shadow-sm font-bold"
                                : "text-zinc-400 hover:text-white"
                            }`}
                          >
                            <span>📚</span>
                            <span>ALL BRIEFINGS ({topics.length})</span>
                          </button>
                          {events.length > 0 && (
                            <button
                              onClick={() => handleOpenEchoFolder("event_sessions")}
                              className={`px-3.5 py-1.5 rounded-full font-mono text-[10px] font-bold tracking-wider transition-colors cursor-pointer flex items-center gap-1.5 ${
                                echoTopicViewMode === "folders" && echoFolderId === "event_sessions"
                                  ? "bg-cyan-500 text-black shadow-sm font-bold"
                                  : "text-zinc-400 hover:text-white"
                              }`}
                            >
                              <span>⚡</span>
                              <span>EVENT SESSIONS ({events.length})</span>
                            </button>
                          )}
                        </div>

                        <div className="font-mono text-[9px] text-zinc-500 uppercase tracking-widest hidden sm:block">
                          COGNITIVE TELEMETRY // AWS BEDROCK AGENTCORE
                        </div>
                      </div>

                      {/* Breadcrumbs Navigation Bar */}
                      <DossierBreadcrumbs
                        items={echoBreadcrumbItems}
                        onNavigate={handleEchoNavigateBreadcrumb}
                        onBack={handleEchoBack}
                        canGoBack={Boolean(echoFolderId || echoFocusedTopicId || echoSelectedSessionId || echoTopicViewMode !== "folders")}
                        currentPathString={echoCurrentPathString}
                        itemCount={
                          echoFocusedTopic
                            ? 1
                            : echoActiveFolder
                            ? echoActiveFolder.isEventFolder
                              ? echoDisplayedEvents.length
                              : echoDisplayedFolderTopics.length
                            : topics.length
                        }
                        className="border border-white/10 bg-[#101217]"
                      />

                      {/* =========================================================================
                          VIEW MODE 1: HIERARCHICAL FOLDERS (LEVEL 1, LEVEL 2, LEVEL 3)
                          ========================================================================= */}
                      {echoTopicViewMode === "folders" && (
                        <div className="space-y-4">
                          {/* LEVEL 1: ROOT DIRECTORY FOLDERS GRID */}
                          {!echoFolderId && (
                            <div className="space-y-4">
                              {/* Directory Stats Banner */}
                              <div className="p-4 rounded-2xl bg-gradient-to-r from-[#12141a] via-[#161922] to-[#12141a] border border-white/10 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                                <div className="space-y-1">
                                  <div className="font-mono text-[9px] text-amber-400 tracking-[0.2em] uppercase font-bold flex items-center gap-1.5">
                                    <span>🗂️</span>
                                    <span>STRUCTURED AMBIENT KNOWLEDGE VAULT</span>
                                  </div>
                                  <h4 className="font-serif text-lg sm:text-xl text-white font-bold">
                                    Echo Research Dossier Directory
                                  </h4>
                                  <p className="font-sans text-xs text-zinc-400 max-w-xl">
                                    Topic research is grouped into specialized repositories according to semantic domain. Tap any folder to browse or inspect synthesized dossiers.
                                  </p>
                                </div>
                                <div className="flex items-center gap-2 shrink-0">
                                  <div className="px-3 py-1.5 rounded-xl bg-black/40 border border-white/10 text-center min-w-[75px]">
                                    <div className="font-mono text-base font-bold text-amber-400">{topics.length}</div>
                                    <div className="font-mono text-[8px] text-zinc-400 uppercase tracking-wider">Briefings</div>
                                  </div>
                                  <div className="px-3 py-1.5 rounded-xl bg-black/40 border border-white/10 text-center min-w-[75px]">
                                    <div className="font-mono text-base font-bold text-cyan-400">{events.length}</div>
                                    <div className="font-mono text-[8px] text-zinc-400 uppercase tracking-wider">Events</div>
                                  </div>
                                  <div className="px-3 py-1.5 rounded-xl bg-black/40 border border-white/10 text-center min-w-[75px]">
                                    <div className="font-mono text-base font-bold text-emerald-400">{echoAllFolders.length}</div>
                                    <div className="font-mono text-[8px] text-zinc-400 uppercase tracking-wider">Folders</div>
                                  </div>
                                </div>
                              </div>

                              {/* Folder Cards Grid */}
                              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3.5">
                                {echoAllFolders.map((folder) => {
                                  const count = folder.isEventFolder
                                    ? events.length
                                    : topics.filter((t) => folder.contextTypes.includes(t.context_type)).length;

                                  let secondary = "";
                                  if (count === 0) {
                                    secondary = folder.isEventFolder ? "0 Sessions" : "Empty Directory";
                                  } else if (folder.isEventFolder) {
                                    const activeEvents = events.filter((e) => e.status === "active").length;
                                    secondary = activeEvents > 0 ? `${activeEvents} Live Recording` : `${count} Concluded`;
                                  } else {
                                    const finals = topics.filter(
                                      (t) => folder.contextTypes.includes(t.context_type) && t.kind === "final"
                                    ).length;
                                    secondary = finals > 0 ? `${finals} Final Syntheses` : "Categorized";
                                  }

                                  return (
                                    <DossierFolderCard
                                      key={folder.id}
                                      folder={folder}
                                      itemCount={count}
                                      secondaryLabel={secondary}
                                      onClick={() => handleOpenEchoFolder(folder.id)}
                                    />
                                  );
                                })}
                              </div>

                              {/* Quick Access: Recent Syntheses */}
                              {topics.length > 0 && (
                                <div className="space-y-2 pt-2 border-t border-white/5">
                                  <div className="flex items-center justify-between">
                                    <span className="font-mono text-[10px] text-amber-400 tracking-wider uppercase font-bold flex items-center gap-1.5">
                                      <span>⚡</span>
                                      <span>RECENT DOSSIERS QUICK ACCESS</span>
                                    </span>
                                    <button
                                      onClick={() => setEchoTopicViewMode("all_feed")}
                                      className="font-mono text-[9px] text-zinc-400 hover:text-white tracking-widest uppercase transition-colors cursor-pointer"
                                    >
                                      View Flat Feed →
                                    </button>
                                  </div>
                                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                                    {topics.slice(0, 2).map((top) => (
                                      <div
                                        key={top.id}
                                        onClick={() => handleSelectEchoTopic(top)}
                                        className="p-3 rounded-xl bg-black/40 border border-white/10 hover:border-amber-500/40 transition-all cursor-pointer flex flex-col justify-between gap-1.5 group"
                                      >
                                        <div className="flex items-center justify-between">
                                          <span className="px-2 py-0.5 rounded text-[8px] font-mono tracking-wider uppercase bg-amber-950/30 border border-amber-500/30 text-amber-300">
                                            {top.context_type?.replace(/_/g, " ") || "RESEARCH"}
                                          </span>
                                          <span className="font-mono text-[8px] text-zinc-500">
                                            #{top.id.substring(0, 6).toUpperCase()}
                                          </span>
                                        </div>
                                        <div className="font-serif text-sm font-bold text-white group-hover:text-amber-300 transition-colors line-clamp-1">
                                          {top.topic_title}
                                        </div>
                                        {top.explanatory_synthesis && (
                                          <div className="text-zinc-400 font-sans text-xs line-clamp-1">
                                            {top.explanatory_synthesis}
                                          </div>
                                        )}
                                      </div>
                                    ))}
                                  </div>
                                </div>
                              )}
                            </div>
                          )}

                          {/* LEVEL 2: INSIDE FOLDER (TOPIC OR EVENT LISTING) */}
                          {echoFolderId && !echoFocusedTopic && !echoSelectedSessionId && (
                            <div className="space-y-4">
                              {/* Folder Header */}
                              {echoActiveFolder && (
                                <div className="p-4 rounded-2xl bg-[#12141a] border border-white/10 flex items-center justify-between gap-3">
                                  <div className="flex items-center gap-3">
                                    <div className="w-11 h-11 rounded-xl bg-black/50 border border-white/10 flex items-center justify-center text-2xl shadow-inner shrink-0">
                                      {echoActiveFolder.icon}
                                    </div>
                                    <div>
                                      <div className="font-mono text-[9px] text-amber-400 tracking-widest uppercase font-bold">
                                        DIRECTORY // {echoActiveFolder.id.toUpperCase()}
                                      </div>
                                      <h3 className="font-serif text-xl text-white font-bold">
                                        {echoActiveFolder.name}
                                      </h3>
                                      <p className="font-sans text-xs text-zinc-400 line-clamp-1">
                                        {echoActiveFolder.description}
                                      </p>
                                    </div>
                                  </div>
                                  <button
                                    onClick={handleEchoBack}
                                    className="px-3 py-1.5 rounded-xl bg-white/5 hover:bg-white/10 border border-white/10 text-zinc-300 hover:text-white font-mono text-[9px] uppercase tracking-wider font-bold shrink-0 transition-colors cursor-pointer"
                                  >
                                    ← All Folders
                                  </button>
                                </div>
                              )}

                              {/* Subfolder Filter Chips */}
                              {echoSubfolders.length > 1 && (
                                <div className="flex items-center gap-1.5 overflow-x-auto hide-scrollbar pb-0.5">
                                  {echoSubfolders.map((sub) => {
                                    const isSelected =
                                      echoSubfolderId === sub.id || (!echoSubfolderId && sub.id === "all");
                                    return (
                                      <button
                                        key={sub.id}
                                        onClick={() => setEchoSubfolderId(sub.id)}
                                        className={`px-3 py-1 rounded-full font-mono text-[9px] font-bold tracking-wider whitespace-nowrap transition-all flex items-center gap-1.5 cursor-pointer ${
                                          isSelected
                                            ? "bg-amber-500 text-black shadow-sm"
                                            : "bg-black/40 border border-white/10 text-zinc-400 hover:text-white hover:border-white/20"
                                        }`}
                                      >
                                        <span>{sub.label}</span>
                                        <span
                                          className={`px-1.5 py-0.2 rounded-full text-[8px] ${
                                            isSelected ? "bg-black/30 text-black" : "bg-white/10 text-zinc-300"
                                          }`}
                                        >
                                          {sub.count}
                                        </span>
                                      </button>
                                    );
                                  })}
                                </div>
                              )}

                              {/* Event Sessions inside Event Folder */}
                              {echoActiveFolder?.isEventFolder && (
                                <div className="space-y-3">
                                  {echoDisplayedEvents.length === 0 ? (
                                    <div className="text-center py-12 text-zinc-500 font-mono text-sm bg-black/20 rounded-2xl border border-white/5">
                                      No event sessions recorded in this folder yet.
                                    </div>
                                  ) : (
                                    echoDisplayedEvents.map((ev, idx) => (
                                      <div
                                        key={ev.session_id || idx}
                                        onClick={() => setEchoSelectedSessionId(ev.session_id)}
                                        className="p-4 rounded-xl bg-[#12141a] border border-white/10 hover:border-cyan-400/50 transition-all cursor-pointer flex flex-col gap-2.5 group"
                                      >
                                        <div className="flex items-center justify-between">
                                          <div className="flex items-center gap-2">
                                            <span
                                              className={`px-2 py-0.5 rounded border font-mono text-[8px] uppercase font-bold tracking-wider ${
                                                ev.status === "active"
                                                  ? "bg-emerald-950/80 border-emerald-500/40 text-emerald-300"
                                                  : ev.status === "paused"
                                                  ? "bg-amber-950/80 border-amber-500/40 text-amber-300"
                                                  : "bg-zinc-900 border-zinc-700 text-zinc-300"
                                              }`}
                                            >
                                              {ev.status === "active" ? "● LIVE" : ev.status === "paused" ? "⏸ PAUSED" : "✓ CONCLUDED"}
                                            </span>
                                            <span className="font-mono text-[9px] text-zinc-400 uppercase">
                                              {ev.domain || "ACADEMIC / MEETING"}
                                            </span>
                                          </div>
                                          <span className="font-mono text-[9px] text-zinc-500">
                                            {typeof ev.start_time === "string" ? ev.start_time.substring(0, 10) : "TODAY"}
                                          </span>
                                        </div>
                                        <div className="flex items-center justify-between gap-3">
                                          <h4 className="font-serif text-lg text-white font-bold group-hover:text-cyan-300 transition-colors">
                                            {ev.final_title || ev.title || "Academic Lecture / Meeting"}
                                          </h4>
                                          <span className="px-2.5 py-1 rounded-lg bg-white/5 border border-white/10 text-cyan-300 font-mono text-[9px] uppercase font-bold tracking-wider shrink-0">
                                            Inspect Session →
                                          </span>
                                        </div>
                                        {Array.isArray(ev.segments) && ev.segments.length > 0 && (
                                          <div className="font-mono text-[9px] text-zinc-400">
                                            🏛️ {ev.segments.length} Event Parts Synthesized
                                          </div>
                                        )}
                                      </div>
                                    ))
                                  )}
                                </div>
                              )}

                              {/* Topic Dossiers inside Topic Folder */}
                              {!echoActiveFolder?.isEventFolder && (
                                <div>
                                  {echoDisplayedFolderTopics.length === 0 ? (
                                    <div className="text-center py-12 text-zinc-500 font-mono text-sm bg-black/20 rounded-2xl border border-white/5">
                                      No research dossiers in this directory yet.
                                    </div>
                                  ) : (
                                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                                      {echoDisplayedFolderTopics.map((top) => (
                                        <div
                                          key={top.id}
                                          onClick={() => setEchoFocusedTopicId(top.id)}
                                          className="p-4 rounded-xl bg-[#12141a] border border-white/10 hover:border-amber-500/40 transition-all cursor-pointer flex flex-col justify-between gap-3 group"
                                        >
                                          <div className="space-y-1.5">
                                            <div className="flex items-center justify-between gap-2">
                                              <div className="flex items-center gap-1.5 flex-wrap">
                                                {top.kind && KIND_BADGES[top.kind] && (
                                                  <span
                                                    className={`px-2 py-0.5 rounded border font-mono text-[8px] uppercase tracking-wider ${
                                                      KIND_BADGES[top.kind].cls
                                                    }`}
                                                  >
                                                    {KIND_BADGES[top.kind].label}
                                                  </span>
                                                )}
                                                <span className="px-2 py-0.5 rounded bg-white/5 border border-white/10 font-mono text-[8px] text-zinc-400 uppercase">
                                                  {top.context_type?.replace(/_/g, " ") || "RESEARCH"}
                                                </span>
                                              </div>
                                              <span className="font-mono text-[8px] text-zinc-500">
                                                #{top.id.substring(0, 6).toUpperCase()}
                                              </span>
                                            </div>
                                            <h4 className="font-serif text-base font-bold text-white group-hover:text-amber-200 transition-colors line-clamp-2">
                                              {top.topic_title}
                                            </h4>
                                            {top.explanatory_synthesis && (
                                              <p className="font-sans text-xs text-zinc-400 line-clamp-2">
                                                {top.explanatory_synthesis}
                                              </p>
                                            )}
                                          </div>

                                          <div className="pt-2 border-t border-white/5 flex items-center justify-between">
                                            <div className="flex items-center gap-2 font-mono text-[9px] text-zinc-400">
                                              <span>⚡ {top.executive_summary?.length || 0} pts</span>
                                              {top.web_sources && top.web_sources.length > 0 && (
                                                <span className="text-amber-400/90">🔗 {top.web_sources.length} srcs</span>
                                              )}
                                            </div>
                                            <span className="font-mono text-[9px] text-amber-400 group-hover:translate-x-0.5 transition-transform font-bold uppercase">
                                              Open Dossier →
                                            </span>
                                          </div>
                                        </div>
                                      ))}
                                    </div>
                                  )}
                                </div>
                              )}
                            </div>
                          )}

                          {/* LEVEL 3: FOCUSED TOPIC DOSSIER */}
                          {echoFocusedTopic && (
                            <div className="p-5 rounded-2xl bg-[#12141a] border border-amber-500/40 space-y-4 animate-in fade-in">
                              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-white/10">
                                <div className="space-y-1">
                                  <div className="flex items-center gap-2 flex-wrap">
                                    <span className="font-mono text-[9px] text-amber-400 font-bold uppercase tracking-wider">
                                      📄 DOSSIER #{echoFocusedTopic.id.substring(0, 6).toUpperCase()}
                                    </span>
                                    {echoFocusedTopic.kind && KIND_BADGES[echoFocusedTopic.kind] && (
                                      <span className={`px-2 py-0.5 rounded border font-mono text-[8px] uppercase font-bold tracking-wider ${KIND_BADGES[echoFocusedTopic.kind].cls}`}>
                                        {KIND_BADGES[echoFocusedTopic.kind].label}
                                      </span>
                                    )}
                                    <span className="px-2 py-0.5 rounded bg-purple-950/80 border border-purple-500/30 text-purple-300 font-mono text-[8px] uppercase font-bold tracking-wider">
                                      {echoFocusedTopic.context_type || "TECH STACK"}
                                    </span>
                                  </div>
                                  <span className="font-mono text-[9px] text-zinc-500 block">
                                    SYNTHESIZED: {typeof echoFocusedTopic.created_at === "string" ? echoFocusedTopic.created_at.substring(0, 10) : "LIVE"}
                                  </span>
                                </div>

                                <div className="flex items-center gap-2 shrink-0 flex-wrap">
                                  {echoPrevTopic && (
                                    <button
                                      onClick={() => setEchoFocusedTopicId(echoPrevTopic.id)}
                                      className="px-2.5 py-1 rounded-lg border border-white/10 bg-white/5 hover:bg-white/10 text-zinc-300 font-mono text-[9px] font-bold uppercase cursor-pointer"
                                      title="Previous dossier"
                                    >
                                      ← Prev
                                    </button>
                                  )}
                                  {echoNextTopic && (
                                    <button
                                      onClick={() => setEchoFocusedTopicId(echoNextTopic.id)}
                                      className="px-2.5 py-1 rounded-lg border border-white/10 bg-white/5 hover:bg-white/10 text-zinc-300 font-mono text-[9px] font-bold uppercase cursor-pointer"
                                      title="Next dossier"
                                    >
                                      Next →
                                    </button>
                                  )}
                                  <button
                                    onClick={() => handleDownloadEchoTopic(echoFocusedTopic)}
                                    className="px-3 py-1 rounded-lg bg-amber-950/80 hover:bg-amber-900 border border-amber-500/40 text-amber-300 font-mono text-[10px] uppercase tracking-wider font-bold transition-colors cursor-pointer flex items-center gap-1.5"
                                    title="Download markdown dossier"
                                  >
                                    <span>💾</span>
                                    <span>Download .md</span>
                                  </button>
                                  <button
                                    onClick={() =>
                                      speakAlexaReassurance(
                                        `Briefing for ${echoFocusedTopic.topic_title}: ${echoFocusedTopic.explanatory_synthesis || (Array.isArray(echoFocusedTopic.executive_summary) ? echoFocusedTopic.executive_summary[0] : null) || "Analysis complete."}`
                                      )
                                    }
                                    className="px-3 py-1 rounded-lg bg-purple-500/20 hover:bg-purple-500/30 border border-purple-400/40 text-purple-300 font-mono text-[10px] uppercase tracking-wider font-bold transition-colors cursor-pointer flex items-center gap-1.5"
                                  >
                                    <span>🔊</span>
                                    <span>Read Aloud</span>
                                  </button>
                                </div>
                              </div>

                              <h3 className="font-serif text-2xl text-white font-bold">
                                {echoFocusedTopic.topic_title}
                              </h3>

                              {/* Thesis */}
                              {echoFocusedTopic.explanatory_synthesis && (
                                <div className="p-3.5 rounded-xl bg-amber-950/20 border border-amber-500/30 text-amber-200 font-sans text-sm leading-relaxed">
                                  ⚡ <strong className="font-mono text-[10px] tracking-wider uppercase text-amber-300 mr-1">Thesis:</strong>
                                  {echoFocusedTopic.explanatory_synthesis}
                                </div>
                              )}

                              {/* Event parts timeline if briefing is part of an event session */}
                              {Array.isArray((echoFocusedTopic as any).segments) && (echoFocusedTopic as any).segments.length > 0 && (
                                <div className="bg-black/40 border border-white/10 rounded-xl p-3.5 space-y-2">
                                  <div className="font-mono text-[10px] tracking-wider text-cyan-300 uppercase flex items-center justify-between">
                                    <span>🏛️ Event parts</span>
                                    <span className="text-zinc-400">
                                      {String((echoFocusedTopic as any).status || "").toUpperCase()}
                                    </span>
                                  </div>
                                  <div className="space-y-1.5">
                                    {(echoFocusedTopic as any).segments.map((seg: any, idx: number) => (
                                      <div
                                        key={seg?.index ?? idx}
                                        className="flex items-center justify-between gap-3 text-xs bg-black/30 p-2 rounded border border-white/5"
                                      >
                                        <span className="text-zinc-200 truncate flex items-center gap-2">
                                          <span className="font-mono text-[10px] text-cyan-400 font-bold">
                                            #{seg?.index ?? idx + 1}
                                          </span>
                                          <span className="truncate">{seg?.title || "Part " + (seg?.index ?? idx + 1)}</span>
                                        </span>
                                        <span className="font-mono text-[9px] text-zinc-400 shrink-0">{seg?.time_range || ""}</span>
                                      </div>
                                    ))}
                                  </div>
                                </div>
                              )}

                              {/* Bullets */}
                              {Array.isArray(echoFocusedTopic.executive_summary) && echoFocusedTopic.executive_summary.length > 0 && (
                                <div className="space-y-1.5">
                                  <div className="font-mono text-[9px] text-zinc-400 tracking-widest uppercase">Key Insights:</div>
                                  <ul className="space-y-1 text-xs text-zinc-200 font-sans">
                                    {echoFocusedTopic.executive_summary.map((b, i) => (
                                      <li key={i} className="flex items-start gap-2">
                                        <span className="text-amber-400 font-bold">•</span>
                                        <span>{b}</span>
                                      </li>
                                    ))}
                                  </ul>
                                </div>
                              )}

                              {/* Deep Dive Markdown Section on Echo Show */}
                              {echoFocusedTopic.deep_dive_markdown && (
                                <div className="space-y-2 pt-2 border-t border-white/10">
                                  <MarkdownRenderer
                                    content={echoFocusedTopic.deep_dive_markdown}
                                    allowRawToggle={true}
                                    defaultMode="rendered"
                                    title="Technical Report"
                                    filename={sanitizeFilename(echoFocusedTopic.topic_title, ".md")}
                                    accentColor="amber"
                                    showDownloadButton={true}
                                    showCopyButton={true}
                                  />
                                </div>
                              )}

                              {/* Web Sources */}
                              {Array.isArray(echoFocusedTopic.web_sources) && echoFocusedTopic.web_sources.length > 0 && (
                                <div className="pt-2 border-t border-white/10 flex flex-wrap gap-2">
                                  <span className="font-mono text-[9px] text-zinc-400 uppercase tracking-wider">Sources:</span>
                                  {echoFocusedTopic.web_sources.slice(0, 3).map((src, i) => {
                                    const url = typeof src === "string" ? src : (src as any)?.url || "";
                                    const label = typeof src === "string" ? src : (src as any)?.title || url || "Source";
                                    return (
                                      <a
                                        key={i}
                                        href={url}
                                        target="_blank"
                                        rel="noreferrer"
                                        className="text-[10px] font-mono text-amber-300 hover:underline truncate max-w-xs"
                                      >
                                        🔗 {label}
                                      </a>
                                    );
                                  })}
                                </div>
                              )}

                              {/* Return to Folder Button */}
                              <div className="pt-3 border-t border-white/10 flex items-center justify-between">
                                <button
                                  onClick={() => setEchoFocusedTopicId(null)}
                                  className="px-3.5 py-1.5 rounded-xl bg-white/5 hover:bg-white/10 border border-white/10 text-zinc-200 font-mono text-[10px] uppercase font-bold tracking-wider cursor-pointer flex items-center gap-1.5"
                                >
                                  <span>←</span>
                                  <span>Return to {echoActiveFolder?.name || "Folder"} Directory</span>
                                </button>
                                <span className="font-mono text-[9px] text-zinc-500 uppercase tracking-wider">
                                  {echoFocusedIndex >= 0 ? `Entry ${echoFocusedIndex + 1} of ${echoDisplayedFolderTopics.length}` : ""}
                                </span>
                              </div>
                            </div>
                          )}

                          {/* LEVEL 3: FOCUSED EVENT SESSION */}
                          {echoSelectedSessionId && echoFocusedEvent && (
                            <div className="p-5 rounded-2xl bg-[#12141a] border border-cyan-500/40 space-y-4 animate-in fade-in">
                              <div className="flex items-center justify-between">
                                <div className="flex items-center gap-2">
                                  <span
                                    className={`px-2.5 py-0.5 rounded border font-mono text-[9px] uppercase font-bold tracking-wider ${
                                      echoFocusedEvent.status === "active"
                                        ? "bg-emerald-950/80 border-emerald-500/40 text-emerald-300"
                                        : echoFocusedEvent.status === "paused"
                                        ? "bg-amber-950/80 border-amber-500/40 text-amber-300"
                                        : "bg-zinc-900 border-zinc-700 text-zinc-300"
                                    }`}
                                  >
                                    {echoFocusedEvent.status === "active"
                                      ? "● LIVE"
                                      : echoFocusedEvent.status === "paused"
                                      ? "⏸ PAUSED"
                                      : "✓ CONCLUDED"}
                                  </span>
                                  <span className="font-mono text-[9px] text-zinc-400 uppercase">
                                    {echoFocusedEvent.domain || "ACADEMIC / MEETING"}
                                  </span>
                                </div>
                                <span className="font-mono text-[9px] text-zinc-500">
                                  {typeof echoFocusedEvent.start_time === "string" ? echoFocusedEvent.start_time.substring(0, 10) : "TODAY"}
                                </span>
                              </div>

                              <h3 className="font-serif text-2xl text-white font-bold">
                                {echoFocusedEvent.final_title || echoFocusedEvent.title || "Academic Lecture / Meeting"}
                              </h3>

                              {/* Event parts timeline (SESSION_DOSSIER_VIEWER) */}
                              {Array.isArray(echoFocusedEvent.segments) && echoFocusedEvent.segments.length > 0 && (
                                <div className="bg-black/40 border border-white/10 rounded-xl p-3.5 space-y-2">
                                  <div className="font-mono text-[10px] tracking-wider text-cyan-300 uppercase flex items-center justify-between">
                                    <span>🏛️ Event parts ({echoFocusedEvent.segments.length})</span>
                                    <span className="text-zinc-400">
                                      {String(echoFocusedEvent.status || "").toUpperCase()}
                                      {echoFocusedEvent.final_status !== "ready" ? " · PARTIAL BRIEFING" : " · FINAL"}
                                    </span>
                                  </div>
                                  <div className="space-y-1.5">
                                    {echoFocusedEvent.segments.map((seg: any, idx: number) => (
                                      <div
                                        key={seg?.index ?? seg?.segment_id ?? idx}
                                        className="flex items-center justify-between gap-3 text-xs bg-black/30 p-2 rounded border border-white/5"
                                      >
                                        <span className="text-zinc-200 truncate flex items-center gap-2">
                                          <span className="font-mono text-[10px] text-cyan-400 font-bold">
                                            #{seg?.index ?? idx + 1}
                                          </span>
                                          <span className="truncate">
                                            {seg?.title || (seg?.status === "open" ? "Recording utterance stream…" : "Awaiting synthesis")}
                                          </span>
                                        </span>
                                        <span className="font-mono text-[9px] text-zinc-400 shrink-0">{seg?.time_range || ""}</span>
                                      </div>
                                    ))}
                                  </div>
                                </div>
                              )}

                              {/* Top Terms */}
                              {Array.isArray(echoFocusedEvent.top_terms) && echoFocusedEvent.top_terms.length > 0 && (
                                <div className="flex flex-wrap gap-1.5 pt-1">
                                  {echoFocusedEvent.top_terms.map((term: string, idx: number) => (
                                    <span
                                      key={idx}
                                      className="px-2 py-0.5 rounded bg-cyan-950/40 border border-cyan-500/20 text-cyan-300 font-mono text-[9px]"
                                    >
                                      #{term}
                                    </span>
                                  ))}
                                </div>
                              )}

                              {/* Return to Event Sessions Folder */}
                              <div className="pt-3 border-t border-white/10 flex items-center justify-between">
                                <button
                                  onClick={() => setEchoSelectedSessionId(null)}
                                  className="px-3.5 py-1.5 rounded-xl bg-white/5 hover:bg-white/10 border border-white/10 text-zinc-200 font-mono text-[10px] uppercase font-bold tracking-wider cursor-pointer flex items-center gap-1.5"
                                >
                                  <span>←</span>
                                  <span>Return to Event Sessions Directory</span>
                                </button>
                                <button
                                  onClick={() =>
                                    speakAlexaReassurance(
                                      `Event summary for ${echoFocusedEvent.final_title || echoFocusedEvent.title || "Academic Lecture"}: ${echoFocusedEvent.segments?.length || 0} recorded segments recorded into memory.`
                                    )
                                  }
                                  className="px-3 py-1 rounded-lg bg-cyan-500/20 hover:bg-cyan-500/30 border border-cyan-400/40 text-cyan-300 font-mono text-[10px] uppercase tracking-wider font-bold transition-colors cursor-pointer"
                                >
                                  🔊 Read Event Summary
                                </button>
                              </div>
                            </div>
                          )}
                        </div>
                      )}

                      {/* =========================================================================
                          VIEW MODE 2: SPECULAR FLAT FEED (ALL BRIEFINGS)
                          ========================================================================= */}
                      {echoTopicViewMode === "all_feed" && (
                        <div className="space-y-4">
                          {/* Topics Pill Selector with Category Filter */}
                          {topics.length > 0 && (
                            <div className="space-y-2">
                              {/* Category Filter Pills */}
                              <div className="flex items-center gap-1.5 overflow-x-auto hide-scrollbar pb-0.5">
                                {topicCategories.map((cat) => (
                                  <button
                                    key={cat}
                                    onClick={() => {
                                      setEchoTopicCategory(cat);
                                      setSelectedTopicIndex(0);
                                    }}
                                    className={`px-2.5 py-1 rounded-full font-mono text-[9px] uppercase font-bold tracking-wider transition-colors shrink-0 cursor-pointer ${
                                      echoTopicCategory === cat
                                        ? "bg-purple-500 text-white shadow-sm"
                                        : "bg-black/40 text-zinc-400 hover:text-white border border-white/10"
                                    }`}
                                  >
                                    {cat ? cat.replace(/_/g, " ") : "ALL"}
                                  </button>
                                ))}
                              </div>

                              {/* Topics Pill Carousel */}
                              <div className="flex items-center gap-2 overflow-x-auto hide-scrollbar pb-1">
                                {echoFilteredTopics.map((t, idx) => (
                                  <button
                                    key={t.id || idx}
                                    onClick={() => setSelectedTopicIndex(idx)}
                                    className={`px-3 py-1.5 rounded-xl font-mono text-xs whitespace-nowrap transition-all cursor-pointer ${
                                      selectedTopicIndex === idx
                                        ? "bg-purple-500 text-white font-bold shadow-md shadow-purple-500/30"
                                        : "bg-black/40 text-zinc-400 hover:text-white border border-white/10"
                                    }`}
                                  >
                                    {t.topic_title || "Untitled Briefing"}
                                  </button>
                                ))}
                              </div>
                            </div>
                          )}

                          {selectedTopic ? (
                            <div className="p-5 rounded-2xl bg-[#12141a] border border-white/10 space-y-4">
                              <div className="flex items-center justify-between">
                                <div className="flex items-center gap-2">
                                  {selectedTopic.kind && Object.prototype.hasOwnProperty.call(KIND_BADGES, selectedTopic.kind) && KIND_BADGES[selectedTopic.kind] && (
                                    <span className={`px-2.5 py-0.5 rounded border font-mono text-[9px] uppercase font-bold tracking-wider ${KIND_BADGES[selectedTopic.kind].cls}`}>
                                      {KIND_BADGES[selectedTopic.kind].label}
                                    </span>
                                  )}
                                  <span className="px-2.5 py-0.5 rounded bg-purple-950/80 border border-purple-500/30 text-purple-300 font-mono text-[9px] uppercase font-bold tracking-wider">
                                    {selectedTopic.context_type || "TECH STACK"}
                                  </span>
                                </div>
                                <span className="font-mono text-[9px] text-zinc-500">
                                  {typeof selectedTopic.created_at === "string" ? selectedTopic.created_at.substring(0, 10) : "LIVE"}
                                </span>
                              </div>

                              <div className="flex items-start justify-between gap-3">
                                <h3 className="font-serif text-2xl text-white font-bold">
                                  {selectedTopic.topic_title}
                                </h3>

                                <button
                                  onClick={() => handleDownloadEchoTopic(selectedTopic)}
                                  className="px-3 py-1 rounded-lg bg-purple-950/80 hover:bg-purple-900 border border-purple-500/40 text-purple-300 font-mono text-[10px] uppercase tracking-wider font-bold shrink-0 transition-colors cursor-pointer flex items-center gap-1.5"
                                  title="Download markdown dossier"
                                >
                                  <span>💾</span>
                                  <span>Download .md</span>
                                </button>
                              </div>

                              {/* Synthesis */}
                              {selectedTopic.explanatory_synthesis && (
                                <div className="p-3.5 rounded-xl bg-amber-950/20 border border-amber-500/30 text-amber-200 font-sans text-sm leading-relaxed">
                                  ⚡ <strong className="font-mono text-[10px] tracking-wider uppercase text-amber-300 mr-1">Thesis:</strong>
                                  {selectedTopic.explanatory_synthesis}
                                </div>
                              )}

                              {/* Bullets */}
                              {Array.isArray(selectedTopic.executive_summary) && selectedTopic.executive_summary.length > 0 && (
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

                              {/* Deep Dive Markdown Section on Echo Show */}
                              {selectedTopic.deep_dive_markdown && (
                                <div className="space-y-2 pt-2 border-t border-white/10">
                                  <MarkdownRenderer
                                    content={selectedTopic.deep_dive_markdown}
                                    allowRawToggle={true}
                                    defaultMode="rendered"
                                    title="Technical Report"
                                    filename={sanitizeFilename(selectedTopic.topic_title, ".md")}
                                    accentColor="purple"
                                    showDownloadButton={true}
                                    showCopyButton={true}
                                  />
                                </div>
                              )}

                              {/* Web Sources */}
                              {Array.isArray(selectedTopic.web_sources) && selectedTopic.web_sources.length > 0 && (
                                <div className="pt-2 border-t border-white/10 flex flex-wrap gap-2">
                                  <span className="font-mono text-[9px] text-zinc-400 uppercase tracking-wider">Sources:</span>
                                  {selectedTopic.web_sources.slice(0, 3).map((src, i) => {
                                    const url = typeof src === "string" ? src : (src as any)?.url || "";
                                    const label = typeof src === "string" ? src : (src as any)?.title || url || "Source";
                                    return (
                                      <a
                                        key={i}
                                        href={url}
                                        target="_blank"
                                        rel="noreferrer"
                                        className="text-[10px] font-mono text-purple-300 hover:underline truncate max-w-xs"
                                      >
                                        🔗 {label}
                                      </a>
                                    );
                                  })}
                                </div>
                              )}
                            </div>
                          ) : (
                            <div className="text-center py-12 text-zinc-500 font-mono text-sm">
                              No technical research dossiers compiled yet.
                            </div>
                          )}
                        </div>
                      )}
                    </div>

                    {/* Bottom Status & Voice Reassurance Bar */}
                    <div className="pt-3 border-t border-white/10 flex items-center justify-between">
                      <span className="text-xs font-mono text-zinc-400">
                        Research Engine: <strong className="text-purple-400">AWS BEDROCK + DUCKDUCKGO</strong>
                      </span>
                      {echoTopicViewMode === "folders" && echoFocusedTopic ? (
                        <div className="flex items-center gap-2">
                          <button
                            onClick={() => handleDownloadEchoTopic(echoFocusedTopic)}
                            className="px-3.5 py-1.5 rounded-full bg-amber-950/80 hover:bg-amber-900 border border-amber-500/40 text-amber-300 font-mono text-xs uppercase tracking-wider font-bold transition-colors cursor-pointer flex items-center gap-1.5"
                          >
                            <span>💾</span>
                            <span>Download .md</span>
                          </button>
                          <button
                            onClick={() =>
                              speakAlexaReassurance(
                                `Briefing for ${echoFocusedTopic.topic_title}: ${echoFocusedTopic.explanatory_synthesis || (Array.isArray(echoFocusedTopic.executive_summary) ? echoFocusedTopic.executive_summary[0] : null) || "Analysis complete."}`
                              )
                            }
                            className="px-4 py-1.5 rounded-full bg-purple-500/20 hover:bg-purple-500/30 border border-purple-400/40 text-purple-300 font-mono text-xs uppercase tracking-wider font-bold transition-colors cursor-pointer"
                          >
                            🔊 Read Dossier Aloud
                          </button>
                        </div>
                      ) : echoTopicViewMode === "folders" && echoSelectedSessionId && echoFocusedEvent ? (
                        <button
                          onClick={() =>
                            speakAlexaReassurance(
                              `Event summary for ${echoFocusedEvent.final_title || echoFocusedEvent.title || "Academic Lecture"}: ${echoFocusedEvent.segments?.length || 0} recorded segments recorded into memory.`
                            )
                          }
                          className="px-4 py-1.5 rounded-full bg-cyan-500/20 hover:bg-cyan-500/30 border border-cyan-400/40 text-cyan-300 font-mono text-xs uppercase tracking-wider font-bold transition-colors cursor-pointer"
                        >
                          🔊 Read Event Summary
                        </button>
                      ) : echoTopicViewMode === "all_feed" && selectedTopic ? (
                        <div className="flex items-center gap-2">
                          <button
                            onClick={() => handleDownloadEchoTopic(selectedTopic)}
                            className="px-3.5 py-1.5 rounded-full bg-purple-950/80 hover:bg-purple-900 border border-purple-500/40 text-purple-300 font-mono text-xs uppercase tracking-wider font-bold transition-colors cursor-pointer flex items-center gap-1.5"
                          >
                            <span>💾</span>
                            <span>Download .md</span>
                          </button>
                          <button
                            onClick={() =>
                              speakAlexaReassurance(
                                `Briefing for ${selectedTopic.topic_title}: ${selectedTopic.explanatory_synthesis || (Array.isArray(selectedTopic.executive_summary) ? selectedTopic.executive_summary[0] : null) || "Analysis complete."}`
                              )
                            }
                            className="px-4 py-1.5 rounded-full bg-purple-500/20 hover:bg-purple-500/30 border border-purple-400/40 text-purple-300 font-mono text-xs uppercase tracking-wider font-bold transition-colors cursor-pointer"
                          >
                            🔊 Read Dossier Aloud
                          </button>
                        </div>
                      ) : (
                        <span className="font-mono text-[10px] text-zinc-500 uppercase tracking-wider">
                          Autonomous Ambient Knowledge Vault
                        </span>
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
                        className="px-4 py-1.5 rounded-full bg-cyan-500/20 hover:bg-cyan-500/30 border border-cyan-400/40 text-cyan-300 font-mono text-xs uppercase tracking-wider font-bold transition-colors cursor-pointer"
                      >
                        🔊 Test Echo Audio
                      </button>
                    </div>
                  </div>
                )}
              </EchoShowErrorBoundary>
            </div>
          </div>
        </div>
      </div>
    </div>,
    document.body
  );
}
