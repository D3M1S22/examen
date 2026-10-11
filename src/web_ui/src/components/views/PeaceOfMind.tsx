import { useState } from "react";
import { VerifiedAction } from "@/types/schemas";
import { ScreenHeader } from "../ui/ScreenHeader";
import { Badge } from "../ui/Badge";
import { FilterButton } from "../ui/FilterButton";
import { MockAsterisk } from "../ui/MockAsterisk";

interface PeaceOfMindProps {
  actionsData: { actions: VerifiedAction[] } | undefined;
}

export function PeaceOfMind({ actionsData }: PeaceOfMindProps) {
  const [activeFilter, setActiveFilter] = useState<string>("ALL");

  const actions = actionsData?.actions || [];
  const uniqueDomains = Array.from(new Set(actions.map(a => a.domain))).filter(Boolean);

  const filteredActions = activeFilter === "ALL" 
    ? actions 
    : actions.filter(a => a.domain === activeFilter);

  return (
    <div className="space-y-space-lg animate-in fade-in max-w-[1400px] mx-auto">
      <ScreenHeader 
        directive="SCREEN PURPOSE // ARCHITECTURAL CONTEXT"
        title="DOMESTIC REASSURANCE & ACOUSTIC PROOF"
        description={<>The Peace of Mind sector captures unplanned tasks, ad-hoc reminders, and spontaneous verbal notes that fall outside your strict daily routines. Whether it's verifying you locked the door, reminding you to buy groceries mentioned in passing, or capturing a quick thought, EXAMEN passively corroborates these general peace of mind checks via the Bee wearable. Never lose track of the unstructured moments of your day.</>}
        rightElement={
          <div className="bg-[#121316] border border-surface-container-highest rounded-lg p-4 font-mono w-[300px]">
            <div className="flex justify-between items-center text-[8px] text-secondary tracking-[0.2em] uppercase mb-2">
              <span>SENSOR MESH</span>
              <span className="text-primary font-bold">BEE EARPIECE V4</span>
            </div>
            <div className="flex justify-between items-center text-[8px] text-secondary tracking-[0.2em] uppercase mb-2">
              <span>PROCESSING MODEL</span>
              <span className="text-primary font-bold">DSP EMBEDDED EDGE</span>
            </div>
            <div className="flex justify-between items-center text-[8px] text-secondary tracking-[0.2em] uppercase">
              <span>LATENCY OVERHEAD</span>
              <span className="text-primary font-bold">12ms PASSIVE</span>
            </div>
          </div>
        }
      />

      {/* KPI Full Width Card */}
      <div className="card-elevated p-space-xl flex flex-col md:flex-row items-start md:items-center justify-between gap-space-lg mb-space-lg bg-surface-container-low border-surface-container-highest">
        <div className="flex items-center gap-space-lg">
          <div className="w-16 h-16 rounded-full bg-[#121316] border border-surface-container-highest flex items-center justify-center text-primary shrink-0">
             <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>
          </div>
          <div>
            <div className="flex items-center gap-4 mb-2">
              <h3 className="font-serif text-[28px] text-primary">Unplanned Reminders & Notes</h3>
              <Badge variant="filled" className="bg-[#121316] text-secondary border border-surface-container-highest">{actions.length} CAPTURED TODAY</Badge>
            </div>
            <div className="font-sans text-body-md text-secondary">Spontaneous ideas • Grocery additions • Ad-hoc lock checks • Passive mental notes</div>
          </div>
        </div>
        
        <div className="flex items-center gap-space-xl shrink-0 md:border-l border-surface-container-highest md:pl-space-xl">
          <div className="flex flex-col">
            <div className="font-mono text-[9px] text-secondary tracking-[0.2em] uppercase mb-1">AVERAGE CONFIDENCE</div>
            <div className="flex items-baseline gap-1 font-serif text-[44px] text-primary">
              {actions.length > 0 ? (actions.reduce((acc, a) => acc + a.confidence, 0) / actions.length * 100).toFixed(1) : "0"}
              <span className="text-[20px]">%</span>
            </div>
          </div>
          <button className="btn-primary font-mono text-[11px] font-bold tracking-[0.2em] bg-primary text-background px-6 py-4 rounded hover:bg-surface-tint ml-4">
            ADD QUICK NOTE
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center justify-between gap-4 mb-space-xl">
        <div className="flex flex-wrap items-center gap-2">
          <FilterButton active={activeFilter === "ALL"} onClick={() => setActiveFilter("ALL")}>
            ALL VERIFIED ({actions.length})
          </FilterButton>
          {uniqueDomains.map(domain => (
            <FilterButton key={domain} active={activeFilter === domain} onClick={() => setActiveFilter(domain)}>
              {domain.replace(/_/g, ' ').toUpperCase()} ({actions.filter(a => a.domain === domain).length})
            </FilterButton>
          ))}
        </div>
        <div className="flex items-center gap-2">
          <div className="px-4 py-2.5 font-mono text-[9px] text-secondary tracking-[0.2em] flex items-center gap-2 uppercase">
            <div className="w-1.5 h-1.5 rounded-full bg-outline-variant"></div>
            ACOUSTIC INGESTION: CONTINUOUS
          </div>
        </div>
      </div>

      {/* Action Cards Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-space-lg">
        {/* 
          // MOCK CARDS COMMENTED OUT
          Mock Card 1 
        <div className="card-elevated p-space-xl flex flex-col bg-surface-container-low border-surface-container-highest">
          <div className="flex items-start justify-between mb-8">
            <div className="flex items-center gap-4">
               <div className="w-12 h-12 rounded-lg bg-[#121316] border border-surface-container-highest flex items-center justify-center text-primary shrink-0">
                 <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><rect x="4" y="8" width="16" height="8" rx="2" ry="2"/><path d="M16 12h-8"/><path d="M8 12H6"/><path d="M18 12h-2"/></svg>
               </div>
               <div>
                 <div className="font-mono text-[9px] text-secondary tracking-[0.2em] uppercase mb-1">OUTLET A3 // MASTER SUITE</div>
                 <h3 className="font-serif text-[26px] text-primary font-normal">Iron & Styling Wand<MockAsterisk /></h3>
               </div>
            </div>
            <Badge variant="filled" dot="active" className="bg-[#121316] text-primary border border-surface-container-highest">UNPLUGGED</Badge>
          </div>
          
          <div className="flex items-center justify-between font-mono text-[9px] text-secondary tracking-[0.2em] uppercase mb-4">
             <span>ACOUSTIC DETENT SNAP + VOCAL CONFIRMATION</span>
             <span className="text-primary font-bold">07:42:19 CET</span>
          </div>
          <p className="font-sans text-body-md text-secondary mb-8 leading-relaxed">
            “Receptacle detent snap captured. Vocal utterance registered: 'Iron is unplugged.' Thermal decay envelope validated.”
          </p>

          <div className="flex items-center gap-4 mb-10">
            <div className="bg-[#121316] border border-surface-container-highest rounded-lg p-3 flex-1 flex items-center">
              <div className="flex items-end gap-1 h-8 px-2">
                 {[4,8,6,12,18,14,10,16,8,4,2,2].map((h, i) => (
                   <div key={i} className="w-1 bg-secondary rounded-t-sm" style={{height: `${h}px`}}></div>
                 ))}
                 <div className="w-8"></div>
              </div>
            </div>
            <div className="font-mono text-[9px] text-secondary tracking-[0.2em] uppercase shrink-0">
               HASH: 4b9a_sig
            </div>
          </div>
          
          <div className="mt-auto flex items-center justify-between border-t border-surface-container-highest pt-6">
            <div className="font-mono text-[10px] text-secondary tracking-[0.2em] uppercase">
              CONFIDENCE: <span className="text-primary font-bold">99.4%</span>
            </div>
            <div className="flex gap-2">
              <button className="px-5 py-2.5 rounded bg-surface-container-highest text-primary font-mono text-[9px] font-bold tracking-[0.2em] flex items-center gap-2 hover:bg-outline-variant transition-colors">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M15.54 8.46a5 5 0 0 1 0 7.07"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14"/></svg>
                PLAY CITATION
              </button>
              <button className="px-5 py-2.5 rounded border border-surface-container-highest bg-transparent hover:bg-surface-container text-secondary hover:text-primary font-mono text-[9px] tracking-[0.2em] transition-colors">
                ECHO REASSURANCE
              </button>
            </div>
          </div>
        </div>

        Mock Card 2 
        <div className="card-elevated p-space-xl flex flex-col bg-surface-container-low border-surface-container-highest">
          <div className="flex items-start justify-between mb-8">
            <div className="flex items-center gap-4">
               <div className="w-12 h-12 rounded-lg bg-[#121316] border border-surface-container-highest flex items-center justify-center text-primary shrink-0">
                 <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M17 10H7l-5 8h20l-5-8z"/><path d="M7 10V6a5 5 0 0 1 10 0v4"/><path d="M12 2v2"/><path d="M15 2l-1 2"/><path d="M9 2l1 2"/></svg>
               </div>
               <div>
                 <div className="font-mono text-[9px] text-secondary tracking-[0.2em] uppercase mb-1">ZONE K1 // INDUCTION CORE</div>
                 <h3 className="font-serif text-[26px] text-primary font-normal">Stove & Induction Cooktop<MockAsterisk /></h3>
               </div>
            </div>
            <Badge variant="filled" dot="idle" className="bg-[#121316] text-secondary border border-surface-container-highest">COLD / INACTIVE</Badge>
          </div>
          
          <div className="flex items-center justify-between font-mono text-[9px] text-secondary tracking-[0.2em] uppercase mb-4">
             <span>ROTARY DETENT CLICK + INVERTER ZERO NOISE</span>
             <span className="text-primary font-bold">07:55:04 CET</span>
          </div>
          <p className="font-sans text-body-md text-secondary mb-8 leading-relaxed">
            Tactile knob mechanical return registered at 07:55 CET. Resonant pan removal resonance confirmed. Current transducer indicates 0W standby draw.
          </p>

          <div className="flex items-center gap-4 mb-10">
            <div className="bg-[#121316] border border-surface-container-highest rounded-lg p-3 flex-1 flex items-center">
              <div className="flex items-end gap-1 h-8 px-2">
                 {[12,6,10,4,2,2,2,2,2].map((h, i) => (
                   <div key={i} className="w-1 bg-secondary rounded-t-sm" style={{height: `${h}px`}}></div>
                 ))}
              </div>
            </div>
            <div className="font-mono text-[9px] text-secondary tracking-[0.2em] uppercase shrink-0">
               HASH: 8d12_det
            </div>
          </div>
          
          <div className="mt-auto flex items-center justify-between border-t border-surface-container-highest pt-6">
            <div className="font-mono text-[10px] text-secondary tracking-[0.2em] uppercase">
              CONFIDENCE: <span className="text-primary font-bold">98.9%</span>
            </div>
            <div className="flex gap-2">
              <button className="px-5 py-2.5 rounded border border-surface-container-highest bg-transparent hover:bg-surface-container text-secondary hover:text-primary font-mono text-[9px] tracking-[0.2em] transition-colors">
                ECHO REASSURANCE
              </button>
            </div>
          </div>
        </div>
        */}

        {/* Dynamic Mapping from actionsData */}
        {filteredActions.map(action => (
          <div key={action.id} className="card-elevated p-space-xl flex flex-col bg-surface-container-low border-surface-container-highest">
            <div className="flex items-start justify-between mb-8">
              <div className="flex items-center gap-4">
                 <div className="w-12 h-12 rounded-lg bg-[#121316] border border-surface-container-highest flex items-center justify-center text-primary shrink-0 text-xl">
                   {action.domain === 'safety' ? '🛡️' : action.domain === 'work_task' ? '💼' : '📋'}
                 </div>
                 <div>
                   <div className="font-mono text-[9px] text-secondary tracking-[0.2em] uppercase mb-1">DYNAMIC DOMAIN // {action.domain}</div>
                   <h3 className="font-serif text-[26px] text-primary font-normal capitalize">{action.action_type.replace(/_/g, ' ')}</h3>
                 </div>
              </div>
              <Badge variant="filled" dot="active" className="bg-[#121316] text-primary border border-surface-container-highest">VERIFIED</Badge>
            </div>
            
            <div className="flex items-center justify-between font-mono text-[9px] text-secondary tracking-[0.2em] uppercase mb-4">
               <span>DYNAMIC CAPTURE LOG</span>
               <span className="text-primary font-bold">{action.timestamp?.split('T')[1]?.substring(0,8) || action.timestamp}</span>
            </div>
            <p className="font-sans text-body-md text-secondary mb-8 leading-relaxed italic">
              "{action.raw_statement}"
            </p>

            <div className="flex items-center gap-4 mb-10">
              <div className="bg-[#121316] border border-surface-container-highest rounded-lg p-3 flex-1 flex items-center">
                {/* Waveform placeholder for dynamic ones */}
                <svg width="100%" height="24" viewBox="0 0 400 24" preserveAspectRatio="none" className="text-secondary stroke-current opacity-50" fill="none" strokeWidth="1.5">
                   <path d="M0,12 L150,12 L160,2 L170,22 L180,12 L400,12"/>
                </svg>
              </div>
              <div className="font-mono text-[9px] text-secondary tracking-[0.2em] uppercase shrink-0">
                 HASH: {action.id.substring(0, 8)}
              </div>
            </div>
            
            <div className="mt-auto flex items-center justify-between border-t border-surface-container-highest pt-6">
              <div className="font-mono text-[10px] text-secondary tracking-[0.2em] uppercase">
                CONFIDENCE: <span className="text-primary font-bold">{(action.confidence * 100).toFixed(1)}%</span>
              </div>
              <div className="flex gap-2">
                <button className="px-5 py-2.5 rounded border border-surface-container-highest bg-transparent hover:bg-surface-container text-secondary hover:text-primary font-mono text-[9px] tracking-[0.2em] transition-colors">
                  ECHO REASSURANCE
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
