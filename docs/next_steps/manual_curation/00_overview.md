# ✏️ Manual Curation — Overview

> **Document Status:** Planned (decisions D1–D4 confirmed 2026-10-22, D5–D8 proposed by design)
> **Related:** [deep_topic_event_engine/](../deep_topic_event_engine/00_overview.md) (events, merge/split), [06_social_web_enrichment.md](../06_social_web_enrichment.md) (web profiler), [historical_backfill/](../historical_backfill/00_overview.md) (re-analysis of chunks), [dynamodb_storage/](../dynamodb_storage/00_overview.md) (second store backend)
> **Audience:** EXAMEN engineers implementing edit and delete of extracted results, in the dashboard and over MCP

---

## 1. Why this exists

EXAMEN extracts actions, routines, contacts and topic events from Bee transcripts. Extraction is not always right, and today the user can fix almost nothing:

| Result | Edit | Delete |
|---|---|---|
| Action (Peace of Mind) | ✗ | ✗ |
| Routine (Daily Routines) | ✗ in the UI (`PUT /api/routines/{id}` exists, unused) | ✓ UI, ✗ MCP |
| Contact (Social Rolodex) | ✗ | ✗ |
| Topic event (Topic Dossiers) | merge / split ✓ | ✗ (store method only) |

Two consequences matter most.

1. **Noise stays forever.** An action extracted from chatter that is not of interest cannot be removed, so it skews the recap, the confidence average and what Alexa+ answers.
2. **Wrong anchors break enrichment.** The web profiler searches with the contact's name and role ([06](../06_social_web_enrichment.md), `verify_disambiguation_anchors`). In a recent test, a name extracted with one wrong letter made the search return nothing useful. The user must be able to correct the name, add context (company, role, website), and have the search run again.

Two UI issues ship with the same work.

3. **Acoustic placeholders.** Daily Routines shows an "ACOUSTIC ANCHOR REGISTERED / ACOUSTIC SENSING ARMED" box with a fake waveform and invented text ("Passive acoustic verification…"). Peace of Mind has the same graphic as "SPECTRAL ENVELOPE". EXAMEN receives **transcripts** from the Bee, never audio, so these graphics misrepresent the product.
4. **Routines lack context.** A Peace of Mind card shows the spoken sentence the action came from. A routine card does not, so two routines with similar titles cannot be told apart. The data exists: `PlannedTask.raw_statement` (tasks born from speech or from a commitment) and `verified_action_id` (the action that completed the task).

---

## 2. Scope

**In scope**
- Edit and delete of actions, routines and contacts: dashboard **and** MCP.
- Delete of topic events (dossiers): dashboard and MCP. Editing stays merge and split.
- Transcript excerpt on routine cards ("Origin" and "Completed by").
- Removal of the acoustic placeholder graphics on both screens.

**Out of scope**
- Editing an event's content (title, segments, briefings): merge and split cover the real need.
- Merging two contacts (a rename that collides with another contact is refused, D5).
- Editing the transcript text itself (`raw_statement` is the evidence and stays read-only).

---

## 3. Decisions

| # | Decision | Status |
|---|---|---|
| **D1** | Deleting an action is a **tombstone**: `is_revoked = 1` (field already in `VerifiedAction`, already filtered by `list_recent_actions` and `get_action_status`). A routine the action had completed goes back to `pending`. The tombstone stops a backfill retry of the same chunk from recreating it ([01](01_current_state.md) §5a). | Confirmed |
| **D2** | Deleting a contact **cascades**: the contact, its commitments, and the tasks scheduled from those commitments. | Confirmed |
| **D3** | When a contact's anchors change (name, company or role), the old web profile is dropped and enrichment **re-runs automatically** in the background; the result arrives over SSE. | Confirmed |
| **D4** | Destructive MCP tools take **exact ids only** and use a **two-step confirmation**: without `confirm=true` they return a preview of what would be deleted; with it they delete. They carry `destructiveHint`. | Confirmed |
| **D5** | Renaming a contact to the name of another existing contact is refused with **409** (`UniqueConflict`). No silent merge. | Proposed |
| **D6** | Deleting an event removes its dossier, its chunk log and its briefings. The actions, contacts and tasks linked to it **stay**: they are results in their own right. | Proposed |
| **D7** | Any change to an event's micro-event links goes through the **event engine** (`unlink_micro_event`), never only through the store: the engine's in-memory copy would otherwise add the link back ([01](01_current_state.md) §5b). | Proposed |
| **D8** | Every delete in the dashboard asks for confirmation and shows the cascade ("also deletes 2 commitments and 1 routine"). The routine delete, which today has no confirmation, is aligned. | Proposed |

---

## 4. Target flow

```
 Dashboard (PUT/DELETE /api/…) ─┐
                                ├─► curation_tools.execute_*  ──► AbstractContextStore (SQLite | DynamoDB)
 MCP tools (update_*/delete_*) ─┘        │  validation, cascade       update_action · revoke_action
                                         │  preview (MCP, no confirm) update/delete_social_contact
                                         │                            delete_event · unlink_micro_event
                                         ├─► EventEngine.delete / unlink_micro_event (current event, job queue)
                                         ├─► enrich_social_contact_sync (background, D3)
                                         └─► broadcast_event(action_updated | contact_deleted | event_deleted …)
                                                         │
 Dashboard SSE handler ◄─────────────────────────────────┘  mutate SWR caches, toast
```

One service module (`src/serving/tools/curation_tools.py`) owns the cascade, the engine calls and the broadcasts. REST routes and MCP tools are thin wrappers around it, so the two surfaces cannot drift apart.

---

## 5. Documents

| Doc | Content |
|---|---|
| [01_current_state.md](01_current_state.md) | What exists today in store, API, MCP and UI, and the five pitfalls the design must handle |
| [02_data_layer.md](02_data_layer.md) | New store methods (both backends) and event engine operations |
| [03_api_and_mcp.md](03_api_and_mcp.md) | `curation_tools`, REST routes, SSE events, MCP tools and the confirmation protocol |
| [04_ui.md](04_ui.md) | Edit and delete in each view, transcript excerpts, removal of the acoustic placeholders |
| [05_implementation_plan_and_testing.md](05_implementation_plan_and_testing.md) | Phases, test plan, manual smoke |
