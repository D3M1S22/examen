import React from "react";
import { DossierFolderDef } from "@/types/schemas";

interface DossierFolderCardProps {
  folder: DossierFolderDef;
  itemCount: number;
  secondaryLabel?: string;
  onClick: () => void;
  className?: string;
}

const ACCENT_STYLES: Record<
  string,
  {
    border: string;
    hoverBorder: string;
    badgeBg: string;
    badgeText: string;
    iconBg: string;
    glow: string;
  }
> = {
  amber: {
    border: "border-amber-500/20",
    hoverBorder: "hover:border-amber-400/60",
    badgeBg: "bg-amber-950/40 border-amber-500/30",
    badgeText: "text-amber-300",
    iconBg: "bg-gradient-to-br from-amber-500/20 to-amber-950/30 border-amber-500/30",
    glow: "group-hover:shadow-[0_0_24px_rgba(245,158,11,0.12)]",
  },
  cyan: {
    border: "border-cyan-500/20",
    hoverBorder: "hover:border-cyan-400/60",
    badgeBg: "bg-cyan-950/40 border-cyan-500/30",
    badgeText: "text-cyan-300",
    iconBg: "bg-gradient-to-br from-cyan-500/20 to-cyan-950/30 border-cyan-500/30",
    glow: "group-hover:shadow-[0_0_24px_rgba(6,182,212,0.12)]",
  },
  emerald: {
    border: "border-emerald-500/20",
    hoverBorder: "hover:border-emerald-400/60",
    badgeBg: "bg-emerald-950/40 border-emerald-500/30",
    badgeText: "text-emerald-300",
    iconBg: "bg-gradient-to-br from-emerald-500/20 to-emerald-950/30 border-emerald-500/30",
    glow: "group-hover:shadow-[0_0_24px_rgba(16,185,129,0.12)]",
  },
  purple: {
    border: "border-purple-500/20",
    hoverBorder: "hover:border-purple-400/60",
    badgeBg: "bg-purple-950/40 border-purple-500/30",
    badgeText: "text-purple-300",
    iconBg: "bg-gradient-to-br from-purple-500/20 to-purple-950/30 border-purple-500/30",
    glow: "group-hover:shadow-[0_0_24px_rgba(168,85,247,0.12)]",
  },
  blue: {
    border: "border-blue-500/20",
    hoverBorder: "hover:border-blue-400/60",
    badgeBg: "bg-blue-950/40 border-blue-500/30",
    badgeText: "text-blue-300",
    iconBg: "bg-gradient-to-br from-blue-500/20 to-blue-950/30 border-blue-500/30",
    glow: "group-hover:shadow-[0_0_24px_rgba(59,130,246,0.12)]",
  },
  zinc: {
    border: "border-white/10",
    hoverBorder: "hover:border-white/30",
    badgeBg: "bg-white/5 border-white/10",
    badgeText: "text-zinc-300",
    iconBg: "bg-[#1c1f26] border-white/10",
    glow: "group-hover:shadow-[0_0_24px_rgba(255,255,255,0.05)]",
  },
};

export function DossierFolderCard({
  folder,
  itemCount,
  secondaryLabel,
  onClick,
  className = "",
}: DossierFolderCardProps) {
  const accent = ACCENT_STYLES[folder.accent] || ACCENT_STYLES.zinc;

  return (
    <button
      type="button"
      onClick={onClick}
      className={`group w-full text-left p-6 bg-surface-container-low border ${accent.border} ${accent.hoverBorder} ${accent.glow} rounded-2xl transition-all duration-200 flex flex-col justify-between gap-5 relative overflow-hidden focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-400 ${className}`}
    >
      {/* Top row: Folder icon & Count Badge */}
      <div className="flex items-start justify-between gap-3 w-full">
        <div
          className={`w-12 h-12 rounded-xl flex items-center justify-center text-2xl border ${accent.iconBg} shadow-inner transition-transform duration-200 group-hover:scale-110`}
        >
          {folder.icon}
        </div>

        <div className="flex flex-col items-end gap-1">
          <span
            className={`px-3 py-1 rounded-full font-mono text-[10px] font-bold tracking-wider uppercase border ${accent.badgeBg} ${accent.badgeText}`}
          >
            {itemCount} {itemCount === 1 ? "FILE" : "FILES"}
          </span>
          {secondaryLabel && (
            <span className="font-mono text-[9px] text-zinc-400 tracking-wider">
              {secondaryLabel}
            </span>
          )}
        </div>
      </div>

      {/* Center: Folder Name & Description */}
      <div className="space-y-1.5 w-full">
        <h4 className="font-serif text-xl sm:text-2xl text-primary font-bold group-hover:text-amber-200 transition-colors">
          {folder.name}
        </h4>
        <p className="font-sans text-xs text-secondary leading-relaxed line-clamp-2">
          {folder.description}
        </p>
      </div>

      {/* Bottom row: Explore Folder Link */}
      <div className="pt-3 border-t border-white/5 flex items-center justify-between w-full font-mono text-[10px] tracking-widest text-secondary group-hover:text-primary transition-colors uppercase font-bold">
        <span>EXPLORE DIRECTORY</span>
        <span className="text-amber-400 text-sm transition-transform duration-200 group-hover:translate-x-1">
          →
        </span>
      </div>
    </button>
  );
}
