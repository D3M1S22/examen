# ✏️ Manual Curation — 02: Data Layer

> **Document Status:** Implemented 2026-10-22 (deviations in [05](05_implementation_plan_and_testing.md) §0)
> **Related:** [01_current_state.md](01_current_state.md) §1, §5 · [dynamodb_storage/02](../dynamodb_storage/02_user_store_data_model.md) (item layout, guards, versions)

Every method below is added **abstract** to `AbstractContextStore` ([base.py](../../../src/core/storage/base.py)) and implemented in both `SQLiteContextStore` and `DynamoContextStore`. `tests/test_store_contract.py` keeps the signatures aligned. Shared rules (normalisation, which fields count as anchors) go in [rules.py](../../../src/core/storage/rules.py), so the two backends cannot diverge.

---

## 1. Actions

### `update_action(action_id: str, changes: ActionChanges) -> Optional[VerifiedAction]`
- `ActionChanges` is a new Pydantic model in `schemas.py`:
  - `action_type: Optional[str]`;
  - `domain: Optional[Literal["safety", "routine", "work_task"]]`.
- `action_type` is normalised like the pipeline output (`rules.normalize_action_type`: trim, lower case, whitespace → `_`, 1–80 chars), because the UI renders it with `replace(/_/g, " ")`.
- These fields are **not editable**:
  - `raw_statement`, the transcript evidence;
  - `confidence`;
  - `timestamp`;
  - `matched_task_id`.
- Returns `None` when the id does not exist **or the action is revoked**.
- **SQLite:** one `UPDATE`, plus a refresh of the `fts_actions` row.
- **DynamoDB:** `UpdateItem` on `ACTION#<id>` with `attribute_exists(sk) AND is_revoked = 0`. The `timeline` index key (`timestamp#id`) does not change.
- No automatic re-matching against pending routines. A corrected title does not complete a routine on its own; the user toggles it if needed.

### `revoke_action(action_id: str) -> Optional[RevokeResult]`
1. Read the action and return `None` if it is missing or already revoked.
2. Set `is_revoked = 1`. The item stays as a **tombstone** (D1), so `node_persist` finds it through `get_verified_action` and never recreates it ([01](01_current_state.md) §5a).
3. If `matched_task_id` names a task whose `verified_action_id == action_id` and whose status is `completed`, reopen it:
   - `status = pending`;
   - `completed_at = None`;
   - `verified_action_id = None`.
4. Return `RevokeResult(action, reopened_task_id, session_id)`. The service layer uses `session_id` to unlink the action from its event (§4).

- **SQLite:** steps 2–3 run in one transaction, and the `fts_actions` row is deleted.
- **DynamoDB:** steps 2–3 run in one `TransactWriteItems`:
  - an `Update` of the action, conditioned on `is_revoked = 0`;
  - an `Update` of the task, conditioned on `verified_action_id = :id`.
  - If the task condition fails (another action completed it meanwhile), the action is revoked alone.
- Fulfilled commitments are **not** reopened: `match_and_resolve_task` does not record which action fulfilled a commitment, so the link cannot be traced back.

## 2. Contacts

### `update_social_contact(contact_id: str, changes: ContactChanges) -> Optional[ContactUpdate]`
- `ContactChanges` fields:
  - `person_name`;
  - `company_or_role`;
  - `contact_info`;
  - `website_url`;
  - `key_topics: List[str]`;
  - `location_encountered`.

  An omitted field is left unchanged; an explicit empty string clears it, except `person_name`, which cannot be empty.
- `ContactUpdate = (contact: SocialEntity, anchors_changed: bool, renamed_from: Optional[str])`.
- **Anchors** are `rules.CONTACT_ANCHORS = ("person_name", "company_or_role")`. When either changes (case-insensitive), the old web profile no longer describes the right person:
  - `web_profile_json` is cleared;
  - `website_url` is cleared, unless the same request sets it;
  - `anchors_changed = True` makes the service layer re-run enrichment (D3, [03](03_api_and_mcp.md) §2).
- **Rename** (new `contact_name_key` ≠ old):
  1. **Conflict (D5).** If another contact already owns the new name, raise `UniqueConflict` ([errors.py](../../../src/core/storage/errors.py)).
     - SQLite: `SELECT id … WHERE LOWER(person_name) = LOWER(?) AND id <> ?`.
     - DynamoDB: a `CONTACTNAME#<new>` guard pointing to another id.
  2. **Commitments.** Every commitment of the contact (matched by its old name) gets the new `contact_name`. The legacy `commitments_json` column of the contact is rewritten from the structured rows.
  3. **Guards (DynamoDB).**
     - `CONTACTNAME#<old>` is deleted (conditioned on pointing to this contact).
     - `CONTACTNAME#<new>` is created with `attribute_not_exists(sk) OR contact_id = :id`.
     - Each commitment's `COMMITKEY#<sha(old name, …)>` moves to `COMMITKEY#<sha(new name, …)>`, conditioned the same way. A collision means the renamed contact already has an identical commitment; the duplicate is then deleted, keeping the older one.
  4. **Atomicity.**
     - SQLite: one transaction.
     - DynamoDB: one `TransactWriteItems` per ≤ 100 operations, ordered contact + name guards first, then commitments in batches. Every step is idempotent, so a retry after a partial failure completes the rename (same approach as `assign_chunks`).
- **SQLite:** refresh the `fts_social` row.
- The micro-event headline already stored in a dossier ("Met <old name> (…)") is **not** rewritten. It is a historical label, and the dashboard resolves the contact by id.

### `delete_social_contact(contact_id: str) -> Optional[ContactDeletion]`
Cascade (D2):
1. Delete every commitment of the contact (by name) through `delete_social_commitment`, which already removes the task each commitment auto-scheduled.
2. Delete the contact and, in DynamoDB, its `CONTACTNAME` guard (conditioned on pointing to it).
3. **SQLite:** delete the `fts_social` row.

Returns `ContactDeletion(contact_id, name, session_id, commitments_deleted, tasks_deleted)`. The counts feed the dashboard confirmation (D8) and the MCP preview (D4).

**Preview without writing:** `rules.contact_cascade(store, contact)` lists the commitments and their `auto_scheduled_task_id`s. It is used by both the preview and the delete, so the preview always matches what the delete does.

## 3. Events

### `delete_event(session_id: str) -> Optional[EventDeletion]`
Cascade (D6):
1. Delete the briefings: every briefing returned by `list_briefings_for_session(session_id)`, plus `final_briefing_id`.
2. Delete the chunk log.
   - SQLite: `DELETE FROM session_chunks WHERE session_id = ?`, plus their `utterance_diarization` rows.
   - DynamoDB: the `CHUNK#<session>#…` items, their `CHUNKREF#<chunk_id>` pointers and `DIAR#<chunk_id>`, with `batch_write`.
3. Delete the dossier. The existing `delete_session_dossier` stays for the engine's merge.

Returns `EventDeletion(session_id, title, briefings_deleted, chunks_deleted)`. Linked actions, contacts and tasks are **not** touched: their `session_id` becomes dangling and readers already tolerate a missing session.

The ingest ledger, the coverage records and the backfill runs stay as they are. The utterances count as analysed, so the backfill does not rebuild the event.

### `unlink_micro_event(session_id: str, event_type: str, record_id: str) -> bool`
- Removes one `MicroEventRef` from `linked_micro_events`.
- **DynamoDB:**
  - drops the `link_versions_json` entry;
  - writes through `_write_dossier` with the `version` condition and the usual retry, the same path as `link_micro_event_to_session`;
  - a link absent from `link_versions_json` is never merged back by `save_session_dossier`, so the removal is stable.
- **SQLite:** rewrites `linked_micro_events_json`.
- Returns `False` when the dossier or the link does not exist.

## 4. Event engine ([event_engine.py](../../../src/ingestion/event_engine.py))

The engine keeps the open event in memory (`_current`) and a synthesis queue (`_jobs`). Two new operations run under `self._lock`, like `merge` and `split`.

### `EventEngine.delete(session_id) -> Optional[EventDeletion]`
1. `rehydrate()`, then load the event; return `None` if it does not exist.
2. If it is `_current`:
   - set `_current = None`;
   - clear the pending-split / pause state kept for it;
   - the next qualified chunk opens a new event, as after a conclusion.
3. Drop its queued jobs: filter `_jobs` and `_job_keys` by `session_id`. A job already running finishes and finds no dossier; the runners already return early ([01](01_current_state.md) §5e).
4. `store.delete_event(session_id)`.
5. `_emit("event_deleted", {"session_id": …})`.

Deleting a concluded event whose final synthesis is running is safe: if the synthesizer finishes after step 4, `_run_final_job` loads `None` and returns without saving.

### `EventEngine.unlink_micro_event(session_id, event_type, record_id) -> bool`
- If `_current` is that event, remove the ref from `_current.linked_micro_events` first, then call the store method.
- If `_current` were left untouched, `_merge_persisted_links` would see the ref in memory and write it back ([01](01_current_state.md) §5b, D7).

Engine instances are per tenant (`get_event_engine()`). The live orchestrator and the API share the user's instance, so one call covers both.

## 5. Schemas (`src/core/schemas.py`)

| Model | Purpose |
|---|---|
| `ActionChanges` | editable action fields (validated `domain` literal) |
| `ContactChanges` | editable contact fields (`person_name` min length 1, `website_url` http(s) only, `key_topics` ≤ 20 items) |
| `TaskChanges` | editable routine fields: `title`, `domain`, `scheduled_time` (`HH:MM` or ISO), `recurrence` (`none \| daily \| weekdays \| weekly`) |
| `RevokeResult`, `ContactUpdate`, `ContactDeletion`, `EventDeletion` | results of the operations above (ids and counts only, never transcript text) |

`TaskChanges` also validates the existing `PUT /api/routines/{id}`, which today accepts any string. `status` stays reachable only through the toggle route.
