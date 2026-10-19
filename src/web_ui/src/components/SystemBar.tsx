"use client";

import React, { useState, useRef, useEffect } from "react";
import { SessionUser } from "@/types/schemas";
import { exportUserDataJson } from "@/utils/auth";

interface SystemBarProps {
  activeTab: string;
  setActiveTab: (tab: string) => void;
  currentTime: string;
  onOpenEchoModal?: () => void;
  sseConnected?: boolean;
  statusData?: any;
  currentUser?: SessionUser | null;
  onOpenLoginModal?: () => void;
  onLogout?: () => void;
  onPurgeData?: () => void;
  onOpenBeePairing?: () => void;
  onDisconnectBee?: () => void;
  updatedTabs?: Record<string, number | boolean>;
  onClearTabBadge?: (tabId: string) => void;
}

export function SystemBar({
  activeTab,
  setActiveTab,
  currentTime,
  onOpenEchoModal,
  sseConnected = true,
  statusData,
  currentUser,
  onOpenLoginModal,
  onLogout,
  onPurgeData,
  onOpenBeePairing,
  onDisconnectBee,
  updatedTabs,
  onClearTabBadge,
}: SystemBarProps) {
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const userMenuRef = useRef<HTMLDivElement>(null);

  const tabs = [
    { id: "overview", label: "OVERVIEW HUB" },
    { id: "peace", label: "PEACE OF MIND" },
    { id: "routines", label: "DAILY ROUTINES" },
    { id: "social", label: "SOCIAL ROLODEX" },
    { id: "topics", label: "TOPIC DOSSIERS" },
    { id: "simulator", label: "AMBIENT SIMULATOR" },
  ];

  // Close dropdown on outside click
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (userMenuRef.current && !userMenuRef.current.contains(event.target as Node)) {
        setUserMenuOpen(false);
      }
    }
    if (userMenuOpen) {
      document.addEventListener("mousedown", handleClickOutside);
      return () => document.removeEventListener("mousedown", handleClickOutside);
    }
  }, [userMenuOpen]);

  const beeDevice = statusData?.telemetry?.bee_device;
  const isBeeConnected = !!currentUser?.bee_connected || !!beeDevice?.connected || beeDevice?.status === "STREAMING";
  const beeAccountName = currentUser?.bee_account || beeDevice?.account || null;

  return (
    <header className="sys-bar">
      <div className="flex items-center gap-3 shrink-0">
        <div className="w-2.5 h-2.5 rounded-full bg-primary animate-pulse"></div>
        <div className="font-sans text-headline-sm tracking-wide font-semibold text-primary flex items-center gap-2">
          EXAMEN OS
          <span className="text-label-sm tracking-widest text-secondary uppercase font-mono ml-2 opacity-60">
            HUB-02
          </span>
        </div>
      </div>

      {/* Tab Navigation with Real-Time Update Badges */}
      <nav className="segmented-nav mx-auto overflow-x-auto hide-scrollbar">
        {tabs.map((tab) => {
          const rawVal = updatedTabs?.[tab.id];
          const count = typeof rawVal === "number" ? rawVal : rawVal ? 1 : 0;
          const hasUpdate = count > 0 && activeTab !== tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => {
                setActiveTab(tab.id);
                onClearTabBadge?.(tab.id);
              }}
              className={`segmented-tab relative inline-flex items-center gap-1.5 ${
                activeTab === tab.id ? "segmented-tab-active" : "segmented-tab-inactive"
              }`}
            >
              <span>{tab.label}</span>
              {hasUpdate && (
                count > 1 ? (
                  <span
                    className="relative inline-flex items-center justify-center px-1.5 py-0.2 min-w-[16px] h-4 text-[9px] font-mono font-bold leading-none text-black bg-cyan-400 rounded-full shadow-[0_0_8px_rgba(6,182,212,0.9)]"
                    title={`${count} updates`}
                  >
                    {count}
                  </span>
                ) : (
                  <span className="relative flex h-2 w-2 ml-0.5 shrink-0" title="New update received">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-75"></span>
                    <span className="relative inline-flex rounded-full h-2 w-2 bg-cyan-400 shadow-[0_0_8px_rgba(6,182,212,0.9)]"></span>
                  </span>
                )
              )}
            </button>
          );
        })}
      </nav>

      {/* Right Controls */}
      <div className="shrink-0 flex items-center gap-3 sm:gap-4 ml-auto">
        {onOpenEchoModal && (
          <button
            onClick={onOpenEchoModal}
            className="hidden sm:flex items-center gap-2 px-3 py-1.5 rounded-lg bg-cyan-950/60 border border-cyan-500/40 text-cyan-300 font-mono text-[10px] tracking-widest uppercase hover:bg-cyan-900 transition-colors shadow-sm"
            title="Open Alexa Echo Show 15 Multimodal Ext-App simulator"
          >
            <span>📺</span>
            <span>Echo Show Ext-App</span>
          </button>
        )}

        {/* User Management & GDPR Session Controls */}
        {currentUser ? (
          <div className="relative" ref={userMenuRef}>
            <button
              onClick={() => setUserMenuOpen(!userMenuOpen)}
              className="flex items-center gap-2 px-2.5 py-1.5 rounded-xl bg-zinc-900/90 hover:bg-zinc-800 border border-white/15 text-white transition-all shadow-sm cursor-pointer"
              title="User session &amp; GDPR data controls"
            >
              <div className="w-6 h-6 rounded-full bg-cyan-500/20 border border-cyan-400 text-cyan-300 font-mono text-[10px] font-bold flex items-center justify-center">
                {currentUser.handle ? currentUser.handle.charAt(0).toUpperCase() : "U"}
              </div>
              <div className="text-left hidden md:block">
                <div className="font-sans text-[11px] font-medium leading-tight max-w-[120px] truncate text-white">
                  {currentUser.handle}
                </div>
                <div className="font-mono text-[8px] text-zinc-400 tracking-wider flex items-center gap-1">
                  <span
                    className={`w-1.5 h-1.5 rounded-full ${
                      isBeeConnected ? "bg-emerald-400" : "bg-zinc-500"
                    }`}
                  />
                  <span>{isBeeConnected ? "BEE LINKED" : "DEMO USER"}</span>
                </div>
              </div>
              <span className={`text-[10px] text-zinc-400 transition-transform ${userMenuOpen ? "rotate-180" : ""}`}>
                ▾
              </span>
            </button>

            {/* User Dropdown Menu */}
            {userMenuOpen && (
              <div className="absolute right-0 mt-2 w-80 rounded-2xl bg-[#0e1117]/95 backdrop-blur-2xl border border-white/15 shadow-[0_20px_50px_rgba(0,0,0,0.95)] p-4 z-50 text-left space-y-3.5 animate-in fade-in slide-in-from-top-2 duration-150">
                {/* User Header */}
                <div className="pb-3 border-b border-white/10">
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-[9px] uppercase tracking-widest text-zinc-400 font-semibold">
                      AUTHENTICATED SESSION
                    </span>
                    <span className="font-mono text-[8px] px-1.5 py-0.5 rounded bg-cyan-950 text-cyan-300 border border-cyan-500/30 font-bold uppercase">
                      GDPR ART. 25
                    </span>
                  </div>
                  <div className="font-sans text-sm font-semibold text-white mt-1">
                    {currentUser.handle}
                  </div>
                  <div className="font-mono text-[10px] text-zinc-400 flex items-center gap-1.5 mt-0.5">
                    <span>ANONYMIZED ID:</span>
                    <span className="text-cyan-300 select-all">{currentUser.user_id}</span>
                  </div>
                </div>

                {/* Bee Wearable Device Status & Pairing Option */}
                <div className="p-3 rounded-xl bg-zinc-900/70 border border-white/10 space-y-2">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-1.5 font-sans text-xs font-semibold text-white">
                      <span>🐝</span>
                      <span>Bee Wearable AI</span>
                    </div>
                    <span
                      className={`font-mono text-[9px] px-2 py-0.5 rounded-full uppercase font-bold tracking-wider ${
                        isBeeConnected
                          ? "bg-emerald-950/70 text-emerald-300 border border-emerald-500/40"
                          : "bg-zinc-800 text-zinc-400 border border-white/10"
                      }`}
                    >
                      {isBeeConnected ? "CONNECTED" : "DISCONNECTED"}
                    </span>
                  </div>

                  {isBeeConnected ? (
                    <div className="space-y-2 pt-1 text-[11px]">
                      <div className="text-zinc-300 font-mono text-[10px]">
                        Account: <span className="text-cyan-300">{beeAccountName || "Verified User"}</span>
                      </div>
                      {onDisconnectBee && (
                        <button
                          onClick={() => {
                            onDisconnectBee();
                            setUserMenuOpen(false);
                          }}
                          className="w-full py-1.5 px-2.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-300 hover:text-white font-mono text-[10px] uppercase tracking-wider transition-colors border border-white/10 text-center"
                        >
                          Disconnect Bee Device
                        </button>
                      )}
                    </div>
                  ) : (
                    <div className="space-y-2 pt-1">
                      <p className="text-[10px] text-zinc-400 font-sans leading-relaxed">
                        Pair your Bee Wearable to enable real-time ambient audio ingestion.
                      </p>
                      {onOpenBeePairing && (
                        <button
                          onClick={() => {
                            onOpenBeePairing();
                            setUserMenuOpen(false);
                          }}
                          className="w-full py-1.5 px-2.5 rounded-lg bg-cyan-950/80 hover:bg-cyan-900 text-cyan-300 border border-cyan-500/40 font-mono text-[10px] uppercase tracking-wider transition-colors text-center font-semibold"
                        >
                          Connect Bee Wearable →
                        </button>
                      )}
                    </div>
                  )}
                </div>

                {/* GDPR Privacy & Data Controls */}
                <div className="space-y-1.5 pt-1">
                  <div className="font-mono text-[9px] uppercase tracking-widest text-zinc-400 font-semibold mb-1">
                    GDPR PRIVACY &amp; DATA CONTROLS
                  </div>

                  <button
                    onClick={() => {
                      exportUserDataJson(currentUser, statusData);
                      setUserMenuOpen(false);
                    }}
                    className="w-full flex items-center justify-between px-2.5 py-1.5 rounded-lg hover:bg-white/5 text-zinc-300 hover:text-white text-xs font-sans transition-colors"
                  >
                    <span className="flex items-center gap-2">
                      <span>📥</span>
                      <span>Export My Data (JSON)</span>
                    </span>
                    <span className="font-mono text-[9px] text-zinc-500">Art. 20</span>
                  </button>

                  {onPurgeData && (
                    <button
                      onClick={() => {
                        if (confirm("GDPR Art. 17: Are you sure you want to permanently erase all stored telemetry and session data?")) {
                          onPurgeData();
                          setUserMenuOpen(false);
                        }
                      }}
                      className="w-full flex items-center justify-between px-2.5 py-1.5 rounded-lg hover:bg-red-950/40 text-red-400 hover:text-red-300 text-xs font-sans transition-colors"
                    >
                      <span className="flex items-center gap-2">
                        <span>🗑️</span>
                        <span>Erase All Data (Right to be Forgotten)</span>
                      </span>
                      <span className="font-mono text-[9px] text-red-500/70">Art. 17</span>
                    </button>
                  )}
                </div>

                {/* User Profiles Management */}
                <div className="pt-1 border-t border-white/10">
                  {onOpenLoginModal && (
                    <button
                      onClick={() => {
                        onOpenLoginModal();
                        setUserMenuOpen(false);
                      }}
                      className="w-full flex items-center justify-between px-2.5 py-1.5 rounded-lg hover:bg-white/5 text-zinc-300 hover:text-white text-xs font-sans transition-colors"
                    >
                      <span className="flex items-center gap-2">
                        <span>👥</span>
                        <span>Switch / Manage Profiles</span>
                      </span>
                      <span className="font-mono text-[9px] text-cyan-400">Manage →</span>
                    </button>
                  )}
                </div>

                {/* Logout Action */}
                <div className="pt-2 border-t border-white/10">
                  <button
                    onClick={() => {
                      if (onLogout) onLogout();
                      setUserMenuOpen(false);
                    }}
                    className="w-full flex items-center justify-center gap-2 px-3 py-2 rounded-xl bg-red-950/50 hover:bg-red-900/60 border border-red-500/30 text-red-300 font-mono text-xs tracking-wider uppercase transition-colors"
                  >
                    <span>🚪</span>
                    <span>Log Out</span>
                  </button>
                </div>
              </div>
            )}
          </div>
        ) : (
          <button
            onClick={onOpenLoginModal}
            className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-cyan-950/50 hover:bg-cyan-900/60 border border-cyan-500/30 text-cyan-300 font-mono text-[11px] tracking-wider transition-all shadow-sm cursor-pointer"
            title="Start GDPR-compliant demo session"
          >
            <span>👤</span>
            <span>Sign In</span>
          </button>
        )}

        <div className="text-right hidden sm:block">
          <div className="font-mono text-label-lg text-primary">{currentTime}</div>
          <div className="font-mono text-label-sm text-secondary mt-0.5">STABLE CADENCE</div>
        </div>
      </div>
    </header>
  );
}
