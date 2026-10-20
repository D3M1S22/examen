"use client";

// Account administration (admins only): list accounts with their Bee state, create an account with a
// one-time password, reset a password, disable / enable an account. Nothing here shows a user's data.

import React, { useCallback, useEffect, useState } from "react";
import {
  AdminUser,
  createAdminUser,
  listAdminUsers,
  resetAdminUserPassword,
  setAdminUserStatus,
} from "@/utils/auth";

const btn = "px-2.5 py-1 rounded-lg text-[11px] font-semibold transition-colors disabled:opacity-50";
const input =
  "w-full px-3 py-2 rounded-xl bg-black/50 border border-white/15 text-white text-xs focus:outline-none focus:border-cyan-400";

const BEE_LABEL: Record<string, string> = {
  linked: "Bee linked",
  unlinked: "no Bee",
  invalid: "Bee login rejected",
  conflict: "Bee held by another account",
};

export function AdminSection({ selfId, setMessage }: {
  selfId: string;
  setMessage: (m: { kind: "ok" | "error"; text: string } | null) => void;
}) {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [email, setEmail] = useState("");
  const [makeAdmin, setMakeAdmin] = useState(false);
  const [secret, setSecret] = useState<{ email: string; password: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    listAdminUsers()
      .then((r) => setUsers(r.users))
      .catch((e) => setMessage({ kind: "error", text: e?.message || "Could not load accounts." }));
  }, [setMessage]);
  useEffect(() => { load(); }, [load]);

  const act = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    try {
      await fn();
    } catch (e: any) {
      setMessage({ kind: "error", text: e?.message || "Action failed." });
    } finally {
      setBusy(false);
      load();
    }
  };

  return (
    <div className="space-y-4">
      <p className="text-[11px] text-zinc-400">
        You manage accounts only: nobody, administrators included, can read another user&apos;s data.
      </p>

      {secret && (
        <div role="status" className="p-3 rounded-xl bg-amber-950/40 border border-amber-500/30 text-amber-100 text-[11px] space-y-1">
          <p>One-time password for <span className="font-semibold">{secret.email}</span> (shown once):</p>
          <code className="block font-mono text-xs break-all select-all">{secret.password}</code>
          <p className="text-amber-200/80">Hand it over privately; the user should change it after signing in.</p>
        </div>
      )}

      <ul className="space-y-2">
        {users.map((u) => (
          <li key={u.id} className="p-3 rounded-xl bg-white/5 border border-white/10 flex items-center justify-between gap-3">
            <div className="min-w-0 text-xs">
              <p className="text-zinc-100 truncate">
                {u.email}
                {u.is_admin && <span className="ml-1.5 text-[10px] text-cyan-300">admin</span>}
                {u.status === "disabled" && <span className="ml-1.5 text-[10px] text-red-300">disabled</span>}
              </p>
              <p className={`text-[11px] ${u.streaming ? "text-emerald-300" : "text-zinc-500"}`}>
                🐝 {BEE_LABEL[u.bee_link_state] || u.bee_link_state}
                {u.bee_account ? ` (${u.bee_account})` : ""}
                {u.streaming ? " · listening" : ""}
              </p>
            </div>
            {u.id !== selfId && (
              <div className="flex gap-1.5 shrink-0">
                <button className={`${btn} bg-white/5 hover:bg-white/10 text-zinc-200`} disabled={busy}
                  onClick={() => act(async () => {
                    const r = await resetAdminUserPassword(u.id);
                    setSecret({ email: u.email, password: r.initial_password });
                  })}>Reset password</button>
                <button className={`${btn} ${u.status === "disabled" ? "bg-emerald-950/50 text-emerald-200" : "bg-red-950/50 text-red-200"}`}
                  disabled={busy}
                  onClick={() => {
                    const disabling = u.status !== "disabled";
                    if (disabling && !confirm(`Disable ${u.email}? They are signed out everywhere and their Bee stops listening.`)) return;
                    act(() => setAdminUserStatus(u.id, disabling ? "disabled" : "active"));
                  }}>
                  {u.status === "disabled" ? "Enable" : "Disable"}
                </button>
              </div>
            )}
          </li>
        ))}
      </ul>

      <form className="space-y-2" onSubmit={(e) => {
        e.preventDefault();
        act(async () => {
          const r = await createAdminUser({ email: email.trim(), is_admin: makeAdmin });
          setSecret({ email: r.user.email, password: r.initial_password });
          setEmail("");
          setMakeAdmin(false);
        });
      }}>
        <label htmlFor="admin-new-email" className="block text-[11px] font-semibold text-zinc-300">Create an account</label>
        <div className="flex items-center gap-2">
          <input id="admin-new-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)}
            placeholder="name@example.com" className={input} />
          <label className="flex items-center gap-1 text-[11px] text-zinc-400 shrink-0">
            <input type="checkbox" checked={makeAdmin} onChange={(e) => setMakeAdmin(e.target.checked)} /> admin
          </label>
          <button type="submit" disabled={busy || !email.includes("@")}
            className={`${btn} bg-cyan-500 hover:bg-cyan-400 text-zinc-950 shrink-0`}>Create</button>
        </div>
      </form>
    </div>
  );
}
