"use client";

import React, { useState } from "react";
import { AuthConfig, acceptPrivacyNotice, loginAccount, registerAccount } from "@/utils/auth";
import { PrivacyNotice } from "@/components/ui/PrivacyNotice";

interface AuthScreenProps {
  config: AuthConfig | null;
  /** Signed in but the privacy notice changed since the user accepted it */
  consentOnly?: boolean;
  onAuthenticated: () => void;
  onSignOut?: () => void;
}

const inputClass =
  "w-full px-3.5 py-2.5 rounded-xl bg-black/50 border border-white/15 text-white text-sm focus:outline-none focus:border-cyan-400 transition-colors";
const labelClass = "block text-[11px] font-mono font-semibold uppercase tracking-wider text-zinc-300 mb-1.5";

export function AuthScreen({ config, consentOnly = false, onAuthenticated, onSignOut }: AuthScreenProps) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [consent, setConsent] = useState(false);
  const [showNotice, setShowNotice] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const minLength = config?.min_password_length ?? 10;

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (mode === "register") {
      if (password !== confirm) return setError("Passwords do not match.");
      if (password.length < minLength) return setError(`Password must be at least ${minLength} characters.`);
      if (!consent) return setError("Accept the privacy notice to create an account.");
    }
    setBusy(true);
    try {
      if (mode === "register") {
        await registerAccount({ email, password, display_name: displayName || undefined, privacy_consent: true });
      } else {
        await loginAccount(email, password);
      }
      setPassword("");
      setConfirm("");
      onAuthenticated();
    } catch (err: any) {
      setError(err?.message || "Something went wrong. Try again.");
    } finally {
      setBusy(false);
    }
  };

  const acceptNotice = async () => {
    if (!consent) return setError("Tick the box to accept the privacy notice.");
    setBusy(true);
    try {
      await acceptPrivacyNotice();
      onAuthenticated();
    } catch (err: any) {
      setError(err?.message || "Could not save your consent.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen bg-background flex items-center justify-center p-4">
      <div className="w-full max-w-md bg-[#0e1117] border border-white/15 rounded-2xl shadow-[0_25px_60px_rgba(0,0,0,0.95)] overflow-hidden">
        <div className="p-6 border-b border-white/10 bg-zinc-950/80">
          <div className="flex items-center gap-2.5">
            <span className="w-2.5 h-2.5 rounded-full bg-cyan-400 shadow-[0_0_8px_rgba(34,211,238,0.8)]" />
            <h1 className="font-sans text-lg font-semibold text-white tracking-wide">EXAMEN</h1>
          </div>
          <p className="mt-1 text-xs text-zinc-400">Ambient Knowledge &amp; Action Engine</p>
        </div>

        {consentOnly ? (
          <div className="p-6 space-y-4">
            <h2 className="text-sm font-semibold text-white">The privacy notice has changed</h2>
            <div className="p-3.5 rounded-xl bg-zinc-900/60 border border-white/10 max-h-72 overflow-y-auto">
              <PrivacyNotice version={config?.privacy_notice_version} />
            </div>
            <label className="flex items-start gap-2 text-xs text-zinc-300 cursor-pointer">
              <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} className="mt-0.5 accent-cyan-400" />
              <span>I have read and accept the privacy notice.</span>
            </label>
            {error && <p className="text-xs text-red-300">{error}</p>}
            <div className="flex justify-between">
              <button type="button" onClick={onSignOut} className="px-4 py-2 rounded-xl bg-white/5 hover:bg-white/10 text-zinc-300 text-xs">
                Sign out
              </button>
              <button type="button" disabled={busy} onClick={acceptNotice} className="px-5 py-2.5 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-zinc-950 font-semibold text-xs disabled:opacity-50">
                Accept and continue
              </button>
            </div>
          </div>
        ) : (
          <form onSubmit={submit} className="p-6 space-y-4" noValidate>
            <div className="grid grid-cols-2 gap-1 p-1 rounded-xl bg-black/40 border border-white/10">
              {(["login", "register"] as const).map((m) => (
                <button
                  key={m}
                  type="button"
                  onClick={() => {
                    setMode(m);
                    setError(null);
                  }}
                  className={`py-2 rounded-lg text-xs font-semibold transition-colors ${
                    mode === m ? "bg-cyan-500/20 text-cyan-200 border border-cyan-400/50" : "text-zinc-400 hover:text-zinc-200"
                  }`}
                >
                  {m === "login" ? "Sign in" : "Create account"}
                </button>
              ))}
            </div>

            {mode === "register" && (
              <div>
                <label htmlFor="auth-name" className={labelClass}>Name (optional)</label>
                <input id="auth-name" className={inputClass} value={displayName} maxLength={60}
                  onChange={(e) => setDisplayName(e.target.value)} autoComplete="nickname" />
              </div>
            )}
            <div>
              <label htmlFor="auth-email" className={labelClass}>Email</label>
              <input id="auth-email" type="email" required className={inputClass} value={email}
                onChange={(e) => setEmail(e.target.value)} autoComplete="email" />
            </div>
            <div>
              <label htmlFor="auth-password" className={labelClass}>Password</label>
              <input id="auth-password" type="password" required className={inputClass} value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete={mode === "login" ? "current-password" : "new-password"}
                minLength={mode === "register" ? minLength : undefined} />
              {mode === "register" && (
                <p className="mt-1 text-[10px] text-zinc-500">At least {minLength} characters. A short sentence works well.</p>
              )}
            </div>
            {mode === "register" && (
              <>
                <div>
                  <label htmlFor="auth-confirm" className={labelClass}>Repeat password</label>
                  <input id="auth-confirm" type="password" required className={inputClass} value={confirm}
                    onChange={(e) => setConfirm(e.target.value)} autoComplete="new-password" />
                </div>
                <div className="p-3 rounded-xl bg-cyan-950/20 border border-cyan-500/25 space-y-2">
                  <label className="flex items-start gap-2 text-xs text-zinc-300 cursor-pointer">
                    <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} className="mt-0.5 accent-cyan-400" />
                    <span>
                      I have read and accept the{" "}
                      <button type="button" onClick={() => setShowNotice((v) => !v)} className="text-cyan-300 underline underline-offset-2">
                        privacy notice
                      </button>
                      .
                    </span>
                  </label>
                  {showNotice && (
                    <div className="pt-2 border-t border-white/10 max-h-60 overflow-y-auto">
                      <PrivacyNotice version={config?.privacy_notice_version} />
                    </div>
                  )}
                </div>
              </>
            )}

            {error && (
              <div role="alert" className="p-3 rounded-xl bg-red-950/60 border border-red-500/40 text-red-300 text-xs">
                {error}
              </div>
            )}

            <button type="submit" disabled={busy}
              className="w-full py-2.5 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-zinc-950 font-semibold text-sm transition-all disabled:opacity-50">
              {busy ? "Please wait…" : mode === "login" ? "Sign in" : "Create account"}
            </button>
            {mode === "login" && (
              <p className="text-[10px] text-zinc-500 text-center">Forgot your password? Ask the server operator to reset it.</p>
            )}
          </form>
        )}
      </div>
    </div>
  );
}
