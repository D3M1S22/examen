# EXAMEN — Project Context (for humans and AI agents)

> **Purpose:** one-page deep context to load before working on this repo. It condenses `README.md`, `AGENTS.MD`, docs 01–19 and the code layout, and records how the dev environment really works on the maintainer's machine.
> **Snapshot:** 2026-10-23, branch `pitch` (commit `effd5a3`). Re-check anything time-sensitive against the linked sources.
> **Rules for agents:** `AGENTS.MD` is authoritative. This file summarises it; it never overrides it.

---

## 1. What EXAMEN is

EXAMEN (*Ambient Knowledge & Action Engine*, Latin *exāmen* = a swarm of bees, and a careful weighing) turns the continuous speech captured by the **Bee** wearable into structured, useful memory, without wake words:

| Domain | Input heard by Bee | What EXAMEN produces | Where you see it |
|---|---|---|---|
| **Action-state** | "I unplugged the iron", "front door locked" | Certified completed actions with timestamp + verbatim quote | Peace of Mind view; MCP `verify_action_status` |
| **Scheduled tasks** | "Remind me to call Dr. Smith tomorrow at 3" | `PlannedTask` (domain, time, recurrence) | Daily Routines view; MCP `get_upcoming_tasks` |
| **Social recall** | "Nice to meet you Marco, I'm tech lead at Acme… I'll send you the docs by 5" | Contacts, roles, bilateral commitments (debtor/creditor) | Social Rolodex; MCP `get_social_commitments` |
| **Deep topics** | Meetings, lectures, technical discussions | Events (R0–R9 state machine), part + final briefings, web sources | Topic Dossiers + Echo Show view; MCP `get_topic_briefing` |

Served to **Alexa+** through a self-hosted **MCP server** (Streamable HTTP, protocol 2025-11-25, 22 tools) and to a **Next.js dashboard** (desktop + Echo Show layout).

### Hackathon
- **Amazon Developer Hackathon 2026.** Tracks: Bee Wearable AI (primary), Alexa+ (self-hosted MCP server), AWS Builder mini-challenge.
- **Deadline:** Fri 23 Oct 2026, 12:00 PT = **21:00 CEST**. Judging 9–20 Nov.
- **Video:** under 3 minutes, shows the project on the intended device, public on YouTube/Vimeo, no unlicensed music or trademarks, English. A *simulated* Alexa+ experience is accepted if clearly shown as such.
- Source: `docs/14_aws_and_hackathon_reference.md`.

---

## 2. Current branch state

| Item | Value |
|---|---|
| Current branch | `pitch` |
| Ahead of `main` | 9 commits (speaker review, manual curation, Alexa add-on docs, doc refresh, video-pitch scenes) |
| Uncommitted | `video-pitch/bun.lock` (untracked) + the v2 video work from 2026-10-23 (see §9) |
| Other branches | `main`, `Next_steps`, `feature/multi-user-auth`, `feature/speaker-identity`, `optimization/bee-opt`, `review/merge-web-ui-into-main`, `update/web_ui` |
| Remote | GitHub `D3M1S22/amazon_challenge` (private at the time of doc 17; the submission needs it public with an OSS licence or shared with judges) |
| Submodules | `resources/agentcore-samples`, `resources/bee-cli` — **read-only reference** |

---

## 3. Architecture (data flow)

```
Bee wearable / Apple Watch app
  └─ bee CLI SSE (private `bee proxy` on 127.0.0.1, fallback `bee stream --json`)
       new-utterance, tagged-utterance (speaker), locations
         ▼
src/ingestion/stream_convo.py  (BeeClient, per-user, bee_subprocess_env())
src/ingestion/orchestrator.py  (per-utterance screening, ring buffer, speaker-tag wait 1.5 s)
         ▼
src/ingestion/gatekeeper.py    Semantic Gatekeeper (fast Bedrock model; heuristic fallback)
         │ labels: action | scheduled_task | social | deep_topic   (no-op → dropped, ~90 %)
         ├─ deep_topic ──► src/ingestion/event_engine.py (R0–R9 events, Titan V2 continuity,
         │                  part + final synthesis, web research)
         ▼
src/pipeline/remote.py invoke_pipeline()  → AgentCore Runtime (PIPELINE_MODE=agentcore) or in-process
src/pipeline/graph.py   LangGraph StateGraph (ExamenState), multi-label fan-out:
     nodes/action_state.py · nodes/scheduler.py · nodes/social.py · nodes/social_profiler.py
     nodes/topic_research.py (ddgs web search with SSRF guard) · nodes/persist.py
         ▼
src/core/storage/  AbstractContextStore → sqlite_store.py (FTS5)  |  dynamo/ (examen-user/-auth/-ops)
         ▼
src/serving/mcp_server.py  one Starlette app: /mcp (FastMCP, 22 tools), REST /api/*, SSE /api/events,
                           admin /api/admin/*, static dashboard (src/web_ui/out)
         ▼
Alexa+ (bearer token exm_…)        Dashboard: Overview, Peace of Mind, Daily Routines,
                                   Social Rolodex, Topic Dossiers, Ambient Simulator, Admin
```

### Key modules
| Path | Role |
|---|---|
| `src/core/config.py` | Pydantic settings from `.env` |
| `src/core/models.py` | Model factory (Bedrock Converse + Bedrock Mantle OpenAI-compatible). **All models go through here** (token counter) |
| `src/core/schemas.py` | Pydantic V2 contracts: `ExamenState`, `PlannedTask`, `ChunkClassification`, … |
| `src/core/tenancy.py` | Per-user tenant scope; `MissingTenant` is fail-closed |
| `src/core/storage/` | `base.py` interface, `rules.py` shared domain rules, SQLite and DynamoDB backends |
| `src/core/runtime_settings.py` | Admin-tunable settings registry |
| `src/core/service_log.py` | Sanitised service log + incident codes |
| `src/ingestion/` | Bee stream, orchestrator, gatekeeper, event engine, topic continuity, backfill, coverage, pairing, speaker identity |
| `src/pipeline/` | LangGraph graph, AgentCore entrypoint (`app.py`), remote invoke, nodes, tools |
| `src/serving/` | MCP server, auth/admin routes, tool modules (`action`, `curation`, `ingestion`, `session`, `social`, `topic`) |
| `src/web_ui/` | Next.js 14 + React 18 + Tailwind + SWR, static export, built with Bun |

### The 22 MCP tools
- Base (12): `create_planned_task`, `get_upcoming_tasks`, `verify_action_status`, `get_daily_actions_recap`, `query_social_contact`, `get_contact_profile`, `get_social_commitments`, `get_topic_briefing`, `get_session_dossier`, `list_session_dossiers`, `get_live_event_outline`, `get_ingestion_coverage`
- Curation edits (3): `update_action`, `update_planned_task`, `update_contact`
- Two-step deletes (4): `delete_action`, `delete_planned_task`, `delete_contact`, `delete_session_dossier`
- Speaker review (3): `list_items_to_review`, `accept_item`, `dismiss_item`

### Behaviours that surprise people
- **Speaker review:** speech not tagged to the wearer within `BEE_SPEAKER_TAG_WAIT_SECONDS` produces items in status `review` (Review tray), not in the main lists, unless auto-accept is on (`SPEAKER_AUTO_ACCEPT_UNTAGGED` / per-user Account setting).
- **Tasks follow the person who must do them:** "Marco, send me the docs" becomes Marco's task, not yours.
- **Gatekeeper fallback:** without model credentials or with `MOCK_AI=true`, an English-only regex heuristic classifies (`_heuristic_classify`). It matches *remind me to / remember to / don't forget to / need to …*, not "remember me to".
- **Bee payloads differ from the official docs:** no speaker in `new-utterance`, ISO `spoken_at`, relative `start/end`. Read `docs/10_bee_cli_reference.md` before touching Bee parsing.
- **`EVENT_PROFILE=demo`** shortens the event-engine timers (20 s / 90 s) for live demos.

---

## 4. Deployments

| Target | State | Notes |
|---|---|---|
| **AWS (production)** | Live since 2026-10-21 at `https://examen.devgiov.com` (CloudFront → EC2 in eu-central-1) | DynamoDB `examen-user/-auth/-ops` (eu-central-1); pipeline on **AgentCore Runtime** (`PIPELINE_MODE=agentcore`, in-process fallback); Bedrock in **us-east-1**, model Nemotron Super 3 120B. Stacks in `deploy/aws/` (`compute.yaml`, `dynamodb.yaml`, `agentcore.yaml`, `iam/`). Runbook: doc 17 |
| **Homelab** | Proxmox LXC test instance since 2026-10-19 | `deploy/homelab/` (`deploy.sh`, systemd units, auto-update timer). Doc 11 |
| **MCP endpoint** | `https://examen.devgiov.com/mcp` | Bearer token per user (`Account → Alexa+ / MCP access tokens`) |

Admin and account credentials live outside the repo (SSM / the maintainer); never put them in docs or code.

---

## 5. Development environment (this machine)

### Nix flake + direnv
- `flake.nix` (nixos-unstable) defines one dev shell with **`python3`** (latest in nixpkgs, currently 3.14: the `.venv` caches are `cpython-314`), `pip`, `virtualenv`, **`bun`**, **`nodejs`** (fallback for tools that need Node) and `git`.
- `.envrc` is `use flake`, so with direnv the shell loads on `cd` into the repo. Without direnv: `nix develop` from the repo root.
- The **shellHook** creates `.venv` if missing, activates it, then runs `pip install -r requirements.txt` and `pip install -e .` **on every shell entry** (slow on first load, quick afterwards).
- One-off commands without an interactive shell: `nix develop -c <cmd>`, e.g.
  - `nix develop -c pytest`
  - `nix develop -c python -m src.serving.mcp_server`
  - `nix develop -c bash -c "cd video-pitch && npm run dev"`
- The README's `uv sync` path also targets `.venv`. Pick one installer per venv; the Nix shell uses pip.
- Production runs Python **3.12** (`deploy/homelab`, AgentCore); the Nix shell is newer. Keep code 3.11+-compatible.
- Agent rule (`.cursorrules`): rely on Nix flakes and Docker; never suggest global OS-level installs.

### Everyday commands
| Task | Command |
|---|---|
| Tests (SQLite) | `.venv/bin/pytest tests/` (31+ modules, 588 tests per AGENTS.MD) |
| Tests (DynamoDB via moto) | `EXAMEN_TEST_STORAGE=dynamo .venv/bin/pytest tests/` |
| Run server + dashboard | `python -m src.serving.mcp_server` → `http://localhost:8000/` (MCP at `/mcp`) |
| Build dashboard | `./scripts/build_ui.sh` (= `cd src/web_ui && bun install && bun run build`) |
| Mock conversations | `python scripts/simulate_mock_conversations.py --help` |
| Event-engine replay / calibration | `python scripts/replay_event_scenarios.py --calibrate` |
| Live benchmark (Bedrock) | `python scripts/run_live_benchmark.py` |
| Users (operator CLI) | `python scripts/manage_users.py` |
| Bee spike | `python scripts/bee_spike.py check` (needs `bee login`) |
| Video (Remotion) | `cd video-pitch && npm run dev` (Studio), `npm run render` (v1), `npm run render:v2` (v2) |

Tests never run the real `bee` binary (`tests/conftest.py` stubs it).

---

## 6. Rules that matter most (from AGENTS.MD)

1. **English only** in code, comments, docs and commits. **Relative paths only** in docs; no local usernames in committed paths.
2. **`resources/` is read-only.**
3. Cross-module data uses **Pydantic V2** schemas from `src/core/schemas.py`; LangGraph state is `ExamenState`.
4. Storage only through `AbstractContextStore` / `get_storage_store()`; a store change updates **both** backends; DynamoDB requests stay in the tenant's partition, **never `Scan`**.
5. Background work for a user runs inside `tenant_scope(user_id)`; no per-user objects in module globals; dispatch the pipeline via `invoke_pipeline()`.
6. Loggers under `examen.*`; **no user content in logs** (`tests/test_admin_console.py` checks).
7. Models only through `src/core/models.py`; LLM calls through `llm_slot()`.
8. Every `bee` subprocess passes `env=bee_subprocess_env()`; never `bee logout` the host.
9. User edits/deletes go through `src/serving/tools/curation_tools.py`.
10. Keep `mcp>=1.10.0,<2.0.0` (2.0 breaks AgentCore compatibility).
11. Log non-obvious problems in `FRICTION_LOG.md` (Problem / Root cause / Resolution).

---

## 7. Documentation map

| Doc | Read it for |
|---|---|
| `README.md` | Vision, quickstart, tracks, benchmark numbers |
| `AGENTS.MD` | Agent rules, layout, commands (authoritative) |
| `FRICTION_LOG.md` | Known gotchas (Bee CLI, Bedrock, MCP behind proxies, DynamoDB, AWS deploy) |
| `docs/01–07` | Baseline architecture (partly outdated: earlier window model, fewer tools) |
| `docs/08` | Telemetry and Bee hardware contracts |
| `docs/10` | **Real Bee CLI payloads** |
| `docs/12` | Repo audit (19 Oct, with a 23 Oct status note) |
| `docs/13` | Multi-user accounts, pairing, tokens, GDPR |
| `docs/14` | Hackathon rules, AWS quotas and prices |
| `docs/15–17` | AWS split architecture, data layer choice, deployment runbook (live) |
| `docs/18` | **Video pitch v1** script and production guide |
| `docs/19` | **Video pitch v2**: live "remind me about Danilo" demo, line-by-line VO timing |
| `docs/next_steps/` | Specs per feature (event engine, backfill, DynamoDB, admin console, curation, speaker review, Alexa add-on) and `ROADMAP.md` |
| `.agents/rules/`, `.cursor/rules/` | UI, data-fetching, git, security, devops standards |

---

## 8. Known inconsistencies to watch

- **Model names:** v1 pitch visuals and `.env.example` say Nova Micro (gatekeeper) + Claude 3.5 Sonnet (reasoner); the live deployment uses Nemotron Super 3 120B in us-east-1 (doc 17). The README mentions others too. Say "Bedrock models" unless you have checked the running config.
- **Cost claims:** "< $0.01/day" (pitch v1) vs "~$0.04/day" for continuous listening (README benchmark).
- **Test counts:** 588 (AGENTS.MD, README) vs 476/473 (doc 17 at deploy time); a quick grep finds ~533 `def test_` functions (parametrised tests raise the collected count).
- **Docs 01–07** describe an earlier design (sliding window, 5 tools, vanilla UI); trust the code and docs 08+.
- **v1 Alexa scene** listed tool names that do not exist (`list_commitments`, `get_briefing_report`, …); v2 uses the real names.

---

## 9. Video pitch assets (`video-pitch/`)

Remotion 4.0.538 project (React 19, TypeScript, `@remotion/media`, `@remotion/transitions`). Run it inside the Nix shell (needs Node ≥ 20.19).

| Composition | What | Status |
|---|---|---|
| `ExamenPitchVideo` + `Scene1-…`–`Scene7-…` | **v1**, 7 scenes, 2:57, subtitles baked into scenes | Unchanged |
| `v2/ExamenPitchVideoV2` | **v2**, 8 scenes, 2:54.5: v1 content re-timed + live Danilo scene + voiceover track | New (2026-10-23) |
| `v2/ExamenPitchVideoV2-Guide` | v2 with teleprompter overlay, for recording the voiceover | New |
| `v2/V2Scene03-LiveReminder` | The new live scene alone | New |

v2 timing lives in `video-pitch/src/v2/voiceover-v2.json`; `npm run vo:placeholders` writes silent WAVs to `public/voiceover-v2/` (missing files only). Full guide: `docs/19_video_pitch_v2_script_live_demo.md`.

Screen recording: no cap.so connection was available to the agent on 2026-10-23, so the scenes use animated mockups; doc 19 §5 has the shot list for recording the clips by hand.
