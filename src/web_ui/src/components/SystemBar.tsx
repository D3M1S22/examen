import React from "react";

interface SystemBarProps {
  activeTab: string;
  setActiveTab: (tab: string) => void;
  currentTime: string;
  onOpenEchoModal?: () => void;
  sseConnected?: boolean;
  statusData?: any;
}

export function SystemBar({
  activeTab,
  setActiveTab,
  currentTime,
  onOpenEchoModal,
  sseConnected = true,
  statusData,
}: SystemBarProps) {
  const tabs = [
    { id: "overview", label: "OVERVIEW HUB" },
    { id: "peace", label: "PEACE OF MIND" },
    { id: "routines", label: "DAILY ROUTINES" },
    { id: "social", label: "SOCIAL ROLODEX" },
    { id: "topics", label: "TOPIC DOSSIERS" },
    { id: "simulator", label: "AMBIENT SIMULATOR" },
  ];


  return (
    <header className="sys-bar">
      <div className="flex items-center gap-3 shrink-0">
        <div className="w-2.5 h-2.5 rounded-full bg-primary animate-pulse"></div>
        <div className="font-sans text-headline-sm tracking-wide font-semibold text-primary flex items-center gap-2">
          EXAMEN OS
          <span className="text-label-sm tracking-widest text-secondary uppercase font-mono ml-2 opacity-60">
            HUB-02
          </span>
        </div>
      </div>

      {/* Tab Navigation */}
      <nav className="segmented-nav mx-auto overflow-x-auto hide-scrollbar">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`segmented-tab ${
              activeTab === tab.id ? "segmented-tab-active" : "segmented-tab-inactive"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </nav>

      {/* Right Controls */}
      <div className="shrink-0 flex items-center gap-4 ml-auto">
        {onOpenEchoModal && (
          <button
            onClick={onOpenEchoModal}
            className="hidden sm:flex items-center gap-2 px-3 py-1.5 rounded-lg bg-cyan-950/60 border border-cyan-500/40 text-cyan-300 font-mono text-[10px] tracking-widest uppercase hover:bg-cyan-900 transition-colors shadow-sm"
            title="Open Alexa Echo Show 15 Multimodal Ext-App simulator"
          >
            <span>📺</span>
            <span>Echo Show Ext-App</span>
          </button>
        )}

        <div className="text-right hidden sm:block">
          <div className="font-mono text-label-lg text-primary">{currentTime}</div>
          <div className="font-mono text-label-sm text-secondary mt-0.5">STABLE CADENCE</div>
        </div>
      </div>
    </header>
  );
}
