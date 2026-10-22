# 🎙️ Speaker Review — 02: Data and Pipeline

> **Document Status:** Implemented 2026-10-23 (deviations in [04](04_implementation_plan_and_testing.md) §0)
> **Related:** [00_overview.md](00_overview.md) (decisions R1–R9), [01_current_state.md](01_current_state.md), [manual_curation/02](../manual_curation/02_data_layer.md)

Store changes go to both backends (SQLite, DynamoDB) through `AbstractContextStore`, with signatures kept aligned by `tests/test_store_contract.py` (AGENTS.MD §E).

---

## 1. Schema (`src/core/schemas.py`)

| Model | Change |
|---|---|
| `PlannedTask.status` | adds `"review"` (waiting for the owner) and `"dismissed"` (tombstone, hidden) |
| `VerifiedAction` | new `needs_review: bool = False`, hidden from the model's structured-output schema (`SkipJsonSchema`, like `speaker`) |
| `SpeakerAttribution.source` | adds `"user_confirmed"`: the owner accepted it by hand |
| `ExamenState` | new `auto_accept_untagged: Optional[bool]` |
| `TaskChanges.status` | keeps its literal **without** `review` / `dismissed`: those states change only through accept / discard ([03](03_api_mcp_ui.md) §1) |

Storage columns:
- **SQLite:** `verified_actions.needs_review INTEGER NOT NULL DEFAULT 0`, added by the existing `ALTER TABLE` start-up list. The `planned_tasks.status` column is free text.
- **DynamoDB:** `needs_review` attribute on `ACTION#` items, written only when 1. Readers treat a missing attribute as 0. `COLUMNS["verified_actions"]` gains it for the export.
- `rules.row_to_action` maps it.

## 2. The review rule (`src/pipeline/nodes/persist.py`)

One function decides, so actions and tasks cannot drift apart:

```python
def needs_review(speaker: Optional[SpeakerAttribution], auto_accept_untagged: bool) -> bool:
    """R1/R2/R6/R7: only untagged speech that is not a request to the owner waits for the owner."""
    if speaker is None:                      # dashboard, simulator, MCP entries (R7)
        return False
    if speaker.addressed_to_user:            # "Damiano, push tonight" (R2)
        return False
    return speaker.role == "unknown" and speaker.source == "untagged" and not auto_accept_untagged
```

- `role == "unknown"` with source `history_name` cannot happen: REST "Unknown" maps to `untagged`.
- `internal` speakers (simulator with a name) are never reviewed.

In `node_persist`:
- **Action:** `action_data.needs_review = needs_review(...)`, then `store.save_action(action_data)`. The store skips routine matching for a review action (§3).
- **Task:** when `needs_review(...)`, `scheduled_task.status = "review"` before `save_planned_task`.
- **Micro-event links:** review results are still linked to their event. The dossier shows them with a "to confirm" marker, and a discard unlinks them through the engine, as curation deletes do.
- `state["auto_accept_untagged"]` defaults to `False` when absent (an older orchestrator, or AgentCore with an older payload).

## 3. Store methods

### Changed
- `save_action(action)`: if `action.needs_review`, **skip** `match_and_resolve_task` and the pre-matched completion. Write the row with `needs_review = 1` and no `matched_task_id`.
- `list_recent_actions`, `get_action_status`: exclude `needs_review = 1`, as they exclude `is_revoked = 1`.
  - SQLite: `AND needs_review = 0`.
  - DynamoDB filter: `attribute_not_exists(needs_review) OR needs_review = :zero`.
- `list_planned_tasks`: unchanged. Callers filter by status, and the default listing (no status) must hide `dismissed`. Today it returns every row, so add `status <> 'dismissed'` when no status is given.
- `match_and_resolve_task`: already uses `status="pending"`, so review tasks are never completed by an action.

### New (abstract)
| Method | Behaviour |
|---|---|
| `list_review_actions(limit: int = 50) -> List[VerifiedAction]` | Actions with `needs_review = 1` and `is_revoked = 0`, newest first. DynamoDB: the `timeline` index with the same filter |
| `accept_action(action_id: str, speaker: SpeakerAttribution) -> Optional[VerifiedAction]` | Clears `needs_review`, sets the speaker, then runs the routine matching skipped at save time (`match_and_resolve_task`, honouring the historical guard for backfill actions) and stores `matched_task_id`. Returns `None` if missing, revoked or not in review |

**Tasks need no new method.** Accept is `status: review → pending` and discard is `review/pending → dismissed`, both through `update_planned_task`. The conditions live in the service layer ([03](03_api_mcp_ui.md) §1).

**Discarding an action** reuses `revoke_action` (tombstone, R4). A review action has no completed routine to reopen.

## 4. Late tags (`BeeStreamOrchestrator.reconcile_speaker`)

Extend the existing reconciliation (ids from `derived_entity_id(source_key, …)`):

| Tag | Action in review | Task in review | Active action | Active task |
|---|---|---|---|---|
| **user** | accept (`accept_action`, source from the tag) | → `pending`, speaker from the tag | speaker updated (as today) | speaker updated (as today) |
| **contact**, request to the owner | — | → `pending`, "asked by" (R2) | — | stays, "asked by" (as today) |
| **contact**, otherwise | discard (`revoke_action`) | → `dismissed` | revoked, routine reopened (as today) | → **`dismissed`** (today `cancelled`, gap 01 §2c) |

- **Unlink and broadcast.** Each discard unlinks the result from its event through the engine (manual curation D7) and broadcasts the SSE event of [03](03_api_mcp_ui.md) §2.
- **Shared code.** Today `reconcile_speaker` revokes the action directly through `set_action_speaker(revoke=True)`. Route it through `curation_tools` (`revoke_action` + unlink + notify) so that every path behaves the same.

## 5. The setting (R6)

| Mode | Where it lives | How it is read |
|---|---|---|
| Accounts on | New user field `auto_accept_untagged: bool = False`: `users` column in SQLite (`ALTER TABLE` on start), attribute of the `USER#…` profile item in DynamoDB. `AuthStore.set_preference(user_id, key, value)` updates it | The orchestrator and the backfill read it when they build a payload, through `get_auth_store().get_user(tenant)`, cached per runtime and refreshed when it changes (§6) |
| Single user | Runtime setting `SPEAKER_AUTO_ACCEPT_UNTAGGED` (default false) in `runtime_settings.REGISTRY`, `apply = hot` | `settings.speaker_auto_accept_untagged` |

The value travels in the pipeline payload (`auto_accept_untagged`), next to `wearer_name`:
- `src/ingestion/orchestrator.py` and `src/ingestion/backfill.py` set it;
- `src/pipeline/app.py` copies it into `ExamenState`.

This way the AgentCore runtime never needs the auth table (01 §2e).

Turning it **on** does not touch existing review items. The dashboard offers "Accept all" for that.

## 6. Changing the setting at runtime

- `PATCH /api/account {"auto_accept_untagged": bool}` stores it and calls a hook (as `TenantHooks` does for other account changes) that updates the user's running orchestrator, so the next payload carries the new value.
- The backfill service reads it per run.

## 7. Scheduler prompt (01 §2b)

`_SpeakerView.prompt_section` gains one line for the `user` and `unknown` roles:

> If the speaker tells another named person to do something ("Marco, push tonight"), it is that person's task: for_owner=false.

The pattern fallback stays as it is (features degrade without a model).

## 8. Counters (R9)

| Place | Change |
|---|---|
| `/api/status` stats ([mcp_server.py:713](../../../src/serving/mcp_server.py#L713)) | `planned_tasks_pending = status == "pending"`; add `planned_tasks_review`, `actions_review` |
| `execute_get_daily_actions_recap` ([action_tools.py:232](../../../src/serving/tools/action_tools.py#L232)) | Same rule; the recap mentions "N items to confirm" when there are any |
| OverviewHub fallback | `t.status === "pending"` |
