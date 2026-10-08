import { PlannedTask } from "@/types/schemas";
import { MockAsterisk } from "../ui/MockAsterisk";

interface OverviewHubProps {
  routinesData: { tasks: PlannedTask[] } | undefined;
  setActiveTab: (tab: string) => void;
  setSimText: (text: string) => void;
  handleToggleRoutine: (task: PlannedTask) => void;
}

export function OverviewHub({ routinesData, setActiveTab, setSimText, handleToggleRoutine }: OverviewHubProps) {
  return (
    <div className="space-y-space-xl animate-in fade-in max-w-[1400px] mx-auto">
      {/* Top Status Panel */}
      <div className="card-elevated p-space-xl flex flex-col md:flex-row md:items-center justify-between gap-space-lg bg-surface-container-low border-surface-container-highest">
        <div className="flex items-center gap-space-xl flex-1">
          <div className="flex items-center gap-4 border-r border-surface-container-highest pr-space-xl">
            <div className="w-6 h-6 rounded-full border-4 border-primary flex items-center justify-center shrink-0">
               <div className="w-2 h-2 rounded-full bg-background"></div>
            </div>
            <div>
              <div className="font-mono text-[9px] text-secondary tracking-[0.2em] uppercase mb-1">DOMESTIC POSTURE</div>
              <div className="font-sans text-display-lg-mobile text-primary leading-none">All Clear •<br/>Calibrated</div>
            </div>
          </div>
          
          <div className="grid grid-cols-2 gap-y-2 gap-x-8 text-[9px] font-mono tracking-[0.2em] text-secondary uppercase py-2">
            <div>0 PENDING ALERTS •</div>
            <div>4 VERIFIED ANCHORS •</div>
            <div>1 SOCIAL CAPTURE •</div>
            <div>1 DOSSIER COMPILED</div>
          </div>
        </div>
        
        <div className="flex items-center gap-space-md shrink-0">
          <button className="px-6 py-3 rounded border border-surface-container-highest bg-surface-container hover:bg-surface-container-high text-secondary hover:text-primary font-mono text-[9px] tracking-[0.2em] flex items-center gap-3 transition-colors">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" x2="12" y1="19" y2="22"/></svg>
            ALEXA VOICE<br/>QUERY
          </button>
          <button onClick={() => setActiveTab('simulator')} className="px-6 py-3 rounded border border-primary bg-background hover:bg-primary hover:text-background text-primary font-mono text-[9px] font-bold tracking-[0.2em] flex items-center gap-3 transition-colors">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polygon points="5 3 19 12 5 21 5 3"/></svg>
            RUN<br/>SIMULATOR
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-space-lg">
        {/* SECTOR 01: Peace of Mind */}
        <div className="lg:col-span-8 card-elevated p-space-xl bg-surface-container-low border-surface-container-highest flex flex-col">
          <div className="flex items-center justify-between mb-8">
            <div className="font-mono text-[10px] text-primary tracking-[0.2em] uppercase flex items-center gap-2">
              <span className="text-secondary opacity-50">SECTOR 01 //</span> Peace of Mind (Acoustic Corroborations)
            </div>
            <div className="font-mono text-[9px] text-secondary tracking-[0.2em] uppercase">ECHO MIC ARRAY • AGENT ACTIVE</div>
          </div>
          
          <div className="grid grid-cols-1 md:grid-cols-2 gap-space-md flex-1">
            {/* Mock Anchors for Dashboard */}
            {[
              { title: "Iron & Styling Wand", badge: "UNPLUGGED", label: "APPLIANCE SENSOR", time: "07:42:11 CET", desc: "Dual-channel verification: Wall receptacle detent snap + vocal self-affirmation.", conf: "99.4%" },
              { title: "Stove & Cooktop", badge: "COLD / OFF", label: "RANGE & HEATING", time: "07:55:04 CET", desc: "Rotary switch hard detent latching corroborated with induction cooling slope.", conf: "98.9%" },
              { title: "Front Deadbolt", badge: "SECURED", label: "PERIMETER ACCESS", time: "08:14:30 CET", desc: "Tumbler throw click and frame acoustic contact cycle confirmed via Bee wearable.", conf: "99.8%" },
              { title: "Morning Medications", badge: "COMPLETED", label: "HEALTH PROTOCOL", time: "08:02:45 CET", desc: "Pill organizer chamber hatch click and water glass draw acoustic profile.", conf: "97.5%" }
            ].map(item => (
              <div key={item.title} className="bg-[#121316] border border-surface-container-highest rounded-lg p-space-lg flex flex-col justify-between">
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <div className="font-mono text-[8px] text-secondary tracking-[0.2em] uppercase">{item.label}</div>
                    <div className="font-mono text-[8px] text-primary tracking-[0.2em] flex items-center gap-1.5 px-2 py-1 rounded bg-surface-container-highest">
                      <div className="w-1 h-1 rounded-full bg-primary"></div> {item.badge}
                    </div>
                  </div>
                  <div className="font-serif text-[20px] text-primary mb-4">{item.title}<MockAsterisk /></div>
                  
                  <div className="bg-surface-container-low border border-surface-container-highest rounded p-3 mb-6">
                    <div className="font-mono text-[9px] text-secondary tracking-[0.2em] mb-2">Verified {item.time}</div>
                    <div className="font-sans text-body-sm text-secondary leading-relaxed">{item.desc}</div>
                  </div>
                </div>
                <div className="flex items-center justify-between">
                   <div className="font-mono text-[9px] text-secondary tracking-[0.2em] uppercase">CONFIDENCE {item.conf}</div>
                   <button className="flex items-center gap-2 font-mono text-[9px] tracking-[0.2em] text-secondary hover:text-primary transition-colors">
                     <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M15.54 8.46a5 5 0 0 1 0 7.07"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14"/></svg>
                     ECHO REASSURANCE
                   </button>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* SECTOR 02: Daily Routines */}
        <div className="lg:col-span-4 card-elevated p-space-xl bg-surface-container-low border-surface-container-highest flex flex-col">
          <div className="flex items-center justify-between mb-8 pb-4 border-b border-surface-container-highest">
            <div className="font-mono text-[10px] text-primary tracking-[0.2em] uppercase">
              <span className="text-secondary opacity-50">SECTOR 02 //</span> Daily Routines
            </div>
            <div className="font-mono text-[9px] text-primary tracking-[0.2em] uppercase font-bold">4 / 4 COMPLETE</div>
          </div>
          
          <div className="h-1 bg-surface-container-highest rounded-full mb-6 overflow-hidden">
            <div className="w-full h-full bg-primary"></div>
          </div>
          
          <div className="space-y-4 flex-1">
            {[
              { title: "Morning Window Ventilation", desc: "Latched closed after 20m", time: "07:15" },
              { title: "Espresso Boiler Isolated", desc: "Thermal pressure released", time: "07:38" },
              { title: "Pet Feeder Gate Verification", desc: "Dispenser solenoid engaged", time: "08:00" },
              { title: "Balcony Door Interlock", desc: "Deadlatch seal registered", time: "08:12" }
            ].map(task => (
              <div key={task.title} className="flex items-start gap-4 p-3 rounded hover:bg-surface-container-highest transition-colors">
                 <div className="w-5 h-5 rounded bg-primary text-background flex items-center justify-center shrink-0 mt-0.5">
                   <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><polyline points="20 6 9 17 4 12"/></svg>
                 </div>
                 <div className="flex-1">
                   <div className="font-sans text-body-sm text-primary mb-1 flex items-center justify-between">
                     {task.title}<MockAsterisk />
                     <span className="font-mono text-[8px] text-secondary">{task.time}</span>
                   </div>
                   <div className="font-sans text-[11px] text-secondary opacity-60">{task.desc}</div>
                 </div>
              </div>
            ))}
          </div>

          <div className="mt-6 pt-4 border-t border-surface-container-highest font-mono text-[8px] text-secondary tracking-[0.2em] uppercase flex justify-between">
            <span>CYCLE: MORNING DEPARTURE</span>
            <span>NEXT: 18:30 EVENING INGRESS</span>
          </div>
        </div>

        {/* BOTTOM ROW (Social & Topic) */}
        <div className="lg:col-span-12 grid grid-cols-1 md:grid-cols-2 gap-space-lg">
          <div className="card-elevated p-space-xl bg-surface-container-low border-surface-container-highest flex items-center justify-between cursor-pointer hover:border-outline-variant transition-colors" onClick={() => setActiveTab('social')}>
            <div className="font-mono text-[10px] text-primary tracking-[0.2em] uppercase">
              <span className="text-secondary opacity-50">SECTOR 03 //</span> Social Rolodex (Passive Ingestion)
            </div>
            <div className="font-mono text-[9px] text-secondary tracking-[0.2em] uppercase">1 SYNTHESIZED TODAY</div>
          </div>
          
          <div className="card-elevated p-space-xl bg-surface-container-low border-surface-container-highest flex items-center justify-between cursor-pointer hover:border-outline-variant transition-colors" onClick={() => setActiveTab('topics')}>
            <div className="font-mono text-[10px] text-primary tracking-[0.2em] uppercase">
              <span className="text-secondary opacity-50">SECTOR 04 //</span> Topic Dossiers
            </div>
            <div className="font-mono text-[9px] text-secondary tracking-[0.2em] uppercase">HARVESTED AT BREAKFAST</div>
          </div>
        </div>
      </div>
    </div>
  );
}
