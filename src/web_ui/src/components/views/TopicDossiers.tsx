import { useState } from "react";
import { BriefingReport } from "@/types/schemas";
import { ScreenHeader } from "../ui/ScreenHeader";
import { FilterButton } from "../ui/FilterButton";
import { Badge } from "../ui/Badge";
import { MockAsterisk } from "../ui/MockAsterisk";

interface TopicDossiersProps {
  topicsData: { topics: BriefingReport[] } | undefined;
}

export function TopicDossiers({ topicsData }: TopicDossiersProps) {
  const [activeFilter, setActiveFilter] = useState<string>("ALL");
  const [searchQuery, setSearchQuery] = useState("");

  const topics = topicsData?.topics || [];
  const uniqueContexts = Array.from(new Set(topics.map(t => t.context_type))).filter(Boolean);

  const filteredTopics = topics.filter(t => {
    const matchesFilter = activeFilter === "ALL" || t.context_type === activeFilter;
    const matchesSearch = t.topic_title.toLowerCase().includes(searchQuery.toLowerCase()) || 
                          (t.executive_summary?.some(s => s.toLowerCase().includes(searchQuery.toLowerCase())));
    return matchesFilter && matchesSearch;
  });

  return (
    <div className="space-y-space-lg animate-in fade-in max-w-[1400px] mx-auto">
      <ScreenHeader 
        icon={<svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M12 2a9 9 0 0 0-9 9c0 4.97 4 9 9 9s9-4.03 9-9a9 9 0 0 0-9-9z"/><path d="M9 16v2"/><path d="M15 16v2"/><path d="M12 12v6"/><path d="M8 12a4 4 0 0 1 8 0"/></svg>}
        directive={<>COGNITIVE TELEMETRY SUBSYSTEM <span className="mx-2 opacity-50">•</span> <Badge variant="outline" className="!py-0.5 !px-2 border-white/10 opacity-70">AWS BEDROCK ZERO-SHOT AGENT</Badge></>}
        title="SCREEN PURPOSE: AUTONOMOUS TOPIC RESEARCH & ENRICHED DOSSIERS"
        description={<>Topic Dossiers act as your automated research organizer. When the Bee wearable listens to university class lectures, dense work calls, or technical discussions, EXAMEN's background agent automatically initiates deep research on the subjects mentioned. It synthesizes the ambient arguments into organized, citation-backed dossiers, perfect for reviewing study notes or catching up on complex meeting topics.</>}
        rightElement={
          <div className="flex flex-col items-end gap-1">
            <Badge variant="outline" dot="active" className="border-white/10 opacity-70 mb-1">
              SYNTHESIS ENGINE RUNNING
            </Badge>
            <div className="font-mono text-[9px] text-secondary tracking-[0.2em] uppercase">CADENCE: 14 SEC LATENCY</div>
          </div>
        }
      />

      {/* Search / Filter Row */}
      <div className="flex flex-col md:flex-row items-center gap-space-md mb-space-xl">
        <div className="flex-1 w-full relative">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="absolute left-4 top-1/2 -translate-y-1/2 text-secondary"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
          <input 
            type="text" 
            placeholder="Filter dossiers by thesis, author, protocol, or runtime token..." 
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full bg-surface-container-low border border-surface-container-highest rounded-md py-3 pl-12 pr-4 text-body-sm font-sans text-primary placeholder-secondary focus:outline-none focus:border-outline-variant" 
          />
        </div>
        <div className="flex flex-wrap items-center gap-2 shrink-0">
          <FilterButton active={activeFilter === "ALL"} onClick={() => setActiveFilter("ALL")}>
            ALL ({topics.length})
          </FilterButton>
          {uniqueContexts.map(ctx => (
            <FilterButton key={ctx} active={activeFilter === ctx} onClick={() => setActiveFilter(ctx as string)}>
              {ctx?.replace(/_/g, ' ').toUpperCase()} ({topics.filter(t => t.context_type === ctx).length})
            </FilterButton>
          ))}
        </div>
      </div>

      <div className="space-y-space-lg">
        {/* 
          // MOCK CARDS COMMENTED OUT
          Mock Card 
        <div className="card-elevated p-space-xl bg-surface-container-low border-surface-container-highest flex flex-col gap-6">
          <div className="flex items-start justify-between">
             <div className="flex flex-col">
                <div className="font-mono text-[9px] text-primary tracking-[0.2em] uppercase flex items-center gap-2 mb-4 font-bold">
                  DOSSIER #418 • HARVESTED AT BREAKFAST <span className="opacity-50 mx-1">•</span> <span className="text-secondary font-normal">SYNTHESIZED 08:14 UTC</span>
                </div>
                <h3 className="font-serif text-[36px] text-primary leading-none mb-3">The Anxious Generation<MockAsterisk /></h3>
                <div className="font-sans text-body-lg text-secondary">Jonathan Haidt (Penguin Press, 2024 Analysis)</div>
             </div>
             <div className="flex gap-2 shrink-0">
                <button className="px-5 py-2.5 rounded border border-surface-container-highest bg-transparent hover:bg-surface-container text-secondary hover:text-primary font-mono text-[9px] tracking-[0.2em] flex items-center gap-2 transition-colors">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1 0-5H20"/></svg>
                  ABSTRACT
                </button>
                <button className="px-5 py-2.5 rounded border border-surface-container-highest bg-surface-container-highest text-primary font-mono text-[9px] tracking-[0.2em] font-bold flex items-center gap-2 hover:bg-outline-variant transition-colors">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/></svg>
                  BROADCAST
                </button>
             </div>
          </div>

          <div className="bg-[#121316] border border-surface-container-highest rounded-lg p-space-md flex gap-4 mt-2">
             <div className="shrink-0 pt-1 text-secondary">
               <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 2v20M17 5v14M22 10v4M7 5v14M2 10v4"/></svg>
             </div>
             <div>
               <div className="font-mono text-[9px] text-secondary tracking-[0.2em] uppercase mb-2">CONVERSATION ORIGIN SNIPPET</div>
               <div className="font-sans text-body-md text-primary italic">“Mentioned during 08:14 conversation with Elena regarding smartphone policies in primary schools and the collapse of unstructured play.”</div>
             </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-space-md mt-4">
             <div className="bg-[#121316] border border-surface-container-highest rounded-lg p-space-lg flex flex-col">
               <div className="flex items-center justify-between mb-6 font-mono text-[9px] text-secondary tracking-[0.2em] uppercase">
                 <span>THESIS 01</span>
                 <span>2010-2015</span>
               </div>
               <div className="font-serif text-[20px] text-primary mb-4">The Great Rewiring</div>
               <p className="font-sans text-body-sm text-secondary leading-relaxed mb-12 flex-1">
                 The fundamental migration of early adolescent development from a physical play-based reality to a continuous phone-based existence, causing systematic disruption in sleep, physical sociality, and sustained cognitive focus.
               </p>
               <div className="flex items-center gap-2 font-mono text-[8px] text-secondary tracking-[0.2em] uppercase border-t border-surface-container-highest pt-4">
                 <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
                 EPIDEMIOLOGICAL CORRELATION: 0.88
               </div>
             </div>

             <div className="bg-[#121316] border border-surface-container-highest rounded-lg p-space-lg flex flex-col">
               <div className="flex items-center justify-between mb-6 font-mono text-[9px] text-secondary tracking-[0.2em] uppercase">
                 <span>THESIS 02</span>
                 <span>FRAMEWORK</span>
               </div>
               <div className="font-serif text-[20px] text-primary mb-4">Four Norm Reforms</div>
               <div className="font-sans text-body-sm text-secondary leading-relaxed mb-12 flex-1 space-y-2">
                 <div>1. Zero smartphones prior to high school.</div>
                 <div>2. Zero social media platforms prior to age 16.</div>
                 <div>3. Strictly phone-free campus architecture.</div>
                 <div>4. Restored community-level unsupervised autonomy.</div>
               </div>
               <div className="flex items-center gap-2 font-mono text-[8px] text-secondary tracking-[0.2em] uppercase border-t border-surface-container-highest pt-4">
                 <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/></svg>
                 SYSTEMIC COLLECTIVE ACTION
               </div>
             </div>

             <div className="bg-[#121316] border border-surface-container-highest rounded-lg p-space-lg flex flex-col">
               <div className="flex items-center justify-between mb-6 font-mono text-[9px] text-secondary tracking-[0.2em] uppercase">
                 <span>EXAMEN SYNTHESIS</span>
                 <span>LOCAL OS</span>
               </div>
               <div className="font-serif text-[20px] text-primary mb-4">Calm Computing Counterpoint</div>
               <p className="font-sans text-body-sm text-secondary leading-relaxed mb-12 flex-1">
                 Hardware-native ambient monitors act as grounding physical anchors. By replacing infinite pull-to-refresh feeds with deterministic glanceability, EXAMEN neutralizes dopaminergic behavioral conditioning.
               </p>
               <div className="flex items-center gap-2 font-mono text-[8px] text-secondary tracking-[0.2em] uppercase border-t border-surface-container-highest pt-4">
                 <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="20 6 9 17 4 12"/></svg>
                 ALIGNMENT METRIC: 99.4%
               </div>
             </div>
          </div>
        </div>
        */}

        {/* Dynamic Mapping from topicsData */}
        {filteredTopics.map(topic => (
          <div key={topic.id} className="card-elevated p-space-xl bg-surface-container-low border-surface-container-highest flex flex-col gap-6">
            <div className="flex items-start justify-between">
               <div className="flex flex-col">
                  <div className="font-mono text-[9px] text-primary tracking-[0.2em] uppercase flex items-center gap-2 mb-4 font-bold">
                    DOSSIER #{topic.id.substring(0,6).toUpperCase()} • DYNAMIC CAPTURE <span className="opacity-50 mx-1">•</span> <span className="text-secondary font-normal">SYNTHESIZED {topic.created_at?.split('T')[1]?.substring(0,5) || '-'} UTC</span>
                  </div>
                  <h3 className="font-serif text-[36px] text-primary leading-none mb-3">{topic.topic_title}</h3>
                  <div className="font-sans text-body-lg text-secondary">
                    {topic.context_type?.replace(/_/g, ' ').toUpperCase() || 'GENERAL RESEARCH'}
                  </div>
               </div>
               <div className="flex gap-2 shrink-0">
                  <button className="px-5 py-2.5 rounded border border-surface-container-highest bg-transparent hover:bg-surface-container text-secondary hover:text-primary font-mono text-[9px] tracking-[0.2em] flex items-center gap-2 transition-colors">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1 0-5H20"/></svg>
                    ABSTRACT
                  </button>
                  <button className="px-5 py-2.5 rounded border border-surface-container-highest bg-surface-container-highest text-primary font-mono text-[9px] tracking-[0.2em] font-bold flex items-center gap-2 hover:bg-outline-variant transition-colors">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/></svg>
                    BROADCAST
                  </button>
               </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-space-md mt-2">
               {/* Summary */}
               <div className="bg-[#121316] border border-surface-container-highest rounded-lg p-space-lg flex flex-col">
                 <div className="flex items-center justify-between mb-6 font-mono text-[9px] text-secondary tracking-[0.2em] uppercase">
                   <span>EXECUTIVE SUMMARY</span>
                 </div>
                 <div className="font-sans text-body-sm text-secondary leading-relaxed flex-1 space-y-2">
                   {topic.executive_summary?.map((sum, i) => <div key={i}>• {sum}</div>) || <div>No summary available</div>}
                 </div>
               </div>

               {/* Action Items / Sources */}
               <div className="bg-[#121316] border border-surface-container-highest rounded-lg p-space-lg flex flex-col">
                 <div className="flex items-center justify-between mb-6 font-mono text-[9px] text-secondary tracking-[0.2em] uppercase">
                   <span>ACTION ITEMS & SOURCES</span>
                 </div>
                 <div className="font-sans text-body-sm text-secondary leading-relaxed flex-1 space-y-4">
                   {topic.action_items && topic.action_items.length > 0 && (
                     <div>
                       <strong className="text-primary font-mono text-[9px] tracking-widest uppercase mb-2 block">Action Items</strong>
                       {topic.action_items.map((act, i) => <div key={i}>• {act}</div>)}
                     </div>
                   )}
                   {topic.web_sources && topic.web_sources.length > 0 && (
                     <div>
                       <strong className="text-primary font-mono text-[9px] tracking-widest uppercase mb-2 block">Citations</strong>
                       {topic.web_sources.map((src, i) => (
                         <a key={i} href={src} target="_blank" className="block text-primary hover:underline truncate" title={src}>🔗 {src}</a>
                       ))}
                     </div>
                   )}
                 </div>
               </div>
            </div>
          </div>
        ))}
        
      </div>
    </div>
  );
}
