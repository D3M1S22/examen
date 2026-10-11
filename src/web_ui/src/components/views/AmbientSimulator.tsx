import { ScreenHeader } from "../ui/ScreenHeader";
import { Badge } from "../ui/Badge";
import { MockAsterisk } from "../ui/MockAsterisk";

interface AmbientSimulatorProps {
  simText: string;
  setSimText: (text: string) => void;
  simRunning: boolean;
  runSimulation: () => void;
  simResult: any;
}

export function AmbientSimulator({ simText, setSimText, simRunning, runSimulation, simResult }: AmbientSimulatorProps) {
  
  const presets = [
    {
      id: "01",
      title: "Iron & Gas Safety",
      desc: "Triggers acoustic iron disconnect click & stove dial lock sequence. High certainty corroboration.",
      badge: "DOMESTIC_SAFETY",
      icon: <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>,
      text: "I just unplugged the clothes iron and styled my hair — all good. Gas stovetop is cold and switched off."
    },
    {
      id: "02",
      title: "Social Networking",
      desc: "Simulates dialogue meeting Andrea from Almaviva, extracting contact commitments & follow-up.",
      badge: "CONTACT_ROLODEX",
      icon: <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>,
      text: "Hi! I'm Andrea Valenti, DevOps Lead at Almaviva. Great to meet you at AWS re:Invent. I will send you the fastmcp schema on Slack by Thursday."
    },
    {
      id: "03",
      title: "AWS AgentCore Tech",
      desc: "Engineering deep-dive on Bedrock Mantle and FastMCP architecture, drafting synthetic topic notes.",
      badge: "TOPIC_DOSSIER",
      icon: <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><line x1="9" y1="3" x2="9" y2="21"/></svg>,
      text: "We spent the morning discussing how to route FastMCP streams directly into Bedrock AgentCore. The main action item is for Sarah to test the latency overhead."
    },
    {
      id: "04",
      title: "Casual Banter (Drop >90%)",
      desc: "Elevator talk concerning drizzle; verifies PII scrubber drops low-entropy ephemeral small talk.",
      badge: "DROP_FILTER_ACTIVE",
      icon: <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/></svg>,
      text: "Man, it's really raining outside today. I should have brought my umbrella. Oh well, the coffee here is good."
    }
  ];

  return (
    <div className="space-y-space-lg animate-in fade-in max-w-[1400px] mx-auto">
      <ScreenHeader 
        directive="DIAGNOSTIC TESTBENCH // SECTOR 06"
        title="SCREEN PURPOSE: AMBIENT AUDIO STREAM SIMULATOR & PIPELINE TESTING"
        description={<>Welcome, Hackathon Judges and Testers! This Ambient Simulator provides a direct interface to test EXAMEN's AgentCore pipeline without needing the physical Bee hardware. Simulate a wearable conversation by typing or pasting a transcript below. The system will process your text as if it were ambient audio, extracting tasks, creating contacts, or generating topic dossiers in real-time.</>}
        rightElement={
          <div className="bg-surface-container-highest rounded-lg p-4 font-mono">
            <div className="text-[9px] text-secondary tracking-[0.2em] uppercase mb-1">INSPECTION CADENCE</div>
            <div className="text-[14px] text-primary font-bold tracking-wider mb-1">REALTIME ZERO-LAG</div>
            <div className="text-[9px] text-secondary tracking-[0.2em] uppercase">BUFFER: 2048 SAMPLES</div>
          </div>
        }
      />

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-space-lg">
        {/* Left Column */}
        <div className="lg:col-span-7 flex flex-col gap-space-lg">
          {/* Presets */}
          <div className="card-elevated p-space-lg bg-surface-container-low border-surface-container-highest">
            <div className="flex items-center justify-between mb-6">
              <div className="font-mono text-[10px] text-primary tracking-[0.2em] uppercase flex items-center gap-2 font-bold">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="4" y1="21" x2="4" y2="14"/><line x1="4" y1="10" x2="4" y2="3"/><line x1="12" y1="21" x2="12" y2="12"/><line x1="12" y1="8" x2="12" y2="3"/><line x1="20" y1="21" x2="20" y2="16"/><line x1="20" y1="12" x2="20" y2="3"/><line x1="1" y1="14" x2="7" y2="14"/><line x1="9" y1="8" x2="15" y2="8"/><line x1="17" y1="16" x2="23" y2="16"/></svg>
                SYNTHETIC INGEST PRESETS
              </div>
              <div className="font-mono text-[9px] text-secondary tracking-[0.2em] uppercase">QUICK INJECT BUFFERS</div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-space-md">
              {presets.map(p => (
                <button key={p.id} onClick={() => setSimText(p.text)} className="bg-[#121316] border border-surface-container-highest rounded-lg p-space-md text-left hover:border-outline transition-colors group">
                  <div className="flex items-start justify-between mb-2">
                    <div className="font-mono text-[10px] text-primary tracking-widest font-bold">{p.id} // {p.title}</div>
                    <div className="text-secondary group-hover:text-primary transition-colors">{p.icon}</div>
                  </div>
                  <div className="font-sans text-body-sm text-secondary mb-4 leading-relaxed">{p.desc}</div>
                  <Badge variant="outline" dot="active" className="!text-[8px] !py-1 w-max border-white/5 bg-surface-container-lowest">{p.badge}</Badge>
                </button>
              ))}
            </div>
          </div>

          {/* Injector Textarea */}
          <div className="card-elevated p-space-lg bg-surface-container-low border-surface-container-highest flex-1 flex flex-col">
            <div className="flex items-center justify-between mb-6">
              <div className="font-mono text-[10px] text-primary tracking-[0.2em] uppercase flex items-center gap-2 font-bold">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" x2="12" y1="19" y2="22"/></svg>
                TRANSCRIBED UTTERANCE INJECTOR
              </div>
              <div className="font-mono text-[9px] text-secondary tracking-[0.2em] uppercase">OPUS 48KHZ RAW</div>
            </div>
            
            <div className="flex items-center justify-between mb-2">
              <div className="font-mono text-[9px] text-secondary tracking-[0.2em] uppercase">SYNTHETIC TRANSCRIPT BUFFER</div>
              <div className="font-mono text-[9px] text-secondary tracking-[0.2em] uppercase">{simText.length} CHRS</div>
            </div>
            
            <textarea 
              className="w-full flex-1 min-h-[160px] bg-[#121316] border border-surface-container-highest rounded-lg p-space-md font-sans text-body-md text-primary placeholder-secondary/50 focus:outline-none focus:border-outline resize-none mb-4"
              placeholder="Ho appena staccato il ferro da stiro..."
              value={simText}
              onChange={(e) => setSimText(e.target.value)}
            />
            <div className="flex justify-end">
              <button 
                onClick={runSimulation} 
                disabled={simRunning}
                className="btn-primary font-mono text-[10px] tracking-[0.2em] font-bold"
              >
                {simRunning ? "PROCESSING PIPELINE..." : "INJECT STREAM TO AGENTCORE"}
              </button>
            </div>
          </div>
        </div>

        {/* Right Column */}
        <div className="lg:col-span-5 flex flex-col gap-space-lg">
          <div className="card-elevated p-space-lg bg-surface-container-low border-surface-container-highest flex-1">
            <div className="flex items-center justify-between mb-8">
              <div className="font-mono text-[10px] text-primary tracking-[0.2em] uppercase flex items-center gap-2 font-bold">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
                AGENTCORE EXECUTION FLOW
              </div>
              <Badge variant="filled" className={simRunning ? "bg-primary text-background" : "bg-[#121316] text-secondary"}>
                {simRunning ? "PROCESSING" : "STANDBY"}
              </Badge>
            </div>

            <div className="space-y-3 relative before:absolute before:inset-0 before:ml-[1.4rem] before:-translate-x-px md:before:mx-auto md:before:translate-x-0 before:h-full before:w-0.5 before:bg-gradient-to-b before:from-transparent before:via-surface-container-highest before:to-transparent">
              {[
                { id: 1, title: "Bee Audio Input", desc: "48kHz Opus stream chunk unpacked & timestamped." },
                { id: 2, title: "Nemotron PII Gatekeeper", desc: "Anonymize speaker identities; evaluate relevance gate." },
                { id: 3, title: "Intent Classification", desc: "Route to Domestic Security vs Social Memory vs Dossier." },
                { id: 4, title: "Bedrock Agentic Synthesis", desc: "Extract entities, corroboration schema, vector write." },
                { id: 5, title: "FastMCP Alexa+ Server Broadcast", desc: "Publish entity state for immediate ambient recall query." }
              ].map((step, idx) => (
                <div key={step.id} className="relative flex items-center bg-[#121316] border border-surface-container-highest rounded-lg p-space-md z-10">
                  <div className="w-6 h-6 rounded-full bg-surface-container-highest text-secondary flex items-center justify-center font-mono text-[10px] mr-4 shrink-0">
                    {step.id}
                  </div>
                  <div className="flex-1">
                    <div className={`font-sans text-body-sm font-bold ${simRunning && idx === 2 ? 'text-primary' : 'text-secondary'}`}>{step.title}</div>
                    <div className="font-sans text-[11px] text-secondary opacity-60 mt-0.5">{step.desc}</div>
                  </div>
                  <div className="font-mono text-[10px] text-secondary opacity-40">--</div>
                </div>
              ))}
            </div>
          </div>

          <div className="card-elevated p-space-lg bg-surface-container-low border-surface-container-highest">
            <div className="flex items-center justify-between mb-4">
              <div className="font-mono text-[10px] text-primary tracking-[0.2em] uppercase flex items-center gap-2 font-bold">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>
                SYNTHESIZED EMISSION PREVIEW
              </div>
              <div className="flex bg-[#121316] rounded border border-surface-container-highest p-0.5">
                <button className="px-3 py-1 font-mono text-[9px] tracking-widest bg-white text-black rounded font-bold">CARD VIEW</button>
                <button className="px-3 py-1 font-mono text-[9px] tracking-widest text-secondary rounded">JSON PAYLOAD</button>
              </div>
            </div>
            
            <div className="bg-[#121316] border border-surface-container-highest rounded-lg p-space-md min-h-[120px] font-mono text-[10px] text-secondary overflow-x-auto">
              {simResult ? JSON.stringify(simResult, null, 2) : <span className="opacity-40">Awaiting stream processing cycle...</span>}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
