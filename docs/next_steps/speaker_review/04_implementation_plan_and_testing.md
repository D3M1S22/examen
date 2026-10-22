# 04 — Implementation Plan, Tests & Acceptance Criteria

> Part of the [Speaker Review](00_overview.md) specification.

---

## 0. Status (2026-10-23, branch `final_fix`)

| Phase | Status | Code |
|---|---|---|
| A Schema, store, review rule | ✅ | `PlannedTask.status` review / dismissed, `VerifiedAction.needs_review`, source `user_confirmed` in [schemas.py](../../../src/core/schemas.py); `list_review_actions` / `accept_action` and review-aware listings in both stores; `needs_review()` in [persist.py](../../../src/pipeline/nodes/persist.py) |
| B Late tags, setting, counters | ✅ | `reconcile_speaker` through `curation_tools` ([orchestrator.py](../../../src/ingestion/orchestrator.py)); [speaker_prefs.py](../../../src/core/speaker_prefs.py), `users.auto_accept_untagged`, runtime setting `SPEAKER_AUTO_ACCEPT_UNTAGGED`, payload field; scheduler prompt line; counters in `/api/status`, the Alexa recap and OverviewHub |
| C Service layer, REST, SSE, MCP | ✅ | review functions in [curation_tools.py](../../../src/serving/tools/curation_tools.py); `/api/review` routes; `list_items_to_review`, `accept_item`, `dismiss_item` |
| D Dashboard | ✅ | [ReviewTray.tsx](../../../src/web_ui/src/components/ui/ReviewTray.tsx) in Peace of Mind and Daily Routines; "Speaker recognition" block in Account; "Confirmed by you" badge |
| E Docs & rollout | ✅ | this section, doc 08 §5, ROADMAP Phase 12 |

**Tests:**
- [test_speaker_review.py](../../../tests/test_speaker_review.py) (23), on both backends;
- `test_untagged_history_waits_for_confirmation` in `test_backfill.py`;
- the late-tag test of `test_speaker_identity.py` now expects `dismissed`.

The three backfill tests about temporal guards opt in to auto-accept: their fixture history is untagged.

**Mutation checks:**
- disabling the rule fails 9 tests;
- letting a review action match routines fails 1.

**Smoke, local server (`MOCK_AI=true`, HTTP):**
- an untagged action and task wait in `/api/review` and the routine stays pending (`/api/status` reports 1 + 1 to confirm);
- accepting the action completes the routine and marks it "user_confirmed";
- the dismissed task disappears;
- the owner's own action skips review.

**Deviations from 02–03**
1. **The preference is read when each payload is built** (one account lookup), not cached; no orchestrator hook is needed when it changes.
2. **No `review_added` SSE:** the live orchestrator emits no SSE after a dispatch, so the dashboard polls `/api/review` every 15 s and refreshes on `review_resolved`.
3. **Simulator:** `/api/simulate` with an explicit `speaker_role: "unknown"` simulates untagged speech, so it goes to review (handy for demos). The dashboard never sends a role, so its entries never do (R7).
4. **"Accept all" in a tray** accepts that tray's items. `POST /api/review/accept-all` (both kinds) is offered when the setting is turned on.
5. **Deleting a routine in review discards it** (tombstone) instead of deleting it.
6. **Status changes on a routine in review:** `PUT /api/routines/{id}` with a status answers 409 for a routine in review; review states are not accepted in `TaskChanges` (400).
7. **T-SR-12 (bun helpers) not added:** the tray holds no pure logic beyond the existing curation helpers.

---

## 1. Phases

Each phase keeps both suites green:
- `.venv/bin/python -m pytest -q`;
- `EXAMEN_TEST_STORAGE=dynamo .venv/bin/python -m pytest -q`.

### A. Schema, store, review rule ([02](02_data_and_pipeline.md) §1–3)
1. Schema changes: statuses, `needs_review`, `user_confirmed`, `auto_accept_untagged` in state.
2. Store, both backends:
   - `save_action` skips matching in review;
   - list filters;
   - `list_review_actions`;
   - `accept_action`;
   - default task listing hides `dismissed`.
3. `needs_review()` in `persist`; review actions and tasks saved accordingly.

### B. Late tags, setting, counters ([02](02_data_and_pipeline.md) §4–8)
1. `reconcile_speaker` routed through the curation functions (accept / dismiss / unlink / notify). Contact tags dismiss instead of cancelling.
2. User preference:
   - auth store column / attribute;
   - runtime setting for single-user mode;
   - payload field from orchestrator and backfill;
   - copied into the state in `pipeline/app.py`;
   - orchestrator hook on change.
3. Scheduler prompt line for the owner addressing someone else.
4. Counters: `/api/status`, Alexa recap, OverviewHub.

### C. Service layer, REST, SSE, MCP ([03](03_api_mcp_ui.md) §1–3)

### D. Dashboard ([03](03_api_mcp_ui.md) §4)

### E. Docs & rollout
- [08_speaker_identity.md](../08_speaker_identity.md) §5: "untagged speech is still the user's" becomes "untagged speech waits for confirmation unless the user opts in".
- ROADMAP entry.
- §0 of this document.
- No data migration:
  - existing untagged results stay active;
  - only new ones go to review;
  - existing late-tag `cancelled` tasks stay as they are.

---

## 2. Tests

Store tests use `new_store(path)` so they run on both backends.

| ID | Test | File |
|---|---|---|
| T-SR-1 | `needs_review()` truth table: owner / contact / untagged / addressed / no speaker / internal × setting on/off | `tests/test_speaker_review.py` (new) |
| T-SR-2 | `node_persist` with an untagged action: stored with `needs_review`, absent from `list_recent_actions` and `get_action_status`, and the matching routine stays `pending` | same |
| T-SR-3 | Untagged task → `status == "review"`, not returned by `get_upcoming_tasks`. With the setting on → `pending` with "Voice not verified" | same |
| T-SR-4 | Request naming the owner from an untagged speaker → `pending`, "asked by" (R2), with and without a model (pattern fallback) | same |
| T-SR-5 | `accept_action` → visible, speaker `user_confirmed`, and it completes the matching routine it skipped. Historical guard honoured for a backfill action | `tests/test_curation_store.py` |
| T-SR-6 | Dismiss: an action → tombstone, a task → `dismissed`, hidden from listings. A re-run of `node_persist` with the same `source_key` does not recreate either (R4) | same |
| T-SR-7 | Late tags: user tag accepts a review action and task; a contact tag dismisses them, except a request to the owner. A contact tag on an active task → `dismissed` (not `cancelled`). Discards unlink the micro-event and broadcast SSE | `tests/test_speaker_identity.py` |
| T-SR-8 | REST: list / accept / dismiss / accept-all; 404 unknown id; 409 already resolved; `PUT /api/routines` refuses review states | `tests/test_curation_api.py` |
| T-SR-9 | MCP: `list_items_to_review`, `accept_item`, `dismiss_item`, and their annotations; `get_daily_actions_recap` mentions the count | same |
| T-SR-10 | Setting: `PATCH /api/account` stores it (SQLite and DynamoDB auth stores); the next orchestrator payload carries it; single-user mode reads the runtime setting; the payload reaches `ExamenState` in `agent_invocation` | `tests/test_accounts.py`, `tests/test_pipeline_remote.py` |
| T-SR-11 | Counters: `/api/status` pending excludes review / dismissed / cancelled and reports the review counts | `tests/test_mcp_server.py` |
| T-SR-12 | UI helpers (review grouping, counters) | `src/web_ui/src/utils/review.test.ts` (bun) |

## 3. Manual and device checks

1. **Simulator.** `/api/simulate` entries never go to review (R7).
2. **Live, wearer alone** (`scripts/bee_spike.py capture`):
   - tagged sentences are active with "Your voice";
   - untagged ones appear in "To confirm";
   - ✔ makes them active, ✕ removes them.
3. **Live, second person not saved in the Bee app.** Their "I need to push tonight" lands in "To confirm", not in the routines.
4. **Live, second person saved in the Bee app.**
   - Their own plans are dropped.
   - "Damiano, push tonight" becomes an active task "asked by <name>".
5. **Setting on.** Untagged sentences are active at once with "Voice not verified". Turning it on offers to accept the waiting items.
6. **Alexa+.**
   - "What do I have to confirm?" lists the items.
   - "Yes, that was me" → `accept_item`.
   - Upcoming tasks never include review items.

## 4. Acceptance criteria

- The four cases of [00](00_overview.md) §1 behave as described, live and in history backfill.
- No untagged result completes a routine or is reported as done or due before the owner accepts it (setting off).
- A discarded result never comes back from a re-analysis.
- "Pending" counts only `pending` tasks everywhere.
- Both suites green; the new tests run on both backends.
