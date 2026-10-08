export function SystemFooter() {
  return (
    <footer className="fixed bottom-0 left-0 right-0 h-10 border-t border-surface-container bg-background/95 backdrop-blur z-[100] flex items-center justify-between px-gutter-desktop">
      <div className="flex items-center gap-6 font-mono text-label-sm text-secondary uppercase">
        <span>EXAMEN OPERATING SYSTEM</span>
        <span className="hidden sm:inline">•</span>
        <span className="hidden sm:inline">SILENT OBSERVATION NODE 32</span>
      </div>
      <div className="flex items-center gap-6 font-mono text-label-sm text-secondary uppercase">
        <span className="hidden md:inline">CALM COMPUTE INITIATIVE</span>
        <span className="hidden md:inline">LATENCY 12ms</span>
        <span>© EXAMEN RESEARCH LABS</span>
      </div>
    </footer>
  );
}
