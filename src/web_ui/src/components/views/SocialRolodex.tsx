import { SocialEntity } from "@/types/schemas";
import { ScreenHeader } from "../ui/ScreenHeader";
import { Badge } from "../ui/Badge";
import { FilterButton } from "../ui/FilterButton";
import { MockAsterisk } from "../ui/MockAsterisk";

interface SocialRolodexProps {
  socialData: { contacts: SocialEntity[] } | undefined;
}

export function SocialRolodex({ socialData }: SocialRolodexProps) {
  return (
    <div className="space-y-space-lg animate-in fade-in max-w-[1200px] mx-auto">
      <ScreenHeader 
        directive="SCREEN PURPOSE // SUB-SYSTEM DIRECTORY"
        title="PASSIVE CONVERSATIONAL CRM & SOCIAL MEMORY"
        description={<>EXAMEN passively captures bilateral commitments, professional introductions, and coworker mentions from ambient dialogue. It automatically isolates roles, technical architectures, and mutual promises without manual intervention, constructing a private local knowledge graph synchronized to your trusted contacts.</>}
        rightElement={
          <Badge variant="outline" className="border-white/10 opacity-70">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
            PII SANITIZED LOCAL ENCLAVE
          </Badge>
        }
      />

      {/* 3 KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-space-md mb-space-lg">
        <div className="card-elevated p-space-lg flex flex-col justify-between">
          <div className="font-mono text-[9px] text-secondary tracking-[0.2em] uppercase mb-6">INGESTED TODAY</div>
          <div className="flex items-center justify-between">
            <div className="font-serif text-[44px] text-primary">01</div>
            <div className="w-12 h-12 rounded-lg bg-surface-container-highest flex items-center justify-center text-primary">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><line x1="19" y1="8" x2="19" y2="14"/><line x1="22" y1="11" x2="16" y2="11"/></svg>
            </div>
          </div>
        </div>
        <div className="card-elevated p-space-lg flex flex-col justify-between">
          <div className="font-mono text-[9px] text-secondary tracking-[0.2em] uppercase mb-6">TOTAL ENCOUNTERS INDEXED</div>
          <div className="flex items-center justify-between">
            <div className="font-serif text-[44px] text-primary">148</div>
            <div className="w-12 h-12 rounded-lg bg-surface-container-highest flex items-center justify-center text-primary">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>
            </div>
          </div>
        </div>
        <div className="card-elevated p-space-lg flex flex-col justify-between">
          <div className="font-mono text-[9px] text-secondary tracking-[0.2em] uppercase mb-6">PENDING FOLLOW-UPS</div>
          <div className="flex items-center justify-between">
            <div className="flex items-baseline gap-2">
              <span className="font-serif text-[44px] text-primary">03</span>
              <span className="font-mono text-[9px] text-error tracking-[0.2em] uppercase">NEEDS ACTION</span>
            </div>
            <div className="w-12 h-12 rounded-lg bg-surface-container-highest flex items-center justify-center text-primary">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><rect x="8" y="2" width="8" height="4" rx="1" ry="1"/><circle cx="12" cy="14" r="3"/><path d="M12 11v3l2 1"/></svg>
            </div>
          </div>
        </div>
      </div>

      {/* Search / Filter Row */}
      <div className="flex flex-col md:flex-row items-center gap-space-md mb-space-xl">
        <div className="flex-1 w-full relative">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="absolute left-4 top-1/2 -translate-y-1/2 text-secondary"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
          <input type="text" placeholder="Search contacts, organizations, mutual commitments, or tags..." className="w-full bg-surface-container-low border border-surface-container-highest rounded-md py-3 pl-12 pr-4 text-body-sm font-sans text-primary placeholder-secondary focus:outline-none focus:border-outline-variant" />
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <FilterButton active>ALL (148)</FilterButton>
          <FilterButton>COMMITMENTS DUE (3)</FilterButton>
          <FilterButton>RECENTLY INGESTED</FilterButton>
          <button className="w-10 h-10 rounded-md bg-surface-container-low border border-surface-container-highest flex items-center justify-center text-secondary hover:text-primary transition-colors ml-2">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="4" y1="21" x2="4" y2="14"/><line x1="4" y1="10" x2="4" y2="3"/><line x1="12" y1="21" x2="12" y2="12"/><line x1="12" y1="8" x2="12" y2="3"/><line x1="20" y1="21" x2="20" y2="16"/><line x1="20" y1="12" x2="20" y2="3"/><line x1="1" y1="14" x2="7" y2="14"/><line x1="9" y1="8" x2="15" y2="8"/><line x1="17" y1="16" x2="23" y2="16"/></svg>
          </button>
        </div>
      </div>

      <div className="flex items-center justify-between font-mono text-[9px] text-secondary tracking-[0.2em] uppercase mb-4 border-b border-surface-container-highest pb-4">
        <span>SOCIAL INDEX FEED / SORTED BY RECENCY</span>
        <span>{socialData?.contacts?.length || 1} DISPLAYED</span>
      </div>

      {/* Action Cards Grid */}
      <div className="space-y-space-lg">
        {/* Hardcoded mock for visual parity */}
        <div className="card-elevated p-space-xl flex flex-col gap-8 bg-surface-container-lowest border-surface-container-highest">
          {/* Header Row */}
          <div className="flex flex-col md:flex-row justify-between items-start gap-4">
            <div className="flex items-start gap-4">
              <div className="w-14 h-14 rounded-lg bg-surface-container-highest border border-outline-variant flex items-center justify-center text-primary font-serif text-[20px]">
                AV
              </div>
              <div>
                <div className="flex items-center gap-3 mb-1">
                  <h3 className="font-serif text-[24px] text-primary font-normal">Andrea<MockAsterisk /></h3>
                  <Badge variant="filled" className="text-background bg-primary">FIRST ENCOUNTER TODAY</Badge>
                </div>
                <div className="font-sans text-body-sm text-secondary mb-3">DevOps Lead at <span className="text-primary">Almaviva</span></div>
                <div className="flex items-center gap-3 font-mono text-[9px] text-secondary tracking-[0.2em] uppercase">
                  <span className="flex items-center gap-1"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg> OCT 06, 2026 • HUB CORRIDOR</span>
                  <span className="opacity-40">•</span>
                  <span>DURATION: 11M 40S</span>
                </div>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <button className="px-4 py-2 rounded border border-surface-container-highest bg-transparent hover:bg-surface-container text-secondary hover:text-primary font-mono text-[9px] tracking-[0.2em] flex items-center gap-2 transition-colors">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
                EXPORT CARD
              </button>
              <button className="px-4 py-2 rounded border border-surface-container-highest bg-transparent hover:bg-surface-container text-secondary hover:text-primary font-mono text-[9px] tracking-[0.2em] flex items-center gap-2 transition-colors">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/></svg>
                DRAFT FOLLOW-UP
              </button>
              <button className="px-4 py-2 rounded border border-primary bg-primary text-background font-mono text-[9px] font-bold tracking-[0.2em] flex items-center gap-2 hover:bg-surface-tint transition-colors">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
                VIEW TRACE
              </button>
            </div>
          </div>

          {/* Extracted Details Row */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-space-lg">
            {/* Left: Context */}
            <div className="flex flex-col">
              <div className="font-mono text-[9px] text-secondary tracking-[0.2em] uppercase mb-3">EXTRACTED AGENT CONTEXT</div>
              <div className="bg-[#121316] border border-surface-container-highest rounded-lg p-space-md mb-4 text-body-md text-secondary leading-relaxed font-sans">
                “Discussed branch test automation and Bedrock Mantle pipeline deployment strategies. Noted mutual preference for trunk-based continuous delivery and acoustic isolation in open layouts.”
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <span className="px-2 py-1 rounded bg-surface-container-low border border-surface-container-highest font-mono text-[10px] text-secondary hover:text-primary transition-colors cursor-pointer">#DevOps</span>
                <span className="px-2 py-1 rounded bg-surface-container-low border border-surface-container-highest font-mono text-[10px] text-secondary hover:text-primary transition-colors cursor-pointer">#GitHub</span>
                <span className="px-2 py-1 rounded bg-surface-container-low border border-surface-container-highest font-mono text-[10px] text-secondary hover:text-primary transition-colors cursor-pointer">#Branch-Testing</span>
                <span className="px-2 py-1 rounded bg-surface-container-low border border-surface-container-highest font-mono text-[10px] text-secondary hover:text-primary transition-colors cursor-pointer">#Bedrock-Mantle</span>
                <span className="px-2 py-1 rounded bg-surface-container-low border border-surface-container-highest font-mono text-[10px] text-secondary hover:text-primary transition-colors cursor-pointer">#Almaviva</span>
              </div>
            </div>

            {/* Right: Commitment */}
            <div className="flex flex-col h-full bg-[#121316] border border-surface-container-highest rounded-lg p-space-lg">
              <div className="flex items-center justify-between mb-4">
                <div className="font-mono text-[9px] text-primary tracking-[0.2em] uppercase flex items-center gap-2 font-bold">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>
                  BILATERAL COMMITMENT
                </div>
                <div className="px-2 py-1 rounded border border-error/30 text-error font-mono text-[9px] tracking-[0.2em]">
                  DUE THURSDAY
                </div>
              </div>
              <div className="text-body-md text-primary leading-relaxed font-sans mb-8">
                “Agreed to send Bedrock Mantle fastmcp schema over Slack before Thursday.”
              </div>
              <div className="mt-auto flex items-center justify-between font-mono text-[9px] text-secondary tracking-[0.2em] border-t border-surface-container-highest pt-4">
                <span>SYNAPSE STATE: UNFULFILLED</span>
                <span className="text-primary hover:underline cursor-pointer">MARK DISPATCHED</span>
              </div>
            </div>
          </div>
        </div>

        {/* Dynamic Mapping */}
        {socialData?.contacts?.map(contact => (
          <div key={contact.id} className="card-elevated p-space-xl flex flex-col gap-8 bg-surface-container-lowest border-surface-container-highest">
            <div className="flex flex-col md:flex-row justify-between items-start gap-4">
              <div className="flex items-start gap-4">
                <div className="w-14 h-14 rounded-lg bg-surface-container-highest border border-outline-variant flex items-center justify-center text-primary font-serif text-[20px]">
                  {contact.name.substring(0, 2).toUpperCase()}
                </div>
                <div>
                  <div className="flex items-center gap-3 mb-1">
                    <h3 className="font-serif text-[24px] text-primary font-normal">{contact.name}</h3>
                  </div>
                  <div className="font-sans text-body-sm text-secondary mb-3">{contact.company_or_role || 'Independent Contact'}</div>
                  <div className="flex items-center gap-3 font-mono text-[9px] text-secondary tracking-[0.2em] uppercase">
                    <span className="flex items-center gap-1"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg> {contact.timestamp?.split('T')[0] || '-'}</span>
                    <span className="opacity-40">•</span>
                    <span>{contact.contact_info || 'NO COMM DATA'}</span>
                  </div>
                </div>
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-space-lg">
              <div className="flex flex-col">
                <div className="font-mono text-[9px] text-secondary tracking-[0.2em] uppercase mb-3">EXTRACTED AGENT CONTEXT</div>
                <div className="flex flex-wrap items-center gap-2 mt-auto">
                  {contact.key_topics?.map(topic => (
                    <span key={topic} className="px-2 py-1 rounded bg-surface-container-low border border-surface-container-highest font-mono text-[10px] text-secondary hover:text-primary transition-colors cursor-pointer">#{topic}</span>
                  ))}
                </div>
              </div>
              {contact.commitments && contact.commitments.length > 0 && (
                <div className="flex flex-col h-full bg-[#121316] border border-surface-container-highest rounded-lg p-space-lg">
                  <div className="font-mono text-[9px] text-primary tracking-[0.2em] uppercase flex items-center gap-2 font-bold mb-4">
                    BILATERAL COMMITMENTS ({contact.commitments.length})
                  </div>
                  <ul className="list-disc list-inside space-y-2 text-body-md text-primary font-sans mb-8">
                    {contact.commitments.map((cmt, i) => <li key={i}>{cmt}</li>)}
                  </ul>
                </div>
              )}
            </div>
          </div>
        ))}

      </div>
    </div>
  );
}
