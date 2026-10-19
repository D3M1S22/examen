"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import { AccountToken, AdminUser, BeeLinkInfo, SessionUser } from "@/types/schemas";
import {
  changePassword,
  createToken,
  createUser,
  fetchSession,
  listTokens,
  listUsers,
  login,
  logoutEverywhere,
  refreshBeeLink,
  resetUserPassword,
  revokeToken,
  setUserStatus,
  signup,
  signupFormError,
  startBeePairing,
  unlinkBee,
} from "@/utils/auth";

interface LoginModalProps {
  isOpen: boolean;
  onClose: () => void;
  /** `created` is true right after a self-registration (the page keeps the account panel open). */
  onLoginSuccess: (user: SessionUser, created?: boolean) => void;
  currentUser?: SessionUser | null;
  /** Signed out: offer the "Create account" tab (server `AUTH_ALLOW_SIGNUP`). */
  signupEnabled?: boolean;
  initialConnectBee?: boolean;
  onLogout?: () => void;
  /** Signed out: the sign-in form cannot be dismissed. */
  mandatory?: boolean;
  /** Called when the Bee link or the account changed (refresh the session in the page). */
  onSessionChanged?: (user: SessionUser | null) => void;
}

const inputClass =
  "w-full px-3.5 py-2.5 rounded-xl bg-black/50 border border-white/15 text-white font-mono text-xs focus:outline-none focus:border-cyan-400 transition-colors";
const buttonClass =
  "px-3.5 py-2 rounded-xl bg-white/5 hover:bg-white/10 border border-white/10 text-zinc-200 font-mono text-xs transition-colors cursor-pointer disabled:opacity-50";
const primaryClass =
  "px-5 py-2.5 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-zinc-950 font-sans font-semibold text-xs transition-all shadow-[0_0_15px_rgba(34,211,238,0.4)] disabled:opacity-50 flex items-center gap-2 cursor-pointer";
const sectionClass = "p-4 rounded-xl bg-zinc-900/60 border border-white/10 space-y-3";
const sectionTitle = "font-mono text-[10px] uppercase tracking-wider font-bold text-zinc-300";

const STATE_BADGE: Record<string, string> = {
  linked: "bg-emerald-950/60 border-emerald-500/40 text-emerald-300",
  pairing: "bg-amber-950/60 border-amber-500/40 text-amber-300",
  invalid: "bg-red-950/60 border-red-500/40 text-red-300",
  unlinked: "bg-zinc-900 border-white/10 text-zinc-400",
};

type AuthMode = "signin" | "signup";

const labelClass = "block text-xs font-mono font-semibold uppercase tracking-wider text-zinc-300";

function AuthForm({ mode, signupEnabled, onModeChange, onLoginSuccess }: {
  mode: AuthMode;
  signupEnabled: boolean;
  onModeChange: (mode: AuthMode) => void;
  onLoginSuccess: (user: SessionUser, created?: boolean) => void;
}) {
  const [username, setUsername] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const registering = mode === "signup" && signupEnabled;
  const formError = registering ? signupFormError(username, password, confirm) : null;

  const switchMode = (next: AuthMode) => {
    setError(null);
    setConfirm("");
    onModeChange(next);
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      if (registering) {
        onLoginSuccess(await signup(username, password, displayName), true);
      } else {
        onLoginSuccess(await login(username, password));
      }
    } catch (err: any) {
      setError(err?.message || (registering ? "Registration failed" : "Sign-in failed"));
    } finally {
      setLoading(false);
    }
  };

  const tabClass = (active: boolean) =>
    `flex-1 py-2 rounded-lg font-mono text-xs transition-colors cursor-pointer ${
      active ? "bg-cyan-500/15 border border-cyan-400/40 text-cyan-200" : "text-zinc-400 hover:text-zinc-200"
    }`;

  return (
    <form onSubmit={submit} className="space-y-4">
      {signupEnabled && (
        <div role="tablist" className="flex gap-1 p-1 rounded-xl bg-black/40 border border-white/10">
          <button type="button" role="tab" aria-selected={!registering} className={tabClass(!registering)}
            onClick={() => switchMode("signin")}>Sign in</button>
          <button type="button" role="tab" aria-selected={registering} className={tabClass(registering)}
            onClick={() => switchMode("signup")}>Create account</button>
        </div>
      )}
      {error && (
        <div className="p-3 rounded-xl bg-red-950/60 border border-red-500/40 text-red-300 font-mono text-xs">⚠️ {error}</div>
      )}
      <div className="space-y-2">
        <label htmlFor="login-username" className={labelClass}>Username</label>
        <input id="login-username" autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)}
          required className={inputClass} />
      </div>
      {registering && (
        <div className="space-y-2">
          <label htmlFor="signup-display-name" className={labelClass}>
            Display name <span className="normal-case font-normal text-zinc-500">(optional)</span>
          </label>
          <input id="signup-display-name" autoComplete="name" value={displayName} maxLength={60}
            onChange={(e) => setDisplayName(e.target.value)} className={inputClass} />
        </div>
      )}
      <div className="space-y-2">
        <label htmlFor="login-password" className={labelClass}>Password</label>
        <input id="login-password" type="password" autoComplete={registering ? "new-password" : "current-password"}
          value={password} onChange={(e) => setPassword(e.target.value)} required className={inputClass} />
      </div>
      {registering && (
        <div className="space-y-2">
          <label htmlFor="signup-confirm" className={labelClass}>Confirm password</label>
          <input id="signup-confirm" type="password" autoComplete="new-password" value={confirm}
            onChange={(e) => setConfirm(e.target.value)} required className={inputClass} />
        </div>
      )}
      <p className="text-[11px] text-zinc-400 leading-relaxed">
        {registering
          ? "At least 12 characters. Your account starts empty: link your own Bee device next. Your data is never visible to other users."
          : signupEnabled
            ? "Each EXAMEN account links its own Bee device. Your data is never visible to other users."
            : "Each EXAMEN account links its own Bee device. Your data is never visible to other users. Accounts are created by an administrator."}
      </p>
      {registering && formError && (username || password || confirm) && (
        <p className="text-[11px] font-mono text-amber-300">{formError}</p>
      )}
      <div className="flex justify-end">
        <button type="submit" disabled={loading || !username || !password || Boolean(formError)} className={primaryClass}>
          {loading && <span className="animate-spin text-xs">↻</span>}
          <span>{registering ? "Create account" : "Sign in"}</span>
        </button>
      </div>
    </form>
  );
}

function BeeLinkSection({ initialLink, autoStart, onChanged }: {
  initialLink: BeeLinkInfo | null;
  autoStart: boolean;
  onChanged: () => void;
}) {
  const [link, setLink] = useState<BeeLinkInfo | null>(initialLink);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const started = useRef(false);
  const state = link?.state || "unlinked";

  const run = useCallback(async (action: () => Promise<BeeLinkInfo>) => {
    setBusy(true);
    setError(null);
    try {
      const next = await action();
      setLink(next);
      if (next.state === "linked" || next.state === "unlinked") onChanged();
    } catch (err: any) {
      setError(err?.message || "Bee request failed");
    } finally {
      setBusy(false);
    }
  }, [onChanged]);

  useEffect(() => {
    if (autoStart && !started.current && state !== "linked" && state !== "pairing") {
      started.current = true;
      run(startBeePairing);
    }
  }, [autoStart, state, run]);

  // While pairing, poll until the Bee app approves (or the request expires)
  useEffect(() => {
    if (state !== "pairing") return;
    const timer = setInterval(async () => {
      try {
        const next = await refreshBeeLink();
        setLink(next);
        if (next.state !== "pairing") onChanged();
      } catch (err: any) {
        setError(err?.message || "Bee check failed");
      }
    }, 3000);
    return () => clearInterval(timer);
  }, [state, onChanged]);

  return (
    <div className={sectionClass}>
      <div className="flex items-center justify-between">
        <span className={sectionTitle}>🐝 Your Bee account</span>
        <span className={`font-mono text-[10px] px-2 py-0.5 rounded border uppercase font-bold ${STATE_BADGE[state]}`}>{state}</span>
      </div>
      {error && <div className="text-red-300 font-mono text-[11px]">⚠️ {error}</div>}
      {link?.last_error && state !== "linked" && <div className="text-amber-300 font-mono text-[11px]">{link.last_error}</div>}

      {state === "linked" && (
        <div className="flex items-center justify-between gap-3">
          <span className="text-xs text-zinc-200">
            Linked as <strong className="text-white">{link?.bee_first_name || "Bee user"}</strong>: live ingestion runs for your account only.
          </span>
          <button type="button" disabled={busy} className={buttonClass} onClick={() => {
            if (confirm("Disconnect your Bee account? Live ingestion stops; your data is kept.")) run(unlinkBee);
          }}>
            Disconnect Bee
          </button>
        </div>
      )}

      {state === "pairing" && link?.pairing_url && (
        <div className="space-y-2 text-xs">
          <p className="text-zinc-300">Open this link and approve it in the Bee app (Developer Mode). Waiting for approval…</p>
          <div className="p-2.5 rounded-lg bg-black/60 border border-cyan-500/30 font-mono text-[11px] text-cyan-300 flex items-center justify-between gap-2">
            <a href={link.pairing_url} target="_blank" rel="noopener noreferrer" className="truncate underline underline-offset-2">
              {link.pairing_url}
            </a>
            <button type="button" className="shrink-0 px-2.5 py-1 rounded bg-cyan-950/80 border border-cyan-500/40 text-[10px] uppercase"
              onClick={() => {
                navigator.clipboard?.writeText(link.pairing_url!);
                setCopied(true);
                setTimeout(() => setCopied(false), 2000);
              }}>
              {copied ? "Copied" : "Copy"}
            </button>
          </div>
          {link.pairing_expires_at && (
            <p className="text-[10px] text-zinc-500">Expires at {new Date(link.pairing_expires_at).toLocaleTimeString()}</p>
          )}
        </div>
      )}

      {(state === "unlinked" || state === "invalid") && (
        <div className="flex items-center justify-between gap-3">
          <span className="text-xs text-zinc-400">Link your own Bee account to start ambient ingestion.</span>
          <button type="button" disabled={busy} className={primaryClass} onClick={() => run(startBeePairing)}>
            {busy && <span className="animate-spin text-xs">↻</span>}
            <span>Connect Bee</span>
          </button>
        </div>
      )}
    </div>
  );
}

function TokensSection() {
  const [tokens, setTokens] = useState<AccountToken[]>([]);
  const [name, setName] = useState("");
  const [created, setCreated] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => listTokens().then(setTokens).catch((e) => setError(e.message)), []);
  useEffect(() => { load(); }, [load]);

  return (
    <div className={sectionClass}>
      <span className={sectionTitle}>🔑 MCP access tokens (Alexa+, Claude, …)</span>
      {error && <div className="text-red-300 font-mono text-[11px]">⚠️ {error}</div>}
      {created && (
        <div className="p-2.5 rounded-lg bg-emerald-950/40 border border-emerald-500/30 font-mono text-[11px] text-emerald-200 break-all">
          Copy it now, it will not be shown again: <span className="select-all text-white">{created}</span>
        </div>
      )}
      {tokens.map((t) => (
        <div key={t.token_id} className="flex items-center justify-between text-xs text-zinc-300 font-mono">
          <span>{t.name} <span className="text-zinc-500">· {t.last_used_at ? `used ${new Date(t.last_used_at).toLocaleString()}` : "never used"}</span></span>
          <button type="button" className="text-red-400 hover:text-red-300" onClick={() => revokeToken(t.token_id).then(load)}>Revoke</button>
        </div>
      ))}
      <form className="flex gap-2" onSubmit={async (e) => {
        e.preventDefault();
        try {
          const res = await createToken(name);
          setCreated(res.token);
          setName("");
          load();
        } catch (err: any) {
          setError(err.message);
        }
      }}>
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Token name" className={inputClass} />
        <button type="submit" disabled={!name.trim()} className={buttonClass}>Create</button>
      </form>
    </div>
  );
}

function PasswordSection() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  return (
    <form className={sectionClass} onSubmit={async (e) => {
      e.preventDefault();
      try {
        await changePassword(current, next);
        setMessage("Password changed. Sign in again on your other devices.");
        setCurrent("");
        setNext("");
      } catch (err: any) {
        setMessage(`⚠️ ${err.message}`);
      }
    }}>
      <span className={sectionTitle}>🔒 Change password</span>
      {message && <div className="text-zinc-300 font-mono text-[11px]">{message}</div>}
      <input type="password" autoComplete="current-password" placeholder="Current password" value={current}
        onChange={(e) => setCurrent(e.target.value)} className={inputClass} />
      <input type="password" autoComplete="new-password" placeholder="New password (12+ characters)" value={next}
        onChange={(e) => setNext(e.target.value)} className={inputClass} />
      <div className="flex justify-end"><button type="submit" disabled={!current || next.length < 12} className={buttonClass}>Update</button></div>
    </form>
  );
}

function AdminSection({ selfId }: { selfId: string }) {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [username, setUsername] = useState("");
  const [isAdmin, setIsAdmin] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(() => listUsers().then(setUsers).catch((e) => setNotice(`⚠️ ${e.message}`)), []);
  useEffect(() => { load(); }, [load]);

  return (
    <div className={sectionClass}>
      <span className={sectionTitle}>🛠️ Accounts (admin)</span>
      {notice && <div className="text-zinc-200 font-mono text-[11px] break-all">{notice}</div>}
      {users.map((u) => (
        <div key={u.user_id} className="flex items-center justify-between gap-2 text-xs font-mono text-zinc-300">
          <span>
            {u.username}{u.is_admin ? " (admin)" : ""} · <span className="text-zinc-500">{u.status}</span> ·{" "}
            <span className={u.streaming ? "text-emerald-400" : "text-zinc-500"}>
              🐝 {u.bee_link_state || "unlinked"}{u.streaming ? " · live" : ""}
            </span>
          </span>
          {u.user_id !== selfId && (
            <span className="flex gap-2 shrink-0">
              <button type="button" className="text-cyan-400" onClick={async () => {
                const pw = await resetUserPassword(u.user_id);
                setNotice(`One-time password for ${u.username}: ${pw}`);
              }}>Reset password</button>
              <button type="button" className="text-amber-400" onClick={() =>
                setUserStatus(u.user_id, u.status === "disabled" ? "active" : "disabled").then(load)}>
                {u.status === "disabled" ? "Enable" : "Disable"}
              </button>
            </span>
          )}
        </div>
      ))}
      <form className="flex items-center gap-2" onSubmit={async (e) => {
        e.preventDefault();
        try {
          const res = await createUser(username, isAdmin);
          setNotice(`Created ${res.user.username}. One-time password: ${res.initial_password}`);
          setUsername("");
          load();
        } catch (err: any) {
          setNotice(`⚠️ ${err.message}`);
        }
      }}>
        <input value={username} onChange={(e) => setUsername(e.target.value)} placeholder="New username" className={inputClass} />
        <label className="flex items-center gap-1 text-[11px] text-zinc-400 shrink-0">
          <input type="checkbox" checked={isAdmin} onChange={(e) => setIsAdmin(e.target.checked)} /> admin
        </label>
        <button type="submit" disabled={username.trim().length < 3} className={buttonClass}>Add</button>
      </form>
    </div>
  );
}

export function LoginModal({
  isOpen,
  onClose,
  onLoginSuccess,
  currentUser,
  initialConnectBee = false,
  onLogout,
  mandatory = false,
  onSessionChanged,
  signupEnabled = false,
}: LoginModalProps) {
  const [authMode, setAuthMode] = useState<AuthMode>("signin");
  const refreshSession = useCallback(async () => {
    const user = await fetchSession();
    onSessionChanged?.(user);
  }, [onSessionChanged]);

  if (!isOpen) return null;

  return (
    <div role="dialog" aria-modal="true" aria-labelledby="login-modal-title"
      className="fixed inset-0 z-[10002] flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-in fade-in duration-200">
      <div className="relative w-full max-w-lg max-h-[90vh] overflow-y-auto bg-[#0e1117] border border-white/15 rounded-2xl shadow-[0_25px_60px_rgba(0,0,0,0.95)] flex flex-col">
        <div className="sticky top-0 z-10 flex items-center justify-between p-5 border-b border-white/10 bg-zinc-950/90 backdrop-blur-md">
          <div className="flex items-center gap-2.5">
            <span className="w-2.5 h-2.5 rounded-full bg-cyan-400 animate-pulse shadow-[0_0_8px_rgba(34,211,238,0.8)]" />
            <h2 id="login-modal-title" className="font-sans text-base font-semibold text-white tracking-wide">
              {currentUser
                ? `Account · ${currentUser.handle}`
                : authMode === "signup" && signupEnabled ? "Create your EXAMEN account" : "Sign in to EXAMEN"}
            </h2>
          </div>
          {!mandatory && (
            <button onClick={onClose} aria-label="Close dialog"
              className="w-8 h-8 rounded-lg bg-white/5 hover:bg-white/10 border border-white/10 flex items-center justify-center text-zinc-400 hover:text-white transition-colors text-sm">
              ✕
            </button>
          )}
        </div>

        <div className="p-6 space-y-5">
          {!currentUser ? (
            <AuthForm mode={authMode} signupEnabled={signupEnabled} onModeChange={setAuthMode}
              onLoginSuccess={onLoginSuccess} />
          ) : (
            <>
              <BeeLinkSection initialLink={currentUser.bee_link} autoStart={initialConnectBee} onChanged={refreshSession} />
              <TokensSection />
              <PasswordSection />
              {currentUser.is_admin && <AdminSection selfId={currentUser.user_id} />}
              <div className="flex items-center justify-between pt-3 border-t border-white/10">
                <div className="flex gap-2">
                  {onLogout && (
                    <button type="button" className={buttonClass} onClick={() => { onLogout(); onClose(); }}>🚪 Sign out</button>
                  )}
                  <button type="button" className={buttonClass} onClick={async () => {
                    await logoutEverywhere();
                    onSessionChanged?.(null);
                    onClose();
                  }}>Sign out everywhere</button>
                </div>
                <button type="button" onClick={onClose} className={buttonClass}>Close</button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
