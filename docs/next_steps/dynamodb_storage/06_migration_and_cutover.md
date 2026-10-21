# 🚚 06 — Migration and Cutover (D17)

> No dual-write. Each environment switches once, during a short ingestion pause. The SQLite files stay untouched on disk as the rollback.

---

## 1. Script

**File:** `scripts/migrate_to_dynamo.py`. Logic in `src/core/storage/migration.py`, so it can be tested.

```
migrate_to_dynamo.py users   [--user <id>|--all] [--dry-run] [--verify-only]
migrate_to_dynamo.py auth    [--dry-run]
migrate_to_dynamo.py ops     [--dry-run] [--skip-events]
migrate_to_dynamo.py --from-table <restored table> --user <id>     # restore path (05 §7)
```

**Per user** (`users`):
1. Open `users/<id>/examen.db` read-only (`SQLiteContextStore`, `file:…?mode=ro`).
2. Read every table with `export_all()`. This is the same row format the DynamoDB store exports, so the mapping is tested in both directions.
3. Build items with `DynamoContextStore.items_from_rows(table, rows)`. That is the codec of [02](02_user_store_data_model.md) §5 plus the index, guard and pointer items.
4. Special cases:
   - **Chunks:** `seq` is assigned from the SQLite `rowid` order (`ORDER BY ts, rowid`), so ties keep their order.
   - **Guards** are built from the data. Duplicate names or commitment keys that the start-up purge left behind: the newest row wins (the SQLite rule).
   - **Telemetry** gets `id` = uuid and `ttl` from its timestamp (rows older than 30 days are skipped).
   - **FTS tables** are skipped.
5. Write with `BatchWriteItem` (`PutItem` semantics, so running it twice gives the same result), retrying unprocessed items with back-off. Credentials: the tenant role for that user, or the migration role.
6. **Verify.** For every SQLite table, the row count equals the count of items of that entity. A sample of 20 rows per table compares `export_all()` of both stores, field by field (floats within 1e-9, JSON compared parsed). The report goes to stdout, with counts only.

**Auth:**
- users with their email guard;
- sessions (only those not expired);
- API tokens;
- Bee links with their guard;
- audit rows (only those within the current retention).

**Ops:**
- overrides;
- history: grouped by `change_id` into change-set items;
- settings version;
- incidents;
- token usage, with `first_hour` set;
- events, with the same integer ids. The event counter is set to `max(id)` and the count to the number of rows. `--skip-events` starts the log empty.

## 2. Cutover per environment

**Homelab (CT 147), rehearsal**
1. Deploy the stack under the prefix `examen-hl-` in the chosen region.
2. Stop the service and the auto-update timer: `systemctl stop examen-update.timer examen`. The timer would otherwise restart the service in the middle of the copy. Ingestion pauses, and the backfill catch-up fills the gap afterwards. Re-enable the timer after step 7.
3. Back up the data: `tar czf /var/backups/examen-pre-dynamo.tgz /var/lib/examen/data` (taken even though the files stay unchanged).
4. Copy the data: `migrate_to_dynamo.py users --all && … auth && … ops`, then `--verify-only`.
5. Point the service at DynamoDB: set `STORAGE_BACKEND=dynamo`, `AUTH_STORE_BACKEND=dynamo`, `OPS_STORE_BACKEND=dynamo`, `DYNAMO_*` in `/opt/examen/.env`, and the credentials (an IAM user with the runtime policy; the homelab has no instance role).
6. Start the service and run the smoke list:
   - login;
   - dashboard shows the same counts;
   - `/api/simulate` creates an action;
   - an event opens;
   - the admin console Health view shows `dynamo` and the token usage card;
   - GDPR export downloads.
7. Watch for an hour: the auto catch-up (backfill) closes the stop gap, and no `storage.*` incident opens.

**AWS** (doc 06 / 15 deployment): the same steps. The host starts with `dynamo` from the beginning if it has no data. Otherwise the copy runs from the homelab files.

**Phased variant** (deadline timebox, [07](07_implementation_plan_and_testing.md) §4): only `STORAGE_BACKEND=dynamo` changes, together with `users --all`. Auth and ops stay on SQLite.

## 3. Rollback
| Situation | Action |
|---|---|
| Smoke test fails right after cutover | Stop the service, restore the previous `.env` (SQLite), start again. Nothing in the SQLite files changed. Data written to DynamoDB in the meantime is lost for the dashboard. The Bee history is still there, so the backfill can re-run that window |
| A problem found after days | A reverse export exists only as GDPR export JSON per user. A `--to-sqlite` mode is **out of scope**; restore from PITR instead ([05](05_infrastructure_and_configuration.md) §7) |
| Bad deploy corrupts items | PITR restore of the table, or of one user via `--from-table` |

## 4. After cutover
- Keep the SQLite files read-only for 30 days, then delete them, together with the `tar` backup (GDPR: no stray copies).
- `delete_tenant_data` keeps deleting the Bee folder.
- The `users/<id>/examen.db` files are no longer created when `STORAGE_BACKEND=dynamo`: `tenant_db_path` is not called in that mode.
