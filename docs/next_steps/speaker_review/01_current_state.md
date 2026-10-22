# 🎙️ Speaker Review — 01: Current State

> **Document Status:** Code survey of branch `final_fix` after the speaker-identity merge (`b4065d6`, 2026-10-23); line numbers refer to that state
> **Related:** [00_overview.md](00_overview.md), [08_speaker_identity.md](../08_speaker_identity.md)

---

## 1. Case by case

| Case | Status | Where |
|---|---|---|
| **1. Said by the owner** | ✅ Saved as the owner's, "Your voice" badge. A wrong one can be deleted with manual curation (🗑️, MCP `delete_action` / `delete_planned_task`) | [persist.py](../../../src/pipeline/nodes/persist.py) `speaker_from_state` :31; [curation_tools.py](../../../src/serving/tools/curation_tools.py) |
| **2. Another person Bee recognises** | ✅ Live: the action node returns nothing ([action_state.py:190](../../../src/pipeline/nodes/action_state.py#L190)), and the scheduler drops the person's own plans (`for_owner = false`). ⚠️ Late tag: the action is revoked (hidden), but the task becomes `cancelled` and stays **visible** in Daily Routines | `reconcile_speaker`, [orchestrator.py:457](../../../src/ingestion/orchestrator.py#L457) |
| **3. Nobody recognised** | ❌ Treated as the owner's ([08](../08_speaker_identity.md) §5: "untagged speech is still the user's"). The action is verified and closes routines at once; the task is `pending` at once. Only the grey "Voice not verified" badge shows the doubt | `speaker_from_state` (role `unknown`, source `untagged`) |
| **4. Request naming the owner** | ✅ The owner's task, "asked by" (`SpeakerAttribution.addressed_to_user`), also when the speaker is untagged. The model returns `for_owner` / `requested_by`; without a model, patterns (`_addressed_to_owner`, `is_request_to_owner`) apply | [scheduler.py](../../../src/pipeline/nodes/scheduler.py) :242, `_SpeakerView.prompt_section` :336 |

## 2. Gaps

### a. No review state
- `PlannedTask.status` is `pending | completed | overdue | skipped | cancelled`. Nothing means "not confirmed yet".
- `VerifiedAction` has only `is_revoked`.
- `save_action` runs `match_and_resolve_task` unconditionally, so an untagged action closes a routine as soon as it is stored.

### b. The owner addressing someone else
"Marco, push tonight" said by the owner (tagged or untagged) is Marco's task.
- The **model** sees this only in the description of `ScheduledTaskExtraction.for_owner` ("False when … the owner asks someone else"). `prompt_section` does not state it for the `user` and `unknown` roles.
- The **pattern fallback** turns "Marco, remember to push tonight at 9" into the owner's task "Marco, remember to push". Accepted: features degrade without a model.

### c. Late contact tag on a task
Becomes `cancelled`, a status the owner also uses for commitments they cancelled. It shows in the routine grid with a grey badge. Case 2 wants it gone.

### d. Counters
"Pending" is computed as `status != "completed"`, so it already counts `cancelled` and would count the new states too:
- `/api/status` ([mcp_server.py:713](../../../src/serving/mcp_server.py#L713));
- the Alexa recap ([action_tools.py:232](../../../src/serving/tools/action_tools.py#L232));
- the OverviewHub fallback.

### e. No per-user preference
- Accounts hold profile fields only: `display_name`, consent, `is_admin` (`users` table / DynamoDB `USER#…` item).
- Runtime settings (`runtime_settings.REGISTRY`) are global and admin-only.
- The pipeline may run on AgentCore Runtime, which cannot read the auth table (its IAM policy covers the tenant partition and some ops partitions). So a user preference must travel **in the payload**, like `wearer_name` (orchestrator :342, backfill :737).

## 3. What the design can rely on

- **Speaker attribution on every result.** `speaker_from_state` already builds a `SpeakerAttribution` for each result: `role`, `source`, and `addressed_to_user` from the scheduler. Entries without speaker data (dashboard, simulator, MCP) get `None`. That is the review switch.
- **Late tags.**
  - Tags arrive about 0.6 s after the utterance (08 §7), inside the 1.5 s wait, so most tagged sentences are classified before the pipeline runs.
  - `reconcile_speaker` already finds the derived action and task by `source_key` (ids from `derived_entity_id`).
- **Tombstones.**
  - `persist` skips an action or task whose derived id already exists (persist :64 / :141 in the curation survey).
  - The tombstone pattern of manual curation (`revoke_action`) therefore extends to tasks with a hidden status.
- **One service layer.** Manual curation already has REST + MCP wrappers, SSE notifications, a confirmation dialog and transcript excerpts that the review UI can reuse.
