# ✏️ Manual Curation — 03: Service Layer, REST API and MCP

> **Document Status:** Planned
> **Related:** [02_data_layer.md](02_data_layer.md) · [04_ui.md](04_ui.md) · AGENTS.MD §F2 (tenancy), §F3 (logging)

---

## 1. Service layer: `src/serving/tools/curation_tools.py`

One module owns every curation operation; REST routes and MCP tools only adapt inputs and outputs. It follows the `execute_*` pattern of [action_tools.py](../../../src/serving/tools/action_tools.py): plain functions, with the store and the engine injectable for tests.

| Function | Store / engine calls | SSE events |
|---|---|---|
| `execute_update_action(action_id, changes)` | `update_action` | `action_updated` |
| `execute_delete_action(action_id, confirm)` | `revoke_action`, then `engine.unlink_micro_event(session_id, "action", id)` | `action_deleted`, plus `routine_updated` when a task was reopened |
| `execute_update_task(task_id, changes)` | `get_planned_task`, then `update_planned_task` | `routine_updated` |
| `execute_delete_task(task_id, confirm)` | `delete_planned_task` | `routine_deleted` |
| `execute_update_contact(contact_id, changes)` | `update_social_contact`; if `anchors_changed`, schedule enrichment (§2) | `contact_updated` |
| `execute_delete_contact(contact_id, confirm)` | `delete_social_contact`, then `engine.unlink_micro_event(session_id, "social_contact", id)` | `contact_deleted` |
| `execute_delete_event(session_id, confirm)` | `engine.delete(session_id)` | `event_deleted` (forwarded by the engine runtime) |

Rules:
- **Exact ids only.** No function resolves a name or a fuzzy query. Contacts are no exception, even though `get_social_contact` accepts names: the curation path calls it only with an id, and returns 404 otherwise.
- **`confirm`** (deletes only, D4):
  - `False` returns `{"confirm_required": True, "would_delete": {...}}` and writes nothing.
  - `True` deletes.
  - The REST routes always pass `True`, because the dashboard has already asked the user (D8).
- **Notifications.**
  - `broadcast_event` lives in `mcp_server.py`. To avoid an import cycle, `mcp_server` registers it once at import time with `curation_tools.set_notifier(broadcast_event)`; the default notifier is a no-op, which is what tests use.
  - Events go to the current tenant, and MCP calls already run inside `tenant_scope` through `tenant_tool`.
- **Engine.** Use `get_event_engine()` (one per tenant, AGENTS.MD §F2). REST routes call `_ensure_event_engine()` first, as the existing session routes do, so the runtime is started.
- **Logging.** Log ids and counts only, never names, titles or transcript text (AGENTS.MD §F3). Failures of the background enrichment go through `report_event("contact.enrich_failed", "warning", …)`.
- **Results** are plain dicts built from the result models of [02](02_data_layer.md) §5. They hold ids, titles and counts, so they can be spoken by Alexa+ and rendered by the dashboard.

## 2. Automatic re-enrichment (D3)

When `update_social_contact` reports `anchors_changed`:
1. Return the update at once with `"enrichment": "scheduled"`.
2. Run `enrich_social_contact_sync(contact, store=…, force=True)` ([social_profiler.py:646](../../../src/pipeline/nodes/social_profiler.py#L646)) in the background, inside `tenant_scope(user_id)`:
   - REST: `asyncio.create_task(asyncio.to_thread(...))`, watched with `watch_task()`;
   - MCP: the same, through the running loop.
3. Broadcast the outcome:
   - success: `contact_enriched`, the payload already handled by the dashboard;
   - the disambiguation guardrail rejects the contact (not enough anchors) or the search returns nothing: `contact_enrich_failed {contact_id, reason: "insufficient_anchors" | "no_results"}`.

A second edit while an enrichment is running is fine. The enrichment writes only `web_profile_json` (and `website_url` if absent) through `update_contact_web_profile`, and the newest run wins. A stale run could still write a profile for the old name; to prevent it, the run carries the anchors it started with and skips the write when they no longer match the stored contact.

## 3. REST routes (`src/serving/mcp_server.py`)

| Route | Body | Success | Errors |
|---|---|---|---|
| `PUT /api/actions/{id}` | `ActionChanges` | 200 `{success, action}` | 400 invalid body · 404 missing or revoked |
| `DELETE /api/actions/{id}` | — | 200 `{success, deleted_id, reopened_task_id}` | 404 |
| `PUT /api/routines/{id}` *(existing)* | `TaskChanges` (now validated) | 200 `{success, task}` | 400 · 404 |
| `DELETE /api/routines/{id}` *(existing)* | — | unchanged | unchanged |
| `PUT /api/contacts/{id}` | `ContactChanges` | 200 `{success, contact, enrichment: "scheduled" \| "unchanged"}` | 400 · 404 · **409** name taken (D5) |
| `DELETE /api/contacts/{id}` | — | 200 `{success, deleted_id, commitments_deleted, tasks_deleted}` | 404 |
| `GET /api/contacts/{id}/cascade` | — | 200 `{commitments: [...], tasks: [...]}` (dashboard confirmation, D8) | 404 |
| `DELETE /api/sessions/{id}` | — | 200 `{success, deleted_id, briefings_deleted, chunks_deleted}` | 404 |

Read routes gain the fields the UI needs:
- `GET /api/routines` adds `completion_statement`: the `raw_statement` of the action in `verified_action_id`, when it exists and is not revoked. `origin`, `raw_statement` and `session_id` are already returned.
- `GET /api/contacts` adds `session_id`.

All routes run under the existing auth middleware, so they are tenant-scoped. They are ordinary data routes, not admin routes.

## 4. SSE events

| Event | Payload | Dashboard reaction |
|---|---|---|
| `action_updated` | `{action_id}` | revalidate actions |
| `action_deleted` | `{action_id, reopened_task_id}` | revalidate actions (+ routines if a task reopened), status |
| `routine_updated` / `routine_deleted` | existing | existing |
| `contact_updated` | `{contact_id, enrichment}` | revalidate contacts; show "re-searching" when `enrichment = scheduled` |
| `contact_enriched` | existing | existing |
| `contact_enrich_failed` | `{contact_id, reason}` | clear the "re-searching" state, toast |
| `contact_deleted` | `{contact_id, commitments_deleted}` | revalidate contacts, commitments, routines |
| `event_deleted` | `{session_id}` | `refreshEvents()` (sessions, engine status, topics) |

Payloads carry ids and counts only.

## 5. MCP tools

New tools in `curation_tools.py`, exported from `src/serving/tools/__init__.py` and registered in `mcp_server.py` next to the existing ones:

```python
from mcp.types import ToolAnnotations

EDIT = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True)
DELETE = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True)

mcp.tool(annotations=EDIT)(tenant_tool(update_action))
mcp.tool(annotations=DELETE)(tenant_tool(delete_action))
# update_planned_task, delete_planned_task, update_contact, delete_contact, delete_session_dossier
```

| Tool | Parameters | Notes |
|---|---|---|
| `update_action` | `action_id`, `title?`, `domain?` | `title` maps to `action_type` |
| `delete_action` | `action_id`, `confirm=False` | preview: title, transcript excerpt (≤ 120 chars), routine that would reopen |
| `update_planned_task` | `task_id`, `title?`, `domain?`, `scheduled_time?`, `recurrence?` | |
| `delete_planned_task` | `task_id`, `confirm=False` | preview: title, schedule |
| `update_contact` | `contact_id`, `name?`, `company_or_role?`, `contact_info?`, `website_url?`, `key_topics?` | response says whether the web search was re-run |
| `delete_contact` | `contact_id`, `confirm=False` | preview: name, commitments and routines that go with it |
| `delete_session_dossier` | `session_id`, `confirm=False` | preview: title, period, number of briefings |

### Confirmation protocol (D4)
The docstrings tell the model how to behave, for example:

> "Deletes an extracted action. **Call it first without `confirm`**: you get what would be deleted. Read it back to the user and call again with `confirm=true` only after they agree. Use the `id` from `get_daily_actions_recap`; never guess it."

The preview and the delete are computed by the same function, so they cannot disagree. A second call with `confirm=true` on an id already deleted returns `{"status": "not_found"}`: deletes are idempotent.

### Ids for the model
`verify_action_status` must add `action_id` (and `matched_task_id`, already present) to its result. Without it a voice flow such as "that wasn't the stove, delete it" has no id to act on. The other read tools already expose ids ([01](01_current_state.md) §3).

### Spoken summaries
Every write tool returns a `spoken_summary`, like the existing tools, for Alexa+:
- "I deleted the note 'stove off' and reopened your routine 'check stove'."
- "Renamed to Marco Rossi; I am searching the web for the new name."
