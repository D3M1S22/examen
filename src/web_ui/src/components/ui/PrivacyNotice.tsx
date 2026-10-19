"use client";

import React from "react";

/** Plain-language privacy notice shown at sign-up and when its version changes. */
export function PrivacyNotice({ version }: { version?: string }) {
  return (
    <div className="space-y-2 text-[11px] leading-relaxed text-zinc-300">
      <p>
        <strong className="text-white">What EXAMEN stores about you.</strong> Your email, a salted scrypt hash of your
        password (never the password itself) and the date you accepted this notice.
      </p>
      <p>
        <strong className="text-white">What it processes for you.</strong> When you connect a Bee, the speech it
        transcribes is screened by AWS Bedrock models. Only what is useful (completed actions, people you meet and
        promises, tasks you mention, lecture and meeting briefings) is kept, in a database that belongs to your account
        alone. Topic and contact enrichment runs public web searches.
      </p>
      <p>
        <strong className="text-white">Other people.</strong> Conversations include people around you. Their names,
        roles and promises may be recorded in your account. Use ambient capture only where you are allowed to, and tell
        people when it is on.
      </p>
      <p>
        <strong className="text-white">Your rights.</strong> You can download everything (Account → Export) and delete
        your account at any time, which permanently removes your data and your Bee login from this server. Data is
        kept until you delete it.
      </p>
      {version && <p className="font-mono text-[10px] text-zinc-500">Notice version {version}</p>}
    </div>
  );
}
