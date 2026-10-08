import { PlannedTask } from "@/types/schemas";
import { MockAsterisk } from "../ui/MockAsterisk";

interface DailyRoutinesProps {
  routinesData: { tasks: PlannedTask[] } | undefined;
  handleToggleRoutine: (task: PlannedTask) => void;
}

export function DailyRoutines({ routinesData, handleToggleRoutine }: DailyRoutinesProps) {
  return (
    <div className="space-y-space-lg animate-in fade-in max-w-[1200px] mx-auto">
      {/* Header section matching the mockup */}
      <div className="card-elevated p-space-xl flex flex-col md:flex-row justify-between items-start md:items-center gap-space-lg mb-space-lg bg-surface-container border-outline-variant">
        <div className="max-w-3xl">
          <div className="font-mono text-label-sm text-secondary uppercase tracking-widest mb-2 flex items-center gap-2">
            <span className="w-1.5 h-1.5 bg-secondary rounded-full inline-block"></span>
            OPERATIONAL DIRECTIVE • SECTOR 04
          </div>
          <h2 className="font-serif text-[32px] leading-tight text-primary uppercase mb-4 font-normal">
            SCREEN PURPOSE: PASSIVE ROUTINE TRACKING & SAFETY CHECKLIST
          </h2>
          <p className="font-sans text-body-md text-secondary leading-relaxed max-w-3xl pr-4">
            EXAMEN passively monitors recurring household routines, mechanical closures, and environmental habits without requiring manual checkmarks or tedious app inputs. By sampling natural habit acoustic anchors and ambient resonance profiles throughout the day, the system evaluates completion states in real-time, escalating silent alerts to wearable nodes only if an essential dwelling safety protocol is omitted prior to perimeter egress.
          </p>
        </div>
        <div className="shrink-0 flex flex-col items-end gap-3 self-center md:self-auto mt-4 md:mt-0">
          <div className="status-badge bg-surface-container-low border-white/5 font-mono text-[10px] tracking-widest py-2 px-4 rounded-full">
            ACOUSTIC INGESTION: NOMINAL
            <div className="status-dot status-dot-active ml-2"></div>
          </div>
          <div className="font-mono text-[9px] text-secondary uppercase text-right tracking-[0.2em] pr-2">
            LATENCY: 42MS • ZERO CLOUD EGRESS
          </div>
        </div>
      </div>

      {/* 4 Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-space-md mb-space-xl">
        {/* Card 1 */}
        <div className="card-elevated p-space-lg flex flex-col">
          <div className="flex items-center justify-between mb-8">
            <div className="font-mono text-[10px] text-secondary uppercase tracking-widest">MORNING CYCLE COMPLETION</div>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-primary"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
          </div>
          <div className="mt-auto">
            <div className="flex items-baseline gap-2 mb-4">
              <span className="font-serif text-[40px] text-primary">4 / 4</span>
              <span className="font-mono text-[9px] text-secondary uppercase tracking-widest">100% VERIFIED</span>
            </div>
            <div className="h-1.5 bg-surface-container-highest rounded-full overflow-hidden">
              <div className="h-full bg-primary w-full"></div>
            </div>
          </div>
        </div>
        
        {/* Card 2 */}
        <div className="card-elevated p-space-lg flex flex-col">
          <div className="flex items-center justify-between mb-8">
            <div className="font-mono text-[10px] text-secondary uppercase tracking-widest">NEXT PASSIVE CADENCE</div>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-primary"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
          </div>
          <div className="mt-auto">
            <div className="font-serif text-[32px] text-primary mb-2">18:30:00</div>
            <div className="font-mono text-[9px] text-secondary uppercase tracking-widest mb-3">EVENING INGRESS PROTOCOL</div>
            <div className="font-mono text-[9px] text-secondary uppercase tracking-widest opacity-60">T-MINUS 04H 01M 51S</div>
          </div>
        </div>

        {/* Card 3 */}
        <div className="card-elevated p-space-lg flex flex-col">
          <div className="flex items-center justify-between mb-8">
            <div className="font-mono text-[10px] text-secondary uppercase tracking-widest">DWELL PERIMETER INTEGRITY</div>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-primary"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
          </div>
          <div className="mt-auto">
            <div className="font-serif text-[28px] text-primary mb-2 tracking-wide">CALIBRATED</div>
            <div className="font-mono text-[9px] text-secondary uppercase tracking-widest mb-3">ALL VALVES & SASHES SEALED</div>
            <div className="font-mono text-[9px] text-secondary uppercase tracking-widest flex items-center gap-2">
              <div className="w-1.5 h-1.5 rounded-full bg-primary"></div>
              ZERO ANOMALY LOGGED
            </div>
          </div>
        </div>

        {/* Card 4 */}
        <div className="card-elevated p-space-lg flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-4">
              <div className="font-mono text-[10px] text-secondary uppercase tracking-widest">ROUTINE SUPERVISION</div>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-primary"><line x1="4" y1="21" x2="4" y2="14"/><line x1="4" y1="10" x2="4" y2="3"/><line x1="12" y1="21" x2="12" y2="12"/><line x1="12" y1="8" x2="12" y2="3"/><line x1="20" y1="21" x2="20" y2="16"/><line x1="20" y1="12" x2="20" y2="3"/><line x1="1" y1="14" x2="7" y2="14"/><line x1="9" y1="8" x2="15" y2="8"/><line x1="17" y1="16" x2="23" y2="16"/></svg>
            </div>
            <div className="font-sans text-body-sm text-secondary mb-6 leading-relaxed pr-2">
              Track recurring mechanical steps via acoustic signature profiling.
            </div>
          </div>
          <button className="w-full btn-primary bg-primary text-background hover:bg-surface-tint py-3 font-mono text-[11px] tracking-widest rounded-md mt-auto">
            + ADD MONITORED ROUTINE
          </button>
        </div>
      </div>

      {/* Filter Row */}
      <div className="flex flex-wrap items-center justify-between gap-4 mb-space-lg border-b border-surface-container-highest pb-6">
        <div className="flex flex-wrap items-center gap-2">
          <button className="px-5 py-2.5 rounded-full bg-primary text-background font-mono text-[10px] font-bold tracking-widest">
            MORNING DEPARTURE (ACTIVE)
          </button>
          <button className="px-5 py-2.5 rounded-full text-secondary hover:bg-surface-container hover:text-primary transition-colors font-mono text-[10px] tracking-widest">
            EVENING WIND-DOWN
          </button>
          <button className="px-5 py-2.5 rounded-full text-secondary hover:bg-surface-container hover:text-primary transition-colors font-mono text-[10px] tracking-widest">
            WEEKLY DOMESTIC MAINTENANCE
          </button>
        </div>
        <div className="flex items-center gap-3">
          <div className="px-4 py-2.5 rounded-full bg-surface-container-low border border-surface-container-highest font-mono text-[10px] text-secondary tracking-widest flex items-center gap-2">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M3 18v-6a9 9 0 0 1 18 0v6"/><path d="M21 19a2 2 0 0 1-2 2h-1a2 2 0 0 1-2-2v-3a2 2 0 0 1 2-2h3zM3 19a2 2 0 0 0 2 2h1a2 2 0 0 0 2-2v-3a2 2 0 0 0-2-2H3z"/></svg>
            4 ANCHORS ACTIVE
          </div>
          <div className="px-4 py-2.5 rounded-full bg-surface-container-low border border-surface-container-highest font-mono text-[10px] text-secondary tracking-widest">
            SORT: SEQUENCE CHRONO
          </div>
        </div>
      </div>

      {/* Action Cards Grid (2 cols) */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-space-lg">
        
        {/* Task 1 */}
        <div className="card-elevated p-space-xl flex flex-col bg-surface-container-low border-surface-container-highest">
          <div className="flex items-center justify-between mb-8">
            <div className="font-mono text-[10px] text-secondary tracking-[0.2em] uppercase">STEP 01 • 07:15 UTC</div>
            <div className="px-3 py-1.5 bg-surface-container-highest rounded-full flex items-center gap-2">
               <div className="w-1.5 h-1.5 rounded-full bg-primary"></div>
               <span className="font-mono text-[9px] text-primary tracking-[0.2em] font-bold">COMPLETED</span>
            </div>
          </div>
          
          <div className="flex items-start justify-between mb-3">
            <h3 className="font-serif text-[26px] text-primary font-normal">Morning Window Ventilation<MockAsterisk /></h3>
            <div className="w-12 h-12 rounded-lg bg-surface-container-highest flex items-center justify-center shrink-0">
               <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="text-primary"><path d="M9.59 4.59A2 2 0 1 1 11 8H2m10.59 11.41A2 2 0 1 0 14 16H2m15.73-8.27A2.5 2.5 0 1 1 19.5 12H2"/></svg>
            </div>
          </div>
          <p className="font-sans text-body-md text-secondary mb-10 tracking-wide">Latched closed after 20m air exchange protocol in primary study.</p>

          <div className="bg-[#121316] border border-surface-container-highest rounded-lg p-space-lg mb-8">
            <div className="flex items-center justify-between mb-6">
               <div className="font-mono text-[9px] text-secondary uppercase tracking-widest">ACOUSTIC ANCHOR REGISTERED</div>
               <div className="font-mono text-[9px] text-secondary uppercase tracking-widest">99.4% CONFIDENCE</div>
            </div>
            <div className="flex items-center gap-3 text-primary text-[12px] font-sans mb-6">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
              Double-hung sash lock engagement • 1.2 kHz resonant spike
            </div>
            {/* Waveform placeholder */}
            <svg width="100%" height="40" viewBox="0 0 400 40" preserveAspectRatio="none" className="text-secondary stroke-current" fill="none" strokeWidth="1.5">
               <path d="M0,20 L150,20 L160,10 L170,30 L180,5 L190,20 L400,20"/>
            </svg>
          </div>
          
          <div className="mt-auto flex items-center justify-between font-mono text-[10px] text-secondary tracking-widest uppercase">
            <span>ZONE: EAST FACADE (SENSOR NODE_02)</span>
            <span className="text-primary font-bold">RE-CHECK PASSED</span>
          </div>
        </div>

        {/* Task 2 */}
        <div className="card-elevated p-space-xl flex flex-col bg-surface-container-low border-surface-container-highest">
          <div className="flex items-center justify-between mb-8">
            <div className="font-mono text-[10px] text-secondary tracking-[0.2em] uppercase">STEP 02 • 07:38 UTC</div>
            <div className="px-3 py-1.5 bg-surface-container-highest rounded-full flex items-center gap-2">
               <div className="w-1.5 h-1.5 rounded-full bg-primary"></div>
               <span className="font-mono text-[9px] text-primary tracking-[0.2em] font-bold">COMPLETED</span>
            </div>
          </div>
          
          <div className="flex items-start justify-between mb-3">
            <h3 className="font-serif text-[26px] text-primary font-normal">Espresso Boiler Isolation<MockAsterisk /></h3>
            <div className="w-12 h-12 rounded-lg bg-surface-container-highest flex items-center justify-center shrink-0">
               <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="text-primary"><path d="M18.36 6.64a9 9 0 1 1-12.73 0"/><line x1="12" y1="2" x2="12" y2="12"/></svg>
            </div>
          </div>
          <p className="font-sans text-body-md text-secondary mb-10 tracking-wide">Dual-boiler heating element cut; thermostatic draw dropped to zero.</p>

          <div className="bg-[#121316] border border-surface-container-highest rounded-lg p-space-lg mb-8">
            <div className="flex items-center justify-between mb-6">
               <div className="font-mono text-[9px] text-secondary uppercase tracking-widest">ACOUSTIC ANCHOR REGISTERED</div>
               <div className="font-mono text-[9px] text-secondary uppercase tracking-widest">98.9% CONFIDENCE</div>
            </div>
            <div className="flex items-center gap-3 text-primary text-[12px] font-sans mb-6">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
              Machine toggle click + solenoid cooling hiss decay
            </div>
            {/* Waveform placeholder */}
            <svg width="100%" height="40" viewBox="0 0 400 40" preserveAspectRatio="none" className="text-secondary stroke-current" fill="none" strokeWidth="1.5">
               <path d="M0,20 L180,20 L190,35 L200,5 L210,20 L400,20"/>
            </svg>
          </div>
          
          <div className="mt-auto flex items-center justify-between font-mono text-[10px] text-secondary tracking-widest uppercase">
            <span>ZONE: KITCHEN GALLEY (SENSOR NODE_01)</span>
            <span className="text-primary font-bold">THERMAL: SAFE (21.4°C)</span>
          </div>
        </div>

        {/* Dynamic Mapping for additional routines from DB */}
        {routinesData?.tasks?.map((task, idx) => (
          <div key={task.id} className="card-elevated p-space-xl flex flex-col bg-surface-container-low border-surface-container-highest">
            <div className="flex items-center justify-between mb-8">
              <div className="font-mono text-[10px] text-secondary tracking-[0.2em] uppercase">STEP 0{3 + idx} • {task.scheduled_time || 'PENDING'}</div>
              <button onClick={() => handleToggleRoutine(task)} className="px-3 py-1.5 bg-surface-container-highest rounded-full border border-transparent flex items-center gap-2 cursor-pointer hover:border-primary transition-colors">
                 <div className={`w-1.5 h-1.5 rounded-full ${task.status === 'completed' ? 'bg-primary' : 'bg-outline-variant'}`}></div>
                 <span className={`font-mono text-[9px] tracking-[0.2em] font-bold ${task.status === 'completed' ? 'text-primary' : 'text-secondary'}`}>
                   {task.status === 'completed' ? 'COMPLETED' : 'WATCHING'}
                 </span>
              </button>
            </div>
            
            <div className="flex items-start justify-between mb-3">
              <h3 className="font-serif text-[26px] text-primary font-normal">{task.title}</h3>
              <div className="w-12 h-12 rounded-lg bg-surface-container-highest flex items-center justify-center shrink-0">
                 <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="text-primary"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>
              </div>
            </div>
            <p className="font-sans text-body-md text-secondary mb-10 tracking-wide">Waiting for acoustic anchor confirmation in domain: {task.domain}.</p>

            <div className="bg-[#121316] border border-surface-container-highest rounded-lg p-space-lg mb-8 opacity-50">
              <div className="flex items-center justify-between mb-6">
                 <div className="font-mono text-[9px] text-secondary uppercase tracking-widest">ACOUSTIC ANCHOR PENDING</div>
                 <div className="font-mono text-[9px] text-secondary uppercase tracking-widest">--.-% CONFIDENCE</div>
              </div>
              <div className="flex items-center gap-3 text-primary text-[12px] font-sans mb-6">
                Listening for signature matching routine constraints...
              </div>
              <svg width="100%" height="40" viewBox="0 0 400 40" preserveAspectRatio="none" className="text-secondary stroke-current" fill="none" strokeWidth="1">
                 <path d="M0,20 L400,20"/>
              </svg>
            </div>
            
            <div className="mt-auto flex items-center justify-between font-mono text-[10px] text-secondary tracking-widest uppercase">
              <span>ZONE: GLOBAL SENSOR MESH</span>
              <span>RE-CHECK PENDING</span>
            </div>
          </div>
        ))}

      </div>
    </div>
  );
}
