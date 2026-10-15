import React, { useState, useMemo } from "react";
import {
  BriefingReport,
  EventEngineStatus,
  EventSummary,
  DossierFolderDef,
  DossierBreadcrumbItem,
} from "@/types/schemas";
import { ScreenHeader } from "../ui/ScreenHeader";
import { StatusBadge } from "../ui/StatusBadge";
import { TopicDetailModal } from "../ui/TopicDetailModal";
import { EventAction, EventCard } from "../ui/EventCard";
import { DossierBreadcrumbs } from "../ui/DossierBreadcrumbs";
import { DossierFolderCard } from "../ui/DossierFolderCard";
import { speakAlexaReassurance } from "@/utils/audioEffects";
import { MarkdownRenderer } from "../ui/MarkdownRenderer";
import {
  generateTopicMarkdown,
  downloadTextFile,
  sanitizeFilename,
} from "@/utils/dossierExport";

interface SubfolderItem {
  id: string;
  label: string;
  count: number;
  topicFilter?: (t: BriefingReport) => boolean;
  eventFilter?: (e: EventSummary) => boolean;
}

interface TopicDossiersProps {
  topicsData: { topics: BriefingReport[] } | undefined;
  statusData?: any;
  sessionsData?: { sessions: EventSummary[] };
  engineStatus?: EventEngineStatus;
  onEventAction?: (action: EventAction, event: EventSummary, extra?: Record<string, any>) => Promise<void>;
}

const KIND_BADGES: Record<string, { label: string; cls: string }> = {
  final: { label: "★ EVENT FINAL", cls: "text-amber-300 border-amber-500/50 bg-amber-950/40" },
  segment: { label: "EVENT PART", cls: "text-cyan-300 border-cyan-500/40 bg-cyan-950/30" },
  checkpoint: { label: "CHECKPOINT", cls: "text-cyan-300 border-cyan-500/40 bg-cyan-950/30" },
  standalone: { label: "STANDALONE", cls: "text-zinc-300 border-white/10 bg-[#1c1f26]" },
};

const DEFAULT_FOLDERS: DossierFolderDef[] = [
  {
    id: "academic",
    name: "Academic & Lectures",
    icon: "🏛️",
    accent: "amber",
    description: "University lectures, symposiums, theoretical foundations & scientific research",
    contextTypes: ["academic_lecture"],
  },
  {
    id: "tech_stack",
    name: "Tech Stack & Systems",
    icon: "💻",
    accent: "cyan",
    description: "System architecture, distributed algorithms, AI frameworks & protocols",
    contextTypes: ["tech_stack"],
  },
  {
    id: "engineering",
    name: "Product & Engineering",
    icon: "🚀",
    accent: "emerald",
    description: "Feature specs, engineering standups, bug postmortems & incident reports",
    contextTypes: ["feature_discussion", "bug", "system_incident"],
  },
  {
    id: "business",
    name: "Strategy & Business",
    icon: "💼",
    accent: "purple",
    description: "Executive debriefs, roadmap planning, stakeholder meetings & leadership syncs",
    contextTypes: ["general_meeting"],
  },
  {
    id: "event_sessions",
    name: "Event Sessions & Symposia",
    icon: "⚡",
    accent: "blue",
    description: "Deep Topic Event Engine multi-part macro recordings with live synthesis",
    contextTypes: [],
    isEventFolder: true,
  },
];

export function TopicDossiers({
  topicsData,
  statusData,
  sessionsData,
  engineStatus,
  onEventAction,
}: TopicDossiersProps) {
  const events = sessionsData?.sessions || [];
  const topics = topicsData?.topics || [];

  // Top-level Navigation & Folder States
  const [viewMode, setViewMode] = useState<"folders" | "all_feed">("folders");
  const [currentFolderId, setCurrentFolderId] = useState<string | null>(null);
  const [currentSubfolderId, setCurrentSubfolderId] = useState<string | null>(null);
  const [focusedTopicId, setFocusedTopicId] = useState<string | null>(null);
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);

  // Search & Display layout
  const [searchQuery, setSearchQuery] = useState("");
  const [layoutMode, setLayoutMode] = useState<"grid" | "list">("grid");
  const [modalTopic, setModalTopic] = useState<BriefingReport | null>(null);
  const [broadcastedId, setBroadcastedId] = useState<string | null>(null);
  const [feedFilter, setFeedFilter] = useState<string>("ALL");

  // Telemetry Metrics
  const reasonerModel = (
    statusData?.telemetry?.processing_model?.reasoner ||
    statusData?.config?.reasoner_model ||
    "AWS BEDROCK AGENTCORE"
  ).toUpperCase();
  const latencyMetrics = statusData?.telemetry?.latency;
  const avgLatency = latencyMetrics?.average_ms
    ? `${latencyMetrics.average_ms}MS (AVG)`
    : "BACKGROUND STANDBY";

  // Build complete list of folders including any dynamic / custom context types
  const allFolders: DossierFolderDef[] = useMemo(() => {
    const knownTypes = new Set(DEFAULT_FOLDERS.flatMap((f) => f.contextTypes));
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

    return [...DEFAULT_FOLDERS, ...dynamicFolders];
  }, [topics]);

  // Active folder object
  const activeFolder = useMemo(
    () => allFolders.find((f) => f.id === currentFolderId) || null,
    [allFolders, currentFolderId]
  );

  // Filter topics for the current active folder
  const folderTopics = useMemo(() => {
    if (!activeFolder || activeFolder.isEventFolder) return [];
    return topics.filter((t) => activeFolder.contextTypes.includes(t.context_type));
  }, [activeFolder, topics]);

  // Focused topic dossier object (Level 3 drill-down)
  const focusedTopic = useMemo(() => {
    if (!focusedTopicId) return null;
    return topics.find((t) => t.id === focusedTopicId) || null;
  }, [topics, focusedTopicId]);

  // Subfolders definition for active folder
  const subfolders: SubfolderItem[] = useMemo(() => {
    if (!activeFolder) return [];

    if (activeFolder.isEventFolder) {
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

    if (activeFolder.id === "academic") {
      return [
        { id: "all", label: "ALL ACADEMIC", count: folderTopics.length },
        {
          id: "lectures",
          label: "LECTURES & SYLLABI",
          count: folderTopics.filter((t) => t.kind !== "final").length,
          topicFilter: (t: BriefingReport) => t.kind !== "final",
        },
        {
          id: "final",
          label: "FINAL SYNTHESES",
          count: folderTopics.filter((t) => t.kind === "final").length,
          topicFilter: (t: BriefingReport) => t.kind === "final",
        },
        {
          id: "sources",
          label: "WITH CITATIONS",
          count: folderTopics.filter((t) => Boolean(t.web_sources && t.web_sources.length > 0)).length,
          topicFilter: (t: BriefingReport) => Boolean(t.web_sources && t.web_sources.length > 0),
        },
      ];
    }

    if (activeFolder.id === "tech_stack") {
      return [
        { id: "all", label: "ALL TECH TOPICS", count: folderTopics.length },
        {
          id: "deep_dive",
          label: "DEEP RESEARCH MARKDOWN",
          count: folderTopics.filter((t) => Boolean(t.deep_dive_markdown)).length,
          topicFilter: (t: BriefingReport) => Boolean(t.deep_dive_markdown),
        },
        {
          id: "citations",
          label: "WITH CITATIONS",
          count: folderTopics.filter((t) => Boolean(t.web_sources && t.web_sources.length > 0)).length,
          topicFilter: (t: BriefingReport) => Boolean(t.web_sources && t.web_sources.length > 0),
        },
        {
          id: "actions",
          label: "ACTION ITEMS",
          count: folderTopics.filter((t) => Boolean(t.action_items && t.action_items.length > 0)).length,
          topicFilter: (t: BriefingReport) => Boolean(t.action_items && t.action_items.length > 0),
        },
      ];
    }

    if (activeFolder.id === "engineering") {
      return [
        { id: "all", label: "ALL PRODUCT TOPICS", count: folderTopics.length },
        {
          id: "features",
          label: "FEATURE PROPOSALS",
          count: folderTopics.filter((t) => t.context_type === "feature_discussion").length,
          topicFilter: (t: BriefingReport) => t.context_type === "feature_discussion",
        },
        {
          id: "incidents",
          label: "BUGS & INCIDENTS",
          count: folderTopics.filter(
            (t) => t.context_type === "bug" || t.context_type === "system_incident"
          ).length,
          topicFilter: (t: BriefingReport) =>
            t.context_type === "bug" || t.context_type === "system_incident",
        },
        {
          id: "sources",
          label: "WITH CITATIONS",
          count: folderTopics.filter((t) => Boolean(t.web_sources && t.web_sources.length > 0)).length,
          topicFilter: (t: BriefingReport) => Boolean(t.web_sources && t.web_sources.length > 0),
        },
      ];
    }

    if (activeFolder.id === "business") {
      return [
        { id: "all", label: "ALL BUSINESS", count: folderTopics.length },
        {
          id: "actions",
          label: "WITH ACTION ITEMS",
          count: folderTopics.filter((t) => Boolean(t.action_items && t.action_items.length > 0)).length,
          topicFilter: (t: BriefingReport) => Boolean(t.action_items && t.action_items.length > 0),
        },
        {
          id: "briefs",
          label: "EXECUTIVE BRIEFS",
          count: folderTopics.filter((t) => Boolean(t.executive_summary && t.executive_summary.length > 0)).length,
          topicFilter: (t: BriefingReport) => Boolean(t.executive_summary && t.executive_summary.length > 0),
        },
      ];
    }

    return [
      { id: "all", label: "ALL ITEMS", count: folderTopics.length },
      {
        id: "citations",
        label: "WITH CITATIONS",
        count: folderTopics.filter((t) => Boolean(t.web_sources && t.web_sources.length > 0)).length,
        topicFilter: (t: BriefingReport) => Boolean(t.web_sources && t.web_sources.length > 0),
      },
    ];
  }, [activeFolder, folderTopics, events]);

  // Topics displayed inside active folder after subfolder filter + search
  const displayedFolderTopics = useMemo(() => {
    let result = folderTopics;

    if (currentSubfolderId && currentSubfolderId !== "all") {
      const sub = subfolders.find((s) => s.id === currentSubfolderId);
      if (sub && sub.topicFilter) {
        result = result.filter(sub.topicFilter);
      }
    }

    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      result = result.filter(
        (t) =>
          t.topic_title.toLowerCase().includes(q) ||
          (t.explanatory_synthesis || "").toLowerCase().includes(q) ||
          (t.executive_summary || []).some((s) => s.toLowerCase().includes(q)) ||
          (t.action_items || []).some((a) => a.toLowerCase().includes(q)) ||
          (t.context_type || "").toLowerCase().includes(q)
      );
    }

    return result;
  }, [folderTopics, currentSubfolderId, subfolders, searchQuery]);

  // Event sessions displayed inside event folder after subfolder filter + search
  const displayedEvents = useMemo(() => {
    let result = events;

    if (activeFolder?.isEventFolder && currentSubfolderId && currentSubfolderId !== "all") {
      const sub = subfolders.find((s) => s.id === currentSubfolderId);
      if (sub && sub.eventFilter) {
        result = result.filter(sub.eventFilter);
      }
    }

    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      result = result.filter(
        (ev) =>
          (ev.title || "").toLowerCase().includes(q) ||
          (ev.final_title || "").toLowerCase().includes(q) ||
          (ev.top_terms || []).some((t) => (t || "").toLowerCase().includes(q)) ||
          (ev.segments || []).some((s) => (s.title || "").toLowerCase().includes(q))
      );
    }

    return result;
  }, [events, activeFolder, currentSubfolderId, subfolders, searchQuery]);

  // Global search across ALL topics and events (when searching at root)
  const globalSearchResults = useMemo(() => {
    if (!searchQuery.trim()) return { topics: [], events: [] };
    const q = searchQuery.toLowerCase();

    const matchedTopics = topics.filter(
      (t) =>
        t.topic_title.toLowerCase().includes(q) ||
        (t.explanatory_synthesis || "").toLowerCase().includes(q) ||
        (t.executive_summary || []).some((s) => s.toLowerCase().includes(q)) ||
        (t.action_items || []).some((a) => a.toLowerCase().includes(q)) ||
        (t.context_type || "").toLowerCase().includes(q)
    );

    const matchedEvents = events.filter(
      (ev) =>
        (ev.title || "").toLowerCase().includes(q) ||
        (ev.final_title || "").toLowerCase().includes(q) ||
        (ev.top_terms || []).some((t) => (t || "").toLowerCase().includes(q)) ||
        (ev.segments || []).some((s) => (s.title || "").toLowerCase().includes(q))
    );

    return { topics: matchedTopics, events: matchedEvents };
  }, [searchQuery, topics, events]);

  // Flat feed filtered topics (when user selects "ALL DOSSIERS" feed mode)
  const flatFeedTopics = useMemo(() => {
    return topics.filter((t) => {
      const matchesFilter = feedFilter === "ALL" || t.context_type === feedFilter;
      if (!matchesFilter) return false;
      if (!searchQuery.trim()) return true;
      const q = searchQuery.toLowerCase();
      return (
        t.topic_title.toLowerCase().includes(q) ||
        (t.explanatory_synthesis || "").toLowerCase().includes(q) ||
        (t.executive_summary || []).some((s) => s.toLowerCase().includes(q)) ||
        (t.action_items || []).some((a) => a.toLowerCase().includes(q)) ||
        (t.context_type || "").toLowerCase().includes(q)
      );
    });
  }, [topics, feedFilter, searchQuery]);

  // Unique contexts for flat feed filter
  const uniqueContexts = useMemo(
    () => Array.from(new Set(topics.map((t) => t.context_type))).filter(Boolean),
    [topics]
  );

  // Breadcrumbs Generation (4-Level hierarchy: Root -> Folder -> Subfolder -> Dossier)
  const breadcrumbItems: DossierBreadcrumbItem[] = useMemo(() => {
    const items: DossierBreadcrumbItem[] = [
      {
        id: "root",
        label: "DOSSIERS REPOSITORY",
        icon: "📁",
        count: topics.length,
      },
    ];

    if (viewMode === "all_feed") {
      items.push({
        id: "all_feed",
        label: "ALL DOSSIERS FEED",
        icon: "📚",
        count: flatFeedTopics.length,
      });
      return items;
    }

    if (activeFolder) {
      items.push({
        id: activeFolder.id,
        label: activeFolder.name,
        icon: activeFolder.icon,
        count: activeFolder.isEventFolder ? events.length : folderTopics.length,
      });

      if (currentSubfolderId && currentSubfolderId !== "all") {
        const sub = subfolders.find((s) => s.id === currentSubfolderId);
        if (sub) {
          items.push({
            id: sub.id,
            label: sub.label,
            icon: "📂",
            count: sub.count,
          });
        }
      }

      if (selectedSessionId && activeFolder.isEventFolder) {
        const ev = events.find((e) => e.session_id === selectedSessionId);
        items.push({
          id: selectedSessionId,
          label: ev?.final_title || ev?.title || "EVENT SESSION",
          icon: "🏛️",
        });
      }

      if (focusedTopic) {
        items.push({
          id: focusedTopic.id,
          label: focusedTopic.topic_title,
          icon: "📄",
        });
      }
    }

    return items;
  }, [
    viewMode,
    activeFolder,
    currentSubfolderId,
    subfolders,
    selectedSessionId,
    events,
    focusedTopic,
    topics.length,
    flatFeedTopics.length,
    folderTopics.length,
  ]);

  const currentPathString = useMemo(() => {
    if (viewMode === "all_feed") return "~/dossiers/all_feed/";
    if (!activeFolder) return "~/dossiers/";
    let base = `~/dossiers/${activeFolder.id}/`;
    if (currentSubfolderId && currentSubfolderId !== "all") {
      base += `${currentSubfolderId}/`;
    }
    if (activeFolder.isEventFolder && selectedSessionId) {
      base += `${selectedSessionId.substring(0, 8)}/`;
    }
    if (focusedTopic) {
      const slug = focusedTopic.topic_title
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "-")
        .replace(/(^-|-$)/g, "");
      base += `${slug.substring(0, 20)}/`;
    }
    return base;
  }, [viewMode, activeFolder, currentSubfolderId, selectedSessionId, focusedTopic]);

  // Navigation Handlers
  const handleNavigateBreadcrumb = (item: DossierBreadcrumbItem) => {
    if (item.id === "root") {
      setCurrentFolderId(null);
      setCurrentSubfolderId(null);
      setFocusedTopicId(null);
      setSelectedSessionId(null);
      setViewMode("folders");
    } else if (item.id === "all_feed") {
      setViewMode("all_feed");
    } else if (activeFolder && item.id === activeFolder.id) {
      setCurrentSubfolderId(null);
      setFocusedTopicId(null);
      setSelectedSessionId(null);
    } else if (item.id === currentSubfolderId) {
      setFocusedTopicId(null);
      setSelectedSessionId(null);
    }
  };

  const handleBack = () => {
    if (focusedTopicId) {
      setFocusedTopicId(null);
    } else if (selectedSessionId) {
      setSelectedSessionId(null);
    } else if (currentSubfolderId && currentSubfolderId !== "all") {
      setCurrentSubfolderId(null);
    } else if (currentFolderId) {
      setCurrentFolderId(null);
    } else if (viewMode !== "folders") {
      setViewMode("folders");
    }
  };

  const handleOpenFolder = (folderId: string) => {
    setViewMode("folders");
    setCurrentFolderId(folderId);
    setCurrentSubfolderId(null);
    setFocusedTopicId(null);
    setSelectedSessionId(null);
  };

  const handleSelectTopic = (topic: BriefingReport) => {
    // If not in the topic's folder, open that folder first
    const parentFolder = getFolderForTopic(topic);
    if (!currentFolderId || currentFolderId !== parentFolder.id) {
      setCurrentFolderId(parentFolder.id);
    }
    setFocusedTopicId(topic.id);
  };

  const handleBroadcast = (topic: BriefingReport) => {
    setBroadcastedId(topic.id);
    const text = `Topic briefing for ${topic.topic_title}: ${
      topic.explanatory_synthesis ||
      topic.executive_summary?.[0] ||
      "Synthesized analysis completed."
    }`;
    speakAlexaReassurance(text);
    setTimeout(() => setBroadcastedId(null), 3000);
  };

  const handleCopyDossier = (topic: BriefingReport) => {
    const text = generateTopicMarkdown(topic);
    if (!text) return;
    if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
      navigator.clipboard.writeText(text).catch(() => {});
    }
  };

  const handleDownloadDossier = (topic: BriefingReport) => {
    const text = generateTopicMarkdown(topic);
    const fname = sanitizeFilename(topic.topic_title || "topic_dossier", ".md");
    downloadTextFile(text, fname);
  };

  // Helper to find folder containing a given topic
  const getFolderForTopic = (topic: BriefingReport): DossierFolderDef => {
    if (!topic.context_type) return allFolders[0];
    const found = allFolders.find(
      (f) => !f.isEventFolder && f.contextTypes.includes(topic.context_type)
    );
    return found || allFolders[0];
  };

  // Pager navigation for focused topic
  const focusedIndex = useMemo(() => {
    if (!focusedTopic) return -1;
    return displayedFolderTopics.findIndex((t) => t.id === focusedTopic.id);
  }, [displayedFolderTopics, focusedTopic]);

  const prevTopic = focusedIndex > 0 ? displayedFolderTopics[focusedIndex - 1] : null;
  const nextTopic =
    focusedIndex >= 0 && focusedIndex < displayedFolderTopics.length - 1
      ? displayedFolderTopics[focusedIndex + 1]
      : null;

  return (
    <div className="space-y-space-lg animate-in fade-in max-w-[1400px] mx-auto">
      {/* Full-Screen Pop-up Detail Modal */}
      <TopicDetailModal
        topic={modalTopic}
        isOpen={Boolean(modalTopic)}
        onClose={() => setModalTopic(null)}
      />

      {/* Screen Header */}
      <ScreenHeader
        directive="COGNITIVE TELEMETRY SUBSYSTEM // AWS BEDROCK AGENTCORE"
        title="AUTONOMOUS TOPIC RESEARCH & ENRICHED DOSSIERS"
        description={
          <>
            Topic Dossiers serve as your ambient academic and technical research assistant. Ambient
            discussions are continuously indexed, categorized into domain folders, and synthesized
            with deep explanatory context, action items, and citations.
          </>
        }
        rightElement={
          <div className="flex flex-col items-end gap-1">
            <StatusBadge status="nominal" label="SYNTHESIS ENGINE RUNNING" size="md" />
            <div className="font-mono text-[9px] text-secondary tracking-[0.2em] uppercase">
              CADENCE: {avgLatency} • {reasonerModel}
            </div>
          </div>
        }
      />

      {/* View Mode Switcher & Global Search Bar */}
      <div className="flex flex-col md:flex-row items-stretch md:items-center justify-between gap-4 border-b border-surface-container-highest pb-6">
        {/* Search Input */}
        <div className="flex-1 max-w-md relative">
          <span className="absolute left-4 top-1/2 -translate-y-1/2 text-secondary text-sm">🔍</span>
          <input
            type="text"
            placeholder={
              activeFolder
                ? `Search within ${activeFolder.name}...`
                : "Search dossiers by topic, thesis, keywords, or citations..."
            }
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full bg-[#121419] border border-surface-container-highest rounded-full py-2.5 pl-10 pr-10 text-body-sm font-sans text-primary placeholder-zinc-500 focus:outline-none focus:border-amber-400 transition-colors"
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery("")}
              className="absolute right-3.5 top-1/2 -translate-y-1/2 text-zinc-400 hover:text-white font-mono text-xs w-5 h-5 rounded-full flex items-center justify-center bg-white/5 hover:bg-white/10 transition-colors"
              title="Clear search"
            >
              ✕
            </button>
          )}
        </div>

        {/* Primary View Switcher: Folders vs All Dossiers Feed vs Event Sessions */}
        <div className="flex items-center gap-1 p-1 rounded-full bg-[#121419] border border-surface-container-highest">
          <button
            onClick={() => {
              setViewMode("folders");
              setCurrentFolderId(null);
              setFocusedTopicId(null);
              setSelectedSessionId(null);
            }}
            className={`px-4 py-2 rounded-full font-mono text-[10px] font-bold tracking-widest transition-all ${
              viewMode === "folders" && currentFolderId !== "event_sessions"
                ? "bg-amber-500 text-black shadow-md font-bold"
                : "text-secondary hover:text-primary"
            }`}
          >
            📁 FOLDER DIRECTORY
          </button>
          <button
            onClick={() => {
              setViewMode("all_feed");
              setFocusedTopicId(null);
              setSelectedSessionId(null);
            }}
            className={`px-4 py-2 rounded-full font-mono text-[10px] font-bold tracking-widest transition-all ${
              viewMode === "all_feed"
                ? "bg-primary text-background shadow-md font-bold"
                : "text-secondary hover:text-primary"
            }`}
          >
            📚 ALL DOSSIERS ({topics.length})
          </button>
          <button
            onClick={() => handleOpenFolder("event_sessions")}
            className={`px-4 py-2 rounded-full font-mono text-[10px] font-bold tracking-widest transition-all ${
              viewMode === "folders" && currentFolderId === "event_sessions"
                ? "bg-cyan-500 text-black shadow-md font-bold"
                : "text-secondary hover:text-primary"
            }`}
          >
            🏛️ EVENT SESSIONS ({events.length})
          </button>
        </div>
      </div>

      {/* =========================================================================
          PERSISTENT INTERACTIVE BREADCRUMBS NAVIGATION (AT TOP OF SECTION)
          ========================================================================= */}
      <DossierBreadcrumbs
        items={breadcrumbItems}
        onNavigate={handleNavigateBreadcrumb}
        onBack={handleBack}
        canGoBack={Boolean(currentFolderId || focusedTopicId || selectedSessionId || viewMode !== "folders")}
        currentPathString={currentPathString}
        itemCount={
          focusedTopic
            ? 1
            : activeFolder
            ? activeFolder.isEventFolder
              ? displayedEvents.length
              : displayedFolderTopics.length
            : viewMode === "all_feed"
            ? flatFeedTopics.length
            : topics.length
        }
      />

      {/* =========================================================================
          VIEW MODE 1: HIERARCHICAL FOLDER DIRECTORY (PRIMARY EXPERIENCE)
          ========================================================================= */}
      {viewMode === "folders" && (
        <div className="space-y-space-lg">
          {/* GLOBAL SEARCH RESULTS ACROSS FOLDERS (When searching at root) */}
          {!currentFolderId && searchQuery.trim() && (
            <div className="space-y-4">
              <div className="flex items-center justify-between pb-2 border-b border-white/5 font-mono text-xs text-secondary">
                <span>
                  SEARCH RESULTS ACROSS ALL FOLDERS FOR &ldquo;{searchQuery}&rdquo;
                </span>
                <span className="text-amber-400 font-bold">
                  {globalSearchResults.topics.length + globalSearchResults.events.length} MATCHES
                </span>
              </div>

              {globalSearchResults.topics.length === 0 &&
              globalSearchResults.events.length === 0 ? (
                <div className="p-12 text-center border border-dashed border-surface-container-highest rounded-2xl bg-[#121419]">
                  <div className="text-3xl mb-3">🔍</div>
                  <div className="font-serif text-xl text-primary mb-2">No Matching Research Found</div>
                  <p className="font-sans text-secondary text-sm max-w-md mx-auto mb-4">
                    No dossiers or events matched &ldquo;{searchQuery}&rdquo;. Try another search term.
                  </p>
                  <button
                    onClick={() => setSearchQuery("")}
                    className="px-4 py-2 rounded-xl bg-surface-container-high border border-surface-container-highest text-primary font-mono text-xs hover:border-amber-400 transition-colors"
                  >
                    Clear Search Query
                  </button>
                </div>
              ) : (
                <div className="space-y-4">
                  {globalSearchResults.topics.map((topic) => {
                    const parentFolder = getFolderForTopic(topic);
                    return (
                      <div
                        key={topic.id}
                        className="p-5 rounded-2xl bg-surface-container-low border border-surface-container-highest hover:border-amber-500/40 transition-all flex flex-col md:flex-row md:items-center justify-between gap-4"
                      >
                        <div className="space-y-2">
                          <div className="flex items-center gap-2">
                            <button
                              onClick={() => handleOpenFolder(parentFolder.id)}
                              className="px-2.5 py-0.5 rounded-md bg-amber-950/40 border border-amber-500/30 text-amber-300 font-mono text-[9px] font-bold tracking-wider uppercase flex items-center gap-1 hover:bg-amber-950/70 transition-colors"
                              title={`Jump into ${parentFolder.name}`}
                            >
                              <span>{parentFolder.icon}</span>
                              <span>{parentFolder.name}</span>
                              <span className="text-amber-400">›</span>
                            </button>
                            <span className="font-mono text-[9px] text-zinc-500">
                              DOSSIER #{topic.id.substring(0, 6).toUpperCase()}
                            </span>
                          </div>
                          <h4 className="font-serif text-xl text-primary font-bold">
                            {topic.topic_title}
                          </h4>
                          {topic.explanatory_synthesis && (
                            <p className="font-sans text-xs text-secondary line-clamp-2">
                              {topic.explanatory_synthesis}
                            </p>
                          )}
                        </div>

                        <div className="flex items-center gap-2 shrink-0">
                          <button
                            onClick={() => handleSelectTopic(topic)}
                            className="px-4 py-2 rounded-xl border border-surface-container-highest bg-[#181a20] hover:bg-surface-container text-zinc-300 hover:text-white font-mono text-[9px] font-bold tracking-wider"
                          >
                            📖 OPEN DOSSIER
                          </button>
                          <button
                            onClick={() => handleBroadcast(topic)}
                            className="px-4 py-2 rounded-xl border border-amber-500/40 bg-amber-950/30 hover:bg-amber-950/60 text-amber-300 font-mono text-[9px] font-bold tracking-wider"
                          >
                            🔊 BROADCAST
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}

          {/* ROOT DIRECTORY VIEW: FOLDER CARDS GRID */}
          {!currentFolderId && !searchQuery.trim() && (
            <div className="space-y-8">
              {/* Directory Overview Summary Banner */}
              <div className="p-6 rounded-2xl bg-gradient-to-r from-surface-container-low via-[#181a20] to-surface-container-low border border-surface-container-highest flex flex-col md:flex-row md:items-center justify-between gap-6 shadow-sm">
                <div className="space-y-1.5">
                  <div className="font-mono text-[10px] text-amber-400 tracking-[0.2em] uppercase font-bold flex items-center gap-2">
                    <span>🗂️</span>
                    <span>STRUCTURED AMBIENT KNOWLEDGE VAULT</span>
                  </div>
                  <h3 className="font-serif text-2xl text-primary font-bold">
                    Autonomous Research Dossier Directory
                  </h3>
                  <p className="font-sans text-xs text-secondary max-w-2xl leading-relaxed">
                    Topic research is grouped into specialized repositories according to semantic
                    domain. Browse folder hierarchies or drill down into individual executive briefings
                    and multi-part lecture symposia.
                  </p>
                </div>

                <div className="flex items-center gap-3 shrink-0">
                  <div className="p-3 rounded-xl bg-black/40 border border-white/5 text-center min-w-[100px]">
                    <div className="font-mono text-xl font-bold text-amber-400">{topics.length}</div>
                    <div className="font-mono text-[9px] text-zinc-400 uppercase tracking-wider">
                      Briefings
                    </div>
                  </div>
                  <div className="p-3 rounded-xl bg-black/40 border border-white/5 text-center min-w-[100px]">
                    <div className="font-mono text-xl font-bold text-cyan-400">{events.length}</div>
                    <div className="font-mono text-[9px] text-zinc-400 uppercase tracking-wider">
                      Events
                    </div>
                  </div>
                  <div className="p-3 rounded-xl bg-black/40 border border-white/5 text-center min-w-[100px]">
                    <div className="font-mono text-xl font-bold text-emerald-400">
                      {allFolders.length}
                    </div>
                    <div className="font-mono text-[9px] text-zinc-400 uppercase tracking-wider">
                      Folders
                    </div>
                  </div>
                </div>
              </div>

              {/* Folders Grid */}
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {allFolders.map((folder) => {
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
                      onClick={() => handleOpenFolder(folder.id)}
                    />
                  );
                })}
              </div>

              {/* Quick Glance: Recently Synthesized Research */}
              {topics.length > 0 && (
                <div className="space-y-4 pt-4 border-t border-white/5">
                  <div className="flex items-center justify-between">
                    <div className="font-mono text-xs text-amber-400 uppercase tracking-wider font-bold flex items-center gap-2">
                      <span>⚡</span>
                      <span>RECENT RESEARCH SYNTHESES</span>
                    </div>
                    <button
                      onClick={() => setViewMode("all_feed")}
                      className="font-mono text-[10px] text-secondary hover:text-primary tracking-widest uppercase transition-colors"
                    >
                      VIEW ALL AS FLAT FEED →
                    </button>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {topics.slice(0, 4).map((topic) => {
                      const parentFolder = getFolderForTopic(topic);
                      return (
                        <div
                          key={topic.id}
                          onClick={() => handleSelectTopic(topic)}
                          className="p-5 rounded-2xl bg-surface-container-low border border-surface-container-highest hover:border-amber-500/40 transition-all cursor-pointer flex flex-col justify-between gap-3 group"
                        >
                          <div className="flex items-center justify-between gap-2">
                            <span className="px-2 py-0.5 rounded text-[9px] font-mono tracking-wider uppercase bg-amber-950/30 border border-amber-500/30 text-amber-300">
                              {parentFolder.icon} {parentFolder.name}
                            </span>
                            <span className="font-mono text-[9px] text-zinc-500">
                              {topic.created_at ? topic.created_at.split("T")[1]?.substring(0, 5) : "RECENT"} UTC
                            </span>
                          </div>

                          <h4 className="font-serif text-lg text-primary font-bold group-hover:text-amber-200 transition-colors line-clamp-1">
                            {topic.topic_title}
                          </h4>

                          {topic.explanatory_synthesis && (
                            <p className="font-sans text-xs text-secondary line-clamp-2">
                              {topic.explanatory_synthesis}
                            </p>
                          )}

                          <div className="flex items-center justify-between pt-2 border-t border-white/5 font-mono text-[9px] text-zinc-400">
                            <span>
                              {topic.executive_summary?.length || 0} Key Points •{" "}
                              {topic.action_items?.length || 0} Actions
                            </span>
                            <span className="text-amber-400 group-hover:translate-x-1 transition-transform">
                              Read Dossier →
                            </span>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* INSIDE FOLDER VIEW: TOPICS, EVENT SESSIONS, OR FOCUSED DOSSIER */}
          {currentFolderId && (
            <div className="space-y-6">
              {/* Folder Banner (when not focused on a single dossier) */}
              {activeFolder && !focusedTopic && (
                <div className="p-6 rounded-2xl bg-surface-container-low border border-surface-container-highest flex flex-col md:flex-row md:items-center justify-between gap-4">
                  <div className="flex items-center gap-4">
                    <div className="w-14 h-14 rounded-2xl bg-[#121419] border border-white/10 flex items-center justify-center text-3xl shadow-inner shrink-0">
                      {activeFolder.icon}
                    </div>
                    <div>
                      <div className="font-mono text-[10px] text-amber-400 tracking-widest uppercase font-bold mb-1">
                        DIRECTORY // {activeFolder.id.toUpperCase()}
                      </div>
                      <h3 className="font-serif text-2xl sm:text-3xl text-primary font-bold">
                        {activeFolder.name}
                      </h3>
                      <p className="font-sans text-xs text-secondary max-w-xl">
                        {activeFolder.description}
                      </p>
                    </div>
                  </div>

                  {/* Layout toggle (Grid vs List) for briefings */}
                  {!activeFolder.isEventFolder && (
                    <div className="flex items-center gap-1 p-1 rounded-xl bg-black/40 border border-white/10 shrink-0 self-start md:self-center">
                      <button
                        onClick={() => setLayoutMode("grid")}
                        className={`px-3 py-1.5 rounded-lg font-mono text-[10px] font-bold tracking-wider transition-colors flex items-center gap-1.5 ${
                          layoutMode === "grid"
                            ? "bg-amber-500 text-black shadow-sm"
                            : "text-zinc-400 hover:text-white"
                        }`}
                        title="Grid Card View"
                      >
                        <span>⊞</span>
                        <span>CARDS</span>
                      </button>
                      <button
                        onClick={() => setLayoutMode("list")}
                        className={`px-3 py-1.5 rounded-lg font-mono text-[10px] font-bold tracking-wider transition-colors flex items-center gap-1.5 ${
                          layoutMode === "list"
                            ? "bg-amber-500 text-black shadow-sm"
                            : "text-zinc-400 hover:text-white"
                        }`}
                        title="List Table View"
                      >
                        <span>☰</span>
                        <span>LIST</span>
                      </button>
                    </div>
                  )}
                </div>
              )}

              {/* Subfolders selector pills */}
              {!focusedTopic && subfolders.length > 1 && (
                <div className="flex items-center gap-2 overflow-x-auto hide-scrollbar pb-1">
                  {subfolders.map((sub) => {
                    const isSelected =
                      currentSubfolderId === sub.id || (!currentSubfolderId && sub.id === "all");
                    return (
                      <button
                        key={sub.id}
                        onClick={() => setCurrentSubfolderId(sub.id)}
                        className={`px-4 py-2 rounded-full font-mono text-[10px] font-bold tracking-wider whitespace-nowrap transition-all flex items-center gap-1.5 ${
                          isSelected
                            ? "bg-amber-500 text-black shadow-sm"
                            : "bg-[#14161d] border border-white/10 text-zinc-400 hover:text-white hover:border-white/20"
                        }`}
                      >
                        <span>{sub.label}</span>
                        <span
                          className={`px-1.5 py-0.2 rounded-full text-[9px] ${
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

              {/* =====================================================================
                  LEVEL 3: FOCUSED TOPIC DOSSIER DIRECTORY VIEW
                  ===================================================================== */}
              {focusedTopic && (
                <div className="space-y-6 animate-in fade-in">
                  <div className="p-space-xl bg-surface-container-low border border-amber-500/40 rounded-2xl flex flex-col gap-6 shadow-lg">
                    {/* Top Row: Dossier Identification & Pager Controls */}
                    <div className="flex flex-col md:flex-row items-start justify-between gap-4 pb-4 border-b border-white/5">
                      <div className="space-y-2">
                        <div className="font-mono text-[9px] text-amber-400 tracking-[0.2em] uppercase flex items-center gap-2 font-bold">
                          <span>📄 DOSSIER #{focusedTopic.id.substring(0, 6).toUpperCase()}</span>
                          <span className="opacity-40">•</span>
                          <span className="text-secondary font-normal">
                            SYNTHESIZED{" "}
                            {focusedTopic.created_at
                              ? focusedTopic.created_at.split("T")[1]?.substring(0, 5)
                              : "RECENT"}{" "}
                            UTC
                          </span>
                        </div>

                        <h2 className="font-serif text-[28px] sm:text-[36px] text-primary leading-tight font-bold">
                          {focusedTopic.topic_title}
                        </h2>

                        <div className="flex items-center gap-2 flex-wrap">
                          {focusedTopic.kind && KIND_BADGES[focusedTopic.kind] && (
                            <span
                              className={`px-2.5 py-1 rounded border font-mono text-[9px] tracking-widest uppercase ${
                                KIND_BADGES[focusedTopic.kind].cls
                              }`}
                            >
                              {KIND_BADGES[focusedTopic.kind].label}
                            </span>
                          )}
                          <span className="px-2.5 py-1 rounded bg-[#1c1f26] border border-white/5 font-mono text-[9px] text-secondary tracking-widest uppercase">
                            {focusedTopic.context_type?.replace(/_/g, " ").toUpperCase() ||
                              "GENERAL RESEARCH"}
                          </span>
                          <StatusBadge status="completed" label="SYNTHESIS COMPLETE" />
                        </div>
                      </div>

                      {/* Dossier Action Buttons */}
                      <div className="flex items-center gap-2 shrink-0 self-end md:self-start flex-wrap">
                        {prevTopic && (
                          <button
                            onClick={() => setFocusedTopicId(prevTopic.id)}
                            className="px-3 py-2 rounded-xl border border-surface-container-highest bg-[#181a20] hover:bg-surface-container text-zinc-300 hover:text-white font-mono text-[9px] font-bold tracking-wider"
                            title={`Previous: ${prevTopic.topic_title}`}
                          >
                            ← PREV
                          </button>
                        )}
                        {nextTopic && (
                          <button
                            onClick={() => setFocusedTopicId(nextTopic.id)}
                            className="px-3 py-2 rounded-xl border border-surface-container-highest bg-[#181a20] hover:bg-surface-container text-zinc-300 hover:text-white font-mono text-[9px] font-bold tracking-wider"
                            title={`Next: ${nextTopic.topic_title}`}
                          >
                            NEXT →
                          </button>
                        )}
                        <button
                          onClick={() => handleCopyDossier(focusedTopic)}
                          className="px-4 py-2 rounded-xl border border-surface-container-highest bg-[#181a20] hover:bg-surface-container text-zinc-300 hover:text-white font-mono text-[9px] font-bold tracking-wider flex items-center gap-1.5 cursor-pointer"
                          title="Copy markdown dossier"
                        >
                          <span>📋</span>
                          <span>COPY</span>
                        </button>
                        <button
                          onClick={() => handleDownloadDossier(focusedTopic)}
                          className="px-4 py-2 rounded-xl border border-cyan-500/50 bg-cyan-950/40 hover:bg-cyan-900/60 text-cyan-300 font-mono text-[9px] font-bold tracking-wider flex items-center gap-1.5 transition-colors cursor-pointer"
                          title="Download full research dossier as .md"
                        >
                          <span>💾</span>
                          <span>DOWNLOAD</span>
                        </button>
                        <button
                          onClick={() => handleBroadcast(focusedTopic)}
                          className="px-4 py-2 rounded-xl border border-amber-500/50 bg-amber-500/10 hover:bg-amber-500/20 text-amber-300 font-mono text-[9px] font-bold tracking-wider flex items-center gap-1.5 cursor-pointer"
                          title="Broadcast to Alexa"
                        >
                          <span>🔊</span>
                          <span>{broadcastedId === focusedTopic.id ? "SPEAKING..." : "ALEXA"}</span>
                        </button>
                        <button
                          onClick={() => setModalTopic(focusedTopic)}
                          className="px-4 py-2 rounded-xl border border-white/10 bg-white/5 hover:bg-white/10 text-white font-mono text-[9px] font-bold tracking-wider flex items-center gap-1.5 cursor-pointer"
                          title="Open Fullscreen Pop-up Modal"
                        >
                          <span>⛶</span>
                          <span>POPUP</span>
                        </button>
                      </div>
                    </div>

                    {/* Explanatory Synthesis Box */}
                    {focusedTopic.explanatory_synthesis && (
                      <div className="bg-gradient-to-r from-amber-950/40 via-[#16181f] to-[#121419] border border-amber-500/40 rounded-xl p-5 shadow-inner">
                        <div className="font-mono text-[10px] text-amber-300 tracking-[0.2em] uppercase font-bold mb-2 flex items-center gap-1.5">
                          <span>⚡</span>
                          <span>EXPLANATORY CONTEXTUAL SYNTHESIS</span>
                        </div>
                        <p className="font-sans text-body-base text-amber-100/90 leading-relaxed">
                          {focusedTopic.explanatory_synthesis}
                        </p>
                      </div>
                    )}

                    {/* 2 Columns: Executive Summary & Action Items/Sources */}
                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-space-md">
                      {/* Summary Column */}
                      <div className="bg-[#121419] border border-surface-container-highest rounded-xl p-6 flex flex-col justify-between">
                        <div>
                          <div className="font-mono text-[10px] text-secondary tracking-[0.2em] uppercase mb-4 font-bold flex items-center gap-2">
                            <span>📌</span>
                            <span>EXECUTIVE SUMMARY & INSIGHTS</span>
                          </div>
                          <div className="font-sans text-body-sm text-secondary leading-relaxed space-y-3">
                            {focusedTopic.executive_summary?.map((sum, i) => (
                              <div key={i} className="flex items-start gap-2.5 text-primary">
                                <span className="text-amber-400 select-none font-bold">▪</span>
                                <span>{sum}</span>
                              </div>
                            )) || <div>No summary available</div>}
                          </div>
                        </div>
                      </div>

                      {/* Actions & Citations Column */}
                      <div className="bg-[#121419] border border-surface-container-highest rounded-xl p-6 flex flex-col justify-between">
                        <div>
                          <div className="font-mono text-[10px] text-secondary tracking-[0.2em] uppercase mb-4 font-bold flex items-center gap-2">
                            <span>✅</span>
                            <span>ACTION ITEMS & CITATIONS</span>
                          </div>

                          {focusedTopic.action_items && focusedTopic.action_items.length > 0 && (
                            <div className="mb-5">
                              <strong className="text-primary font-mono text-[9px] tracking-widest uppercase mb-2 block">
                                Key Action Items
                              </strong>
                              <div className="space-y-2">
                                {focusedTopic.action_items.map((act, i) => (
                                  <div
                                    key={i}
                                    className="flex items-start gap-2.5 text-body-xs font-sans text-primary"
                                  >
                                    <span className="text-emerald-400 font-bold">✓</span>
                                    <span>{act}</span>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}

                          {focusedTopic.web_sources && focusedTopic.web_sources.length > 0 && (
                            <div>
                              <strong className="text-primary font-mono text-[9px] tracking-widest uppercase mb-2 block">
                                Corroborating Citations
                              </strong>
                              <div className="space-y-1.5">
                                {focusedTopic.web_sources.map((src, i) => (
                                  <a
                                    key={i}
                                    href={src}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="block text-amber-200/90 hover:text-amber-300 font-mono text-[10px] truncate hover:underline"
                                    title={src}
                                  >
                                    🔗 {src}
                                  </a>
                                ))}
                              </div>
                            </div>
                          )}
                        </div>
                      </div>
                    </div>

                    {/* Deep-Dive Technical Markdown Section */}
                    {focusedTopic.deep_dive_markdown && (
                      <div className="space-y-2">
                        <MarkdownRenderer
                          content={focusedTopic.deep_dive_markdown}
                          allowRawToggle={true}
                          defaultMode="rendered"
                          title="Deep Research & Technical Specification"
                          filename={sanitizeFilename(focusedTopic.topic_title, ".md")}
                          accentColor="cyan"
                          showDownloadButton={true}
                          showCopyButton={true}
                        />
                      </div>
                    )}

                    {/* Bottom Return Bar */}
                    <div className="pt-4 border-t border-white/5 flex items-center justify-between">
                      <button
                        onClick={() => setFocusedTopicId(null)}
                        className="px-4 py-2 rounded-xl bg-surface-container-high border border-surface-container-highest text-primary font-mono text-xs hover:border-amber-400 transition-colors flex items-center gap-2"
                      >
                        <span>←</span>
                        <span>Return to {activeFolder?.name || "Folder"} Directory</span>
                      </button>

                      <span className="font-mono text-[10px] text-zinc-500 uppercase tracking-wider">
                        ENTRY {focusedIndex + 1} OF {displayedFolderTopics.length} IN THIS FOLDER
                      </span>
                    </div>
                  </div>
                </div>
              )}

              {/* FOLDER CONTENTS: EVENT SESSIONS */}
              {!focusedTopic && activeFolder?.isEventFolder && (
                <div className="space-y-space-lg">
                  {displayedEvents.length === 0 ? (
                    <div className="p-12 text-center border border-dashed border-surface-container-highest rounded-2xl bg-[#121419]">
                      <div className="text-3xl mb-3">🏛️</div>
                      <div className="font-serif text-xl text-primary mb-2">
                        No Event Sessions Recorded Yet
                      </div>
                      <p className="font-sans text-secondary text-sm max-w-md mx-auto">
                        Turn on Event mode in the Ambient Simulator (or wear the Bee device during a
                        lecture or architecture meeting): multi-part speech is automatically grouped into
                        sessions, synthesized part by part, and organized here.
                      </p>
                    </div>
                  ) : (
                    displayedEvents.map((ev, i) => (
                      <div
                        key={ev.session_id}
                        onClick={() =>
                          setSelectedSessionId((prev) =>
                            prev === ev.session_id ? null : ev.session_id
                          )
                        }
                        className="transition-all"
                      >
                        <EventCard
                          event={ev}
                          previousEvent={events[i + 1] || null}
                          tHardSeconds={engineStatus?.config?.t_hard_seconds}
                          onAction={onEventAction || (async () => {})}
                          onOpenBriefing={(b) => setModalTopic(b)}
                          defaultExpanded={i === 0 || selectedSessionId === ev.session_id}
                        />
                      </div>
                    ))
                  )}
                </div>
              )}

              {/* FOLDER CONTENTS: REGULAR TOPIC BRIEFINGS */}
              {!focusedTopic && !activeFolder?.isEventFolder && (
                <>
                  {displayedFolderTopics.length === 0 ? (
                    <div className="p-12 text-center border border-dashed border-surface-container-highest rounded-2xl bg-[#121419]">
                      <div className="text-3xl mb-3">📂</div>
                      <div className="font-serif text-xl text-primary mb-2">
                        No Dossiers in This Directory
                      </div>
                      <p className="font-sans text-secondary text-sm mb-6 max-w-md mx-auto">
                        {searchQuery
                          ? `No dossiers matched "${searchQuery}" in this folder.`
                          : "No briefings filed in this folder yet. As ambient conversations touch on this domain, EXAMEN will automatically file new research here."}
                      </p>
                      <button
                        onClick={handleBack}
                        className="px-4 py-2 rounded-xl bg-surface-container-high border border-surface-container-highest text-primary font-mono text-xs hover:border-amber-400 transition-colors"
                      >
                        ← Return to All Folders
                      </button>
                    </div>
                  ) : layoutMode === "list" ? (
                    /* COMPACT FILE LIST TABLE */
                    <div className="bg-[#121419] border border-surface-container-highest rounded-2xl overflow-hidden shadow-sm">
                      <div className="overflow-x-auto">
                        <table className="w-full text-left border-collapse">
                          <thead>
                            <tr className="border-b border-surface-container-highest bg-[#16181f] font-mono text-[9px] text-zinc-400 tracking-wider uppercase">
                              <th className="py-3.5 px-4 font-bold">TOPIC / TITLE</th>
                              <th className="py-3.5 px-4 font-bold">KIND</th>
                              <th className="py-3.5 px-4 font-bold hidden md:table-cell">SYNTHESIS THESIS</th>
                              <th className="py-3.5 px-4 font-bold text-center">POINTS</th>
                              <th className="py-3.5 px-4 font-bold text-center">CITATIONS</th>
                              <th className="py-3.5 px-4 font-bold text-right">ACTIONS</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-white/5 font-sans text-xs">
                            {displayedFolderTopics.map((topic) => (
                              <tr
                                key={topic.id}
                                onClick={() => handleSelectTopic(topic)}
                                className="hover:bg-white/[0.04] transition-colors group cursor-pointer"
                              >
                                <td className="py-3.5 px-4 font-medium text-primary">
                                  <div className="flex items-center gap-2">
                                    <span className="text-amber-400 text-sm">📄</span>
                                    <div>
                                      <div className="font-bold group-hover:text-amber-300 transition-colors">
                                        {topic.topic_title}
                                      </div>
                                      <div className="font-mono text-[9px] text-zinc-500">
                                        #{topic.id.substring(0, 6).toUpperCase()} •{" "}
                                        {topic.created_at
                                          ? topic.created_at.split("T")[1]?.substring(0, 5)
                                          : "RECENT"}{" "}
                                        UTC
                                      </div>
                                    </div>
                                  </div>
                                </td>
                                <td className="py-3.5 px-4 whitespace-nowrap">
                                  {topic.kind && KIND_BADGES[topic.kind] ? (
                                    <span
                                      className={`px-2 py-0.5 rounded border font-mono text-[8px] uppercase tracking-wider ${
                                        KIND_BADGES[topic.kind].cls
                                      }`}
                                    >
                                      {KIND_BADGES[topic.kind].label}
                                    </span>
                                  ) : (
                                    <span className="font-mono text-[9px] text-zinc-500">
                                      STANDALONE
                                    </span>
                                  )}
                                </td>
                                <td className="py-3.5 px-4 text-secondary max-w-xs truncate hidden md:table-cell font-sans">
                                  {topic.explanatory_synthesis || topic.executive_summary?.[0] || "—"}
                                </td>
                                <td className="py-3.5 px-4 text-center font-mono text-[10px] text-zinc-400">
                                  {topic.executive_summary?.length || 0}
                                </td>
                                <td className="py-3.5 px-4 text-center font-mono text-[10px] text-amber-400/90">
                                  {topic.web_sources?.length || 0}
                                </td>
                                <td
                                  className="py-3.5 px-4 text-right whitespace-nowrap"
                                  onClick={(e) => e.stopPropagation()}
                                >
                                  <div className="flex items-center justify-end gap-2">
                                    <button
                                      onClick={() => handleSelectTopic(topic)}
                                      className="px-3 py-1.5 rounded-lg border border-surface-container-highest bg-[#1c1f26] hover:bg-surface-container text-zinc-300 hover:text-white font-mono text-[9px] font-bold tracking-wider"
                                      title="Open dossier detail"
                                    >
                                      READ
                                    </button>
                                    <button
                                      onClick={() => handleBroadcast(topic)}
                                      className="px-3 py-1.5 rounded-lg border border-amber-500/40 bg-amber-950/30 hover:bg-amber-950/60 text-amber-300 font-mono text-[9px] font-bold tracking-wider"
                                      title="Broadcast to Alexa"
                                    >
                                      🔊
                                    </button>
                                  </div>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  ) : (
                    /* RICH GRID CARDS VIEW */
                    <div className="space-y-space-lg">
                      {displayedFolderTopics.map((topic) => {
                        const isBroadcasting = broadcastedId === topic.id;

                        return (
                          <div
                            key={topic.id}
                            className="card-elevated p-space-xl bg-surface-container-low border-surface-container-highest rounded-2xl flex flex-col gap-6 hover:border-amber-500/40 transition-all duration-200"
                          >
                            {/* Header Row */}
                            <div className="flex flex-col md:flex-row items-start justify-between gap-4 pb-4 border-b border-white/5">
                              <div className="flex flex-col">
                                <div className="font-mono text-[9px] text-amber-400 tracking-[0.2em] uppercase flex items-center gap-2 mb-2 font-bold">
                                  <span>DOSSIER #{topic.id.substring(0, 6).toUpperCase()}</span>
                                  <span className="opacity-40">•</span>
                                  <span className="text-secondary font-normal">
                                    SYNTHESIZED{" "}
                                    {topic.created_at
                                      ? topic.created_at.split("T")[1]?.substring(0, 5)
                                      : "RECENT"}{" "}
                                    UTC
                                  </span>
                                </div>

                                <h3
                                  onClick={() => handleSelectTopic(topic)}
                                  className="font-serif text-[28px] sm:text-[34px] text-primary leading-tight mb-2 hover:text-amber-200 cursor-pointer transition-colors"
                                >
                                  {topic.topic_title}
                                </h3>

                                <div className="flex items-center gap-2 flex-wrap">
                                  {topic.kind && KIND_BADGES[topic.kind] && (
                                    <span
                                      className={`px-2.5 py-1 rounded border font-mono text-[9px] tracking-widest uppercase ${
                                        KIND_BADGES[topic.kind].cls
                                      }`}
                                    >
                                      {KIND_BADGES[topic.kind].label}
                                    </span>
                                  )}
                                  <span className="px-2.5 py-1 rounded bg-[#1c1f26] border border-white/5 font-mono text-[9px] text-secondary tracking-widest uppercase">
                                    {topic.context_type?.replace(/_/g, " ").toUpperCase() ||
                                      "GENERAL RESEARCH"}
                                  </span>
                                  <StatusBadge status="completed" label="SYNTHESIS COMPLETE" />
                                </div>
                              </div>

                              {/* Action Buttons */}
                              <div className="flex items-center gap-2 shrink-0 self-end md:self-center flex-wrap">
                                <button
                                  onClick={() => handleCopyDossier(topic)}
                                  className="px-4 py-2.5 rounded-lg border border-surface-container-highest bg-transparent hover:bg-surface-container text-secondary hover:text-primary font-mono text-[9px] tracking-[0.2em] flex items-center gap-1.5 transition-colors uppercase font-bold cursor-pointer"
                                  title="Copy markdown dossier to clipboard"
                                >
                                  <span>📋</span>
                                  <span>COPY</span>
                                </button>

                                <button
                                  onClick={() => handleDownloadDossier(topic)}
                                  className="px-4 py-2.5 rounded-lg border border-cyan-500/40 bg-cyan-950/40 hover:bg-cyan-900/60 text-cyan-300 font-mono text-[9px] tracking-[0.2em] flex items-center gap-1.5 transition-colors uppercase font-bold cursor-pointer"
                                  title="Download full research dossier as .md"
                                >
                                  <span>💾</span>
                                  <span>DOWNLOAD</span>
                                </button>

                                <button
                                  onClick={() => setModalTopic(topic)}
                                  className="px-4 py-2.5 rounded-lg border border-white/10 bg-white/5 hover:bg-white/10 text-white font-mono text-[9px] tracking-[0.2em] flex items-center gap-1.5 transition-colors uppercase font-bold cursor-pointer"
                                  title="Open Fullscreen Pop-up Modal"
                                >
                                  <span>⛶</span>
                                  <span>POPUP</span>
                                </button>

                                <button
                                  onClick={() => handleSelectTopic(topic)}
                                  className="px-5 py-2.5 rounded-lg border border-surface-container-highest bg-transparent hover:bg-surface-container text-secondary hover:text-primary font-mono text-[9px] tracking-[0.2em] flex items-center gap-2 transition-colors uppercase font-bold cursor-pointer"
                                  title="Open full research report"
                                >
                                  <span>📖</span>
                                  <span>READ DOSSIER</span>
                                </button>

                                <button
                                  onClick={() => handleBroadcast(topic)}
                                  className="px-5 py-2.5 rounded-lg border border-amber-500/50 bg-amber-500/10 hover:bg-amber-500/20 text-amber-300 font-mono text-[9px] tracking-[0.2em] font-bold flex items-center gap-2 transition-colors uppercase shadow-sm cursor-pointer"
                                  title="Broadcast topic to Alexa Echo Show"
                                >
                                  <span>🔊</span>
                                  <span>{isBroadcasting ? "SPEAKING..." : "BROADCAST TO ALEXA"}</span>
                                </button>
                              </div>
                            </div>

                            {/* Explanatory Synthesis Box */}
                            {topic.explanatory_synthesis && (
                              <div className="bg-gradient-to-r from-amber-950/30 to-[#121419] border border-amber-500/30 rounded-xl p-4">
                                <div className="font-mono text-[9px] text-amber-300 tracking-[0.2em] uppercase font-bold mb-1 flex items-center gap-1.5">
                                  <span>⚡</span>
                                  <span>EXPLANATORY CONTEXTUAL SYNTHESIS</span>
                                </div>
                                <p className="font-sans text-body-sm text-amber-100/90 leading-relaxed">
                                  {topic.explanatory_synthesis}
                                </p>
                              </div>
                            )}

                            {/* 2 Columns: Executive Summary & Action Items/Sources */}
                            <div className="grid grid-cols-1 lg:grid-cols-2 gap-space-md">
                              {/* Summary */}
                              <div className="bg-[#121419] border border-surface-container-highest rounded-xl p-5 flex flex-col justify-between">
                                <div>
                                  <div className="font-mono text-[9px] text-secondary tracking-[0.2em] uppercase mb-4 font-bold">
                                    EXECUTIVE SUMMARY & INSIGHTS
                                  </div>
                                  <div className="font-sans text-body-sm text-secondary leading-relaxed space-y-2.5">
                                    {topic.executive_summary?.map((sum, i) => (
                                      <div key={i} className="flex items-start gap-2.5 text-primary">
                                        <span className="text-amber-400 select-none">▪</span>
                                        <span>{sum}</span>
                                      </div>
                                    )) || <div>No summary available</div>}
                                  </div>
                                </div>
                              </div>

                              {/* Actions & Citations */}
                              <div className="bg-[#121419] border border-surface-container-highest rounded-xl p-5 flex flex-col justify-between">
                                <div>
                                  <div className="font-mono text-[9px] text-secondary tracking-[0.2em] uppercase mb-4 font-bold">
                                    ACTION ITEMS & CITATIONS
                                  </div>

                                  {topic.action_items && topic.action_items.length > 0 && (
                                    <div className="mb-4">
                                      <strong className="text-primary font-mono text-[9px] tracking-widest uppercase mb-2 block">
                                        Key Action Items
                                      </strong>
                                      <div className="space-y-1.5">
                                        {topic.action_items.map((act, i) => (
                                          <div
                                            key={i}
                                            className="flex items-start gap-2 text-body-xs font-sans text-primary"
                                          >
                                            <span className="text-emerald-400">✓</span>
                                            <span>{act}</span>
                                          </div>
                                        ))}
                                      </div>
                                    </div>
                                  )}

                                  {topic.web_sources && topic.web_sources.length > 0 && (
                                    <div>
                                      <strong className="text-primary font-mono text-[9px] tracking-widest uppercase mb-2 block">
                                        Corroborating Citations
                                      </strong>
                                      <div className="space-y-1">
                                        {topic.web_sources.slice(0, 3).map((src, i) => (
                                          <a
                                            key={i}
                                            href={src}
                                            target="_blank"
                                            rel="noopener noreferrer"
                                            className="block text-amber-200/90 hover:text-amber-300 font-mono text-[10px] truncate hover:underline"
                                            title={src}
                                          >
                                            🔗 {src}
                                          </a>
                                        ))}
                                      </div>
                                    </div>
                                  )}
                                </div>
                              </div>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </>
              )}
            </div>
          )}
        </div>
      )}

      {/* =========================================================================
          VIEW MODE 2: FLAT FEED OF ALL DOSSIERS (RETAINS LEGACY FILTER BUTTONS)
          ========================================================================= */}
      {viewMode === "all_feed" && (
        <div className="space-y-6">
          {/* Filter Pills */}
          <div className="flex flex-wrap items-center gap-2">
            <button
              onClick={() => setFeedFilter("ALL")}
              className={`px-4 py-2 rounded-full font-mono text-[10px] font-bold tracking-widest transition-colors ${
                feedFilter === "ALL"
                  ? "bg-primary text-background shadow"
                  : "text-secondary hover:bg-surface-container hover:text-primary"
              }`}
            >
              ALL ({topics.length})
            </button>
            {uniqueContexts.map((ctx) => {
              const isSelected = feedFilter === ctx;
              const ctxCount = topics.filter((t) => t.context_type === ctx).length;
              const label = ctx ? ctx.replace(/_/g, " ").toUpperCase() : "GENERAL";
              return (
                <button
                  key={ctx}
                  onClick={() => setFeedFilter(ctx as string)}
                  className={`px-4 py-2 rounded-full font-mono text-[10px] font-bold tracking-widest transition-colors flex items-center gap-1.5 ${
                    isSelected
                      ? "bg-amber-500 text-black shadow"
                      : "text-amber-400/80 bg-amber-950/20 border border-amber-500/20 hover:bg-amber-950/40"
                  }`}
                >
                  <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />
                  <span>
                    {label} ({ctxCount})
                  </span>
                </button>
              );
            })}
          </div>

          {/* Dossiers List */}
          {flatFeedTopics.length === 0 ? (
            <div className="p-12 text-center border border-dashed border-surface-container-highest rounded-2xl bg-[#121419]">
              <div className="text-3xl mb-3">📚</div>
              <div className="font-serif text-xl text-primary mb-2">No Topic Dossiers Found</div>
              <p className="font-sans text-secondary text-sm mb-6 max-w-md mx-auto">
                {searchQuery
                  ? `No dossiers matched "${searchQuery}".`
                  : "No dossiers synthesized yet. Run a tech discussion in the ambient simulator to trigger deep topic research."}
              </p>
            </div>
          ) : (
            <div className="space-y-space-lg">
              {flatFeedTopics.map((topic) => {
                const isBroadcasting = broadcastedId === topic.id;
                const parentFolder = getFolderForTopic(topic);

                return (
                  <div
                    key={topic.id}
                    className="card-elevated p-space-xl bg-surface-container-low border-surface-container-highest rounded-2xl flex flex-col gap-6 hover:border-amber-500/40 transition-all duration-200"
                  >
                    {/* Header Row */}
                    <div className="flex flex-col md:flex-row items-start justify-between gap-4 pb-4 border-b border-white/5">
                      <div className="flex flex-col">
                        <div className="font-mono text-[9px] text-amber-400 tracking-[0.2em] uppercase flex items-center gap-2 mb-2 font-bold">
                          <span>DOSSIER #{topic.id.substring(0, 6).toUpperCase()}</span>
                          <span className="opacity-40">•</span>
                          <span className="text-secondary font-normal">
                            SYNTHESIZED{" "}
                            {topic.created_at
                              ? topic.created_at.split("T")[1]?.substring(0, 5)
                              : "RECENT"}{" "}
                            UTC
                          </span>
                        </div>

                        <h3
                          onClick={() => handleSelectTopic(topic)}
                          className="font-serif text-[28px] sm:text-[34px] text-primary leading-tight mb-2 hover:text-amber-200 cursor-pointer transition-colors"
                        >
                          {topic.topic_title}
                        </h3>

                        <div className="flex items-center gap-2 flex-wrap">
                          <button
                            onClick={() => {
                              setViewMode("folders");
                              handleOpenFolder(parentFolder.id);
                            }}
                            className="px-2.5 py-1 rounded bg-[#1c1f26] hover:bg-amber-950/40 border border-white/10 hover:border-amber-500/40 font-mono text-[9px] text-amber-300 tracking-widest uppercase transition-colors flex items-center gap-1"
                            title={`Open in ${parentFolder.name} folder`}
                          >
                            <span>{parentFolder.icon}</span>
                            <span>{parentFolder.name}</span>
                          </button>
                          {topic.kind && KIND_BADGES[topic.kind] && (
                            <span
                              className={`px-2.5 py-1 rounded border font-mono text-[9px] tracking-widest uppercase ${
                                KIND_BADGES[topic.kind].cls
                              }`}
                            >
                              {KIND_BADGES[topic.kind].label}
                            </span>
                          )}
                          <StatusBadge status="completed" label="SYNTHESIS COMPLETE" />
                        </div>
                      </div>

                      {/* Buttons */}
                      <div className="flex items-center gap-2 shrink-0 self-end md:self-center flex-wrap">
                        <button
                          onClick={() => handleCopyDossier(topic)}
                          className="px-4 py-2.5 rounded-lg border border-surface-container-highest bg-transparent hover:bg-surface-container text-secondary hover:text-primary font-mono text-[9px] tracking-[0.2em] flex items-center gap-1.5 transition-colors uppercase font-bold cursor-pointer"
                          title="Copy markdown dossier to clipboard"
                        >
                          <span>📋</span>
                          <span>COPY</span>
                        </button>

                        <button
                          onClick={() => handleDownloadDossier(topic)}
                          className="px-4 py-2.5 rounded-lg border border-cyan-500/40 bg-cyan-950/40 hover:bg-cyan-900/60 text-cyan-300 font-mono text-[9px] tracking-[0.2em] flex items-center gap-1.5 transition-colors uppercase font-bold cursor-pointer"
                          title="Download full research dossier as .md"
                        >
                          <span>💾</span>
                          <span>DOWNLOAD</span>
                        </button>

                        <button
                          onClick={() => setModalTopic(topic)}
                          className="px-4 py-2.5 rounded-lg border border-white/10 bg-white/5 hover:bg-white/10 text-white font-mono text-[9px] tracking-[0.2em] flex items-center gap-1.5 transition-colors uppercase font-bold cursor-pointer"
                          title="Open Fullscreen Pop-up Modal"
                        >
                          <span>⛶</span>
                          <span>POPUP</span>
                        </button>

                        <button
                          onClick={() => handleSelectTopic(topic)}
                          className="px-5 py-2.5 rounded-lg border border-surface-container-highest bg-transparent hover:bg-surface-container text-secondary hover:text-primary font-mono text-[9px] tracking-[0.2em] flex items-center gap-2 transition-colors uppercase font-bold cursor-pointer"
                          title="Open full research report"
                        >
                          <span>📖</span>
                          <span>READ DOSSIER</span>
                        </button>

                        <button
                          onClick={() => handleBroadcast(topic)}
                          className="px-5 py-2.5 rounded-lg border border-amber-500/50 bg-amber-500/10 hover:bg-amber-500/20 text-amber-300 font-mono text-[9px] tracking-[0.2em] font-bold flex items-center gap-2 transition-colors uppercase shadow-sm cursor-pointer"
                          title="Broadcast topic to Alexa Echo Show"
                        >
                          <span>🔊</span>
                          <span>{isBroadcasting ? "SPEAKING..." : "BROADCAST TO ALEXA"}</span>
                        </button>
                      </div>
                    </div>

                    {/* Explanatory Synthesis Box */}
                    {topic.explanatory_synthesis && (
                      <div className="bg-gradient-to-r from-amber-950/30 to-[#121419] border border-amber-500/30 rounded-xl p-4">
                        <div className="font-mono text-[9px] text-amber-300 tracking-[0.2em] uppercase font-bold mb-1 flex items-center gap-1.5">
                          <span>⚡</span>
                          <span>EXPLANATORY CONTEXTUAL SYNTHESIS</span>
                        </div>
                        <p className="font-sans text-body-sm text-amber-100/90 leading-relaxed">
                          {topic.explanatory_synthesis}
                        </p>
                      </div>
                    )}

                    {/* 2 Columns: Executive Summary & Action Items/Sources */}
                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-space-md">
                      <div className="bg-[#121419] border border-surface-container-highest rounded-xl p-5 flex flex-col justify-between">
                        <div>
                          <div className="font-mono text-[9px] text-secondary tracking-[0.2em] uppercase mb-4 font-bold">
                            EXECUTIVE SUMMARY & INSIGHTS
                          </div>
                          <div className="font-sans text-body-sm text-secondary leading-relaxed space-y-2.5">
                            {topic.executive_summary?.map((sum, i) => (
                              <div key={i} className="flex items-start gap-2.5 text-primary">
                                <span className="text-amber-400 select-none">▪</span>
                                <span>{sum}</span>
                              </div>
                            )) || <div>No summary available</div>}
                          </div>
                        </div>
                      </div>

                      <div className="bg-[#121419] border border-surface-container-highest rounded-xl p-5 flex flex-col justify-between">
                        <div>
                          <div className="font-mono text-[9px] text-secondary tracking-[0.2em] uppercase mb-4 font-bold">
                            ACTION ITEMS & CITATIONS
                          </div>

                          {topic.action_items && topic.action_items.length > 0 && (
                            <div className="mb-4">
                              <strong className="text-primary font-mono text-[9px] tracking-widest uppercase mb-2 block">
                                Key Action Items
                              </strong>
                              <div className="space-y-1.5">
                                {topic.action_items.map((act, i) => (
                                  <div
                                    key={i}
                                    className="flex items-start gap-2 text-body-xs font-sans text-primary"
                                  >
                                    <span className="text-emerald-400">✓</span>
                                    <span>{act}</span>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}

                          {topic.web_sources && topic.web_sources.length > 0 && (
                            <div>
                              <strong className="text-primary font-mono text-[9px] tracking-widest uppercase mb-2 block">
                                Corroborating Citations
                              </strong>
                              <div className="space-y-1">
                                {topic.web_sources.slice(0, 3).map((src, i) => (
                                  <a
                                    key={i}
                                    href={src}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="block text-amber-200/90 hover:text-amber-300 font-mono text-[10px] truncate hover:underline"
                                    title={src}
                                  >
                                    🔗 {src}
                                  </a>
                                ))}
                              </div>
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
