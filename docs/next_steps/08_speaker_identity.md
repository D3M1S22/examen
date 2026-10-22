# 08 — Speaker Identity: binding Bee voice tags to the account

> **Status:** implemented 2026-10-22 on branch `feature/speaker-identity`; verified on a device the same day for the wearer alone (§7). Contacts' tags and id stability across sessions are still unverified.
> **Code:** [bee_identity.py](../../src/ingestion/bee_identity.py) (`WearerIdentity.match_tag`), [orchestrator.py](../../src/ingestion/orchestrator.py) (`on_tagged_utterance`, `reconcile_speaker`), [persist.py](../../src/pipeline/nodes/persist.py) (`speaker_from_state`), [action_state.py](../../src/pipeline/nodes/action_state.py), [scheduler.py](../../src/pipeline/nodes/scheduler.py), [SpeakerBadge.tsx](../../src/web_ui/src/components/ui/SpeakerBadge.tsx). **Tests:** `tests/test_speaker_identity.py`.
> **Related:** [10_bee_cli_reference.md](../10_bee_cli_reference.md) §7.3, §8 (the `tagged-utterance` contract), [07_bee_data_alignment.md](07_bee_data_alignment.md) (phase 2 introduced the tag wait).

---

## 1. What Bee sends

When the wearer has enrolled their voice in the Bee app, Bee follows some `new-utterance` events with a `tagged-utterance` about one second later:

```json
{"type": "tagged-utterance", "utterance_id": 3700000001, "person_id": 42,
 "person_first_name": "Ada", "speaker_score": 0.79, "conversation_uuid": "…"}
```

`utterance_id` is the `utterance.id` of the earlier `new-utterance`. In the first capture (doc 10) 22 % of utterances were tagged, all of them the wearer, with scores 0.52–0.86. There is no tag for untagged speech, no `update-utterance`, and no speaker field on `new-utterance`. REST transcripts (history) carry `speaker` = a first name or `"Unknown"`, without a score.

## 2. What was missing

Before this change the orchestrator already cached tags, waited up to `BEE_SPEAKER_TAG_WAIT_SECONDS` for qualified utterances and compared `person_first_name` with `bee me` → `first_name`. But:

| Gap | Effect |
|---|---|
| Only the first name was compared; `person_id` was ignored | A contact with the user's first name counted as the user; a renamed profile lost the match |
| Only the social node read the role | A contact's "I locked the door" verified the user's routine; a contact's "remind me to …" became the user's task |
| Entities did not record who spoke | Dashboard and Alexa+ could not say "you said it" |
| A tag after dispatch only patched the ring buffer | An action extracted as "unknown" stayed attributed to the user even when Bee later said another person spoke |
| No measurement | The tag wait could not be tuned |

## 3. Matching the wearer

`WearerIdentity` (one per user, from the user's own `bee me`) now holds the first name and a set of **person ids bound to the wearer**. `match_tag(person_id, name, score)` decides, in order:

1. `person_id` already bound → **user** (`source = bee_voice_id`).
2. A bound id exists and this is another one → **contact** (`bee_voice_id`), even when the first name is the same.
3. First name equal to the wearer's → **user** (`bee_name`); the tag's `person_id` is bound, so later tags match by id. Ids seen first with another name are never bound.
4. Another first name → **contact** (`bee_name`); no wearer known → **unknown**.

`person_id` is **not** the `bee me` account id (§7, S1): the two are different numbering schemes of similar size, so they are never compared.

Bindings live in memory per runtime and are re-learned from the first tag after a restart.

## 4. Data carried

| Where | Field | Meaning |
|---|---|---|
| `UtteranceChunk` | `speaker_person_id`, `speaker_score`, `speaker_source` | From the tag (`speaker_id` / `speaker_role` as before) |
| Pipeline payload and `ExamenState` | `speaker_score`, `speaker_source` | Next to `speaker`, `speaker_role`; also sent to the AgentCore runtime |
| `VerifiedAction.speaker`, `PlannedTask.speaker` | `SpeakerAttribution {role, name, score, source, addressed_to_user}` | Who said the sentence; `addressed_to_user` = someone asked the owner to do it. `None` = not recorded (manual entries, older rows). Hidden from the action model's structured-output schema |
| Pipeline payload | `wearer_name` | The owner's first name, so the scheduler can recognise "Damiano, remember to …" |
| `ScheduledTaskExtraction` | `for_owner`, `requested_by` | The scheduler model says whether the owner must do it, and who asked |
| Storage | `speaker_json` column / attribute on `verified_actions` and `planned_tasks` | Both backends; SQLite adds the column on start |
| `GET /api/actions`, `GET /api/routines` | `speaker` | For the dashboard |
| MCP `verify_action_status` | `spoken_by`, `voice_verified` | `"you (voice match)"`, `"you"`, a contact's name, or `"unidentified speaker"`; the spoken answer adds "Bee recognised your voice." |
| Orchestrator status | `wearer_voice_id_bound`, `speaker_tags_seen`, `wearer_tags`, `speaker_tag_lag_seconds` (median), `speaker_tag_wait_seconds` | Liveness and tuning |

`speaker_source` values: `bee_voice_id`, `bee_name` (live tags), `history_name` (REST speaker), `untagged`, `internal` (simulator, tests).

## 5. Rules

- **Untagged speech is still the user's.** About four in five utterances carry no tag, and most of them are the wearer's. Treating "unknown" as "not the user" would lose most actions. Only a positive `contact` changes behaviour.
- **Contact speech** never verifies an action (the action node returns nothing). The social node keeps its existing rule: a contact's promise has the contact as debtor.
- **Tasks follow who has to do them, not who spoke.** The scheduler prompt says who the speaker is (owner with voice match, another person, or not identified) and the owner's first name; the model returns `for_owner` and `requested_by`:

  | Said by | Example | Result |
  |---|---|---|
  | Owner (tagged or untagged) | "Remind me to call Marco tomorrow at ten" | Owner's task |
  | Another person, asking the owner | "Damiano, please remember to start the washing machine" / "Can you call me tomorrow?" | Owner's task, **asked by** that person (`addressed_to_user`) |
  | Untagged, naming the owner | "Damiano pls remember to launch the washing machine" | Owner's task, asked by someone (asker unverified) |
  | Another person, own plan | "Remind me to call my mum" | No task |

  Without a model (mock or fallback) the same rules run on patterns: the owner's first name at the start of the sentence or before "please / remember / can you", request lead-ins, and self lead-ins ("remind me", "I need to").
- **Late tags** (after the bounded wait):
  - arriving while the pipeline runs: applied right after it returns;
  - arriving after the utterance was analysed: applied at once (in a thread, tenant context copied);
  - effect: the action and the task derived from that utterance (ids from the source key) get the speaker. If it is a contact, the action is revoked and a task it completed is reopened. A task becomes "asked by" that contact when it was a request to the owner (flagged, or the sentence reads as one); only another person's own plan is cancelled.
  - noop utterances only get the ring-buffer and diarization patch (no entity exists).
- **Dashboard** (actions and routines):

  | Badge | When |
  |---|---|
  | 🎙 Your voice · 81 % (green) | Bee recognised the owner |
  | 📣 Asked by Giulia · 66 % / · unverified (blue) | A request to the owner; the score when Bee recognised the asker |
  | ◌ Voice not verified (grey) | No Bee tag: probably the owner, not verified |
  | 🎙 You · Bee history | Backfill, REST names the owner (no score) |
  | 🗣 Marco (amber) | Said by another person |

  Manual entries and simulator data show no badge. Alexa+ answers add "Bee could not confirm it was your voice." for unverified actions, and `get_upcoming_tasks` returns `spoken_by` ("asked by Giulia").
- **Logging (AGENTS.MD F3):** names and transcripts never reach the logs; only counts and roles do.

## 6. Settings

No new settings. `BEE_SPEAKER_TAG_WAIT_SECONDS` (default 1.5, runtime-editable in the admin console) stays the bounded wait after receipt; tune it from `speaker_tag_lag_seconds`.

## 7. Device verification

To run on a Mac with the Bee paired, inside `nix develop`:

```bash
python scripts/bee_spike.py check
python scripts/bee_spike.py capture --minutes 6     # speak the script below
python scripts/bee_spike.py history --hours 1
python scripts/bee_spike.py speakers                # writes <session>/speakers.md
```

With accounts enabled, set `EXAMEN_CLI_USER=<email>` (or `--user`): the script then uses that account's paired Bee login, like the server does.

Script: three short wearer sentences (an action, a reminder, a routine), two sentences by another person, one long wearer sentence, and two quick alternating turns. Questions answered from `.bee-spike/<date>/` (git-ignored).

**Run of 2026-10-22** (wearer alone, voice enrolled in the Bee app; sentences 1–3 and the long one). Ids below are replaced by placeholders, the real values are in the git-ignored capture:

| # | Question | Result |
|---|---|---|
| S1 | Is `tagged-utterance.person_id` equal to `bee me` → `id`? | **No.** Tags carried person `P` and `bee me` returned another number `A` of the same size. The first-name binding (§3 rule 3) is required |
| S2 | Is `person_id` stable across conversations and sessions? | Same id on every tag of the run (one conversation). Across conversations: pending |
| S3 | Are other people ever tagged? | Not tested (no second speaker). The first capture (doc 10) had only wearer tags too |
| S4 | Tag lag after its `new-utterance` | 0.60 and 0.63 s after receipt (n = 2): inside the 1.5 s wait. The utterances themselves arrived 4.1, 5.8 and 10.4 s after they were spoken; the long one was created by Bee 29.6 s after it |
| S5 | Does the REST history expose `person_id` or a score? | **No.** REST utterances carry only `speaker` = first name or `"Unknown"`; it matched the live tags (tagged → the wearer's first name, untagged → `"Unknown"`), and the long sentence, which reached the stream only after the capture had stopped, is named as the wearer too |

Matching over the capture: 2/2 tags → `user`, the wearer's person id bound from the first one. 2 of 3 short sentences were tagged; the untagged one ("I just locked the front door") stays `unknown` and still counts as the user's (§5).

## 8. Next

- Persist the bound person ids per user (today they are re-learned after a restart).
- Pass the speaker to the gatekeeper once tags arrive before screening (they arrive about 1 s after the utterance, screening starts at once).
- Correct a social commitment's debtor on a late contact tag.
