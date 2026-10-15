import React from "react";
import { DossierBreadcrumbItem } from "@/types/schemas";

interface DossierBreadcrumbsProps {
  items: DossierBreadcrumbItem[];
  onNavigate: (item: DossierBreadcrumbItem, index: number) => void;
  onBack?: () => void;
  canGoBack?: boolean;
  currentPathString?: string;
  itemCount?: number;
  className?: string;
}

export function DossierBreadcrumbs({
  items,
  onNavigate,
  onBack,
  canGoBack = false,
  currentPathString,
  itemCount,
  className = "",
}: DossierBreadcrumbsProps) {
  return (
    <nav
      aria-label="Topic Dossiers folder navigation"
      className={`flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-3.5 bg-[#121419] border border-surface-container-highest rounded-2xl shadow-sm ${className}`}
    >
      {/* Left: Back button + Breadcrumb items */}
      <div className="flex items-center gap-2 overflow-x-auto hide-scrollbar min-h-[36px]">
        {canGoBack && onBack && (
          <button
            type="button"
            onClick={onBack}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl border border-surface-container-highest bg-[#181a20] hover:bg-surface-container text-zinc-300 hover:text-white font-mono text-[10px] font-bold tracking-wider transition-all duration-150 shrink-0 shadow-sm active:scale-95"
            aria-label="Navigate up one folder level"
            title="Go up one folder level"
          >
            <span className="text-amber-400 text-xs leading-none">←</span>
            <span>BACK</span>
          </button>
        )}

        <ol className="flex items-center gap-1.5 flex-nowrap list-none m-0 p-0 text-xs">
          {items.map((item, idx) => {
            const isLast = idx === items.length - 1;

            return (
              <li key={item.id || idx} className="flex items-center gap-1.5 shrink-0">
                {idx > 0 && (
                  <span className="text-zinc-600 font-mono text-xs select-none" aria-hidden="true">
                    /
                  </span>
                )}

                {isLast ? (
                  <span
                    aria-current="page"
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-amber-950/40 border border-amber-500/40 text-amber-200 font-mono text-[11px] font-bold tracking-wide shadow-sm"
                  >
                    {item.icon && <span className="text-xs">{item.icon}</span>}
                    <span className="truncate max-w-[200px] sm:max-w-[320px]">{item.label}</span>
                    {typeof item.count === "number" && (
                      <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-amber-500/20 text-amber-300 font-mono ml-1">
                        {item.count}
                      </span>
                    )}
                  </span>
                ) : (
                  <button
                    type="button"
                    onClick={() => onNavigate(item, idx)}
                    className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-xl text-zinc-400 hover:text-white hover:bg-white/5 border border-transparent hover:border-white/10 font-mono text-[11px] font-medium tracking-wide transition-all duration-150 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-amber-400"
                    title={`Jump to ${item.label}`}
                  >
                    {item.icon && <span className="text-xs">{item.icon}</span>}
                    <span className="truncate max-w-[150px] sm:max-w-[220px]">{item.label}</span>
                    {typeof item.count === "number" && (
                      <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-white/5 text-zinc-400 font-mono ml-1">
                        {item.count}
                      </span>
                    )}
                  </button>
                )}
              </li>
            );
          })}
        </ol>
      </div>

      {/* Right: Path string & Item count */}
      <div className="flex items-center gap-2 self-end sm:self-center shrink-0">
        {currentPathString && (
          <span className="hidden md:inline-block font-mono text-[9px] text-zinc-500 tracking-wider bg-black/40 px-2.5 py-1 rounded-lg border border-white/5 truncate max-w-[260px]">
            {currentPathString}
          </span>
        )}

        {typeof itemCount === "number" && (
          <span className="px-2.5 py-1 rounded-lg bg-surface-container-high/80 border border-surface-container-highest text-secondary font-mono text-[10px] tracking-wider uppercase font-semibold">
            {itemCount} {itemCount === 1 ? "ENTRY" : "ENTRIES"}
          </span>
        )}
      </div>
    </nav>
  );
}
