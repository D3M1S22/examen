import React, { useEffect, useState } from "react";
import { ActionChanges, VerifiedAction } from "@/types/schemas";
import { displayActionTitle, normalizeActionTitle } from "@/utils/curation";
import { EditModalFrame, fieldInput, fieldLabel } from "./EditModalFrame";

interface EditActionModalProps {
  action: VerifiedAction | null;
  onClose: () => void;
  onSubmit: (actionId: string, changes: ActionChanges) => Promise<void>;
}

const DOMAINS: { value: VerifiedAction["domain"]; label: string }[] = [
  { value: "safety", label: "🛡️ Safety" },
  { value: "routine", label: "📋 Routine" },
  { value: "work_task", label: "💼 Work task" },
];

/** Corrects an extracted action: title and domain. The transcript is the evidence and stays read-only. */
export function EditActionModal({ action, onClose, onSubmit }: EditActionModalProps) {
  const [title, setTitle] = useState("");
  const [domain, setDomain] = useState<VerifiedAction["domain"]>("safety");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (action) {
      setTitle(displayActionTitle(action.action_type));
      setDomain(action.domain);
      setError(null);
    }
  }, [action]);

  const submit = async () => {
    if (!action) return;
    if (!normalizeActionTitle(title)) {
      setError("The title cannot be empty.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await onSubmit(action.id, { action_type: title, domain });
      onClose();
    } catch (err: any) {
      setError(err?.message || "Failed to save the action.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <EditModalFrame
      isOpen={!!action}
      kicker="PEACE OF MIND // CORRECTION"
      title="Edit action"
      error={error}
      submitting={submitting}
      onSubmit={submit}
      onClose={onClose}
    >
      <div>
        <label className={fieldLabel} htmlFor="edit-action-title">Title</label>
        <input
          id="edit-action-title"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          maxLength={80}
          className={fieldInput}
          autoFocus
        />
      </div>
      <div>
        <span className={fieldLabel}>Domain</span>
        <div className="flex gap-2">
          {DOMAINS.map((d) => (
            <button
              key={d.value}
              type="button"
              onClick={() => setDomain(d.value)}
              className={`px-3 py-2 rounded-lg font-mono text-[10px] tracking-wider uppercase border transition-colors ${
                domain === d.value
                  ? "bg-primary text-background border-primary"
                  : "border-[#2b303c] text-secondary hover:text-primary"
              }`}
            >
              {d.label}
            </button>
          ))}
        </div>
      </div>
      {action?.raw_statement && (
        <div>
          <span className={fieldLabel}>Transcript (read-only)</span>
          <p className="p-3 rounded-lg bg-[#0d0e11] border border-[#2b303c] font-sans text-[12px] text-secondary italic">
            &ldquo;{action.raw_statement}&rdquo;
          </p>
        </div>
      )}
    </EditModalFrame>
  );
}
