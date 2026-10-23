# amazon\_challenge — Repository Report

Oct 19, 2026 · @damiano shushku

> [!NOTE]
> **Status Update (23 Oct 2026):** Many historical findings identified below have been addressed:
> - **AWS deployment & storage:** DynamoDB multi-table backend implemented in `src/core/storage/dynamo/` (`examen-user`, `examen-auth`, `examen-ops`), live at `https://examen.devgiov.com`, with AgentCore runtime client in `src/pipeline/remote.py`.
> - **Multi-tenant auth & isolation:** Implemented in `src/core/auth/` and `src/core/tenancy.py` (see [13_multi_user_accounts.md](13_multi_user_accounts.md)).
> - **Docs, tools and tests:** Docs aligned; MCP server serves 22 tools over Streamable HTTP; test suite comprises 588 tests across 31 files; all hardcoded absolute links converted to relative paths. Phase 13 (Alexa+ Add-on) marked as post-hackathon future integration.


## Executive summary

EXAMEN is a working local prototype: one Python process listens to the Bee wearable's live transcript stream, screens each utterance with a Bedrock model, extracts actions, contacts, tasks and topic briefings through a LangGraph pipeline, stores them in SQLite, and serves them over MCP (for Alexa+), a REST/SSE API and a Next.js dashboard. It was built for the Amazon Developer Hackathon 2026 (Bee Wearable AI track and AWS Builder mini-challenge).

- **What runs today:** the full local loop (Bee stream → gatekeeper → pipeline → SQLite → MCP/REST/UI), the Deep Topic Event Engine, historical backfill, and a homelab test instance (Proxmox LXC, live since 19 Oct 2026).
- **What is still a plan:** the AWS deployment (AgentCore Runtime, DynamoDB, AgentCore Memory, S3/CloudFront). The `dynamo` and `agentcore_memory` storage backends raise `NotImplementedError`, and the AWS deploy scripts named in the docs do not exist.
- **Size:** about 16,800 lines of Python in `src/`, 14,300 lines of TypeScript in the UI, 331 test functions across 17 test files, 35 Markdown documents under `docs/`, 78 commits.
- **Biggest documentation issue:** docs 01–07 describe an earlier design (30–45 s sliding window, 5 MCP tools, a vanilla HTML/JS UI, 66 or 85 tests). The code has moved on: screening is per utterance, there are 12 MCP tools, the UI is Next.js, and the test suite has 331 tests. Docs 08, 10, 11 and `next_steps/` are current.

## Repository structure

The project code lives in `src/` (five packages), with tests, scripts and a homelab deploy kit beside it; `resources/` holds two read-only Git submodules used as reference.

| Path | What it holds | Size |
| --- | --- | --- |
| `src/core/` | Settings (`config.py`), dual-provider model factory (`models.py`), Pydantic V2 contracts and `ExamenState` (`schemas.py`), storage interface + SQLite/FTS5 store | `sqlite_store.py` alone is \~90 KB |
| `src/ingestion/` | Bee stream client and proxy, orchestrator, gatekeeper, ring buffer, Deep Topic Event Engine, topic continuity, backfill, coverage ledger, speaker identity, legacy session manager | 14 modules, largest `event_engine.py` (\~83 KB) and `backfill.py` (\~54 KB) |
| `src/pipeline/` | LangGraph graph, AgentCore entrypoint (`app.py`), nodes (action, social, social profiler, scheduler, topic research, persist), web search tool | 6 nodes + 1 tool |
| `src/serving/` | FastMCP server with REST, SSE and static UI (`mcp_server.py`, \~87 KB) and MCP tool modules | 12 MCP tools, 44 REST/SSE routes |
| `src/web_ui/` | Next.js 14 + React 18 + Tailwind + SWR dashboard, built with Bun to a static export in `out/` | 6 views, \~20 UI components |
| `tests/` | Pytest suite; `conftest.py` stubs the real `bee` binary | 17 files, 331 tests |
| `scripts/` | Live benchmark, live tester, mock-conversation simulator, event-scenario replay/calibration, Bee spike tool, DB reset/populate, MCP client test, UI build | 10 scripts |
| `deploy/homelab/` | `deploy.sh` (rsync + systemd) and `examen.service` | 2 files |
| `docs/` | Architecture, pipeline, serving, strategy, stack, AWS, structure, telemetry, frontend gaps, Bee CLI reference, homelab; `next_steps/` roadmap and two sub-specs | 35 files, \~460 KB |
| `resources/` | Submodules `agentcore-samples` (awslabs) and `bee-cli` (bee-computer) | reference only |
| `.agents/`, `.cursor/` | Rules and workflows for AI coding agents (architect, QA, UI, git, secrets) | 22 small files |
| Root | `README.md`, `AGENTS.MD`, `FRICTION_LOG.md`, `Dockerfile`, `pyproject.toml`, `requirements.txt`, `uv.lock`, `flake.nix`, `.env.example` |  |

**Tech stack:** Python 3.11+, LangGraph, `langchain-aws` (Bedrock Converse) and `langchain-openai` (Bedrock Mantle), Pydantic V2, `mcp>=1.10,<2` (FastMCP over Starlette/Uvicorn), SQLite + FTS5, `ddgs` web search, Titan Text Embeddings V2 for topic similarity; Next.js 14 static export for the UI; `uv` and a Nix flake for environments.

## How it works

Everything runs inside one process started by `python -m src.serving.mcp_server`: the Starlette app hosts the MCP endpoint, the REST/SSE API, the static dashboard and, as a background task, the Bee ingestion orchestrator. The pipeline is invoked in-process through `agent_invocation()`; the same function is the AgentCore Runtime entrypoint when deployed.

&#91;embedded content: runtime architecture · one process, SQLite, three client surfaces\]

Every chunk passes the gatekeeper and the event engine; only qualified chunks reach the pipeline, and the backfill service replays missed history through the same pipeline.

### The path of one utterance

1. **Capture.** `BeeClient` (`stream_convo.py`) reads Bee's real-time stream. The default transport is raw SSE through a private `bee proxy` on 127.0.0.1, so the 30 s pings prove liveness; after 3 failures it falls back to `bee stream --json`. Events handled: `new-utterance`, `tagged-utterance` (speaker identity), `new-utterance-chunks` (Bee conversation id mapping), conversation summaries, locations.
2. **Buffer and context.** `BeeStreamOrchestrator` turns each utterance into an `UtteranceChunk` (spoken time, speaker role, last recent GPS fix from `bee locations current`) and pushes it into a 4-chunk `ContextRingBuffer` per conversation.
3. **Screen.** The gatekeeper (`gatekeeper.py`) classifies the single utterance into `social`, `action`, `deep_topic`, `scheduled_task` or `noop`. Its prompt is extended with the rolling context, the open event's topic, and all pending task titles. Without credentials, with `MOCK_AI=true`, or on any model error, a regex heuristic classifier takes over.
4. **Event engine.** Every chunk, including `noop`, goes to the Deep Topic Event Engine before dispatch. It groups lecture/meeting speech into events (ACTIVE → PAUSED → CONCLUDED, rules R0–R9) using time, GPS, pause/closing cues and topic similarity (Titan V2 embeddings, heuristic or LLM judge).
5. **Drop or dispatch.** `noop` chunks are recorded in the ingest ledger and stop. Qualified chunks wait up to 1.5 s for a speaker tag, then go to `agent_invocation()` on a worker thread.
6. **LangGraph fan-out.** `route_categories()` fans out to `extract_action`, `extract_social` (with optional web profiler), `extract_scheduled_task`, and `topic_research`. Topic research runs per utterance only when no event owns the chunk; otherwise the event engine synthesizes per segment and per event.
7. **Persist.** All branches converge on `persist`, which writes through `AbstractContextStore` (SQLite), auto-resolves pending tasks from verified actions, provisions tasks for user commitments, links micro-events to the open event, and records latency telemetry.
8. **Serve.** Writes are broadcast on the `/api/events` SSE stream. Alexa+ (or any MCP client) reads through 12 MCP tools on `/mcp`; the dashboard reads REST endpoints and renders Echo Show card templates.

### Background loops

- **Synthesis jobs.** On a soft close (pause, checkpoint) the engine synthesizes a segment briefing; on a hard close it builds a consolidated event briefing from the segments, reusing a per-event query ledger and a 24 h web-search cache.
- **Backfill.** A coverage ledger records when live screening was healthy. On startup and reconnect, `BackfillService` finds gaps in the last `BACKFILL_LOOKBACK_DAYS` (default 2), pulls final transcripts with `bee conversations`, removes utterances already seen live, and replays the rest through the same path on an isolated event engine with a virtual clock. Results carry `ingest_source="backfill"`.
- **Tick loop.** The engine ticks every 15 s so timers fire during silence.

## Component deep dive

Each module has one job; the tables below list what each one owns.

### Core (`src/core/`)

| Module | Responsibility |
| --- | --- |
| `config.py` | `pydantic-settings` `Settings`: providers, model ids, storage backend, MCP host/port, all `BEE_*`, `EVENT_*`, `BACKFILL_*`, `TOPIC_*` knobs, `MOCK_AI` |
| `models.py` | `get_chat_model()` returns `ChatBedrockConverse` (SigV4) or `ChatOpenAI` pointed at Bedrock Mantle with a minted short-term token; `get_fast_model()` (gatekeeper tier), `get_reasoner_model()`, `get_embedding_model()` (Titan V2) |
| `schemas.py` | All Pydantic V2 contracts: `ChunkClassification`, `VerifiedAction`, `PlannedTask`, `SocialEntity`, `SocialCommitment`, `SocialWebProfile`, `BriefingReport`, `UtteranceChunk`, `LocationTelemetry`, `SessionDossier`/`SessionSegment`, backfill models, and the `ExamenState` TypedDict |
| `storage/base.py` + `sqlite_store.py` | `AbstractContextStore` and its only implementation. 14 tables: `planned_tasks`, `verified_actions`, `social_contacts`, `social_commitments`, `topic_briefings`, `utterance_diarization`, `session_dossiers`, `session_chunks`, `web_search_cache`, `ingest_coverage`, `ingest_ledger`, `bee_conversation_map`, `backfill_runs`, `system_telemetry`, plus FTS5 indexes. Migrations are non-blocking `ALTER TABLE`s at start-up |
| `storage/__init__.py` | `get_storage_store()` singleton; `dynamo` and `agentcore_memory` raise `NotImplementedError` |

### Ingestion (`src/ingestion/`)

| Module | Responsibility |
| --- | --- |
| `stream_convo.py` | `BeeClient` (subprocess per CLI call, binary resolution incl. bundled `dist/platforms/*/bee`), `BeeProxy`, pure `parse_bee_payload` and `SseFrameParser` |
| `orchestrator.py` | `BeeStreamOrchestrator`: reader/worker split, ring buffer, gatekeeper call, event-engine feed, speaker-tag wait, location polling, pipeline dispatch, ingest ledger |
| `gatekeeper.py` | Prompt builder (context + active tasks), structured-output classifier, heuristic fallback, `is_noop` |
| `ring_buffer.py` | 4-chunk FIFO per conversation; context text, rolling hint, late speaker patching |
| `bee_identity.py` | Wearer name from `bee me` (or `BEE_WEARER_NAME`) → `user` / `contact` / `unknown` |
| `event_engine.py` | Pure, clock-injectable state machine (R0–R9), segments, synthesis job queue, manual pause/resume/split/merge, rehydration on restart |
| `topic_continuity.py` | Topic profile, micro-windows, similarity backends, calibrated thresholds (0.42 / 0.37 embedding) |
| `coverage.py`, `bee_history.py`, `backfill.py` | Coverage tracker and gaps; Bee REST history source; planner, de-duplication, replay executor, `BackfillService` triggers and budget guards |
| `scenario_replay.py` | Virtual-clock replay of `resources/event_scenarios.json` for tests and calibration |
| `session_manager.py` | Legacy per-conversation sessions; now mainly shared helpers (haversine) |

### Pipeline (`src/pipeline/`)

| Module | Responsibility |
| --- | --- |
| `app.py` | `BedrockAgentCoreApp` entrypoint. Accepts many payload keys (`raw_transcript`, `transcript_chunk`, `prompt`…), screens if no categories were given, builds `ExamenState`, runs the graph, serializes results |
| `graph.py` | `StateGraph`: conditional fan-out from `START` to 4 nodes, fan-in to `persist` |
| `nodes/action_state.py` | Completed-action verifier; rejects intentions and doubts, uses context for anaphora, heuristic fallback |
| `nodes/social.py` + `social_profiler.py` | Contact and bilateral commitment extraction (debtor from speaker role); web profiler with 2-anchor disambiguation, source evaluation and contamination guards |
| `nodes/scheduler.py` | Future intentions → `PlannedTask` (`origin=ambient_voice`), deterministic relative-time parser |
| `nodes/topic_research.py` | Topic extraction → research → synthesis, reused by the event synthesizer (segment / final) |
| `nodes/persist.py` | Writes entities, task auto-resolution, commitment-to-task provisioning, micro-event linking, backfill temporal guards |
| `tools/web_search.py` | Multi-tier DuckDuckGo search with query normalization, relevance filtering, SSRF checks and prompt-injection defence |

### Serving (`src/serving/`)

MCP tools: `create_planned_task`, `get_upcoming_tasks`, `verify_action_status`, `get_daily_actions_recap`, `query_social_contact`, `get_contact_profile`, `get_social_commitments`, `get_topic_briefing`, `get_session_dossier`, `list_session_dossiers`, `get_live_event_outline`, `get_ingestion_coverage`. Each returns a `display_template` (for example `ACTION_VERIFIED_BADGE`, `SOCIAL_PROFILE_CARD`, `SESSION_DOSSIER_VIEWER`) and a `card_payload` for Echo Show.

REST groups: `/api/auth/*` (demo sessions, Bee pairing, GDPR purge), `/api/orchestrator/*`, `/api/status`, `/api/events` (SSE), `/api/routines`, `/api/actions`, `/api/contacts`, `/api/commitments`, `/api/topics`, `/api/sessions/*` (event operations), `/api/simulate`, `/api/event-scenarios`, `/api/backfill/*`, `/api/cards/preview`. The UI export in `src/web_ui/out` is mounted at `/` and `/ext-app/`.

### Web UI (`src/web_ui/`)

A single-page Next.js app (`app/page.tsx`) with six views: Overview Hub, Peace of Mind, Daily Routines, Social Rolodex, Topic Dossiers (events timeline, folders, Markdown viewer and `.md` export), and Ambient Simulator (typed transcripts and event-scenario player). Supporting pieces: System Bar and Status Dock (Bee/SSE/Bedrock badges, latency), an Echo Show 15 simulator modal, Backfill modal, Login modal, and a typed API layer in `types/schemas.ts`. Data is fetched with SWR and refreshed from SSE events.

## Documentation review

I read all 35 documents under `docs/` plus `README.md`, `AGENTS.MD` and `FRICTION_LOG.md`. They fall into three generations: the original design (01–07, partly outdated), the device-verified reference set (08, 10, 11, 07-alignment, current), and the `next_steps/` specifications (accurate as specs, but several status headers were never updated).

### Top-level guides

| Doc | What it covers | Accuracy against the code |
| --- | --- | --- |
| `01_architecture_flow.md` | 5-stage flow (screen → route → extract → store → serve), Mermaid diagram, store tables, 5 MCP tools | Outdated: describes a 30–45 s sliding window with 5 s overlap (code screens each utterance), omits `scheduled_task`, the event engine and backfill |
| `02_bedrock_agentcore_pipeline.md` | Model tiering table, Pydantic schemas, node code, graph, AgentCore packaging | Illustrative only: node names (`action_node`…), `llm_gatekeeper` and schemas differ from the code; the gatekeeper is no longer a graph node |
| `03_alexa_mcp_serving.md` | MCP tool specs with JSON examples, Echo Show wireframes, `addon.json` | 5 of 12 tools; no `addon.json` exists in the repo; ext-app path is `/ext-app/`, not `/ext-app/index.html` on a tunnel |
| `04_hackathon_strategy_demo.md` | Judging alignment, prize pool, 3-minute video script, 4-sprint plan | Strategy, not code; still usable as a demo script |
| `05_tech_stack_resources.md` | Submodules, libraries, model table, external services | Says the UI is vanilla HTML/CSS/JS (it is Next.js 14); otherwise accurate |
| `06_aws_cloud_deployment_architecture.md` | Target AWS topology: AgentCore Runtime, Memory, DynamoDB, S3, CloudFront | Not implemented: no AWS code, no cloud storage backends |
| `07_repository_structure_modules.md` | Repository tree and module duties | Lists files that do not exist (`dynamo_store.py`, `memory_store.py`, `deploy/build_agentcore_bundle.sh`, `deploy_agentcore_runtime.py`, `deploy_ext_apps_s3.sh`, `alexa_addon.json`, `web_ui/index.html`/`app.js`, `tests/fixtures/`); says 272 tests in the tree and 85 in the commands |
| `08_real_telemetry_and_bee_hardware_spec.md` | Bee capabilities table, device states, `system_telemetry`, `/api/status` contract, per-view UI bindings | Current (updated 19 Oct 2026) |
| `09_frontend_gaps_from_next_steps.md` | Gap analysis after merging `Next_steps` into `update/web_ui` (links tray, disambiguation audit drawer, simulator presets) | Historical: commit `8b94ed3` implemented the P0/P1 items, but the doc still reads as an open assessment |
| `10_bee_cli_reference.md` | Observed bee-cli/API contract: commands, payloads, timestamps, stream events, lifecycle, locations, and audit C1–C16 | Current and declared the source of truth for Bee data; the strongest document in the set |
| `11_homelab_test_deployment.md` | Proxmox LXC instance, deploy script, Bee login on the server, operations, limits | Current; contains LAN IPs and hostnames, which is fine for a private repo |

### `next_steps/` refinement specs

| Doc | What it covers | Status |
| --- | --- | --- |
| `00_overview.md` | Six refinement areas and schema evolution | Says 89/89 tests; links are absolute `file:///home/deggio/...` paths (breaks the AGENTS.MD portability rule) |
| `01_deep_topic_contextual_synthesis.md` | `explanatory_synthesis`, adaptive prompt per `context_type` | Implemented (M1.1) |
| `02_gatekeeper_context_and_multimodal_telemetry.md` | Ring buffer, GPS, async diarization | Implemented (M3.1), with "reality check" notes pointing to doc 10 |
| `03_session_merging_and_micro_event_splitting.md` | `SessionDossier`, micro-event linking | Superseded for `deep_topic` by the event engine; cites a non-existent `src/core/database.py` |
| `04_ambient_scheduled_tasks.md` | `scheduled_task` category, Stage 3D scheduler, `get_upcoming_tasks` | Implemented (M1.2); links point to `src/pipeline/nodes/gatekeeper.py` (real path is `src/ingestion/`) |
| `05_structured_social_commitments.md` | Debtor/creditor commitments, auto-provisioned tasks | Implemented (M1.3) |
| `06_social_web_enrichment.md` | Public-web contact profiler with disambiguation and privacy guardrails | Implemented (M2.1); mentions Tavily, which the code does not use |
| `07_bee_data_alignment.md` | Fix plan for the 19 Oct device findings (C1–C16, I1–I9) | Phases 0–5 done; phase 6 (end-to-end on device + Bedrock) pending |
| `ROADMAP.md` | Status board for phases 1–6, per-milestone work breakdown, dependency graph | Mostly current; Phase 0 cites wrong paths (`src/core/model_factory.py`, `src/pipeline/nodes/gatekeeper.py`) |

### Deep Topic Event Engine (`next_steps/deep_topic_event_engine/`, 8 docs)

Specifies events, segments, the R0–R9 state machine, topic continuity, synthesis scheduling (segment, checkpoint, final), storage, integration, serving/UI and the test plan. Doc 07 records phases A–E as implemented on 13 Oct 2026 and the code matches (`event_engine.py`, `topic_continuity.py`, 42 + 24 + 19 tests). The overview header still says "not yet implemented", and its audit table (findings 1–12) describes the pre-engine code. The cost model claims a 2-hour lecture drops from \~60 synthesis calls to 3–4.

### Historical Transcript Backfill (`next_steps/historical_backfill/`, 7 docs)

Specifies Bee history sources, the coverage ledger and de-duplication, the replay engine with temporal guards and triggers, data model/API/UI, the implementation plan, and the Phase 0 device spike runbook and results. Doc 05 §0 lists phases 0–5 as implemented with ten documented deviations; phase 6 (optimisations) is not started. Again the overview header still says "not yet implemented".

### Root documents

- **`README.md`**: vision, three domains, quickstart, benchmark claims (25/25 scenarios on Nemotron 3 Super 120B, $0.0084 total), doc index and TODO list. Says 272 tests; the suite now has 331.
- **`AGENTS.MD`**: rules for AI agents (English only, relative paths, `resources/` read-only, Pydantic contracts, storage only via the interface, `mcp<2`). Its tree is outdated (66 tests, vanilla UI files, 5 tools) and it has two sections numbered 6.
- **`FRICTION_LOG.md`**: 13 dated entries (28 Sep–19 Oct 2026) on NVIDIA models in `ChatBedrockConverse`, Mantle routing, FastMCP schema inspection, Titan V2 similarity scale, Bee stream envelope, `bee proxy --socket` idle timeouts. Well kept and useful.

## Setup, running and configuration

The system starts with one command once Python deps, the UI build and (optionally) the Bee CLI are in place; without AWS credentials or with `MOCK_AI=true` every model call falls back to heuristics, so the dashboard and tests work offline.

### Local run

```bash
uv sync                                   # or: pip install -r requirements.txt
cp .env.example .env                      # AWS keys, providers, model ids
./scripts/build_ui.sh                     # bun install && bun run build -> src/web_ui/out
python -m src.serving.mcp_server          # http://localhost:8000  (MCP at /mcp)
pytest                                    # 331 tests; tests/conftest.py stubs the bee binary
```

For live Bee data: `git submodule update --init resources/bee-cli`, build the binary with Bun (`bun build ./sources/main.ts --compile ...`), run `bee login` and approve it in the Bee app with Developer Mode enabled. `scripts/bee_spike.py check` validates the account and captures raw payloads into the git-ignored `.bee-spike/`.

### Endpoints

| URL | Purpose |
| --- | --- |
| `/` and `/ext-app/` | Dashboard and Echo Show ext-app (same static export) |
| `/mcp` | MCP Streamable HTTP for Alexa+ or any MCP client |
| `/api/*` | REST API (status, routines, contacts, commitments, sessions, backfill…) |
| `/api/events` | SSE stream that drives live UI updates |

### Key settings (`.env`)

| Group | Variables | Defaults |
| --- | --- | --- |
| Models | `GATEKEEPER_PROVIDER`, `REASONER_PROVIDER` (`bedrock` / `mantle`), `BEDROCK_GATEKEEPER_MODEL`, `BEDROCK_REASONER_MODEL`, `BEDROCK_MANTLE_*` | `bedrock`; `amazon.nova-micro-v1:0` and `anthropic.claude-3-5-sonnet-20241022-v2:0` |
| Storage | `STORAGE_BACKEND`, `SQLITE_DB_PATH` | `sqlite`, `examen.db` (only SQLite works) |
| Bee | `BEE_STREAM_TRANSPORT`, `BEE_PROXY_PORT`, `BEE_STREAM_PING_TIMEOUT_SECONDS`, `BEE_SPEAKER_TAG_WAIT_SECONDS`, `BEE_LOCATION_POLL_SECONDS`, `BEE_WEARER_NAME` | `proxy`, `0`, `90`, `1.5`, `120` |
| Event engine | `EVENT_ENGINE_ENABLED`, `EVENT_PROFILE`, `EVENT_T_SOFT_SECONDS`, `EVENT_T_HARD_SECONDS`, `EVENT_T_CHECKPOINT_SECONDS`, `EVENT_MIN_SEGMENT_WORDS` | `true`, `default`, 300, 1800, 1200, 300 (`demo` profile: 20 s / 90 s) |
| Topic continuity | `TOPIC_SIMILARITY_BACKEND`, `BEDROCK_EMBEDDING_MODEL`, `TOPIC_SIM_SAME` / `TOPIC_SIM_DIFFERENT`, `TOPIC_LLM_JUDGE` | `embedding`, Titan V2 (512 dims), 0.42 / 0.37, `true` |
| Backfill | `BACKFILL_ENABLED`, `BACKFILL_AUTO_ON_STARTUP` / `_ON_RECONNECT`, `BACKFILL_LOOKBACK_DAYS`, `BACKFILL_MAX_ESTIMATED_COST_USD`, `BACKFILL_LIVE_COVERAGE_FRACTION` | `true`, `true`, 2, 1.0, 0.5 |
| Serving | `MCP_HOST`, `MCP_PORT`, `WEB_SEARCH_CACHE_TTL_SECONDS` | `0.0.0.0`, 8000, 86400 |

### Scripts

| Script | Use |
| --- | --- |
| `run_live_benchmark.py` | 25-scenario live evaluation with latency and cost tracking (source of the README numbers) |
| `live_tester.py`, `simulate_mock_conversations.py` | Drive the running server with live or mock conversations |
| `replay_event_scenarios.py --calibrate` | Replay `resources/event_scenarios.json` and recalibrate topic thresholds |
| `bee_spike.py` | Phase 0 device spike: account checks and raw captures |
| `reset_db.py`, `populate_db.py` | Reset or seed `examen.db` |
| `test_mcp_client.py` | Exercise the MCP endpoint as a client |

### Deployment targets

- **Homelab (live):** `deploy/homelab/deploy.sh` rsyncs the working tree to a Proxmox LXC, installs `uv`, Python 3.12, the Bee binary and `examen.service` (systemd). Plain HTTP on the LAN, no auth.
- **Docker:** a two-stage `python:3.11-slim` image. It copies a pre-built `src/web_ui/out` (git-ignored, so it must be built first), does not include the Bee binary, and passes `--host/--port` flags that `run_server()` ignores (the defaults happen to match).
- **AWS:** designed in doc 06, not implemented.

## Gaps, risks and recommendations

The code is ahead of most of its documentation; the two things most likely to hurt a submission are the AWS story (claimed, not built) and the open, unauthenticated API.

| # | Issue | Evidence | Recommendation |
| --- | --- | --- | --- |
| 1 | AWS deployment claimed but absent | `dynamo` / `agentcore_memory` raise `NotImplementedError`; no AgentCore bundle or deploy scripts; doc 06 and README pitch them for the AWS Builder track | Ship at least one real AWS path (pipeline on AgentCore Runtime, or the MCP server on App Runner) or mark doc 06 clearly as "target design" |
| 2 | No authentication on `/mcp` or `/api/*`; CORS `*` with credentials | `create_app()` CORS settings; `/api/auth/login` takes any handle, sessions live in memory | Add a bearer token (or tunnel auth) before exposing the server; restrict CORS origins |
| 3 | Single-tenant data behind a multi-user UI | One SQLite store; `_user_sessions` holds only handles; GDPR purge acts on shared data | Say "single user" in the UI, or partition storage by user id |
| 4 | Docs 01–07 and AGENTS.MD describe an older system | Sliding window vs per-utterance screening; 5 vs 12 MCP tools; vanilla UI vs Next.js; 66 / 85 / 89 / 272 vs 331 tests; missing files listed in doc 07 | Rewrite 01 and 07 from the code, add the event engine and backfill to the architecture flow, and stop hard-coding test counts |
| 5 | Stale status headers and broken links in `next_steps/` | DTEE and backfill overviews say "not yet implemented"; `file:///home/deggio/...` links in 00, 01, 03–06; wrong paths in ROADMAP Phase 0, 03, 04 | Update headers to "Implemented (date)", convert links to relative paths |
| 6 | Bee alignment not verified end to end | `07_bee_data_alignment.md` phase 6 pending; README unchecked items (physical wearable, `new-conversation` capture, real-lecture calibration) | Run the scripted dialogue on the homelab with the wearable and Bedrock, then update doc 10 |
| 7 | Very large modules | `EchoShowModal.tsx` 164 KB, `sqlite_store.py` 90 KB, `mcp_server.py` 87 KB, `event_engine.py` 83 KB | Split `mcp_server.py` into route modules and `sqlite_store.py` into per-domain repositories |
| 8 | Docker image cannot ingest live Bee data | No Bee binary in the image; depends on a pre-built git-ignored `out/`; unused CLI flags | Add a UI build stage and the Bee binary, or document Docker as "no live stream" |
| 9 | Dependency lists drift | `requirements.txt` has `httpx`, `langchain-core`, `langchain-community`, pytest; `pyproject.toml` does not | Make `pyproject.toml` (with a `dev` extra) the single source and generate requirements from `uv` |
| 10 | Logout disconnects Bee for the whole host | `api_auth_logout` runs `bee logout` (kept by design, C11) | Default `disconnect_bee` to false in the UI, or warn before logout |
| 11 | Benchmark numbers are a one-off | 25/25 and $0.0084 come from one run on Nemotron; `.env.example` defaults to Nova Micro + Claude 3.5 Sonnet | Record the date, model and command next to the numbers, and re-run after the alignment changes |

**Review limits:** I read the code structure and key modules, not every line, and I did not run the test suite (the project's `.venv` is tied to your Mac and is not runnable from the workspace).
