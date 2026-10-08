interface SystemBarProps {
  activeTab: string;
  setActiveTab: (tab: string) => void;
  currentTime: string;
}

export function SystemBar({ activeTab, setActiveTab, currentTime }: SystemBarProps) {
  return (
    <header className="sys-bar">
      <div className="flex items-center gap-3 shrink-0">
        <div className="w-2.5 h-2.5 rounded-full bg-primary"></div>
        <div className="font-sans text-headline-sm tracking-wide font-semibold text-primary flex items-center gap-2">
          EXAMEN OS
          <span className="text-label-sm tracking-widest text-secondary uppercase font-mono ml-2 opacity-60">HUB-02</span>
        </div>
      </div>

      <div className="hidden lg:flex items-center gap-4 shrink-0 mx-8">
        <div className="status-badge">
          <div className="status-dot status-dot-active"></div>
          NODE: 01_SYNAPSE
        </div>
        <div className="status-badge">
          <div className="status-dot status-dot-active"></div>
          BEE: LINKED 98%
        </div>
        <div className="status-badge">
          <div className="status-dot status-dot-active"></div>
          AGENTCORE: ACTIVE
        </div>
      </div>

      <nav className="segmented-nav mx-auto overflow-x-auto hide-scrollbar">
        {["overview", "peace", "routines", "social", "topics", "simulator"].map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`segmented-tab ${activeTab === tab ? "segmented-tab-active" : "segmented-tab-inactive"}`}
          >
            {tab === "overview" ? "OVERVIEW HUB" : 
             tab === "peace" ? "PEACE OF MIND" : 
             tab === "routines" ? "DAILY ROUTINES" : 
             tab === "social" ? "SOCIAL ROLODEX" : 
             tab === "topics" ? "TOPIC DOSSIERS" : "AMBIENT SIMULATOR"}
          </button>
        ))}
      </nav>

      <div className="shrink-0 flex items-center gap-6 ml-auto hidden sm:flex">
        <div className="text-right">
          <div className="font-mono text-label-lg text-primary">{currentTime}</div>
          <div className="font-mono text-label-sm text-secondary mt-0.5">STABLE CADENCE</div>
        </div>
        <div className="w-10 h-10 rounded-full bg-surface-container-highest border border-outline-variant flex items-center justify-center">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" className="text-secondary" strokeWidth="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
        </div>
      </div>
    </header>
  );
}
