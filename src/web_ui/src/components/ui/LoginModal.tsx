"use client";

import React, { useState, useEffect, useCallback } from "react";
import { DemoUser, BeePairingInfo } from "@/types/schemas";
import {
  loginUser,
  fetchBeeLink,
  getSavedUsers,
  fetchBackendUsers,
  purgeUserData,
} from "@/utils/auth";

interface LoginModalProps {
  isOpen: boolean;
  onClose: () => void;
  onLoginSuccess: (user: DemoUser) => void;
  currentUser?: DemoUser | null;
  initialConnectBee?: boolean;
  onLogout?: () => void;
}

const PRESET_HANDLES = [
  "Alex • Product Lead",
  "Sam • Security Researcher",
  "Morgan • Systems Architect",
];

export function LoginModal({
  isOpen,
  onClose,
  onLoginSuccess,
  currentUser,
  initialConnectBee = false,
  onLogout,
}: LoginModalProps) {
  const [handle, setHandle] = useState("Alex • Product Lead");
  const [connectBee, setConnectBee] = useState(initialConnectBee);
  const [loading, setLoading] = useState(false);
  const [pairingInfo, setPairingInfo] = useState<BeePairingInfo | null>(null);
  const [copied, setCopied] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [savedUsers, setSavedUsers] = useState<DemoUser[]>([]);
  const [selectedUserId, setSelectedUserId] = useState<string | null>(null);
  const [isRefreshingLink, setIsRefreshingLink] = useState(false);

  // Sync state whenever modal opens or props change
  useEffect(() => {
    if (isOpen) {
      setConnectBee(initialConnectBee);
      setPairingInfo(null);
      setErrorMsg(null);
      if (currentUser) {
        setHandle(currentUser.handle);
        setSelectedUserId(currentUser.user_id);
      } else {
        setSelectedUserId(null);
      }
      // Load saved profiles from localStorage and backend
      const local = getSavedUsers();
      setSavedUsers(local);
      fetchBackendUsers().then((synced) => {
        if (synced && synced.length > 0) {
          setSavedUsers(synced);
        }
      });
    }
  }, [isOpen, initialConnectBee, currentUser]);

  const loadBeeLink = useCallback(async (userId?: string) => {
    setIsRefreshingLink(true);
    try {
      const res = await fetchBeeLink(userId);
      if (res.bee_pairing) {
        setPairingInfo(res.bee_pairing);
      }
    } catch (err: any) {
      console.warn("Could not fetch Bee pairing:", err);
    } finally {
      setIsRefreshingLink(false);
    }
  }, []);

  // Fetch Bee pairing link when connectBee is active
  useEffect(() => {
    if (isOpen && connectBee && !pairingInfo && !isRefreshingLink) {
      loadBeeLink(selectedUserId || currentUser?.user_id);
    }
  }, [isOpen, connectBee, pairingInfo, selectedUserId, currentUser, isRefreshingLink, loadBeeLink]);

  if (!isOpen) return null;

  const handleCopyLink = (url: string) => {
    if (typeof navigator !== "undefined" && navigator.clipboard) {
      navigator.clipboard.writeText(url);
      setCopied(true);
      setTimeout(() => setCopied(false), 2500);
    }
  };

  const handleSelectSavedUser = async (user: DemoUser) => {
    setLoading(true);
    setErrorMsg(null);
    try {
      const res = await loginUser(user.handle, connectBee, user.user_id);
      if (res.success && res.user) {
        onLoginSuccess(res.user);
        onClose();
      }
    } catch (err: any) {
      console.error("Login as saved user error:", err);
      setErrorMsg(err?.message || "Failed to switch user profile.");
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteSavedUser = async (e: React.MouseEvent, userId: string) => {
    e.stopPropagation();
    if (
      confirm(
        "GDPR Art. 17: Are you sure you want to permanently erase this profile and all its credentials?"
      )
    ) {
      await purgeUserData(userId);
      const updated = getSavedUsers();
      setSavedUsers(updated);
      if (currentUser?.user_id === userId) {
        // If current user was purged, reset
        setSelectedUserId(null);
      }
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!handle.trim()) return;
    setLoading(true);
    setErrorMsg(null);

    try {
      // If switching or updating active user
      const targetUserId =
        currentUser && currentUser.handle === handle ? currentUser.user_id : undefined;
      const res = await loginUser(handle, connectBee, targetUserId);
      if (res.success && res.user) {
        onLoginSuccess(res.user);
        onClose();
      }
    } catch (err: any) {
      console.error("Login error:", err);
      setErrorMsg(err?.message || "Failed to initiate session. Please retry.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="login-modal-title"
      className="fixed inset-0 z-[10002] flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-in fade-in duration-200"
    >
      <div className="relative w-full max-w-lg max-h-[90vh] overflow-y-auto bg-[#0e1117] border border-white/15 rounded-2xl shadow-[0_25px_60px_rgba(0,0,0,0.95)] flex flex-col">
        {/* Modal Header */}
        <div className="sticky top-0 z-10 flex items-center justify-between p-5 border-b border-white/10 bg-zinc-950/90 backdrop-blur-md">
          <div className="flex items-center gap-2.5">
            <span className="w-2.5 h-2.5 rounded-full bg-cyan-400 animate-pulse shadow-[0_0_8px_rgba(34,211,238,0.8)]" />
            <h2 id="login-modal-title" className="font-sans text-base font-semibold text-white tracking-wide">
              {currentUser ? "User Management & Bee Pairing" : "EXAMEN User Login & Bee Device Link"}
            </h2>
          </div>
          <button
            onClick={onClose}
            aria-label="Close dialog"
            className="w-8 h-8 rounded-lg bg-white/5 hover:bg-white/10 border border-white/10 flex items-center justify-center text-zinc-400 hover:text-white transition-colors text-sm"
          >
            ✕
          </button>
        </div>

        {/* Modal Body */}
        <div className="p-6 space-y-5">
          {errorMsg && (
            <div className="p-3 rounded-xl bg-red-950/60 border border-red-500/40 text-red-300 font-mono text-xs">
              ⚠️ {errorMsg}
            </div>
          )}

          {/* GDPR Article 25 Notice Banner */}
          <div className="p-3.5 rounded-xl bg-cyan-950/30 border border-cyan-500/30 text-cyan-200 text-xs space-y-1.5">
            <div className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-wider font-bold text-cyan-300">
              <span>🛡️</span>
              <span>GDPR Article 25 • Privacy by Design</span>
            </div>
            <p className="text-[11px] leading-relaxed text-zinc-300">
              Demo sessions operate with <strong className="text-white">zero sensitive PII</strong>. No passwords,
              emails, or biometric voiceprints are collected. Telemetry is pseudonymized and stored ephemerally.
            </p>
          </div>

          {/* Saved User Profiles List (User Management per user) */}
          {savedUsers.length > 0 && (
            <div className="space-y-2.5">
              <div className="flex items-center justify-between">
                <label className="block text-xs font-mono font-semibold uppercase tracking-wider text-zinc-300">
                  Saved User Profiles (Saved per user)
                </label>
                <span className="text-[10px] font-mono text-zinc-400">
                  {savedUsers.length} profile{savedUsers.length === 1 ? "" : "s"}
                </span>
              </div>

              <div className="space-y-1.5 max-h-40 overflow-y-auto pr-1">
                {savedUsers.map((u) => {
                  const isCurrent = currentUser?.user_id === u.user_id;
                  return (
                    <div
                      key={u.user_id}
                      onClick={() => handleSelectSavedUser(u)}
                      className={`group flex items-center justify-between p-2.5 rounded-xl border cursor-pointer transition-all ${
                        isCurrent
                          ? "bg-cyan-950/40 border-cyan-500/50 text-white"
                          : "bg-white/[0.03] hover:bg-white/[0.08] border-white/10 text-zinc-300"
                      }`}
                    >
                      <div className="flex items-center gap-2.5">
                        <div className="w-6 h-6 rounded-full bg-cyan-500/20 border border-cyan-400 text-cyan-300 font-mono text-[10px] font-bold flex items-center justify-center shrink-0">
                          {u.handle.charAt(0).toUpperCase()}
                        </div>
                        <div className="text-left">
                          <div className="font-sans text-xs font-medium text-white flex items-center gap-2">
                            <span>{u.handle}</span>
                            {isCurrent && (
                              <span className="font-mono text-[8px] px-1.5 py-0.2 rounded bg-cyan-900 text-cyan-200 uppercase font-bold">
                                ACTIVE
                              </span>
                            )}
                          </div>
                          <div className="font-mono text-[9px] text-zinc-400 flex items-center gap-2">
                            <span>{u.user_id}</span>
                            <span>•</span>
                            <span className={u.bee_connected ? "text-emerald-400" : "text-zinc-500"}>
                              {u.bee_connected ? "🐝 BEE LINKED" : "NO BEE"}
                            </span>
                          </div>
                        </div>
                      </div>

                      <div className="flex items-center gap-2">
                        <button
                          type="button"
                          onClick={(e) => handleDeleteSavedUser(e, u.user_id)}
                          title="Erase profile (GDPR Art. 17)"
                          className="opacity-0 group-hover:opacity-100 text-zinc-500 hover:text-red-400 transition-opacity p-1 text-xs"
                        >
                          🗑️
                        </button>
                        <span className="text-zinc-400 group-hover:text-cyan-300 text-xs">→</span>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Create New / Switch User Form */}
          <form onSubmit={handleSubmit} className="space-y-4 pt-2 border-t border-white/10">
            <div className="space-y-2">
              <label className="block text-xs font-mono font-semibold uppercase tracking-wider text-zinc-300">
                {savedUsers.length > 0 ? "Or Create / Switch Profile" : "User Pseudonym / Role"}
              </label>
              <div className="flex flex-wrap gap-2 mb-2">
                {PRESET_HANDLES.map((preset) => (
                  <button
                    type="button"
                    key={preset}
                    onClick={() => {
                      setHandle(preset);
                      setSelectedUserId(null);
                    }}
                    className={`text-[11px] px-2.5 py-1 rounded-lg border font-mono transition-colors ${
                      handle === preset
                        ? "bg-cyan-500/20 border-cyan-400 text-cyan-200"
                        : "bg-white/5 border-white/10 text-zinc-400 hover:text-zinc-200"
                    }`}
                  >
                    {preset}
                  </button>
                ))}
              </div>
              <input
                type="text"
                value={handle}
                onChange={(e) => {
                  setHandle(e.target.value);
                  setSelectedUserId(null);
                }}
                placeholder="e.g. Alex (Demo Lead)"
                required
                maxLength={30}
                className="w-full px-3.5 py-2.5 rounded-xl bg-black/50 border border-white/15 text-white font-mono text-xs focus:outline-none focus:border-cyan-400 transition-colors"
              />
            </div>

            {/* Bee Wearable Device Connection Toggle */}
            <div className="p-4 rounded-xl bg-zinc-900/60 border border-white/10 space-y-3">
              <div className="flex items-center justify-between">
                <label htmlFor="connect-bee-toggle" className="flex items-center gap-2 cursor-pointer">
                  <span className="text-base">🐝</span>
                  <span className="font-sans text-xs font-semibold text-white">
                    Connect Bee Wearable AI Device
                  </span>
                </label>
                <input
                  id="connect-bee-toggle"
                  type="checkbox"
                  checked={connectBee}
                  onChange={(e) => {
                    const next = e.target.checked;
                    setConnectBee(next);
                    if (next && !pairingInfo) {
                      loadBeeLink(selectedUserId || currentUser?.user_id);
                    }
                  }}
                  className="w-4 h-4 rounded accent-cyan-400 cursor-pointer"
                />
              </div>

              {connectBee && (
                <div className="space-y-2.5 pt-2 border-t border-white/10 text-xs">
                  {pairingInfo?.connected ? (
                    <div className="flex items-center justify-between p-2.5 rounded-lg bg-emerald-950/50 border border-emerald-500/30 text-emerald-300 font-mono text-[11px]">
                      <div className="flex items-center gap-2">
                        <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                        <span>Verified: {pairingInfo.account || "Bee Device Paired"}</span>
                      </div>
                      <span className="text-[10px] uppercase font-bold text-emerald-400">ONLINE</span>
                    </div>
                  ) : (
                    <>
                      <div className="flex items-center justify-between text-[11px] text-zinc-300 leading-relaxed">
                        <span>Bee CLI authentication link generated for ambient stream ingestion:</span>
                        <button
                          type="button"
                          onClick={() => loadBeeLink(selectedUserId || currentUser?.user_id)}
                          disabled={isRefreshingLink}
                          className="text-[10px] font-mono text-cyan-400 hover:text-cyan-300 underline underline-offset-2 shrink-0 ml-2"
                        >
                          {isRefreshingLink ? "↻ Probing..." : "↻ Refresh link"}
                        </button>
                      </div>

                      {pairingInfo?.pairing_url ? (
                        <div className="space-y-2">
                          <div className="p-2.5 rounded-lg bg-black/60 border border-cyan-500/30 font-mono text-[11px] text-cyan-300 break-all flex items-center justify-between gap-2">
                            <span className="truncate">{pairingInfo.pairing_url}</span>
                            <button
                              type="button"
                              onClick={() => handleCopyLink(pairingInfo.pairing_url!)}
                              className="shrink-0 px-2.5 py-1 rounded bg-cyan-950/80 hover:bg-cyan-900 border border-cyan-500/40 text-cyan-300 text-[10px] font-mono uppercase tracking-wider transition-colors"
                            >
                              {copied ? "Copied!" : "Copy"}
                            </button>
                          </div>
                          <a
                            href={pairingInfo.pairing_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center gap-1.5 text-[11px] font-mono text-cyan-400 hover:text-cyan-300 underline underline-offset-4"
                          >
                            <span>Open pairing authorization link in browser →</span>
                          </a>
                        </div>
                      ) : (
                        <div className="text-zinc-500 font-mono text-[11px] animate-pulse">
                          Probing Bee CLI pairing service...
                        </div>
                      )}
                      <p className="text-[10px] text-zinc-400">
                        💡 <em>Tip: Tap the link above on any device or approve in your Bee companion app.</em>
                      </p>
                    </>
                  )}
                </div>
              )}
            </div>

            {/* Actions */}
            <div className="flex items-center justify-between pt-3 border-t border-white/10">
              {currentUser && onLogout ? (
                <button
                  type="button"
                  onClick={() => {
                    onLogout();
                    onClose();
                  }}
                  className="px-3.5 py-2 rounded-xl bg-red-950/40 hover:bg-red-900/60 border border-red-500/30 text-red-300 font-mono text-xs transition-colors flex items-center gap-1.5 cursor-pointer"
                  title="Sign out and clear session credentials"
                >
                  <span>🚪</span>
                  <span>Sign Out</span>
                </button>
              ) : (
                <div />
              )}
              <div className="flex items-center gap-3">
                <button
                  type="button"
                  onClick={onClose}
                  disabled={loading}
                  className="px-4 py-2 rounded-xl bg-white/5 hover:bg-white/10 text-zinc-300 font-mono text-xs transition-colors cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={loading || !handle.trim()}
                  className="px-5 py-2.5 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-zinc-950 font-sans font-semibold text-xs transition-all shadow-[0_0_15px_rgba(34,211,238,0.4)] disabled:opacity-50 flex items-center gap-2 cursor-pointer"
                >
                  {loading && <span className="animate-spin text-xs">↻</span>}
                  <span>
                    {currentUser
                      ? connectBee
                        ? "Save & Connect Bee"
                        : "Save Profile Changes"
                      : connectBee
                      ? "Connect & Enter Dashboard"
                      : "Start Demo Session"}
                  </span>
                </button>
              </div>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}
