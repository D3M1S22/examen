"use client";

import React, { useState, useRef } from "react";

interface StatusDockProps {
  sseConnected?: boolean;
  statusData?: any;
  onOpenEchoModal?: () => void;
}

export function StatusDock({
  sseConnected = true,
  statusData,
  onOpenEchoModal,
}: StatusDockProps) {
  const [isAreaHovered, setIsAreaHovered] = useState(false);
  const [isDockOpen, setIsDockOpen] = useState(false);
  const [isPinned, setIsPinned] = useState(false);
  const leaveTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  const handleMouseEnterArea = () => {
    if (leaveTimeoutRef.current) {
      clearTimeout(leaveTimeoutRef.current);
      leaveTimeoutRef.current = null;
    }
    setIsAreaHovered(true);
  };

  const handleMouseLeaveArea = () => {
    if (isPinned) return;
    leaveTimeoutRef.current = setTimeout(() => {
      setIsAreaHovered(false);
      setIsDockOpen(false);
    }, 280);
  };

  const handleToggleDock = () => {
    setIsDockOpen((prev) => !prev);
  };

  // Telemetry details from statusData
  const beeDevice = statusData?.telemetry?.bee_device;
  const isBeeConnected = !!beeDevice?.connected || beeDevice?.status === "STREAMING";
  const isBeeListening = beeDevice?.status === "LISTENING";
  const beeAccount = beeDevice?.account;
  const beeLabel = isBeeConnected
    ? "STREAMING"
    : isBeeListening
    ? "LISTENING"
    : beeAccount
    ? "STANDBY"
    : "DISCONNECTED";

  const beeDotClass = isBeeConnected
    ? "bg-emerald-400 animate-pulse shadow-[0_0_8px_rgba(52,211,153,0.8)]"
    : isBeeListening
    ? "bg-cyan-400 animate-pulse shadow-[0_0_8px_rgba(34,211,238,0.8)]"
    : beeAccount
    ? "bg-amber-400"
    : "bg-zinc-600";

  const awsRegion = (statusData?.config?.aws_region || "us-east-1").toUpperCase();
  const reasonerModel = statusData?.config?.reasoner_model || "nvidia.nemotron-super-3-120b";
  const reasonerShort = reasonerModel.split(":").shift()?.split(".").pop()?.toUpperCase() || "ACTIVE";
  const gatekeeperModel = statusData?.config?.gatekeeper_model || "Dual-provider";

  const totalActions = statusData?.stats?.total_actions ?? 0;
  const plannedCompleted = statusData?.stats?.planned_tasks_completed ?? 0;
  const plannedTotal = statusData?.stats?.planned_tasks_total ?? 0;
  const totalContacts = statusData?.stats?.total_contacts ?? 0;

  const showButton = isAreaHovered || isDockOpen || isPinned;

  return (
    <aside
      aria-label="System Status Dock"
      onMouseEnter={handleMouseEnterArea}
      onMouseLeave={handleMouseLeaveArea}
      className="fixed left-0 top-1/2 -translate-y-1/2 z-[90] flex items-center select-none"
    >
      {/* Edge Sensor Hit Zone (Generous invisible hover detection strip along left edge) */}
      <div
        onMouseEnter={handleMouseEnterArea}
        className="absolute left-0 top-1/2 -translate-y-1/2 w-6 sm:w-8 h-80 -z-10 cursor-pointer"
        aria-hidden="true"
      />

      {/* Subtle edge tab when hidden (Visual hint before hovering) */}
      {!showButton && (
        <div
          onMouseEnter={handleMouseEnterArea}
          className="w-1.5 h-16 rounded-r-full bg-cyan-500/30 hover:bg-cyan-400 transition-all cursor-pointer shadow-[0_0_8px_rgba(34,211,238,0.4)]"
          title="Hover to reveal Status Dock button"
        />
      )}

      {/* Hover Trigger Reveal Button (Revealed on hover, stays as long as mouse is in that area) */}
      <div
        className={`transition-all duration-300 ease-out flex items-center ${
          showButton
            ? "opacity-100 translate-x-0 pointer-events-auto"
            : "opacity-0 -translate-x-full pointer-events-none"
        }`}
      >
        <button
          onClick={handleToggleDock}
          onMouseEnter={handleMouseEnterArea}
          aria-expanded={isDockOpen}
          aria-label={isDockOpen ? "Collapse System Dock" : "Expand System Status Dock"}
          title={isDockOpen ? "Click to collapse dock" : "Click to expand Status Dock"}
          className={`flex items-center gap-1.5 px-2.5 py-3.5 rounded-r-2xl bg-zinc-950/95 backdrop-blur-2xl border-y border-r transition-all duration-200 shadow-[0_12px_40px_rgba(0,0,0,0.95)] cursor-pointer group/btn ${
            isDockOpen
              ? "border-cyan-400/50 text-cyan-300 bg-cyan-950/60"
              : "border-white/20 text-zinc-300 hover:text-cyan-300 hover:border-cyan-500/50"
          }`}
        >
          <span className="text-xs">⚡</span>
          <span className="[writing-mode:vertical-rl] font-mono text-[9px] uppercase tracking-widest font-bold">
            {isPinned ? "PINNED" : isDockOpen ? "COLLAPSE" : "DOCK"}
          </span>
          <span
            className={`text-xs text-cyan-400 transition-transform duration-200 ${
              isDockOpen ? "rotate-180" : ""
            }`}
          >
            ›
          </span>
        </button>
      </div>

      {/* MacBook Pro Styled Floating Glass Dock (Opens when button is clicked or pinned) */}
      <div
        className={`transition-all duration-300 ease-out ml-2 sm:ml-3 ${
          isDockOpen || isPinned
            ? "opacity-100 translate-x-0 scale-100 pointer-events-auto"
            : "opacity-0 -translate-x-12 scale-95 pointer-events-none"
        }`}
      >
        <div className="bg-zinc-950/90 backdrop-blur-2xl border border-white/15 rounded-2xl p-1.5 sm:p-2.5 shadow-[0_20px_50px_rgba(0,0,0,0.95)] flex flex-col items-center gap-2 sm:gap-2.5 ring-1 ring-white/10">
          {/* Dock Header & Pin/Unpin Toggle */}
          <div className="flex items-center justify-between w-full px-1">
            <button
              onClick={() => setIsPinned(!isPinned)}
              title={isPinned ? "Unpin dock (auto-hides on mouse leave)" : "Pin dock open permanently"}
              className={`w-7 h-7 rounded-lg text-[10px] font-mono flex items-center justify-center transition-colors ${
                isPinned
                  ? "bg-cyan-500/20 text-cyan-300 border border-cyan-400/40"
                  : "bg-white/5 text-zinc-400 hover:text-white border border-white/10"
              }`}
            >
              {isPinned ? "📌" : "📍"}
            </button>
            <button
              onClick={() => {
                setIsDockOpen(false);
                setIsPinned(false);
              }}
              title="Close dock"
              className="w-7 h-7 rounded-lg text-[10px] text-zinc-400 hover:text-white hover:bg-white/10 transition-colors flex items-center justify-center"
            >
              ✕
            </button>
          </div>

          <div className="w-6 h-px bg-white/10 my-0.5" />

          {/* Dock Item 1: SSE Stream */}
          <div className="group relative flex items-center justify-center">
            <div
              tabIndex={0}
              role="status"
              aria-label={`SSE Stream Status: ${sseConnected ? "Live" : "Connecting"}`}
              className="w-9 h-9 sm:w-10 sm:h-10 rounded-xl bg-white/[0.04] hover:bg-white/[0.12] border border-white/5 hover:border-white/20 transition-all duration-200 transform hover:scale-110 sm:hover:scale-125 flex items-center justify-center cursor-pointer shadow-sm relative"
            >
              <span className="text-sm sm:text-base select-none">⚡</span>
              {/* Live Indicator Dot */}
              <span
                className={`absolute top-1 right-1 w-2 h-2 rounded-full ${
                  sseConnected
                    ? "bg-emerald-400 animate-pulse shadow-[0_0_6px_rgba(52,211,153,0.9)]"
                    : "bg-amber-400 animate-ping"
                }`}
              />
            </div>

            {/* Smooth Hover Card Popover with continuous hover bridge */}
            <div className="pointer-events-none group-hover:pointer-events-auto opacity-0 -translate-x-3 group-hover:opacity-100 group-hover:translate-x-0 transition-all duration-200 ease-out absolute left-full ml-3.5 top-1/2 -translate-y-1/2 z-50 w-72 p-4 rounded-xl bg-[#0e1117]/95 backdrop-blur-2xl border border-white/15 shadow-[0_20px_45px_rgba(0,0,0,0.9)] text-left before:absolute before:-left-4 before:top-0 before:w-4 before:h-full">
              {/* Pointer Notch */}
              <div className="absolute -left-1.5 top-1/2 -translate-y-1/2 w-3 h-3 bg-[#0e1117] border-l border-b border-white/15 rotate-45" />

              <div className="flex items-center justify-between mb-2">
                <span className="font-mono text-[9px] text-zinc-400 uppercase tracking-widest font-semibold">
                  TELEMETRY STREAM
                </span>
                <span
                  className={`font-mono text-[9px] px-2 py-0.5 rounded-full uppercase font-bold tracking-wider ${
                    sseConnected
                      ? "bg-emerald-950/70 text-emerald-300 border border-emerald-500/40"
                      : "bg-amber-950/70 text-amber-300 border border-amber-500/40"
                  }`}
                >
                  {sseConnected ? "LIVE STREAM" : "CONNECTING"}
                </span>
              </div>

              <div className="font-sans text-sm font-semibold text-white mb-2 flex items-center gap-2">
                <span
                  className={`w-2 h-2 rounded-full ${
                    sseConnected ? "bg-emerald-400 animate-pulse" : "bg-amber-400"
                  }`}
                />
                Server-Sent Events (SSE)
              </div>

              <div className="space-y-1 text-[11px] font-mono text-zinc-300 border-t border-white/5 pt-2">
                <div className="flex justify-between">
                  <span className="text-zinc-500">ENDPOINT:</span>
                  <span className="text-cyan-300">/api/events</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-zinc-500">TRANSPORT:</span>
                  <span>Reactive HTTP Stream</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-zinc-500">REVALIDATION:</span>
                  <span className="text-emerald-400">Zero-Polling Push</span>
                </div>
              </div>

              <p className="mt-2 text-[10px] text-zinc-400 font-sans leading-relaxed">
                Provides real-time event distribution for acoustic anchors, social encounters, and task mutations.
              </p>
            </div>
          </div>

          {/* Dock Item 2: Bee Wearable Audio Bridge */}
          <div className="group relative flex items-center justify-center">
            <div
              tabIndex={0}
              role="status"
              aria-label={`Bee Wearable Status: ${beeLabel}`}
              className="w-9 h-9 sm:w-10 sm:h-10 rounded-xl bg-white/[0.04] hover:bg-white/[0.12] border border-white/5 hover:border-white/20 transition-all duration-200 transform hover:scale-110 sm:hover:scale-125 flex items-center justify-center cursor-pointer shadow-sm relative"
            >
              <span className="text-sm sm:text-base select-none">🐝</span>
              {/* Live Indicator Dot */}
              <span className={`absolute top-1 right-1 w-2 h-2 rounded-full ${beeDotClass}`} />
            </div>

            {/* Smooth Hover Card Popover with continuous hover bridge */}
            <div className="pointer-events-none group-hover:pointer-events-auto opacity-0 -translate-x-3 group-hover:opacity-100 group-hover:translate-x-0 transition-all duration-200 ease-out absolute left-full ml-3.5 top-1/2 -translate-y-1/2 z-50 w-72 p-4 rounded-xl bg-[#0e1117]/95 backdrop-blur-2xl border border-white/15 shadow-[0_20px_45px_rgba(0,0,0,0.9)] text-left before:absolute before:-left-4 before:top-0 before:w-4 before:h-full">
              {/* Pointer Notch */}
              <div className="absolute -left-1.5 top-1/2 -translate-y-1/2 w-3 h-3 bg-[#0e1117] border-l border-b border-white/15 rotate-45" />

              <div className="flex items-center justify-between mb-2">
                <span className="font-mono text-[9px] text-zinc-400 uppercase tracking-widest font-semibold">
                  EDGE HARDWARE
                </span>
                <span className="font-mono text-[9px] px-2 py-0.5 rounded-full bg-cyan-950/70 text-cyan-300 border border-cyan-500/40 uppercase font-bold tracking-wider">
                  BEE: {beeLabel}
                </span>
              </div>

              <div className="font-sans text-sm font-semibold text-white mb-2 flex items-center gap-2">
                <span className={`w-2 h-2 rounded-full ${beeDotClass}`} />
                Bee Wearable Audio Mesh
              </div>

              <div className="space-y-1 text-[11px] font-mono text-zinc-300 border-t border-white/5 pt-2">
                {beeAccount && (
                  <div className="flex justify-between">
                    <span className="text-zinc-500">ACCOUNT:</span>
                    <span className="text-cyan-300 truncate max-w-[150px]">{beeAccount}</span>
                  </div>
                )}
                <div className="flex justify-between">
                  <span className="text-zinc-500">PROTOCOL:</span>
                  <span>SSE Audio Stream</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-zinc-500">SCREENING:</span>
                  <span className="text-emerald-400 font-bold">{gatekeeperModel}</span>
                </div>
              </div>

              <p className="mt-2 text-[10px] text-zinc-400 font-sans leading-relaxed">
                Subscribes to live microphone audio chunks, performing zero-noise edge screening before AWS Bedrock AgentCore dispatch.
              </p>
            </div>
          </div>

          {/* Dock Item 3: Bedrock AgentCore AI Reasoner */}
          <div className="group relative flex items-center justify-center">
            <div
              tabIndex={0}
              role="status"
              aria-label="Bedrock AgentCore Reasoner Active"
              className="w-9 h-9 sm:w-10 sm:h-10 rounded-xl bg-white/[0.04] hover:bg-white/[0.12] border border-white/5 hover:border-white/20 transition-all duration-200 transform hover:scale-110 sm:hover:scale-125 flex items-center justify-center cursor-pointer shadow-sm relative"
            >
              <span className="text-sm sm:text-base select-none">🧠</span>
              {/* Live Indicator Dot */}
              <span className="absolute top-1 right-1 w-2 h-2 rounded-full bg-cyan-400 animate-pulse shadow-[0_0_6px_rgba(34,211,238,0.9)]" />
            </div>

            {/* Smooth Hover Card Popover with continuous hover bridge */}
            <div className="pointer-events-none group-hover:pointer-events-auto opacity-0 -translate-x-3 group-hover:opacity-100 group-hover:translate-x-0 transition-all duration-200 ease-out absolute left-full ml-3.5 top-1/2 -translate-y-1/2 z-50 w-72 p-4 rounded-xl bg-[#0e1117]/95 backdrop-blur-2xl border border-white/15 shadow-[0_20px_45px_rgba(0,0,0,0.9)] text-left before:absolute before:-left-4 before:top-0 before:w-4 before:h-full">
              {/* Pointer Notch */}
              <div className="absolute -left-1.5 top-1/2 -translate-y-1/2 w-3 h-3 bg-[#0e1117] border-l border-b border-white/15 rotate-45" />

              <div className="flex items-center justify-between mb-2">
                <span className="font-mono text-[9px] text-zinc-400 uppercase tracking-widest font-semibold">
                  AGENT RUNTIME
                </span>
                <span className="font-mono text-[9px] px-2 py-0.5 rounded-full bg-cyan-950/70 text-cyan-300 border border-cyan-500/40 uppercase font-bold tracking-wider">
                  BEDROCK AGENTCORE
                </span>
              </div>

              <div className="font-sans text-sm font-semibold text-white mb-2 flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-cyan-400" />
                LangGraph Reasoner ({reasonerShort})
              </div>

              <div className="space-y-1 text-[11px] font-mono text-zinc-300 border-t border-white/5 pt-2">
                <div className="flex justify-between">
                  <span className="text-zinc-500">REGION:</span>
                  <span className="text-cyan-300">{awsRegion}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-zinc-500">GATEKEEPER:</span>
                  <span className="text-zinc-300 font-bold">{gatekeeperModel}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-zinc-500">REASONER:</span>
                  <span className="text-white font-bold truncate max-w-[140px]">
                    {reasonerShort}
                  </span>
                </div>
              </div>

              <p className="mt-2 text-[10px] text-zinc-400 font-sans leading-relaxed">
                Bedrock AgentCore StateGraph with multi-label parallel fan-out across action-state, social contacts, and topic research.
              </p>
            </div>
          </div>

          {/* Dock Item 4: Domestic Posture */}
          <div className="group relative flex items-center justify-center">
            <div
              tabIndex={0}
              role="status"
              aria-label="Domestic Safety Posture: All Clear"
              className="w-9 h-9 sm:w-10 sm:h-10 rounded-xl bg-white/[0.04] hover:bg-white/[0.12] border border-white/5 hover:border-white/20 transition-all duration-200 transform hover:scale-110 sm:hover:scale-125 flex items-center justify-center cursor-pointer shadow-sm relative"
            >
              <span className="text-sm sm:text-base select-none">🛡️</span>
              {/* Live Indicator Dot */}
              <span className="absolute top-1 right-1 w-2 h-2 rounded-full bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.8)]" />
            </div>

            {/* Smooth Hover Card Popover with continuous hover bridge */}
            <div className="pointer-events-none group-hover:pointer-events-auto opacity-0 -translate-x-3 group-hover:opacity-100 group-hover:translate-x-0 transition-all duration-200 ease-out absolute left-full ml-3.5 top-1/2 -translate-y-1/2 z-50 w-72 p-4 rounded-xl bg-[#0e1117]/95 backdrop-blur-2xl border border-white/15 shadow-[0_20px_45px_rgba(0,0,0,0.9)] text-left before:absolute before:-left-4 before:top-0 before:w-4 before:h-full">
              {/* Pointer Notch */}
              <div className="absolute -left-1.5 top-1/2 -translate-y-1/2 w-3 h-3 bg-[#0e1117] border-l border-b border-white/15 rotate-45" />

              <div className="flex items-center justify-between mb-2">
                <span className="font-mono text-[9px] text-zinc-400 uppercase tracking-widest font-semibold">
                  DOMESTIC POSTURE
                </span>
                <span className="font-mono text-[9px] px-2 py-0.5 rounded-full bg-emerald-950/70 text-emerald-300 border border-emerald-500/40 uppercase font-bold tracking-wider">
                  ALL CLEAR
                </span>
              </div>

              <div className="font-sans text-sm font-semibold text-white mb-2 flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-emerald-400" />
                Acoustic Ledger Corroborated
              </div>

              <div className="space-y-1 text-[11px] font-mono text-zinc-300 border-t border-white/5 pt-2">
                <div className="flex justify-between">
                  <span className="text-zinc-500">VERIFIED ANCHORS:</span>
                  <span className="text-emerald-400 font-bold">{totalActions}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-zinc-500">ROUTINES COMPLETED:</span>
                  <span>
                    {plannedCompleted} / {plannedTotal}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-zinc-500">CONTACTS INDEXED:</span>
                  <span className="text-cyan-300">{totalContacts}</span>
                </div>
              </div>

              <p className="mt-2 text-[10px] text-zinc-400 font-sans leading-relaxed">
                Real-time peace-of-mind acoustic verification protecting home security, iron, stove, and daily regimens.
              </p>
            </div>
          </div>

          {/* Divider Bar */}
          <div className="w-6 h-px bg-white/10 my-0.5" />

          {/* Dock Item 5: Alexa Echo Show Launcher */}
          {onOpenEchoModal && (
            <div className="group relative flex items-center justify-center">
              <button
                onClick={onOpenEchoModal}
                title="Open Alexa Echo Show 15 Ext-App Simulator"
                className="w-9 h-9 sm:w-10 sm:h-10 rounded-xl bg-cyan-950/50 hover:bg-cyan-900/60 border border-cyan-500/30 hover:border-cyan-400/60 text-cyan-300 transition-all duration-200 transform hover:scale-110 sm:hover:scale-125 flex items-center justify-center cursor-pointer shadow-sm relative"
              >
                <span className="text-sm sm:text-base select-none">📺</span>
                <span className="absolute top-1 right-1 w-2 h-2 rounded-full bg-cyan-400 animate-pulse shadow-[0_0_6px_rgba(34,211,238,0.9)]" />
              </button>

              {/* Smooth Hover Card Popover with continuous hover bridge */}
              <div className="pointer-events-none group-hover:pointer-events-auto opacity-0 -translate-x-3 group-hover:opacity-100 group-hover:translate-x-0 transition-all duration-200 ease-out absolute left-full ml-3.5 top-1/2 -translate-y-1/2 z-50 w-72 p-4 rounded-xl bg-[#0e1117]/95 backdrop-blur-2xl border border-white/15 shadow-[0_20px_45px_rgba(0,0,0,0.9)] text-left before:absolute before:-left-4 before:top-0 before:w-4 before:h-full">
                {/* Pointer Notch */}
                <div className="absolute -left-1.5 top-1/2 -translate-y-1/2 w-3 h-3 bg-[#0e1117] border-l border-b border-white/15 rotate-45" />

                <div className="flex items-center justify-between mb-2">
                  <span className="font-mono text-[9px] text-zinc-400 uppercase tracking-widest font-semibold">
                    MULTIMODAL EXT-APP
                  </span>
                  <span className="font-mono text-[9px] px-2 py-0.5 rounded-full bg-cyan-950/70 text-cyan-300 border border-cyan-500/40 uppercase font-bold tracking-wider">
                    ECHO SHOW 15
                  </span>
                </div>

                <div className="font-sans text-sm font-semibold text-white mb-2 flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse" />
                  Alexa+ Ambient Simulator
                </div>

                <p className="text-[10px] text-zinc-300 font-sans leading-relaxed mb-2">
                  Full-fidelity Echo Show 15 touch canvas previewing cards, live bilateral commitments, peace of mind verification, and speech synthesis.
                </p>

                <div className="pt-2 border-t border-white/5 text-[9px] font-mono text-cyan-400 uppercase tracking-wider font-bold">
                  Click dock icon to launch →
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </aside>
  );
}
