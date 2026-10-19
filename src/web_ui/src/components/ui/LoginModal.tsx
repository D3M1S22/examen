"use client";

// Account & Bee modal: pair this user's Bee with a QR code, manage MCP access tokens and password,
// export or delete the account (GDPR). Kept under its historical name so callers do not change.

import React, { useCallback, useEffect, useRef, useState } from "react";
import QRCode from "qrcode";
import { BeePairingInfo, DemoUser } from "@/types/schemas";
import {
  ApiTokenInfo,
  cancelBeePairing,
  changePassword,
  createApiToken,
  deleteAccount,
  disconnectBee,
  exportUserDataJson,
  getBeePairing,
  listApiTokens,
  revokeApiToken,
  startBeePairing,
  updateDisplayName,
} from "@/utils/auth";
import { PrivacyNotice } from "@/components/ui/PrivacyNotice";

type Section = "bee" | "account" | "privacy";

interface LoginModalProps {
  isOpen: boolean;
  onClose: () => void;
  /** Called after any change to the account or Bee link, so the page reloads the session */
  onLoginSuccess: (user: DemoUser) => void;
  currentUser?: DemoUser | null;
  initialConnectBee?: boolean;
  initialSection?: Section;
  onLogout?: () => void;
  onAccountDeleted?: () => void;
  authEnabled?: boolean;
}

const btn = "px-3.5 py-2 rounded-xl text-xs font-semibold transition-colors disabled:opacity-50";
const btnPrimary = `${btn} bg-cyan-500 hover:bg-cyan-400 text-zinc-950`;
const btnGhost = `${btn} bg-white/5 hover:bg-white/10 border border-white/10 text-zinc-200`;
const btnDanger = `${btn} bg-red-950/50 hover:bg-red-900/60 border border-red-500/40 text-red-200`;
const input =
  "w-full px-3 py-2 rounded-xl bg-black/50 border border-white/15 text-white text-xs focus:outline-none focus:border-cyan-400";

export function LoginModal({
  isOpen,
  onClose,
  onLoginSuccess,
  currentUser,
  initialConnectBee = false,
  initialSection,
  onLogout,
  onAccountDeleted,
  authEnabled = true,
}: LoginModalProps) {
  const [section, setSection] = useState<Section>("bee");
  const [message, setMessage] = useState<{ kind: "ok" | "error"; text: string } | null>(null);

  useEffect(() => {
    if (isOpen) {
      setSection(initialSection || (initialConnectBee ? "bee" : authEnabled ? "account" : "bee"));
      setMessage(null);
    }
  }, [isOpen, initialSection, initialConnectBee, authEnabled]);

  const refresh = useCallback(() => {
    if (currentUser) onLoginSuccess(currentUser);
  }, [currentUser, onLoginSuccess]);

  if (!isOpen) return null;

  const sections: { id: Section; label: string }[] = authEnabled
    ? [
        { id: "bee", label: "🐝 Bee device" },
        { id: "account", label: "👤 Account" },
        { id: "privacy", label: "🛡️ Privacy" },
      ]
    : [{ id: "bee", label: "🐝 Bee device" }];

  return (
    <div role="dialog" aria-modal="true" aria-labelledby="account-modal-title"
      className="fixed inset-0 z-[10002] flex items-center justify-center p-4 bg-black/80 backdrop-blur-md">
      <div className="relative w-full max-w-lg max-h-[90vh] overflow-y-auto bg-[#0e1117] border border-white/15 rounded-2xl shadow-[0_25px_60px_rgba(0,0,0,0.95)] flex flex-col">
        <div className="sticky top-0 z-10 p-5 border-b border-white/10 bg-zinc-950/90 backdrop-blur-md space-y-3">
          <div className="flex items-center justify-between">
            <div>
              <h2 id="account-modal-title" className="font-sans text-base font-semibold text-white">
                {currentUser?.handle || "Your account"}
              </h2>
              {currentUser?.email && <p className="text-[11px] text-zinc-400">{currentUser.email}</p>}
            </div>
            <button onClick={onClose} aria-label="Close dialog"
              className="w-8 h-8 rounded-lg bg-white/5 hover:bg-white/10 border border-white/10 text-zinc-400 hover:text-white text-sm">
              ✕
            </button>
          </div>
          {sections.length > 1 && (
            <div className="flex gap-1">
              {sections.map((s) => (
                <button key={s.id} onClick={() => { setSection(s.id); setMessage(null); }}
                  className={`px-3 py-1.5 rounded-lg text-[11px] font-semibold ${
                    section === s.id ? "bg-cyan-500/20 text-cyan-200 border border-cyan-400/50" : "text-zinc-400 hover:text-zinc-200"
                  }`}>
                  {s.label}
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="p-6 space-y-5">
          {message && (
            <div role="status" className={`p-3 rounded-xl text-xs ${
              message.kind === "ok" ? "bg-emerald-950/50 border border-emerald-500/30 text-emerald-200" : "bg-red-950/60 border border-red-500/40 text-red-300"
            }`}>
              {message.text}
            </div>
          )}
          {section === "bee" && <BeeSection currentUser={currentUser} onChanged={refresh} setMessage={setMessage} />}
          {section === "account" && authEnabled && (
            <AccountSection currentUser={currentUser} onChanged={refresh} setMessage={setMessage} />
          )}
          {section === "privacy" && authEnabled && (
            <PrivacySection setMessage={setMessage} onDeleted={() => { onClose(); onAccountDeleted?.(); }} />
          )}

          {onLogout && authEnabled && (
            <div className="pt-4 border-t border-white/10 flex items-center justify-between">
              <p className="text-[10px] text-zinc-500 max-w-[60%]">Signing out does not stop your Bee: it keeps listening for you.</p>
              <button className={btnGhost} onClick={() => { onLogout(); onClose(); }}>🚪 Sign out</button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Bee pairing with QR code
// ---------------------------------------------------------------------------

function BeeSection({ currentUser, onChanged, setMessage }: {
  currentUser?: DemoUser | null;
  onChanged: () => void;
  setMessage: (m: { kind: "ok" | "error"; text: string } | null) => void;
}) {
  const [pairing, setPairing] = useState<BeePairingInfo | null>(null);
  const [qr, setQr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const linked = !!currentUser?.bee_connected || pairing?.status === "connected";

  const stopPolling = () => {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = null;
  };

  useEffect(() => {
    getBeePairing().then((r) => setPairing(r.bee_pairing)).catch(() => undefined);
    return stopPolling;
  }, []);

  useEffect(() => {
    if (pairing?.status === "pending" && pairing.pairing_url) {
      QRCode.toDataURL(pairing.pairing_url, { margin: 1, width: 240, errorCorrectionLevel: "M" })
        .then(setQr)
        .catch(() => setQr(null));
    } else {
      setQr(null);
    }
  }, [pairing?.status, pairing?.pairing_url]);

  const poll = () => {
    stopPolling();
    pollRef.current = setInterval(async () => {
      try {
        const r = await getBeePairing();
        setPairing(r.bee_pairing);
        const st = r.bee_pairing?.status;
        if (st === "connected") {
          stopPolling();
          setMessage({ kind: "ok", text: "Your Bee is connected. Ambient listening has started for your account." });
          onChanged();
        } else if (st === "expired" || st === "failed") {
          stopPolling();
          setMessage({ kind: "error", text: r.bee_pairing?.error || "Pairing did not complete. Try again." });
        }
      } catch {
        /* keep polling */
      }
    }, 2000);
  };

  const start = async () => {
    setBusy(true);
    setMessage(null);
    try {
      const r = await startBeePairing();
      setPairing(r.bee_pairing);
      if (r.bee_pairing?.status === "pending") poll();
      if (r.bee_pairing?.status === "connected") onChanged();
    } catch (err: any) {
      setMessage({ kind: "error", text: err?.message || "Could not start Bee pairing." });
    } finally {
      setBusy(false);
    }
  };

  const cancel = async () => {
    stopPolling();
    await cancelBeePairing().catch(() => undefined);
    setPairing({ status: "idle" });
  };

  const disconnect = async () => {
    if (!confirm("Disconnect your Bee from this account? Ambient listening stops; your stored data is kept.")) return;
    setBusy(true);
    const ok = await disconnectBee();
    setBusy(false);
    setPairing({ status: "idle" });
    setMessage(ok ? { kind: "ok", text: "Bee disconnected." } : { kind: "error", text: "Could not disconnect the Bee." });
    onChanged();
  };

  if (linked) {
    return (
      <div className="space-y-3">
        <div className="flex items-center justify-between p-3 rounded-xl bg-emerald-950/40 border border-emerald-500/30">
          <div className="flex items-center gap-2 text-emerald-200 text-xs">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
            <span>Connected{currentUser?.bee_account ? ` as ${currentUser.bee_account}` : ""}</span>
          </div>
          <button className={btnDanger} disabled={busy} onClick={disconnect}>Disconnect</button>
        </div>
        <p className="text-[11px] text-zinc-400">
          Your Bee login is stored only in your private folder on this server and is used only for your account.
        </p>
      </div>
    );
  }

  if (pairing?.status === "pending" && pairing.pairing_url) {
    const mins = pairing.expires_in_seconds != null ? Math.max(1, Math.ceil(pairing.expires_in_seconds / 60)) : null;
    return (
      <div className="space-y-4">
        <ol className="list-decimal list-inside text-xs text-zinc-300 space-y-1">
          <li>In the Bee app, enable Developer Mode (Settings → tap the app version 5 times).</li>
          <li>Scan this code with your phone, or open the link, and approve the connection.</li>
        </ol>
        <div className="flex flex-col items-center gap-3">
          {qr ? (
            <img src={qr} alt="QR code to connect your Bee" width={240} height={240} className="rounded-xl bg-white p-2" />
          ) : (
            <div className="w-[240px] h-[240px] rounded-xl bg-white/5 animate-pulse" />
          )}
          <a href={pairing.pairing_url} target="_blank" rel="noopener noreferrer"
            className="text-[11px] font-mono text-cyan-300 underline underline-offset-4 break-all text-center">
            {pairing.pairing_url}
          </a>
          <p className="text-[11px] text-zinc-400 flex items-center gap-2">
            <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse" />
            Waiting for approval{mins ? ` · expires in about ${mins} min` : ""}
          </p>
        </div>
        <div className="flex justify-end">
          <button className={btnGhost} onClick={cancel}>Cancel</button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <p className="text-xs text-zinc-300 leading-relaxed">
        Connect your Bee to let EXAMEN listen for you. Each account pairs its own Bee: nobody else on this server can
        read your stream or your data.
      </p>
      <button className={btnPrimary} disabled={busy} onClick={start}>
        {busy ? "Preparing QR code…" : pairing?.status === "expired" || pairing?.status === "failed" ? "Try again" : "Connect my Bee"}
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Account: name, password, MCP tokens
// ---------------------------------------------------------------------------

function AccountSection({ currentUser, onChanged, setMessage }: {
  currentUser?: DemoUser | null;
  onChanged: () => void;
  setMessage: (m: { kind: "ok" | "error"; text: string } | null) => void;
}) {
  const [name, setName] = useState(currentUser?.handle && currentUser.handle !== currentUser.email ? currentUser.handle : "");
  const [currentPw, setCurrentPw] = useState("");
  const [newPw, setNewPw] = useState("");
  const [tokens, setTokens] = useState<ApiTokenInfo[]>([]);
  const [newToken, setNewToken] = useState<string | null>(null);
  const [tokenName, setTokenName] = useState("Alexa+");
  const [busy, setBusy] = useState(false);

  const loadTokens = useCallback(() => {
    listApiTokens().then((r) => setTokens(r.tokens)).catch(() => undefined);
  }, []);
  useEffect(loadTokens, [loadTokens]);

  const run = async (fn: () => Promise<void>) => {
    setBusy(true);
    setMessage(null);
    try {
      await fn();
    } catch (err: any) {
      setMessage({ kind: "error", text: err?.message || "Something went wrong." });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-6">
      <form className="space-y-2" onSubmit={(e) => { e.preventDefault(); run(async () => {
        await updateDisplayName(name);
        setMessage({ kind: "ok", text: "Name saved." });
        onChanged();
      }); }}>
        <label htmlFor="acc-name" className="block text-[11px] font-mono uppercase tracking-wider text-zinc-300">Display name</label>
        <div className="flex gap-2">
          <input id="acc-name" className={input} value={name} maxLength={60} onChange={(e) => setName(e.target.value)} />
          <button className={btnGhost} disabled={busy}>Save</button>
        </div>
      </form>

      <form className="space-y-2" onSubmit={(e) => { e.preventDefault(); run(async () => {
        const r = await changePassword(currentPw, newPw);
        setCurrentPw("");
        setNewPw("");
        setMessage({ kind: "ok", text: `Password changed. ${r.other_sessions_signed_out} other session(s) signed out.` });
      }); }}>
        <div className="text-[11px] font-mono uppercase tracking-wider text-zinc-300">Change password</div>
        <input type="password" aria-label="Current password" placeholder="Current password" className={input}
          value={currentPw} onChange={(e) => setCurrentPw(e.target.value)} autoComplete="current-password" />
        <input type="password" aria-label="New password" placeholder="New password" className={input}
          value={newPw} onChange={(e) => setNewPw(e.target.value)} autoComplete="new-password" />
        <button className={btnGhost} disabled={busy || !currentPw || !newPw}>Change password</button>
      </form>

      <div className="space-y-2">
        <div className="text-[11px] font-mono uppercase tracking-wider text-zinc-300">Alexa+ / MCP access tokens</div>
        <p className="text-[11px] text-zinc-400">
          Give an MCP client (Alexa+, Claude) a token so it can read your data at <code className="text-cyan-300">/mcp</code>.
          Send it as <code className="text-cyan-300">Authorization: Bearer …</code>.
        </p>
        {newToken && (
          <div className="p-3 rounded-xl bg-amber-950/40 border border-amber-500/40 space-y-1">
            <p className="text-[11px] text-amber-200">Copy this token now. It will not be shown again.</p>
            <code className="block text-[11px] text-white break-all select-all">{newToken}</code>
          </div>
        )}
        <ul className="space-y-1.5">
          {tokens.map((t) => (
            <li key={t.id} className="flex items-center justify-between p-2 rounded-lg bg-white/[0.03] border border-white/10">
              <div className="text-[11px]">
                <div className="text-white">{t.name}</div>
                <div className="font-mono text-zinc-500">{t.prefix}… · created {t.created_at.slice(0, 10)}
                  {t.last_used_at ? ` · used ${t.last_used_at.slice(0, 10)}` : " · never used"}</div>
              </div>
              <button className={btnDanger} disabled={busy}
                onClick={() => run(async () => { await revokeApiToken(t.id); loadTokens(); })}>Revoke</button>
            </li>
          ))}
        </ul>
        <div className="flex gap-2">
          <input aria-label="Token name" className={input} value={tokenName} maxLength={60} onChange={(e) => setTokenName(e.target.value)} />
          <button className={btnGhost} disabled={busy} onClick={() => run(async () => {
            const r = await createApiToken(tokenName || "MCP client");
            setNewToken(r.token.token || null);
            loadTokens();
          })}>New token</button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Privacy: notice, export, erasure
// ---------------------------------------------------------------------------

function PrivacySection({ setMessage, onDeleted }: {
  setMessage: (m: { kind: "ok" | "error"; text: string } | null) => void;
  onDeleted: () => void;
}) {
  const [password, setPassword] = useState("");
  const [confirmText, setConfirmText] = useState("");
  const [busy, setBusy] = useState(false);

  return (
    <div className="space-y-5">
      <div className="p-3.5 rounded-xl bg-zinc-900/60 border border-white/10 max-h-56 overflow-y-auto">
        <PrivacyNotice />
      </div>

      <div className="flex items-center justify-between">
        <div className="text-xs text-zinc-300">Download everything stored for your account (JSON).</div>
        <button className={btnGhost} disabled={busy} onClick={async () => {
          setBusy(true);
          try {
            await exportUserDataJson();
            setMessage({ kind: "ok", text: "Export downloaded." });
          } catch (err: any) {
            setMessage({ kind: "error", text: err?.message || "Export failed." });
          } finally {
            setBusy(false);
          }
        }}>📥 Export</button>
      </div>

      <form className="space-y-2 p-3.5 rounded-xl border border-red-500/30 bg-red-950/20" onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true);
        try {
          await deleteAccount(password);
          onDeleted();
        } catch (err: any) {
          setMessage({ kind: "error", text: err?.message || "Could not delete the account." });
        } finally {
          setBusy(false);
        }
      }}>
        <div className="text-xs font-semibold text-red-200">Delete account</div>
        <p className="text-[11px] text-zinc-300">
          Permanently deletes your account, your Bee login on this server and every record (actions, contacts,
          tasks, events, briefings). This cannot be undone.
        </p>
        <input type="password" aria-label="Your password" placeholder="Your password" className={input}
          value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" />
        <input aria-label="Type DELETE to confirm" placeholder="Type DELETE to confirm" className={input}
          value={confirmText} onChange={(e) => setConfirmText(e.target.value)} />
        <button className={btnDanger} disabled={busy || !password || confirmText !== "DELETE"}>
          Delete my account and data
        </button>
      </form>
    </div>
  );
}
