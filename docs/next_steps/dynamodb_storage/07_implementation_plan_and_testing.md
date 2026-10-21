# 🧪 07 — Implementation Plan and Testing

> SQLite stays the default backend in every phase. A phase merges only when the full suite is green on **both** backends.

---

## 0. Status (2026-10-21)
| Phase | Status |
|---|---|
| P0 Contract hardening and shared rules | ✅ Done: `rules.py`, every interface method abstract, contract test, `include_chunks`, `delete_all_data`, `UniqueConflict` |
| P1 `DynamoContextStore` | ✅ Done: [dynamo_store.py](../../../src/core/storage/dynamo_store.py), schema, client, I/O helpers; the whole suite is green on DynamoDB (moto), and the store, engine, backfill and account files are also green on DynamoDB Local |
| P2 IAM tenant isolation, infrastructure, AgentCore direct access | ✅ Code done: [dynamodb.yaml](../../../deploy/aws/dynamodb.yaml), `TenantCredentials`, start-up checks, Health `storage` block, [dynamo_iam_check.py](../../../scripts/dynamo_iam_check.py). ⏳ Pending: deploy the stack and run the IAM check on the real account |
| P3 `DynamoAuthStore` and `DynamoOpsStore` | ✅ Done |
| P4 Migration and cutover | ✅ Code done: [migration.py](../../../src/core/storage/migration.py), [migrate_to_dynamo.py](../../../scripts/migrate_to_dynamo.py). ⏳ Pending: the homelab rehearsal ([06](06_migration_and_cutover.md) §2) |
| P5 Follow-ups (optional) | Not started |

**Verified:**
- `.venv/bin/pytest tests/` (SQLite) and `EXAMEN_TEST_STORAGE=dynamo .venv/bin/pytest tests/` (moto) are both green.
- `EXAMEN_TEST_DYNAMO_ENDPOINT=http://localhost:8001` (DynamoDB Local) runs the store, event engine, backfill, synthesis, serving, account and admin console files: 283 tests, green.
- Smoke on DynamoDB Local, with the three stores on `dynamo` and a real server:
  - registration, a routine, `/api/simulate` completing the routine, GDPR export;
  - admin console: Health `storage` block, service log with integer ids, settings change and history, token usage;
  - account erasure leaves the user's partition empty, and no auth item mentions the user.

**Deviations from this plan:**
| # | Planned | Implemented | Why |
|---|---|---|---|
| V1 | A `make_store` fixture parametrised over both backends in one run | `tests/store_backend.py`: `new_store(path)` replaces every `SQLiteContextStore(...)` in tests. `EXAMEN_TEST_STORAGE=dynamo` runs the **whole** suite on DynamoDB (moto, fresh tables per test), and `EXAMEN_TEST_DYNAMO_ENDPOINT` switches it to DynamoDB Local. SQLite-only tests carry `@sqlite_only` (4) or a backend branch (3) | Covers every test file, not only 5, and keeps the default run at 7 minutes |
| V2 | Dossier written with `PutItem` + version condition | `UpdateItem` of every attribute + version condition. `link_micro_event_to_session` stores the version at which each link was added (`link_versions_json`), and a conflicting save re-adds only links newer than the caller's version | A plain merge re-added links that a manual split removed (FRICTION_LOG 2026-10-21) |
| V3 | — | The event engine adopts the stored version when it merges persisted links (`_merge_persisted_links`), and it also merges before a split | The split partitioned a stale link set, which lost links written by the pipeline on SQLite too |
| V4 | Tenant-role trust lists the two service roles | Trust: the account, conditioned on the `user_id` tag. Who may assume it is decided by the identity policies (`RuntimeDataPolicy`, `AgentCoreDataPolicy`) | Lets the homelab IAM user with the runtime policy use it, with no stack change |
| V5 | Separate auth / ops implementations | `DynamoAuthStore(AuthStore)` and `DynamoOpsStore(OpsStore)` inherit the shared logic (`ensure_bootstrap_admin`, summaries). A test fails if a method that opens a SQLite connection is not overridden | No duplicated business rules |
| V6 | — | `delete_tenant_data(uid)` also erases the DynamoDB partition; `list_tenant_ids()` reads the auth store; the AgentCore entrypoint flushes token usage after each invocation when ops is on DynamoDB | Erasure, start-up and token counting work unchanged |

## 1. Phases

### P0 — Contract hardening and shared rules (≈ 0.5 day)
| Change | Files |
|---|---|
| Align `base.py` with the SQLite signatures (§5 of [01](01_current_state.md)) and make every method abstract. New methods: `delete_all_data()`, and `get_session_dossier(session_id=None, include_chunks=True)` | `src/core/storage/base.py`, `sqlite_store.py` |
| Extract the pure rules (`task_keywords`, `action_matches_task`, `commitment_matches_action`, `commitment_key`, `contact_name_key`, `latency_summary`, `sql_like`) and the row → model mappers | new `src/core/storage/rules.py`; `sqlite_store.py` calls them |
| `SessionDossier._store_version` (`PrivateAttr`, never serialised) | `src/core/schemas.py` |
| The event engine's `_save` reads with `include_chunks=False` | `src/ingestion/event_engine.py` |
| `UniqueConflict` exception (SQLite maps `IntegrityError` in `save_bee_link`) | `src/core/storage/errors.py`, `src/core/auth/store.py` |
| Replace the two raw-connection test setups with store calls | `tests/test_event_engine.py`, `tests/test_event_synthesis.py` |

**Tests:**
- `tests/test_store_rules.py`: `sql_like` against SQLite's own `LIKE` on a table of cases (accents, `_`, `%`, NULL), keyword matching, commitment key;
- `tests/test_store_contract.py`: every public method of `SQLiteContextStore` is declared in `AbstractContextStore` with the same signature. Later the same check applies to `DynamoContextStore`.

**Gate:** suite green; no behaviour change.

### P1 — `DynamoContextStore` (≈ 2–3 days)
| Change | Files |
|---|---|
| Table specs | new `src/core/storage/dynamo_schema.py` (`TABLE_SPECS`, `key_part`, prefix helpers) |
| Clients: service client, tenant credentials (P2 fills in `AssumeRole`), retry config | new `src/core/storage/dynamo_client.py` |
| Codec, paging, `batch_get`, `batch_write`, transaction chunking, index-lag test hook | new `src/core/storage/dynamo_io.py` |
| The store: 60 methods per [02](02_user_store_data_model.md) | new `src/core/storage/dynamo_store.py` |
| Factory: `_build_store(cfg, user_id)` picks the backend; SQLite paths only for `sqlite` | `src/core/storage/__init__.py` |
| Settings and `BOOT_KEYS`; start-up checks | `src/core/config.py`, `src/core/runtime_settings.py`, `src/serving/mcp_server.py` (lifespan) |
| `list_tenant_ids()` from the auth store when `STORAGE_BACKEND=dynamo` | `src/core/tenancy.py` |
| Tables for DynamoDB Local / moto | new `scripts/dynamo_tables.py` |
| Scripts aware of the backend | `scripts/reset_db.py`, `scripts/live_tester.py` |
| Dev dependency `moto[dynamodb]>=5,<6` | `requirements.txt` |

**Tests:**
- **Fixture switch.** `tests/conftest.py` gains a `store_backend` parameter, read from `EXAMEN_TEST_BACKENDS` (default `sqlite,dynamo`), and a `make_store(name)` factory:
  - `sqlite` returns `SQLiteContextStore(tmp_path / f"{name}.db")`;
  - `dynamo` returns `DynamoContextStore(user_id=<fresh usr_…>)` inside one session-scoped `mock_aws()`, with tables created once per session from `TABLE_SPECS`. A fresh partition per test gives isolation without recreating tables.
- **Ported test files.** The 5 files that build stores directly use `make_store`: `test_storage`, `test_event_engine`, `test_backfill`, `test_event_synthesis`, `test_session_manager`. That is 125 tests, run twice.
- **Full-stack run.** `EXAMEN_TEST_STORAGE=dynamo` forces `get_storage_store()` to the DynamoDB backend for the API, MCP and pipeline tests (`test_mcp_server`, `test_event_serving`, `test_backfill_api`, `test_langgraph_pipeline`, `test_pipeline_nodes`, …). This is a second CI invocation: `EXAMEN_TEST_STORAGE=dynamo .venv/bin/pytest tests/ -q`.
- **New `tests/test_dynamo_store.py`:**
  - every request carries `pk == user_id` or `g*pk` starting with `user_id#` (a recording client wrapper);
  - guard items: two concurrent `save_social_contact` with the same name give one contact; concurrent `save_social_commitment` gives one commitment and one task;
  - dossier version conflict: a link written between the engine's read and its save is kept;
  - index lag: with the hook hiding the last write from GSIs, `get_open_event` / `list_events_pending_final` still return correct results (confirm-on-read), and listings tolerate the lag;
  - chunk moves: `assign_chunks` of 70 chunks (3 transactions), idempotent on retry; order `ts, seq` kept;
  - item size: a 500 KB `deep_dive_markdown` is compressed and round-trips; above 400 KB after compression it raises `ItemTooLarge` without logging content;
  - `key_part` replaces `#`;
  - `export_all` equals the SQLite export for the same fixture data (after normalising telemetry ids);
  - `delete_all_data` leaves the partition empty and other partitions untouched.
- **New `tests/test_dynamo_schema.py`:** the CloudFormation template matches `TABLE_SPECS`.

**Gate:** both suites green; `make_store` used everywhere a store is built in tests.

### P2 — IAM tenant isolation, infrastructure, AgentCore direct access (≈ 1 day)
| Change | Files |
|---|---|
| CloudFormation stack ([05](05_infrastructure_and_configuration.md) §1) | new `deploy/aws/dynamodb.yaml` |
| `TenantCredentials` (`AssumeRole` + `TagSession`, cache, refresh) | `src/core/storage/dynamo_client.py` |
| Health: backend per store, isolation on/off, `storage.*` event codes, storage counters | `src/serving/health_monitor.py`, `src/core/metrics.py`, admin console doc 03 catalogue |
| AgentCore runtime with `STORAGE_BACKEND=dynamo`: the store is built inside `tenant_scope(payload.user_id)` (already the case in `agent_invocation`) | `src/pipeline/app.py` (start-up check only), AgentCore deployment config |
| IAM verification script: IAM policy simulator with `dynamodb:LeadingKeys` context, plus a live negative test (tenant A credentials, `GetItem` on B → `AccessDeniedException`) | new `scripts/dynamo_iam_check.py` |

**Tests:**
- unit: the credentials cache refreshes before expiry and keeps one client per user (stubbed STS);
- `scripts/dynamo_iam_check.py` against the real stack, manual, with its output pasted into the friction log or the submission.

**Gate:** the IAM check denies cross-tenant reads, writes and index queries, and allows the user's own.

### P3 — `DynamoAuthStore` and `DynamoOpsStore` (≈ 1.5–2 days)
| Change | Files |
|---|---|
| `AuthStoreProtocol`, `OpsStoreProtocol` (`typing.Protocol`), factories pick the backend | `src/core/auth/__init__.py`, `src/core/auth/store.py`, `src/core/ops_store.py` |
| Stores per [03](03_auth_and_ops_data_model.md) | new `src/core/auth/dynamo_store.py`, new `src/core/ops_dynamo_store.py` |
| `PartialWrite` handling in `flush` | `src/core/token_usage.py` |
| AgentCore writes its token usage to ops directly | `src/pipeline/app.py` (flush at the end of an invocation) |

**Tests:** `tests/conftest.py` resets the auth and ops stores on the selected backend. `test_accounts.py` and `test_admin_console.py` run on both backends. New cases:
- the email guard rejects a duplicate;
- `delete_user` resumes after a failure at each step;
- a change set of 80 keys commits atomically;
- the registry has at most 98 keys;
- event ids stay monotonic across batches;
- `before_id` pagination;
- `token_usage` `PartialWrite` does not double-count;
- `list_audit` hides entries beyond a shortened retention.

**Gate:** both suites green; console smoke on DynamoDB Local.

### P4 — Migration and cutover (≈ 0.5–1 day)
| Change | Files |
|---|---|
| Migration module and CLI ([06](06_migration_and_cutover.md)) | new `src/core/storage/migration.py`, new `scripts/migrate_to_dynamo.py` |
| `manage_users.py claim-legacy-db` goes through the migration module when `dynamo` | `scripts/manage_users.py` |
| Homelab `.env` documentation | `docs/11_homelab_test_deployment.md` |

**Tests:**
- `tests/test_migration.py`: a populated SQLite fixture (every table, including duplicate names and chunks with equal timestamps) migrates, then verifies; a second run is a no-op; the counts report is correct;
- auth and ops migration likewise.

**Gate:** the homelab rehearsal passes the smoke list in [06](06_migration_and_cutover.md) §2.

### P5 — Follow-ups (optional, after the hackathon)
- Bee tokens in Secrets Manager (stateless worker, [04](04_security_iam_and_tenancy.md) §6).
- Streams → Lambda trigger for syntheses.
- Remove the unused FTS5 tables from the SQLite store.
- API on Lambda (doc 15 S2).

## 2. File summary
| New | Modified |
|---|---|
| `src/core/storage/{rules,errors,dynamo_schema,dynamo_client,dynamo_io,dynamo_store,migration}.py`, `src/core/auth/dynamo_store.py`, `src/core/ops_dynamo_store.py`, `scripts/{dynamo_tables,dynamo_iam_check,migrate_to_dynamo}.py`, `deploy/aws/dynamodb.yaml`, `tests/test_{store_rules,store_contract,dynamo_store,dynamo_schema,migration}.py` | `src/core/storage/{base,sqlite_store,__init__}.py`, `src/core/schemas.py`, `src/core/config.py`, `src/core/runtime_settings.py`, `src/core/tenancy.py`, `src/core/token_usage.py`, `src/core/metrics.py`, `src/core/auth/{__init__,store}.py`, `src/core/ops_store.py`, `src/ingestion/event_engine.py`, `src/serving/{mcp_server,health_monitor}.py`, `src/pipeline/app.py`, `scripts/{reset_db,live_tester,manage_users}.py`, `tests/conftest.py` + the 5 store test files + `test_accounts.py`, `test_admin_console.py`, `requirements.txt`, `.env.example`, `AGENTS.MD`, `docs/next_steps/ROADMAP.md`, `docs/11_homelab_test_deployment.md` |

## 3. Test matrix
| Layer | SQLite | DynamoDB (moto) | DynamoDB Local | Real AWS |
|---|---|---|---|---|
| Store contract and rules (P0) | ✅ | ✅ | — | — |
| Store behaviour (5 files, 125 tests) | ✅ | ✅ | optional (`EXAMEN_TEST_DYNAMO_ENDPOINT`) | — |
| API, MCP, pipeline, engine (full suite) | ✅ | ✅ (`EXAMEN_TEST_STORAGE=dynamo`) | — | — |
| Dynamo specifics (guards, versions, index lag, size, keys) | — | ✅ | — | — |
| Schema versus CloudFormation | — | ✅ | — | — |
| IAM tenant isolation | — | — | — | ✅ `dynamo_iam_check.py` |
| Migration | ✅ source | ✅ target | — | rehearsal on the homelab |
| Real Bedrock + DynamoDB end to end | — | — | — | homelab smoke list |

moto does not enforce IAM conditions and is strongly consistent on indexes. These two gaps are covered by the IAM script and by the index-lag hook.

## 4. Timebox before the hackathon deadline (Fri 23 Oct 2026, 21:00 CEST)
| When | Work | Go / no-go |
|---|---|---|
| Wed 21 evening | P0 | Suite green |
| Thu 22, until 18:00 | P1 | **Both suites green by 18:00.** Otherwise stop: submit with SQLite (doc 15 P1); DynamoDB stays on its branch and appears in the submission as the documented roadmap |
| Thu 22 evening | P2: stack deployed, IAM check, homelab on `STORAGE_BACKEND=dynamo` (users only, P4 subset) | IAM check denies cross-tenant access |
| Fri 23 morning | Watch the homelab; AgentCore with `dynamo` if doc 15 S1 is deployed; record the IAM denial and the DynamoDB console for the video | No `storage.*` incident for 2 h |
| After the deadline | P3, the rest of P4, P5 | — |

## 5. Acceptance criteria
1. `.venv/bin/pytest tests/ -q` and `EXAMEN_TEST_STORAGE=dynamo .venv/bin/pytest tests/ -q` are both green.
2. Every public method of `SQLiteContextStore` exists on `DynamoContextStore` with the same signature and the same behaviour on the shared tests.
3. With `DYNAMO_TENANT_ROLE_ARN` set, a request for another user's partition fails with `AccessDeniedException`; verified on the real stack.
4. The homelab runs on DynamoDB with the same dashboard counts as before the cutover, and the GDPR export and erasure work.
5. No log line written by the new code contains attribute values (the existing grep test covers the new modules).
6. With no traffic, the AWS bill shows only storage and alarms.

## 6. Open questions
| # | Question | Proposal |
|---|---|---|
| Q1 | Region (doc 06 H2) | eu-central-1, if the gatekeeper and reasoner models pass the console probes there; otherwise eu-west-1. DynamoDB is available in both |
| Q2 | Telemetry TTL of 30 days (new behaviour) | Accept: it feeds latency averages only |
| Q3 | PITR keeps deleted data for up to 35 days | Disclose it in the privacy notice and bump `PRIVACY_NOTICE_VERSION` |
| Q4 | Customer-managed KMS key | Not for the hackathon |
| Q5 | Homelab credentials (no instance role) | An IAM user restricted to the runtime policy, keys in `/opt/examen/.env` (mode 600). Rotate after the hackathon |
| Q6 | Migrate the service log events or start empty | Migrate (keeps incident history coherent); `--skip-events` exists |
