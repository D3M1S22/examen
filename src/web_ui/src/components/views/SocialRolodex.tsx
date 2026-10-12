import React, { useState } from "react";
import { SocialEntity } from "@/types/schemas";
import { ScreenHeader } from "../ui/ScreenHeader";
import { StatusBadge } from "../ui/StatusBadge";
import { ExecutiveDossierModal } from "../ui/ExecutiveDossierModal";
import { FollowUpModal } from "../ui/FollowUpModal";

interface SocialRolodexProps {
  socialData: { contacts: SocialEntity[] } | undefined;
  statusData?: any;
  onEnrichContact?: (contactId: string) => Promise<void>;
  onToggleCommitment?: (commitmentId: string, action: "fulfill" | "cancel") => Promise<void>;
}

export function SocialRolodex({
  socialData,
  statusData,
  onEnrichContact,
  onToggleCommitment,
}: SocialRolodexProps) {
  const [searchQuery, setSearchQuery] = useState("");
  const [activeFilter, setActiveFilter] = useState<string>("ALL");
  const [selectedDossierContact, setSelectedDossierContact] = useState<SocialEntity | null>(null);
  const [selectedFollowUpContact, setSelectedFollowUpContact] = useState<SocialEntity | null>(null);

  // Deduplicate contacts by normalized person name to prevent duplicate card rendering
  const rawContacts = socialData?.contacts || [];
  const contacts = rawContacts.filter((c, idx, arr) => {
    return idx === arr.findIndex((other) => other.name.trim().toLowerCase() === c.name.trim().toLowerCase());
  });

  const needsActionCount = contacts.filter((c) => c.commitments && c.commitments.length > 0).length;
  const enrichedCount = contacts.filter((c) => !!c.web_profile).length;
  const todayDateStr = new Date().toISOString().split("T")[0];

  const filteredContacts = contacts.filter((c) => {
    let matchesFilter = true;
    if (activeFilter === "NEEDS_ACTION") {
      matchesFilter = !!(c.commitments && c.commitments.length > 0);
    } else if (activeFilter === "ENRICHED") {
      matchesFilter = !!c.web_profile;
    } else if (activeFilter === "TODAY") {
      matchesFilter = !!(c.timestamp && c.timestamp.includes(todayDateStr));
    }

    const searchLower = searchQuery.toLowerCase();
    const matchesSearch =
      !searchQuery ||
      c.name.toLowerCase().includes(searchLower) ||
      (c.company_or_role || "").toLowerCase().includes(searchLower) ||
      (c.contact_info || "").toLowerCase().includes(searchLower) ||
      (c.key_topics || []).some((t) => t.toLowerCase().includes(searchLower)) ||
      (c.commitments || []).some((cmt: any) =>
        (typeof cmt === "object" ? cmt.description : String(cmt))
          .toLowerCase()
          .includes(searchLower)
      );

    return matchesFilter && matchesSearch;
  });

  return (
    <div className="space-y-space-lg animate-in fade-in max-w-[1300px] mx-auto">
      {/* Executive Dossier Modal */}
      <ExecutiveDossierModal
        contact={selectedDossierContact}
        isOpen={!!selectedDossierContact}
        onClose={() => setSelectedDossierContact(null)}
        onEnrich={onEnrichContact}
        onToggleCommitment={onToggleCommitment}
      />

      {/* Follow-Up Composer Modal */}
      <FollowUpModal
        contact={selectedFollowUpContact}
        isOpen={!!selectedFollowUpContact}
        onClose={() => setSelectedFollowUpContact(null)}
      />

      {/* Screen Header */}
      <ScreenHeader
        directive="SCREEN PURPOSE // SUB-SYSTEM DIRECTORY"
        title="PASSIVE CONVERSATIONAL CRM & SOCIAL MEMORY"
        description={
          <>
            The Social Rolodex acts as your ambient networking assistant. During meetings and conferences, the Bee wearable passively extracts interlocutor names, roles, contact channels, and bilateral promises. It grounds mutual commitments and synthesizes executive web dossiers in your local private enclave.
          </>
        }
        rightElement={
          <div className="flex flex-col items-end gap-1">
            <StatusBadge status="verified" label="PII SANITIZED LOCAL ENCLAVE" size="md" />
            <div className="font-mono text-[9px] text-secondary tracking-widest uppercase">
              {statusData?.telemetry?.bee_device?.account ? `EDGE IDENTITY: ${statusData.telemetry.bee_device.account.toUpperCase()}` : "ZERO TELEMETRY EGRESS"}
            </div>
          </div>
        }
      />

      {/* 3 KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-space-md mb-space-lg">
        {/* Card 1 */}
        <div className="card-elevated p-space-lg flex flex-col justify-between bg-[#121419] border border-white/5 rounded-2xl">
          <div className="font-mono text-[9px] text-secondary tracking-[0.2em] uppercase mb-4">
            TOTAL ENCOUNTERS INDEXED
          </div>
          <div className="flex items-center justify-between">
            <div className="font-serif text-[44px] text-primary">{contacts.length}</div>
            <div className="w-12 h-12 rounded-xl bg-surface-container-highest flex items-center justify-center text-primary text-xl">
              👥
            </div>
          </div>
        </div>

        {/* Card 2 */}
        <div className="card-elevated p-space-lg flex flex-col justify-between bg-[#121419] border border-white/5 rounded-2xl">
          <div className="font-mono text-[9px] text-secondary tracking-[0.2em] uppercase mb-4">
            BILATERAL COMMITMENTS DUE
          </div>
          <div className="flex items-center justify-between">
            <div className="flex items-baseline gap-2">
              <span className="font-serif text-[44px] text-primary">{needsActionCount}</span>
              <span className="font-mono text-[9px] text-amber-400 tracking-[0.2em] uppercase">
                ACTION NEEDED
              </span>
            </div>
            <div className="w-12 h-12 rounded-xl bg-surface-container-highest flex items-center justify-center text-amber-400 text-xl">
              🤝
            </div>
          </div>
        </div>

        {/* Card 3 */}
        <div className="card-elevated p-space-lg flex flex-col justify-between bg-[#121419] border border-white/5 rounded-2xl">
          <div className="font-mono text-[9px] text-secondary tracking-[0.2em] uppercase mb-4">
            AI WEB DOSSIERS ENRICHED
          </div>
          <div className="flex items-center justify-between">
            <div className="flex items-baseline gap-2">
              <span className="font-serif text-[44px] text-primary">{enrichedCount}</span>
              <span className="font-mono text-[9px] text-cyan-400 tracking-[0.2em] uppercase">
                INTELLIGENCE
              </span>
            </div>
            <div className="w-12 h-12 rounded-xl bg-surface-container-highest flex items-center justify-center text-cyan-400 text-xl">
              ⚡
            </div>
          </div>
        </div>
      </div>

      {/* Search & Filter Row */}
      <div className="flex flex-col md:flex-row items-stretch md:items-center justify-between gap-4 mb-space-xl border-b border-surface-container-highest pb-6">
        {/* Search Input */}
        <div className="flex-1 max-w-md relative">
          <span className="absolute left-4 top-1/2 -translate-y-1/2 text-secondary text-sm">🔍</span>
          <input
            type="text"
            placeholder="Search contacts, roles, tags, or commitments..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full bg-[#121419] border border-surface-container-highest rounded-full py-2.5 pl-10 pr-10 text-body-sm font-sans text-primary placeholder-zinc-500 focus:outline-none focus:border-primary transition-colors"
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery("")}
              className="absolute right-3.5 top-1/2 -translate-y-1/2 text-zinc-400 hover:text-white font-mono text-xs w-5 h-5 rounded-full flex items-center justify-center bg-white/5 hover:bg-white/10 transition-colors"
              title="Clear search"
            >
              ✕
            </button>
          )}
        </div>

        {/* Filter Buttons */}
        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={() => setActiveFilter("ALL")}
            className={`px-4 py-2 rounded-full font-mono text-[10px] font-bold tracking-widest transition-colors ${
              activeFilter === "ALL"
                ? "bg-primary text-background shadow"
                : "text-secondary hover:bg-surface-container hover:text-primary"
            }`}
          >
            ALL ({contacts.length})
          </button>
          <button
            onClick={() => setActiveFilter("NEEDS_ACTION")}
            className={`px-4 py-2 rounded-full font-mono text-[10px] font-bold tracking-widest transition-colors flex items-center gap-1.5 ${
              activeFilter === "NEEDS_ACTION"
                ? "bg-amber-500 text-black shadow"
                : "text-amber-400/80 bg-amber-950/20 border border-amber-500/20 hover:bg-amber-950/40"
            }`}
          >
            <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse" />
            <span>COMMITMENTS DUE ({needsActionCount})</span>
          </button>
          <button
            onClick={() => setActiveFilter("ENRICHED")}
            className={`px-4 py-2 rounded-full font-mono text-[10px] font-bold tracking-widest transition-colors flex items-center gap-1.5 ${
              activeFilter === "ENRICHED"
                ? "bg-cyan-500 text-black shadow"
                : "text-cyan-400/80 bg-cyan-950/20 border border-cyan-500/20 hover:bg-cyan-950/40"
            }`}
          >
            <span className="w-1.5 h-1.5 rounded-full bg-cyan-400" />
            <span>AI ENRICHED ({enrichedCount})</span>
          </button>
          <button
            onClick={() => setActiveFilter("TODAY")}
            className={`px-4 py-2 rounded-full font-mono text-[10px] font-bold tracking-widest transition-colors flex items-center gap-1.5 ${
              activeFilter === "TODAY"
                ? "bg-emerald-500 text-black shadow"
                : "text-emerald-400/80 bg-emerald-950/20 border border-emerald-500/20 hover:bg-emerald-950/40"
            }`}
          >
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
            <span>NEW TODAY</span>
          </button>
        </div>
      </div>

      {/* Contacts List */}
      {filteredContacts.length === 0 ? (
        <div className="p-12 text-center border border-dashed border-surface-container-highest rounded-2xl bg-[#121419]">
          <div className="text-3xl mb-3">👤</div>
          <div className="font-serif text-xl text-primary mb-2">No Contacts Found</div>
          <p className="font-sans text-secondary text-sm mb-6 max-w-md mx-auto">
            {searchQuery
              ? `No contacts matched "${searchQuery}".`
              : "No contacts ingested in this view yet. Run a social conversation in the simulator to test."}
          </p>
        </div>
      ) : (
        <div className="space-y-space-lg">
          {filteredContacts.map((contact) => {
            const hasCommitments = contact.commitments && contact.commitments.length > 0;
            const isToday = contact.timestamp && contact.timestamp.includes(todayDateStr);

            return (
              <div
                key={contact.id}
                className="card-elevated p-space-xl flex flex-col gap-6 bg-surface-container-lowest border-surface-container-highest rounded-2xl hover:border-amber-500/40 transition-all duration-200"
              >
                {/* Header row */}
                <div className="flex flex-col md:flex-row justify-between items-start gap-4 pb-4 border-b border-white/5">
                  <div className="flex items-start gap-4">
                    <div className="w-14 h-14 rounded-2xl bg-surface-container-highest border border-outline-variant flex items-center justify-center text-primary font-serif text-2xl font-bold shrink-0 shadow-md">
                      {contact.name.substring(0, 2).toUpperCase()}
                    </div>
                    <div>
                      <div className="flex items-center gap-3 mb-1">
                        <h3 className="font-serif text-[24px] text-primary font-normal">
                          {contact.name}
                        </h3>
                        {isToday && (
                          <StatusBadge status="verified" label="NEW ENCOUNTER TODAY" />
                        )}
                        {contact.web_profile && (
                          <span className="px-2 py-0.5 rounded bg-cyan-950/70 border border-cyan-500/30 text-cyan-300 font-mono text-[8px] uppercase tracking-wider">
                            ⚡ AI DOSSIER
                          </span>
                        )}
                      </div>
                      <div className="font-sans text-body-sm text-secondary mb-2">
                        {contact.company_or_role || "Independent Contact"}
                      </div>
                      <div className="flex flex-wrap items-center gap-4 font-mono text-[9px] text-secondary tracking-widest uppercase">
                        {contact.contact_info && (
                          <span className="flex items-center gap-1">
                            <span>✉️</span> {contact.contact_info}
                          </span>
                        )}
                        {contact.location_encountered && (
                          <span className="flex items-center gap-1">
                            <span>📍</span> {contact.location_encountered}
                          </span>
                        )}
                        <span className="flex items-center gap-1">
                          <span>📅</span> {contact.timestamp ? contact.timestamp.split("T")[0] : "Recent"}
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Top Action Buttons */}
                  <div className="flex items-center gap-2 self-end md:self-center shrink-0">
                    <button
                      onClick={() => setSelectedFollowUpContact(contact)}
                      className="px-4 py-2 rounded-lg border border-surface-container-highest bg-transparent hover:bg-surface-container text-secondary hover:text-primary font-mono text-[9px] tracking-[0.2em] flex items-center gap-1.5 transition-colors uppercase font-bold"
                      title="Draft follow-up email/Slack"
                    >
                      <span>✉️</span>
                      <span>DRAFT FOLLOW-UP</span>
                    </button>

                    <button
                      onClick={() => setSelectedDossierContact(contact)}
                      className="px-4 py-2 rounded-lg border border-amber-500/50 bg-amber-500/10 hover:bg-amber-500/20 text-amber-300 font-mono text-[9px] font-bold tracking-[0.2em] flex items-center gap-1.5 transition-colors uppercase"
                      title="Open Executive Dossier"
                    >
                      <span>⚡</span>
                      <span>VIEW DOSSIER</span>
                    </button>
                  </div>
                </div>

                {/* Grid for Topics & Commitments */}
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-space-lg">
                  {/* Left Column: Topics */}
                  <div className="flex flex-col justify-between">
                    <div>
                      <div className="font-mono text-[9px] text-secondary tracking-[0.2em] uppercase mb-3">
                        DISCUSSED TOPICS & KEYWORDS
                      </div>
                      <div className="flex flex-wrap items-center gap-2 mb-4">
                        {contact.key_topics?.length ? (
                          contact.key_topics.map((topic, i) => (
                            <span
                              key={i}
                              className="px-3 py-1.5 rounded-lg bg-[#121419] border border-surface-container-highest font-mono text-[10px] text-amber-200/90 hover:border-amber-400 transition-colors cursor-pointer"
                            >
                              #{topic.replace(/\s+/g, "-")}
                            </span>
                          ))
                        ) : (
                          <span className="text-secondary text-body-sm italic opacity-50">
                            No topics extracted yet.
                          </span>
                        )}
                      </div>
                    </div>

                    {contact.web_profile?.executive_summary && (
                      <div className="bg-[#101217] border border-[#232731] rounded-xl p-3.5 mt-2">
                        <div className="font-mono text-[8px] text-cyan-400 tracking-widest uppercase mb-1 flex items-center gap-1">
                          <span>⚡</span>
                          <span>AI Executive Brief</span>
                        </div>
                        <p className="font-sans text-xs text-secondary leading-relaxed line-clamp-3">
                          {contact.web_profile.executive_summary}
                        </p>
                      </div>
                    )}
                  </div>

                  {/* Right Column: Bilateral Commitments */}
                  <div className="flex flex-col">
                    <div className="font-mono text-[9px] text-secondary tracking-[0.2em] uppercase mb-3">
                      BILATERAL SOCIAL COMMITMENTS
                    </div>

                    {(() => {
                      const rawCommitments = contact.commitments || [];
                      // Deduplicate by ID and description to prevent duplicate commitment cards
                      const uniqueCommitments = rawCommitments.filter((cmt: any, index: number, self: any[]) => {
                        const desc = (typeof cmt === "object" && cmt !== null ? cmt.description : String(cmt)).trim().toLowerCase();
                        const id = typeof cmt === "object" && cmt !== null ? cmt.id : null;
                        return index === self.findIndex((c: any) => {
                          const cDesc = (typeof c === "object" && c !== null ? c.description : String(c)).trim().toLowerCase();
                          const cId = typeof c === "object" && c !== null ? c.id : null;
                          return (id && cId && id === cId) || (cDesc === desc);
                        });
                      });

                      if (uniqueCommitments.length === 0) {
                        return (
                          <div className="bg-[#121419]/50 border border-dashed border-surface-container-highest rounded-xl p-6 text-center text-secondary text-sm font-sans italic opacity-60">
                            No active commitments logged with this contact.
                          </div>
                        );
                      }

                      return (
                        <div className="space-y-3">
                          {uniqueCommitments.map((cmt: any, i: number) => {
                            const isObj = typeof cmt === "object" && cmt !== null;
                            const desc = isObj ? cmt.description : String(cmt);
                            const debtor = isObj ? cmt.debtor : "user";
                            const status = isObj ? cmt.status : "open";
                            const commId = isObj ? cmt.id : null;

                            return (
                              <div
                                key={commId || i}
                                className="bg-[#121419] border border-surface-container-highest rounded-xl p-4 flex flex-col justify-between gap-3"
                              >
                                <div className="flex items-start justify-between gap-2">
                                  <div className="flex items-start gap-2.5">
                                    <span className="text-base mt-0.5">
                                      {debtor === "user" ? "📤" : "📥"}
                                    </span>
                                    <div>
                                      <div className="font-mono text-[8px] text-secondary tracking-widest uppercase mb-1">
                                        {debtor === "user" ? "YOU PROMISED" : `${contact.name.toUpperCase()} PROMISED`}
                                      </div>
                                      <p className="font-sans text-body-sm text-primary leading-snug">
                                        "{desc}"
                                      </p>
                                    </div>
                                  </div>
                                  <StatusBadge status={status} size="sm" />
                                </div>

                                {commId && onToggleCommitment && status === "open" && (
                                  <div className="flex justify-end pt-2 border-t border-white/5">
                                    <button
                                      onClick={() => onToggleCommitment(commId, "fulfill")}
                                      className="px-3 py-1 rounded bg-emerald-950/70 border border-emerald-500/40 text-emerald-300 font-mono text-[9px] tracking-wider uppercase hover:bg-emerald-900 transition-colors"
                                    >
                                      Mark Fulfilled ✓
                                    </button>
                                  </div>
                                )}
                              </div>
                            );
                          })}
                        </div>
                      );
                    })()}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
