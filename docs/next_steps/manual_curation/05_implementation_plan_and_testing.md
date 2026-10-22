# 05 — Implementation Plan, Tests & Acceptance Criteria

> Part of the [Manual Curation](00_overview.md) specification.

---

## 0. Status (2026-10-22, branch `final_fix`)

| Phase | Status | Code |
|---|---|---|
| A Store + engine | ✅ | `ActionChanges` / `TaskChanges` / `ContactChanges` and result models in [schemas.py](../../../src/core/schemas.py), `normalize_action_type` / `CONTACT_ANCHORS` / `contact_cascade` in [rules.py](../../../src/core/storage/rules.py), six abstract methods in [base.py](../../../src/core/storage/base.py), implemented in [sqlite_store.py](../../../src/core/storage/sqlite_store.py) and [dynamo_store.py](../../../src/core/storage/dynamo_store.py), `EventEngine.delete` / `unlink_micro_event` in [event_engine.py](../../../src/ingestion/event_engine.py) |
| B Service layer, REST, SSE | ✅ | [curation_tools.py](../../../src/serving/tools/curation_tools.py); routes and `set_notifier(broadcast_event)` in [mcp_server.py](../../../src/serving/mcp_server.py) |
| C MCP tools | ✅ | seven tools with `ToolAnnotations`; `verify_action_status` returns `action_id` |
| D Dashboard | ✅ | `ConfirmDialog`, `TranscriptExcerpt`, `CardActions`, `EditModalFrame`, `EditActionModal`, `EditContactModal`, [curation.ts](../../../src/web_ui/src/utils/curation.ts); views and [page.tsx](../../../src/web_ui/src/app/page.tsx) |
| E Docs & rollout | ✅ docs; rollout with the normal update | this section, ROADMAP Phase 10, AGENTS.MD |

Tests:
- [test_curation_store.py](../../../tests/test_curation_store.py) and [test_curation_api.py](../../../tests/test_curation_api.py), on both backends;
- curation cases in `test_event_engine.py` and `test_dynamo_store.py`;
- `curation.test.ts` (bun).

Verified on a local server (`MOCK_AI=true`), over HTTP, SSE and a real MCP client (streamable HTTP):
- a routine completed by a simulated sentence shows "Completed by"; deleting the action reopens it;
- a contact rename moves its commitment, re-runs the enrichment in the background and broadcasts `contact_updated` then `contact_enriched`;
- deleting the contact removes the routine its commitment scheduled;
- `delete_action` previews without `confirm`, deletes with it, and returns `not_found` the second time.

**Deviations from 02–04**
1. `event_deleted` is broadcast by `curation_tools`, not by the engine: the engine's SSE listener is only wired once the dashboard starts the runtime, and an MCP call may come first.
2. `TaskChanges` keeps `status` (validated literal), so the existing `PUT /api/routines/{id}` clients keep working; the dashboard uses the toggle route for status.
3. A rename that collides with an identical commitment already filed under the new name drops the **moving** duplicate (DynamoDB guard collision), not the older one.
4. `delete_social_contact` skips the commitment cascade when another contact still has the same name (commitments are keyed by name).
5. The background enrichment runs in a daemon thread inside `tenant_scope` (works the same from REST and from MCP tool calls). A stale run is detected by a store proxy (`_AnchorGuard`) that drops the profile write when the anchors changed meanwhile.
6. The contact editor is a separate `EditContactModal`, opened from the dossier modal and from the card, rather than an inline mode of `ExecutiveDossierModal`.
7. [04](04_ui.md) §7 is implemented:
   - "Test Chime", "PLAY CITATION" and `AcousticSignatureBox` are removed;
   - the acoustic header texts of both screens are reworded around transcripts.
8. `CreateTaskModal` offered a "Continuous Mesh" recurrence that the server rejects (`PlannedTask.recurrence`); it is replaced by "One-off" (`none`).

---

## 1. Phases

Each phase leaves the suite green on **both** backends:
- `.venv/bin/python -m pytest -q`;
- `EXAMEN_TEST_STORAGE=dynamo .venv/bin/python -m pytest -q`.

### A. Store and engine ([02](02_data_layer.md))
1. Schemas: `ActionChanges`, `TaskChanges`, `ContactChanges` and the result models.
2. `rules.py`: `normalize_action_type`, `CONTACT_ANCHORS`, `contact_cascade`.
3. Abstract methods in `base.py`:
   - `update_action`;
   - `revoke_action`;
   - `update_social_contact`;
   - `delete_social_contact`;
   - `delete_event`;
   - `unlink_micro_event`.
4. SQLite implementation, FTS mirrors included.
5. DynamoDB implementation: guards, transactions, chunk-log cascade.
6. `EventEngine.delete` and `EventEngine.unlink_micro_event`.

### B. Service layer, REST, SSE ([03](03_api_and_mcp.md) §1–4)
1. `curation_tools.py` with the `execute_*` functions, `set_notifier`, preview and confirm, and the background re-enrichment with the anchor check.
2. Routes:
   - `PUT/DELETE /api/actions/{id}`;
   - `PUT/DELETE /api/contacts/{id}`;
   - `GET /api/contacts/{id}/cascade`;
   - `DELETE /api/sessions/{id}`;
   - validation of the existing `PUT /api/routines/{id}`.
3. Read fields: `completion_statement` on routines, `session_id` on contacts.

### C. MCP tools ([03](03_api_and_mcp.md) §5)
1. The seven tools with their annotations, registered under `tenant_tool`.
2. `verify_action_status` returns `action_id`.

### D. Dashboard ([04](04_ui.md))
1. Shared pieces: `ConfirmDialog`, `TranscriptExcerpt`, `CardActions`, `utils/curation.ts`.
2. Peace of Mind: placeholders out, edit and delete in.
3. Daily Routines: placeholders out, excerpts, edit mode of `CreateTaskModal`, confirmed delete.
4. Social Rolodex: edit form, re-search state, cascade delete.
5. Topic Dossiers: `delete` event action.
6. `page.tsx`: handlers and SSE cases.
7. The open point of [04](04_ui.md) §7, once confirmed.

### E. Docs & rollout
1. Fill in §0 of this document with the code links and any deviations.
2. ROADMAP Phase 10: mark the milestones done.
3. AGENTS.MD rule: curation goes through `curation_tools`.
4. Release through the normal update path (homelab `update.sh`, AWS `aws_deploy.py update`); no data migration is needed.

---

## 2. Tests

The tests follow the existing patterns:
- stores from `new_store(path)` ([tests/store_backend.py](../../../tests/store_backend.py)), so every store test runs on SQLite and on DynamoDB (moto);
- API tests in the style of `test_mcp_server.py` / `test_event_serving.py`.

| ID | Test | File |
|---|---|---|
| T-MC-1 | `update_action` normalises the title, refuses `domain` outside the literal, returns `None` for a revoked action | `tests/test_curation_store.py` (new) |
| T-MC-2 | `revoke_action` hides the action from `list_recent_actions` / `get_action_status` and reopens the routine it completed; another routine completed by a different action is untouched | same |
| T-MC-3 | **Tombstone**: after `revoke_action`, `node_persist` with the same `source_key` does not recreate the action | same |
| T-MC-4 | Rename moves the commitments (`list_social_commitments(contact_name=new)`), the contact is found by the new name and not by the old one, and the web profile is cleared only when an anchor changed | same |
| T-MC-5 | Rename onto another contact's name raises `UniqueConflict`, and nothing changes | same |
| T-MC-6 | DynamoDB: after a rename, the `CONTACTNAME` and `COMMITKEY` guards point to the new keys and the old ones are gone. Saving the same commitment again does not duplicate it | `tests/test_dynamo_store.py` |
| T-MC-7 | `delete_social_contact` deletes the contact, its commitments and their auto-scheduled tasks; a manual routine with a similar title survives | `tests/test_curation_store.py` |
| T-MC-8 | `delete_event` removes the dossier, chunks (+ `CHUNKREF`, `DIAR`) and briefings; the linked action and contact remain | same |
| T-MC-9 | `unlink_micro_event`, then an engine save of the current event: the link stays removed (D7) | `tests/test_event_engine.py` |
| T-MC-10 | `EventEngine.delete` of the current event: `_current` is `None` and the next chunk opens a new event. Delete with queued jobs: they are dropped and `run_pending_jobs_sync` does not recreate the dossier | same |
| T-MC-11 | REST: 200 / 400 / 404 / 409 per route; the SSE events of [03](03_api_and_mcp.md) §4 are broadcast to the caller's tenant only | `tests/test_curation_api.py` (new) |
| T-MC-12 | `GET /api/routines` returns `completion_statement`, and returns none when the completing action is revoked | same |
| T-MC-13 | Re-enrichment: a rename schedules it, and a stale run (anchors changed again meanwhile) does not write its profile. The enrichment is stubbed | same |
| T-MC-14 | MCP: a delete without `confirm` writes nothing and returns `would_delete`; with `confirm` it deletes; a second call returns `not_found`; the tools carry `destructiveHint` / `idempotentHint` | `tests/test_mcp_server.py` |
| T-MC-15 | MCP tenancy: `delete_contact` with another user's id returns `not_found` (the tenant store cannot see it) | `tests/test_accounts.py` |
| T-MC-16 | No user content in logs: the curation paths log ids only (the existing grep of `test_admin_console.py` is extended to the new module) | `tests/test_admin_console.py` |
| T-MC-17 | UI helpers: `formatCascade`, `normalizeActionTitle`, `excerptLabels` | `src/web_ui/src/utils/curation.test.ts` (bun) |

## 3. Manual smoke (dashboard + a real MCP client)

1. **Action.** Simulate "I turned off the stove". Check that the routine "check stove" completes. Edit the action's title, then delete it: the routine goes back to pending, and the card disappears without a reload.
2. **Routines.**
   - A routine created by voice shows "Heard: …".
   - After completion it also shows "Completed by: …".
   - A manual routine shows "Created manually".
   - No acoustic graphics remain on either screen.
3. **Contact.**
   - Correct a one-letter typo in a name and add the company.
   - "Re-searching the web…" appears, then the new profile.
   - Renaming to an existing contact's name shows the 409 message.
   - Delete the contact: the confirmation lists its commitments, and they disappear from the commitments list and from Daily Routines.
4. **Event.**
   - Delete a concluded event: its briefings disappear from Topic Dossiers, while its actions and contacts remain.
   - Delete the live event: a new one opens with the next chunk.
5. **MCP** (`scripts/test_mcp_client.py` or Claude with an access token):
   - `delete_action` without `confirm` returns a preview, and the dashboard is unchanged;
   - with `confirm`, the dashboard updates live through SSE;
   - `update_contact` reports that the web search was re-run.

## 4. Acceptance criteria

- Every result type in [00](00_overview.md) §1 can be edited (routines, actions, contacts) or deleted (all four) from the dashboard **and** over MCP.
- No path recreates a deleted action. A deleted contact or routine can only come back through a backfill retry of a failed chunk ([01](01_current_state.md) §5a, accepted).
- A corrected contact name triggers a new web search without further clicks.
- Both test suites stay green; the new tests run on both backends.
- No "acoustic" placeholder remains in Peace of Mind or Daily Routines (plus §7 of [04](04_ui.md) once confirmed).
