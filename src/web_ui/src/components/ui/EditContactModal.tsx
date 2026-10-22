import React, { useEffect, useState } from "react";
import { ContactChanges, SocialEntity } from "@/types/schemas";
import { EditModalFrame, fieldInput, fieldLabel } from "./EditModalFrame";

interface EditContactModalProps {
  contact: SocialEntity | null;
  onClose: () => void;
  onSubmit: (contactId: string, changes: ContactChanges) => Promise<void>;
}

const nameOf = (c: SocialEntity) => c.name || c.person_name || "";

/** Corrects or completes a contact. Changing the name or the company/role re-runs the web search. */
export function EditContactModal({ contact, onClose, onSubmit }: EditContactModalProps) {
  const [name, setName] = useState("");
  const [role, setRole] = useState("");
  const [info, setInfo] = useState("");
  const [website, setWebsite] = useState("");
  const [topics, setTopics] = useState("");
  const [place, setPlace] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!contact) return;
    setName(nameOf(contact));
    setRole(contact.company_or_role || "");
    setInfo(contact.contact_info || "");
    setWebsite(contact.website_url || "");
    setTopics((contact.key_topics || []).join(", "));
    setPlace(contact.location_encountered || "");
    setError(null);
  }, [contact]);

  const submit = async () => {
    if (!contact) return;
    if (!name.trim()) {
      setError("The name cannot be empty.");
      return;
    }
    if (website.trim() && !/^https?:\/\/\S+$/i.test(website.trim())) {
      setError("The website must start with http:// or https://");
      return;
    }
    // Only the fields that changed: an untouched field never clears what the server holds
    const changes: ContactChanges = {};
    if (name.trim() !== nameOf(contact)) changes.person_name = name.trim();
    if (role.trim() !== (contact.company_or_role || "")) changes.company_or_role = role.trim();
    if (info.trim() !== (contact.contact_info || "")) changes.contact_info = info.trim();
    if (website.trim() !== (contact.website_url || "")) changes.website_url = website.trim();
    if (place.trim() !== (contact.location_encountered || "")) changes.location_encountered = place.trim();
    const topicList = topics.split(",").map((t) => t.trim()).filter(Boolean);
    if (topicList.join("|") !== (contact.key_topics || []).join("|")) changes.key_topics = topicList;
    if (Object.keys(changes).length === 0) {
      onClose();
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await onSubmit(contact.id, changes);
      onClose();
    } catch (err: any) {
      setError(err?.message || "Failed to save the contact.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <EditModalFrame
      isOpen={!!contact}
      kicker="SOCIAL ROLODEX // CORRECTION"
      title="Edit contact"
      error={error}
      submitting={submitting}
      onSubmit={submit}
      onClose={onClose}
    >
      <div>
        <label className={fieldLabel} htmlFor="edit-contact-name">Name</label>
        <input id="edit-contact-name" value={name} onChange={(e) => setName(e.target.value)} maxLength={120}
               className={fieldInput} autoFocus />
      </div>
      <div>
        <label className={fieldLabel} htmlFor="edit-contact-role">Company / role</label>
        <input id="edit-contact-role" value={role} onChange={(e) => setRole(e.target.value)} maxLength={200}
               placeholder="e.g. Staff engineer at Acme" className={fieldInput} />
        <p className="mt-1 font-sans text-[11px] text-secondary">Changing the name or the company/role runs the web search again.</p>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div>
          <label className={fieldLabel} htmlFor="edit-contact-info">Contact info</label>
          <input id="edit-contact-info" value={info} onChange={(e) => setInfo(e.target.value)} maxLength={500}
                 placeholder="email, phone, handle" className={fieldInput} />
        </div>
        <div>
          <label className={fieldLabel} htmlFor="edit-contact-website">Website</label>
          <input id="edit-contact-website" value={website} onChange={(e) => setWebsite(e.target.value)} maxLength={500}
                 placeholder="https://" className={fieldInput} />
        </div>
      </div>
      <div>
        <label className={fieldLabel} htmlFor="edit-contact-topics">Key topics (comma separated)</label>
        <input id="edit-contact-topics" value={topics} onChange={(e) => setTopics(e.target.value)} className={fieldInput} />
      </div>
      <div>
        <label className={fieldLabel} htmlFor="edit-contact-place">Where we met</label>
        <input id="edit-contact-place" value={place} onChange={(e) => setPlace(e.target.value)} maxLength={200}
               className={fieldInput} />
      </div>
    </EditModalFrame>
  );
}
