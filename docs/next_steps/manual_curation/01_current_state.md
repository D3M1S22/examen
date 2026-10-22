# ✏️ Manual Curation — 01: Current State

> **Document Status:** Planned (code survey of branch `aws`, 2026-10-22)
> **Related:** [00_overview.md](00_overview.md)

---

## 1. Store (`AbstractContextStore`, both backends)

| Entity | Methods today | Missing |
|---|---|---|
| `PlannedTask` | `save_planned_task`, `update_planned_task` (full overwrite of the editable fields), `delete_planned_task` | none |
| `VerifiedAction` | `save_action` (runs task matching), `get_verified_action` (returns revoked rows too), `get_action_status` / `list_recent_actions` (skip `is_revoked = 1`) | update, revoke |
| `SocialEntity` | `save_social_contact` (upsert; an unnamed id is resolved by name), `update_contact_web_profile`, `search_social_contact` | update with rename, delete |
| `SocialCommitment` | `save_social_commitment` (dedup key = contact name + description + debtor), `update_social_commitment_status`, `delete_social_commitment` (also deletes its auto-scheduled task) | none |
| `SessionDossier` | `save_session_dossier`, `delete_session_dossier` (dossier row/item **only**), `link_micro_event_to_session` | cascade delete, unlink |
| `BriefingReport` | `delete_topic_briefing`, `list_briefings_for_session` | none |

References: [sqlite_store.py](../../../src/core/storage/sqlite_store.py) (`update_planned_task` :521, `delete_planned_task` :553, `save_action` :612, `save_social_contact` :717, `delete_social_commitment` :1003, `delete_session_dossier` :1327), [dynamo_store.py](../../../src/core/storage/dynamo_store.py) (same methods at :217, :229, :271, :349, :559, :838).

Backend notes that shape the new methods:
- **SQLite** keeps FTS5 mirrors: `fts_actions`, `fts_social` and `fts_briefings`. Every update and delete must keep them in step, as `delete_topic_briefing` already does.
- **DynamoDB** keeps uniqueness guard items: `CONTACTNAME#<name>` → contact id, and `COMMITKEY#<sha(contact, description, debtor)>` → commitment id. The per-chunk log is `CHUNK#<session>#…` with `CHUNKREF#<chunk_id>` pointers. Dossiers are written with optimistic concurrency (`version`, `link_versions_json`).

## 2. REST API (`src/serving/mcp_server.py`)

| Route | Today |
|---|---|
| `GET /api/actions` | list (no write route) |
| `GET/POST /api/routines`, `PUT/DELETE /api/routines/{id}`, `POST …/toggle` | full CRUD, but `PUT` accepts any `domain` / `status` string and is not used by the UI |
| `GET /api/contacts`, `GET …/{id}/profile`, `POST …/{id}/enrich` | read and manual re-enrichment (`enrich_social_contact_sync(force=True)`) |
| `GET/POST /api/commitments`, `…/fulfill`, `…/cancel`, `GET/DELETE /api/commitments/{id}` | full lifecycle |
| `/api/sessions/…` pause, resume, conclude, split, merge | event engine operations; **no delete** |

Every write broadcasts an SSE event (`routine_deleted`, `contact_enriched`, `event_merged`, …) that the dashboard turns into SWR revalidations and toasts.

## 3. MCP tools

Twelve tools are registered at [mcp_server.py:160-171](../../../src/serving/mcp_server.py#L160-L171) as `mcp.tool()(tenant_tool(fn))`. Each follows the `execute_*` (store injectable) + documented wrapper pattern of [action_tools.py](../../../src/serving/tools/action_tools.py). All are reads except `create_planned_task`.

Ids exposed by the read tools, which the new write tools will need:

| Tool | Exposes |
|---|---|
| `get_daily_actions_recap` | action and task `id` |
| `get_upcoming_tasks` | task `id` |
| `query_social_contact`, `get_contact_profile` | contact `id` |
| `list_session_dossiers`, `get_session_dossier` | `session_id` |
| `verify_action_status` | **no id** (to add) |

The installed SDK (`mcp<2`) supports `FastMCP.tool(annotations=ToolAnnotations(...))`, so `destructiveHint` / `idempotentHint` are available.

## 4. Dashboard

| View | Card today | Write controls |
|---|---|---|
| [PeaceOfMind.tsx](../../../src/web_ui/src/components/views/PeaceOfMind.tsx) | title (`action_type`), "Captured Spoken Utterance" block (:321-328), fake "SPECTRAL ENVELOPE" waveform (:330-351), "ACOUSTIC DETENT + VOCAL PROOF" label (:314), "PLAY CITATION" (fake tone), "ECHO REASSURANCE" (speech synthesis) | none |
| [DailyRoutines.tsx](../../../src/web_ui/src/components/views/DailyRoutines.tsx) | title, invented "Passive acoustic verification…" paragraph (:396-400), "ACOUSTIC ANCHOR REGISTERED / SENSING ARMED" box with fake waveform (:402-453), "Test Chime" (fake tone) | toggle; delete **without confirmation** (:466-475) |
| [SocialRolodex.tsx](../../../src/web_ui/src/components/views/SocialRolodex.tsx) + [ExecutiveDossierModal.tsx](../../../src/web_ui/src/components/ui/ExecutiveDossierModal.tsx) | contact card, dossier modal with web profile | re-run enrichment (:464), commitment fulfil/cancel |
| [TopicDossiers.tsx](../../../src/web_ui/src/components/views/TopicDossiers.tsx) + [EventCard.tsx](../../../src/web_ui/src/components/ui/EventCard.tsx) | events and briefings | `EventAction = "pause" \| "resume" \| "conclude" \| "split" \| "merge"` (:16) |

Wiring lives in [page.tsx](../../../src/web_ui/src/app/page.tsx): SWR keys per view, `handleDeleteRoutine`, `handleEventAction` (:526), and the SSE switch that revalidates.

The TS `PlannedTask` ([schemas.ts](../../../src/web_ui/src/types/schemas.ts)) lacks `origin`, `raw_statement` and `session_id`, although `GET /api/routines` already returns them.

## 5. Pitfalls the design must handle

**a. Re-analysis recreates deleted results.**
- `node_persist` derives entity ids from `source_key` and skips a write when the id already exists ([persist.py](../../../src/pipeline/nodes/persist.py) :64 for actions, :141 for tasks).
- A chunk is re-analysed when the backfill retries a `failed` live chunk, which happens on an AgentCore outcome-unknown (doc 17 §5.4).
- A hard-deleted action would come back on that retry; a tombstone (D1) is found by `get_verified_action` and blocks it.
- Contacts and routines are hard-deleted: the same retry could recreate them. This edge is accepted, because a retry only concerns chunks that failed.

**b. The engine re-adds links removed in the store.**
- `EventEngine._save` calls `_merge_persisted_links` ([event_engine.py:1451](../../../src/ingestion/event_engine.py#L1451)), which only *adds* persisted links missing from memory.
- The open event lives in memory (`_current`) with its own `linked_micro_events`. A link removed only in the store is written back on the next engine save.
- Unlinking must therefore update `_current` too (D7).

**c. Commitments reference contacts by name.**
- `SocialCommitment.contact_name` is a string. `list_social_commitments(contact_name=…)` matches it case-insensitively.
- The commitment dedup key includes it (`rules.commitment_key`, DynamoDB guard `COMMITKEY#…`).
- A rename that does not rewrite the commitments detaches them from the contact.

**d. The contact name guard.**
- DynamoDB resolves a contact by name through `CONTACTNAME#<lower(name)>`; `save_social_contact` already moves it when the name changes.
- SQLite matches `LOWER(person_name)`.
- Both must reject a rename onto another contact's name (D5), otherwise later extractions of that name would land on an arbitrary contact.

**e. Pending synthesis jobs.**
- The engine queues segment and final jobs by `session_id` (`_jobs`, `_job_keys`).
- Both job runners return early when the dossier is gone (`if ev is None … return`), so a deleted event does not crash them.
- They should still be dropped from the queue, so that `pending_jobs` in `/api/event-engine/status` stays truthful.
