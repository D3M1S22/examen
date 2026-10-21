# ☁️ 05 — Infrastructure and Configuration

---

## 1. Infrastructure as code (D13)

**File:** `deploy/aws/dynamodb.yaml` (CloudFormation). Deployed once per environment:

```bash
aws cloudformation deploy --stack-name examen-data --template-file deploy/aws/dynamodb.yaml \
  --capabilities CAPABILITY_NAMED_IAM --region eu-central-1 \
  --parameter-overrides Prefix=examen- RuntimeRoleArn=<arn> AgentCoreRoleArn=<arn>
```

| Resource | Content |
|---|---|
| `UserTable`, `AuthTable`, `OpsTable` | `BillingMode: PAY_PER_REQUEST`; keys and GSIs from [02](02_user_store_data_model.md) §1 and [03](03_auth_and_ops_data_model.md); `TimeToLiveSpecification` on `ttl`; `PointInTimeRecoverySpecification: true`; `DeletionProtectionEnabled: true`; `StreamSpecification: NEW_AND_OLD_IMAGES` (user table only); `SSESpecification` default (AWS-owned key) |
| `TenantDataRole` | The trust policy and the `LeadingKeys` policy from [04](04_security_iam_and_tenancy.md) §1–2 |
| `RuntimeDataPolicy` (managed) | `sts:AssumeRole` + `TagSession` on `TenantDataRole`; item actions on the auth and ops tables and their indexes. Attached to the role given in `RuntimeRoleArn` |
| `AgentCoreDataPolicy` (managed) | `AssumeRole` + `TagSession` on `TenantDataRole`; `UpdateItem` on the ops table limited to `USAGE#*` and `META` (LeadingKeys). Attached to `AgentCoreRoleArn` |
| Alarms | Per table: `ThrottledRequests > 0` over 5 min, `SystemErrors > 0` over 5 min. Optional SNS topic for e-mail |
| Outputs | Table names and ARNs, the `TenantDataRole` ARN: the values of the settings in §2 |

**Single source of truth for tests.** The Python module `src/core/storage/dynamo_schema.py` holds `TABLE_SPECS`: keys, GSIs, projections and TTL in the shape expected by `CreateTable`.
- moto and DynamoDB Local tables are created from it (`scripts/dynamo_tables.py create`).
- `tests/test_dynamo_schema.py` loads the CloudFormation YAML (with a loader that ignores the `!Ref` / `!Sub` tags) and asserts that its key schema, GSIs and projections equal `TABLE_SPECS`.

## 2. Settings

All new keys are **boot-only**: they go into `BOOT_KEYS` in [runtime_settings.py](../../../src/core/runtime_settings.py). The admin console shows them read-only.

| Env var | Default | Meaning |
|---|---|---|
| `STORAGE_BACKEND` (exists) | `sqlite` | Per-user store: `sqlite` \| `dynamo` |
| `AUTH_STORE_BACKEND` | `sqlite` | Accounts: `sqlite` \| `dynamo` |
| `OPS_STORE_BACKEND` | `sqlite` | Service log, incidents, settings overrides, token usage: `sqlite` \| `dynamo` |
| `DYNAMO_REGION` | value of `AWS_REGION` **in the environment at start-up** | Never follows a runtime override of `AWS_REGION` (D15): that override moves Bedrock calls, not data. With `OPS_STORE_BACKEND=dynamo`, the overrides themselves live in DynamoDB, so the region must be known before they are read |
| `DYNAMO_TABLE_PREFIX` | `examen-` | Tables `<prefix>user`, `<prefix>auth`, `<prefix>ops`. Tests use a random prefix per session |
| `DYNAMO_ENDPOINT_URL` | empty | DynamoDB Local (`http://localhost:8001`) |
| `DYNAMO_TENANT_ROLE_ARN` | empty | Turns on IAM tenant isolation ([04](04_security_iam_and_tenancy.md) §3) |
| `DYNAMO_TELEMETRY_TTL_DAYS` | `30` | TTL of `TEL#` items |

**Start-up checks** (fail fast, logged with event code `storage.misconfigured`):
- `dynamo` without a region;
- a table that is missing, or whose key schema differs from `TABLE_SPECS` (one `DescribeTable` per table);
- `DYNAMO_TENANT_ROLE_ARN` set while `AUTH_ENABLED=false`;
- `AssumeRole` failing for a probe tag value.

The Health view shows the backend of each store and "IAM tenant isolation: on/off" (the `storage` component of `HealthMonitor.snapshot`).

## 3. Capacity, backup and encryption (D16)

| Topic | Choice | Why |
|---|---|---|
| Capacity mode | On-demand | Spiky, small traffic (backfill bursts). No capacity planning. Default quota 40 000 RRU / WRU per second per table |
| PITR | On (35 days) | Point-in-time restore after a bad deploy or migration |
| Deletion protection | On | |
| Encryption | AWS-owned key | Free. A customer-managed KMS key is optional ([04](04_security_iam_and_tenancy.md) §4) |
| Table class | Standard | Standard-IA only pays off above about 25 GB |
| Streams | User table only, no consumer | Ready for an event-driven synthesis trigger later (doc 16 M5) |

## 4. Cost (5 active users, eu-central-1 ≈ us-east-1 + 10–20 %)

| Item | Assumption | Monthly |
|---|---|---|
| Writes | ≈ 30 WRU per utterance × 1 500 utterances per user per day ([02](02_user_store_data_model.md) §8) + UI and pipeline writes ≈ 7 M WRU | ≈ $4.4 at $0.625 per million |
| Reads | Engine dossier reads (`include_chunks=False`, ≈ 7 RCU consistent), pipeline context, dashboard and MCP ≈ 5 M RRU | ≈ $0.6 at $0.125 per million |
| Storage | < 100 MB | $0 (25 GB free) |
| PITR | < 100 MB | ≈ $0.02 |
| Streams, TTL deletes | — | $0 |
| CloudWatch alarms | 6 alarms | ≈ $0.6 |
| **Total** | | **≈ $5–6** |

This supersedes the ≈ $2 estimate of [16](../../16_aws_data_layer_k3.md) §5, which ignored dossier rewrites. **Idle cost is $0**, plus storage and alarms. *(verify the eu-central-1 on-demand rates on the DynamoDB pricing page before submission.)*

## 5. Local development

| Mode | How |
|---|---|
| Default | SQLite, nothing changes |
| DynamoDB Local | `docker run -d -p 8001:8000 amazon/dynamodb-local`, then `DYNAMO_ENDPOINT_URL=http://localhost:8001 STORAGE_BACKEND=dynamo .venv/bin/python scripts/dynamo_tables.py create`, then start the server with the same env. Dummy credentials (`AWS_ACCESS_KEY_ID=local`) work |
| Real AWS (dev account) | `DYNAMO_TABLE_PREFIX=examen-dev-` with the stack deployed under that prefix; SSO credentials |
| Tests | moto in-process (no Docker, no network): [07](07_implementation_plan_and_testing.md) §3 |

## 6. Monitoring
- **CloudWatch:** the alarms in §1, plus the `ConsumedRead/WriteCapacityUnits` dashboards that come with the table.
- **In-app** (admin console, [admin_console/03](../admin_console/03_service_log_and_anomalies.md)):
  - counters in `src/core/metrics.py`: `storage.requests`, `storage.throttled`, `storage.conditional_conflicts`, `storage.latency_ms` (p95 per operation);
  - new event codes in the catalogue (doc 03 §4.5): `storage.throttled` (warning, opened as an incident when sustained for 5 minutes), `storage.unavailable` (error), `storage.item_too_large` (error), `storage.tenant_isolation_off` (warning at start-up), `storage.misconfigured` (critical).
- **Health rules:** the `HealthMonitor` treats the storage error rate like the model error rate (rule set in doc 03 §5).

## 7. Backup and restore runbook
1. **Restore** with PITR into a new table: `aws dynamodb restore-table-to-point-in-time --source-table-name examen-user --target-table-name examen-user-r20261022 --restore-date-time <ts>`. The new table has the GSIs, but TTL, PITR and Streams must be re-enabled on it.
2. **Then either:**
   - *(a) whole-table rollback:* deploy the stack with `Prefix` pointing at restored tables (rename plan in the stack); or
   - *(b) one user:* `scripts/migrate_to_dynamo.py --from-table examen-user-r20261022 --user <id>` copies that partition back ([06](06_migration_and_cutover.md) §2).
3. **Long-term archive** (optional): `export-table-to-point-in-time` to S3 (DynamoDB JSON), monthly.
