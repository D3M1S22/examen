# 🎙️ Speaker Review — 03: API, MCP and Dashboard

> **Document Status:** Implemented 2026-10-23 (deviations in [04](04_implementation_plan_and_testing.md) §0)
> **Related:** [02_data_and_pipeline.md](02_data_and_pipeline.md), [manual_curation/03](../manual_curation/03_api_and_mcp.md), [manual_curation/04](../manual_curation/04_ui.md)

---

## 1. Service layer

Extends `src/serving/tools/curation_tools.py`, the one place for user edits (AGENTS.MD rule). Same conventions:
- exact ids only;
- `CurationError` → HTTP status;
- `_notify` for SSE;
- logs with ids and counts only.

| Function | Behaviour |
|---|---|
| `execute_list_review(store=None)` | `{"actions": [...], "tasks": [...], "count": n}` from `list_review_actions()` and `list_planned_tasks(status="review")`, serialised with `action_dict` / `task_dict` (speaker included) |
| `execute_accept(kind, item_id)` | Action: `accept_action` with `SpeakerAttribution(role="user", source="user_confirmed")`. Task: `review → pending` with the same speaker. 404 if missing; 409 if no longer in review (accepted elsewhere, or resolved by a late tag) |
| `execute_dismiss(kind, item_id)` | Action: `revoke_action` + unlink. Task: `review/pending → dismissed` + unlink (`task_scheduled`). 404 / 409 as above |
| `execute_accept_all()` | Accepts every review item (used after turning the setting on, and by the "Accept all" button) |
| `execute_update_task` | Refuses `status` values `review` / `dismissed` (400): they change only through accept / discard |

Late tags ([02](02_data_and_pipeline.md) §4) call the same accept / dismiss functions, so dashboard, MCP and Bee resolve reviews identically.

## 2. REST and SSE

| Route | Response | SSE |
|---|---|---|
| `GET /api/review` | `{actions, tasks, count}` | — |
| `POST /api/review/{kind}/{id}/accept` (`kind` = `action` \| `task`) | `{success, action \| task}` | `review_resolved {kind, id, outcome: "accepted"}`, plus `action_updated` / `routine_updated` |
| `POST /api/review/{kind}/{id}/dismiss` | `{success, dismissed_id}` | `review_resolved {…, outcome: "dismissed"}` |
| `POST /api/review/accept-all` | `{success, accepted: n}` | one `review_resolved` with `outcome: "accepted_all"` |
| `PATCH /api/account` | accepts `auto_accept_untagged: bool` | — |
| `GET /api/account` | `user.auto_accept_untagged` | — |
| `GET /api/status` | `stats.planned_tasks_review`, `stats.actions_review` | — |

New review items appear through the existing pipeline SSE events (the dashboard revalidates actions and routines), plus a `review_added {kind, id}` broadcast by `persist` callers:
- the orchestrator, after the dispatch returns;
- the backfill, once per run with counts, as for its other entities.

In single-user mode the setting is the runtime setting of the admin console ([02](02_data_and_pipeline.md) §5).

## 3. MCP tools

| Tool | Parameters | Annotations | Notes |
|---|---|---|---|
| `list_items_to_review` | — | read-only | Each item: id, kind, title, transcript excerpt, time. `spoken_summary`: "You have 3 things to confirm: …" |
| `accept_item` | `kind`, `item_id` | idempotent | "Added 'push the branch' to your routines." |
| `dismiss_item` | `kind`, `item_id` | idempotent | No two-step confirmation: the item is unconfirmed by definition and the outcome is what the owner asks for. Discard is still a tombstone (R4) |

- `get_upcoming_tasks` and `verify_action_status` ignore review items, as they ignore revoked ones.
- `get_daily_actions_recap` mentions the count to confirm.

## 4. Dashboard

### Shared component: `ReviewTray`
New, used by both views:
- a collapsible panel at the top, "To confirm (N)", visible only when N > 0;
- one row per item:
  - title, `TranscriptExcerpt`, time, event link if any;
  - "Voice not identified" note;
  - **✔ Mine** (accept) and **✕ Not mine** (discard) buttons;
- an **Accept all** button when there are 2 or more items;
- optimistic removal, rolled back on error, as the curation handlers do.

### Peace of Mind
- `ReviewTray` lists actions in review.
- The main grid, the KPIs and the confidence average use only accepted actions (already the case: the list route excludes review).

### Daily Routines
- `ReviewTray` lists tasks in review.
- The grid hides `review` and `dismissed`; `cancelled` stays (cancelled commitments).
- The PENDING filter and counters use `status === "pending"`.
- The task edit modal does not offer review states.

### Overview
- A small "N to confirm" badge links to the tab that has items.
- Tab update markers fire on `review_added`.

### Account settings (`LoginModal`, Account section)
New block "Speaker recognition":

> ☐ **Accept untagged speech automatically**
> When Bee does not recognise who is speaking, EXAMEN asks you to confirm each action and task. Turn this on to accept them as yours straight away. **Other people's sentences may then become your tasks or close your routines.**

- `PATCH /api/account`.
- When turned on with items waiting, offer "Accept the N waiting items too?" (calls accept-all).
- `utils/auth.ts`: `updatePreferences({auto_accept_untagged})`; `AccountUser.auto_accept_untagged`.

### Types (`src/web_ui/src/types/schemas.ts`)
- `PlannedTask.status` adds `"review" | "dismissed"`;
- `VerifiedAction.needs_review?: boolean`;
- `SpeakerAttribution.source` adds `"user_confirmed"`;
- `SpeakerBadge` shows "✔ Confirmed by you" for `user_confirmed`.
