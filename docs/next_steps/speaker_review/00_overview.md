# 🎙️ Speaker Review — Overview

> **Document Status:** Implemented 2026-10-23 (decisions R1–R9; status and deviations in [04](04_implementation_plan_and_testing.md) §0)
> **Related:** [08_speaker_identity.md](../08_speaker_identity.md) (Bee voice tags bound to the wearer), [manual_curation/](../manual_curation/00_overview.md) (edit, delete, tombstones), [historical_backfill/](../historical_backfill/00_overview.md) (re-analysis of chunks)
> **Audience:** EXAMEN engineers extending speaker identity with a confirmation step for unidentified speech

---

## 1. Why this exists

Speaker identity ([08](../08_speaker_identity.md)) tells EXAMEN who said a sentence, as far as Bee knows. Today only one outcome changes behaviour: **another recognised person**, whose own plans and statements are dropped. Speech with **no Bee tag** is treated as the owner's (08 §5) and becomes an active task or a verified action immediately.

In a discussion, an unrecognised person's "I need to push tonight" therefore becomes the owner's task, and their "I locked the door" closes the owner's routine. The owner only sees a grey "Voice not verified" badge, after the fact.

The goal is that every extracted result falls into one of four cases.

| # | Who spoke | Outcome |
|---|---|---|
| 1 | **The owner** (Bee matched the voice) | Saved as the owner's. If wrong, the owner deletes it (manual curation) |
| 2 | **Another person Bee recognises** (a person saved in the Bee app) | Dropped |
| 3 | **Nobody recognised** (no Bee tag) | Kept **to confirm**: not active until the owner accepts it; the owner can also discard it |
| 4 | **Anyone, addressing the owner by name** ("Damiano, push tonight") | The owner's task, marked "asked by", active at once |

Cases 1, 2 and 4 are mostly implemented ([01](01_current_state.md)). Case 3 is new.

---

## 2. Scope

**In scope**
- A **review state** for actions (Peace of Mind) and tasks (Daily Routines) extracted from unidentified speech.
- **Accept** and **discard** from the dashboard and over MCP.
- Late Bee tags resolving a pending review automatically.
- A **per-user setting** "Accept untagged speech automatically" (off by default, with a warning).
- Late contact tags **discard** a task instead of leaving it visible as `cancelled`.
- Correct "pending" counters (today they count everything that is not completed).
- An explicit scheduler rule for the owner addressing someone else ("Marco, push tonight" said by the owner is Marco's task).

**Out of scope**
- Correcting Bee's voice binding ("this is not my voice"), and persisting the bound person ids: follow-ups of 08 §8.
- Social commitments: their debtor already follows who spoke (08 §5).
- Re-analysing sentences that were dropped as another person's (case 2): they stay dropped.

---

## 3. Decisions

| # | Decision |
|---|---|
| **R1** | An action or task extracted from **untagged** speech is saved in **review**. It does not count as done or due, it does not complete routines, and Alexa+ does not report it as verified or upcoming, until the owner accepts it. |
| **R2** | A request that **names the owner** (case 4) skips review: the owner is the one who has to do it, whoever spoke. It is saved active with "asked by". |
| **R3** | A **user** tag (live, or arriving late) accepts automatically. A **contact** tag drops the result (live) or discards it (late), except requests to the owner (R2). |
| **R4** | **Discard is a tombstone**, as manual-curation deletes of actions are. Tasks get status `dismissed` and actions `is_revoked`, both hidden. A backfill re-analysis of the same sentence finds the tombstone and does not recreate the result. |
| **R5** | **Accept** makes the result the owner's: the speaker becomes `user` with source `user_confirmed`. An accepted action runs the routine matching it skipped while in review. |
| **R6** | Setting **"Accept untagged speech automatically"**, per user, **off by default**, with the warning that other people's sentences may become the owner's tasks. When on, untagged results are saved as today (active, "Voice not verified"). Single-user mode reads `SPEAKER_AUTO_ACCEPT_UNTAGGED`. |
| **R7** | Results without speaker information (dashboard entries, the simulator, MCP `create_planned_task`) never go to review. |
| **R8** | History backfill follows the same rules. A REST transcript naming the owner is the owner's (`history_name`); `"Unknown"` is untagged, so it goes to review. |
| **R9** | "Pending" means `status == "pending"` everywhere (overview, `/api/status`, Alexa recap). Review, dismissed and cancelled are counted apart. |

---

## 4. Target flow

```
 utterance ──► orchestrator / backfill ──► payload {speaker_role, speaker_source, wearer_name,
                                                    auto_accept_untagged}
                                                    │
                                   pipeline nodes (unchanged rules for contacts and requests)
                                                    │
                                     persist: review_state(speaker, addressed, setting)
                          ┌─────────────────────────┼─────────────────────────────┐
                    owner / request            untagged, setting off          untagged, setting on
                  active (as today)          REVIEW (action needs_review,     active, "Voice not
                                              task status "review")           verified" (as today)
                                                    │
               ┌────────────────────────────────────┼───────────────────────────────┐
         late user tag                    owner: Accept / Discard            late contact tag
         → accept (R3)                    (dashboard, MCP)                   → discard (R3),
                                                                             requests stay (R2)
```

---

## 5. Documents

| Doc | Content |
|---|---|
| [01_current_state.md](01_current_state.md) | What already works for each case, and the gaps |
| [02_data_and_pipeline.md](02_data_and_pipeline.md) | Schema, store methods, persist rule, late tags, setting plumbing |
| [03_api_mcp_ui.md](03_api_mcp_ui.md) | REST routes, MCP tools, dashboard (review sections, setting), counters |
| [04_implementation_plan_and_testing.md](04_implementation_plan_and_testing.md) | Phases, tests, manual and device checks |
