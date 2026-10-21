# 🛡️ 04 — Security, IAM and Tenancy

> Goal: a missing filter in EXAMEN's own code cannot read or change another user's data. DynamoDB refuses the request, because the credentials in use can only touch one partition. This adds to the application isolation of [13_multi_user_accounts.md](../../13_multi_user_accounts.md) (`tenant_scope`, fail-closed `MissingTenant`); it does not replace it.

---

## 1. Roles

| Role | Assumed by | Permissions |
|---|---|---|
| `examen-runtime` (instance or task role of the worker / API host) | EC2 instance profile or ECS task role | `sts:AssumeRole` + `sts:TagSession` on `examen-tenant-data`. Full item access to `examen-auth` and `examen-ops`. **No direct access to `examen-user`**: every user-data request, erasure included (§5), goes through the tenant role. Bedrock as today |
| `examen-agentcore` (AgentCore execution role) | AgentCore Runtime | `sts:AssumeRole` + `sts:TagSession` on `examen-tenant-data`. `UpdateItem` on `examen-ops` restricted to `USAGE#*` and `META` partitions (LeadingKeys). Bedrock, CloudWatch as the AgentCore template |
| `examen-tenant-data` | The two roles above, with session tag `user_id` | Item actions on `examen-user` and its indexes, restricted to the caller's partition (§2). No `Scan`, no table management |
| `examen-migration` (optional, human) | Operator via SSO / CLI | `examen-user` full item access including `Scan`, for the one-shot migration and disaster recovery. Not attached to any running service |

The trust policy of `examen-tenant-data` requires the `user_id` tag. As implemented in [dynamodb.yaml](../../../deploy/aws/dynamodb.yaml) (07 §0, V4), the principal is the account: only identities that hold `RuntimeDataPolicy` or `AgentCoreDataPolicy` can assume the role. That includes the homelab IAM user, with no stack change. The stricter variant below lists the two roles:

```json
{
  "Effect": "Allow",
  "Principal": {"AWS": ["arn:aws:iam::<acct>:role/examen-runtime", "arn:aws:iam::<acct>:role/examen-agentcore"]},
  "Action": ["sts:AssumeRole", "sts:TagSession"],
  "Condition": {"StringLike": {"aws:RequestTag/user_id": "usr_*"}}
}
```

## 2. Tenant policy

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Sid": "OwnPartitionOnly",
    "Effect": "Allow",
    "Action": ["dynamodb:GetItem", "dynamodb:BatchGetItem", "dynamodb:Query", "dynamodb:PutItem",
               "dynamodb:UpdateItem", "dynamodb:DeleteItem", "dynamodb:BatchWriteItem",
               "dynamodb:ConditionCheckItem"],
    "Resource": ["arn:aws:dynamodb:<region>:<acct>:table/examen-user",
                 "arn:aws:dynamodb:<region>:<acct>:table/examen-user/index/*"],
    "Condition": {"ForAllValues:StringLike": {"dynamodb:LeadingKeys": [
        "${aws:PrincipalTag/user_id}", "${aws:PrincipalTag/user_id}#*"]}}
  }]
}
```

- **Transactions.** `TransactWriteItems` and `TransactGetItems` are authorised per contained action (Put, Update, Delete, ConditionCheck). Each contained item is checked against the same condition.
- **No `Scan`.** `Scan` ignores leading keys, so it is deliberately absent (DynamoDB developer guide, fine-grained access control).
- **The `#*` pattern is unambiguous.** User ids have a fixed length (`usr_` + 32 hex, `is_valid_user_id`), so no user id is a prefix of another.
- **Single-user mode.** `AUTH_ENABLED=false` uses the partition `_local`. The tenant role is not used in that mode (no tenant), so it is meant for development only. `DYNAMO_TENANT_ROLE_ARN` must be empty, and the service refuses to start with `dynamo` + tenant role + `AUTH_ENABLED=false`.

## 3. Scoped credentials in code

New module `src/core/storage/dynamo_client.py`:

```
TenantCredentials(role_arn, duration=3600)
  .client_for(user_id) -> botocore client
      cache[user_id] = (client, expires_at); refresh 5 min before expiry (lock per user)
      sts.assume_role(RoleArn, RoleSessionName=f"examen-{user_id[:16]}", Tags=[{"Key": "user_id", "Value": user_id}],
                      DurationSeconds=duration)
service_client() -> botocore client with the process credentials (auth, ops, erasure)
```

- **Who builds the client.** `get_tenant_store(user_id)` builds `DynamoContextStore(user_id, client_provider=lambda: creds.client_for(user_id))`. The store never receives a client for another user. The `user_id` passed to the store is also the `pk` of every request. A test asserts that every request built by the store carries `pk == user_id` or `g*pk` starting with `user_id#`.
- **Without `DYNAMO_TENANT_ROLE_ARN`** (local, tests, homelab), the store uses the service client. Isolation is then application-only, as it is today with SQLite. The admin Health view shows "IAM tenant isolation: off" as a warning (event code `storage.tenant_isolation_off`).
- **On AgentCore,** `agent_invocation` already validates `payload["user_id"]` and enters `tenant_scope`. The store built inside that scope assumes the tenant role for that user. Only the worker host can invoke the runtime: its resource policy allows only `examen-runtime`. A forged payload therefore requires the host's credentials.
- **Limits.** One `AssumeRole` per user per hour is far below the STS request quotas.

## 4. Encryption, backup, protection
| Control | Setting |
|---|---|
| Encryption at rest | AWS-owned key (default, free). A customer-managed KMS key (≈ $1 per month + requests) is optional: it adds key-level revocation and CloudTrail data on key use |
| In transit | HTTPS endpoints only (SDK default) |
| Point-in-time recovery | On for all three tables (35 days) |
| Deletion protection | On for all three tables |
| CloudTrail | Management events (default). Data events on `examen-user` are optional (they cost per event) and useful for an access audit |
| Logs | The store logs entity names, ids and error codes, never attribute values (AGENTS.MD F3). `ConditionalCheckFailed` and throttling are counted by the metrics module |

## 5. GDPR erasure and export
- **Erasure** (`DELETE /api/account`, `manage_users.py delete`):
  - The request runs inside the user's tenant scope: `DynamoContextStore.delete_all_data()` with the tenant credentials removes the partition.
  - Then `delete_tenant_data(uid)` removes the Bee folder on disk, `DynamoOpsStore.delete_user` and `DynamoAuthStore.delete_user` (service role).
  - A failure part-way leaves the account disabled with an incident (`account.erasure_incomplete`). The admin can retry from the console, because every step is idempotent.
- **PITR keeps deleted items restorable for up to 35 days.** This is acceptable under GDPR as a backup, provided it is disclosed. The privacy notice gains one sentence: "backups are kept for up to 35 days". The notice version is bumped (`PRIVACY_NOTICE_VERSION`), so users re-consent.
- **Export** (`export_all`) produces the same JSON shape as SQLite ([02](02_user_store_data_model.md) §3.7).

## 6. Threat model (deltas from today)
| Threat | Today (SQLite) | With DynamoDB |
|---|---|---|
| Bug in a query reads another user's rows | Impossible: separate files per user | Impossible when the tenant role is on: `LeadingKeys`. Application-only when off |
| Host disk stolen or snapshot leaked | All data readable | Only Bee tokens and logs on disk. Data is behind IAM |
| Credentials of the host leaked | Disk access needed | The attacker can assume the tenant role for any user, and read auth and ops. Mitigations: instance role (no static keys), IMDSv2, short sessions, a CloudTrail alarm on `AssumeRole` from outside the instance |
| AgentCore runtime compromised | — | Can assume any tenant (it receives arbitrary user ids). The same trust as the worker; the invocation policy limits who can call it |
| Accidental table deletion | `rm` of the data folder | Deletion protection + PITR |
| Bee token leak | On the host disk | Unchanged (D18). Follow-up: tokens in Secrets Manager (`examen/bee/<uid>`), written to a tmpfs `BEE_CONFIG_DIR` at stream start, so the worker holds no state on disk |
