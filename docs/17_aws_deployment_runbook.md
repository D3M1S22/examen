# 🚀 17 — AWS Deployment Runbook (readiness and plan)

> **Document Status:** **Phase 1 deployed** on 2026-10-21, 23:25 CEST.
> - URL: **https://examen.devgiov.com**, served by CloudFront with an ACM certificate (us-east-1), DNS-only CNAME at Cloudflare. The distribution's own URL https://dxovk55s504hk.cloudfront.net keeps working.
> - Stacks: `examen-compute` (instance `i-0d044dbe01e1e85a4`, EIP 52.59.154.82, distribution `E36UWEYZRX6X14`) and `examen-data`, both in eu-central-1.
> - Bundle `841b14d120c2`.
> - Admin `admin@examen.cloud`. The password was changed from the dashboard on 2026-10-21 23:04 UTC, so the SSM parameter `/examen/bootstrap-admin-password` only holds the first, now invalid, value.
> - **Phase 2 live** (23:45 CEST): the pipeline runs on **AgentCore Runtime** `arn:aws:bedrock-agentcore:eu-central-1:301356686376:runtime/examen_pipeline-Vhjiwg2S4f` (direct code deployment, Python 3.12 ARM64). The host has `PIPELINE_MODE=agentcore`, with in-process fallback.
> - Smoke results: §6.1 and §6.2.
> **Related:** [06](06_aws_cloud_deployment_architecture.md) (hosting options and costs, option A chosen), [15](15_aws_split_architecture_report.md) (AgentCore split), [16](16_aws_data_layer_k3.md) and [next_steps/dynamodb_storage/](next_steps/dynamodb_storage/00_overview.md) (data layer, deployed), [11](11_homelab_test_deployment.md) (homelab scripts reused here), [14](14_aws_and_hackathon_reference.md) (hackathon rules)
> **Deadline:** Fri 23 Oct 2026, 12:00 PT (21:00 CEST).

---

## 1. Readiness

### 1.1 Ready
| Item | State | Evidence |
|---|---|---|
| Application | One process (REST, SSE, MCP, dashboard, per-user Bee ingestion), suites green on SQLite (476) and DynamoDB (473 + 3 skipped) | [dynamodb_storage/07](next_steps/dynamodb_storage/07_implementation_plan_and_testing.md) §0 |
| Data layer | Stack `examen-data` in **eu-central-1**: `examen-user`, `examen-auth`, `examen-ops` (on-demand, PITR, TTL, deletion protection), tenant role, runtime and AgentCore policies | Schema check clean; IAM simulator 8/8; live `dynamo_iam_check.py` 10/10 |
| Tenant isolation | `DYNAMO_TENANT_ROLE_ARN=arn:aws:iam::301356686376:role/examen-tenant-data` | A request on another user's partition gets `AccessDeniedException` |
| Bedrock | Models answer in **us-east-1** (Nemotron Super 3 120B; Titan V2 listed) with the `Examen` user | Converse probe, 21 tokens |
| Host scripts | `deploy/homelab/deploy.sh`, `update.sh`, `examen.service` (Debian/Ubuntu, `uv`, Python 3.12, systemd hardening) | Running on CT 147 |
| Bee CLI | `resources/bee-cli/dist/platforms/linux-x64/bee` (x86 only) | Used by `deploy.sh` |
| Health probe | `GET /api/health` (unauthenticated liveness) | Used by `update.sh` |
| SSE behind a proxy | User and admin SSE send `: keepalive` every 15 s (under CloudFront's 30 s origin timeout) | [mcp_server.py](../src/serving/mcp_server.py) |

### 1.2 Missing
| # | Item | Why it matters | Owner | Estimate |
|---|---|---|---|---|
| M1 | **Compute stack** `deploy/aws/compute.yaml`: EC2, security group, instance role, CloudFront, artifact bucket | Nothing runs the app on AWS yet | Claude | 1.5 h |
| M2 | **Code delivery** without GitHub access: the repo `D3M1S22/amazon_challenge` is **private** (the API answers 404 anonymously), so the instance cannot `git pull` | `update.sh` assumes `git fetch`. The instance needs a bundle from S3 (or a deploy key) | Claude | 1 h |
| M3 | **Bootstrap and update** for EC2: `deploy/aws/bootstrap.sh` (user data) and `deploy/aws/update.sh` (run through SSM Run Command) | No SSH on the instance (SSM only) | Claude | 1 h |
| M4 | **Cloud `.env`**: DynamoDB backends, tenant role, Bedrock region, public URL settings, closed sign-up, bootstrap admin from SSM Parameter Store | Several defaults are wrong behind CloudFront (§4) | Claude | 0.5 h |
| M5 | **AgentCore pipeline** (optional for the deadline): `PIPELINE_MODE=local\|agentcore`, a remote invoke client, the runtime deployed from `src/pipeline/app.py` | AgentCore showcase; with DynamoDB the remote pipeline writes the user's data directly (doc 16) | Claude | 4–6 h |
| M6 | **Branch**: the deployment code is on `aws`, 6 commits ahead of `main` | The bundle can come from any branch, but the submission and future updates should track `main` | Team | 10 min (review + merge) |
| M7 | **Submission requirements**: no `LICENSE` file; the repo is private | The repo must be public with an OSS license, or shared with the judges (doc 14) | Team | 15 min |

### 1.3 Blockers (account owner)
| # | Blocker | Found | Unblocks |
|---|---|---|---|
| **B1** | The `Examen` IAM user (the app's identity) has no rights on CloudFormation, EC2, IAM, CloudFront, S3, SSM or ECR (`AccessDenied` on list calls). The root keys used for the data stack were removed, as recommended | 2026-10-21 | Every step from §5.2 on |
| **B2** | **Bedrock in eu-central-1** answers *"Your account is currently being verified … normally less than 2 hours"*. us-east-1 works | Converse and InvokeModel probes, 2026-10-21 | Optional: Bedrock in the same region as compute and data. **Not blocking**: phase 1 keeps Bedrock in us-east-1 |

**B1 options** (one is needed):
- **B1-a ★ (recommended)**: grant `Examen` the temporary deploy policy of Appendix A, scoped to `examen-*` resources. Claude deploys and verifies; the owner removes the policy after the deadline. About 10 minutes in the IAM console.
- **B1-b**: the owner deploys `compute.yaml` from the CloudFormation console (as for the data stack) and runs the SSM commands of §5.3. Slower round trips, the same result.

---

## 2. Target for the deadline

```
                        CloudFront (https://dXXXX.cloudfront.net, default certificate)
 Browser / Echo / MCP ──►   behaviour * : CachingDisabled, AllViewerExceptHostHeader, all methods
                              │  HTTP :8000 (security group: CloudFront origin-facing prefix list only)
                              ▼
            EC2 t3a.small (x86, Ubuntu 24.04, eu-central-1, IMDSv2, SSM, no SSH)
              systemd examen: REST · SSE · /mcp · dashboard · per-user bee proxy + ingestion
              EBS gp3 20 GB encrypted: /var/lib/examen/data (Bee tokens, logs only)
              instance role: Bedrock (us-east-1) · examen-runtime-data (DynamoDB + AssumeRole tenant)
                              │                                  │
                              ▼                                  ▼
            DynamoDB eu-central-1 (deployed)          Bedrock us-east-1 (switch to eu-central-1
            examen-user / -auth / -ops                 from the admin console once B2 clears)
                              ▲
            (phase 2) AgentCore Runtime eu-central-1: pipeline, tenant role per invocation
```

**Why this shape:**
- Doc 06 option A: one always-on host, because the Bee streams are long-lived.
- DynamoDB removes the database from the host. The EBS volume only keeps Bee tokens and logs, so losing the instance loses no user data.
- CloudFront gives HTTPS with no domain or certificate work. The origin is reachable only from CloudFront.
- `t3a.small` (2 GB) instead of `t3a.medium`: no SQLite cache or backfill writes on the host any more. About 115 MB idle, plus 50–80 MB per Bee proxy, leaves headroom for 5 users.

**Monthly cost** (eu-central-1):
- t3a.small ≈ $16;
- public IPv4 $3.6;
- EBS 20 GB ≈ $1.9;
- CloudFront (free tier) $0;
- DynamoDB ≈ $5–6;
- S3 artifacts < $0.1.

That is **≈ $27 per month plus model tokens** (doc 06 §7).

---

## 3. Decisions for this deployment

| # | Topic | Decision | Alternative kept open |
|---|---|---|---|
| R1 | Hosting | EC2 single instance (doc 06 H1 = A) | Fargate after the Bee tokens leave the disk |
| R2 | Region | Compute and data in **eu-central-1**; Bedrock in **us-east-1** until B2 clears, then switch from the admin console (`AWS_REGION` is a runtime setting; `DYNAMO_REGION` is not) | Bedrock in eu-central-1 from day one if B2 clears before the deploy |
| R3 | HTTPS | CloudFront default domain and certificate | Route 53 domain + ACM certificate later |
| R4 | Credentials | **Instance role**: no AWS keys in the cloud `.env` (doc 06 H4) | — |
| R5 | Code delivery | **S3 bundle** built locally (code, built dashboard, `bee` binary), installed by bootstrap and by an SSM-run update script | GitHub deploy key + today's `update.sh` once the repo is reachable |
| R6 | OS | Ubuntu 24.04 LTS (x86): the homelab scripts are apt-based, and the Canonical AMI ships the SSM agent | Amazon Linux 2023 |
| R7 | Sign-up | **Closed** (`AUTH_ALLOW_SIGNUP=false`): the admin creates accounts (doc 06 H8) | Open sign-up behind WAF |
| R8 | Pipeline | In-process for the first deploy; AgentCore as phase 2 behind `PIPELINE_MODE` with a local fallback | — |

---

## 4. Cloud configuration (`/opt/examen/.env` on the instance)

Written by `bootstrap.sh`. The admin password comes from SSM Parameter Store and never sits in the user data.

| Key | Value | Why |
|---|---|---|
| `AUTH_ENABLED` | `true` | Multi-user |
| `AUTH_ALLOW_SIGNUP` | `false` | R7 |
| `AUTH_COOKIE_SECURE` | `true` | CloudFront talks HTTP to the origin and sends no `X-Forwarded-Proto` (only `CloudFront-Forwarded-Proto`), so `auto` would issue non-Secure cookies |
| `MCP_HOST` / `MCP_PORT` | `0.0.0.0` / `8000` | CloudFront custom origin port |
| `MCP_ALLOWED_HOSTS` | `*` | The origin only accepts CloudFront traffic (security group), and the Host header is the EC2 name (AllViewerExceptHostHeader) |
| `CORS_ALLOWED_ORIGINS` | `https://<distribution>.cloudfront.net` | **Required.** CloudFront sends the EC2 host name as `Host` (AllViewerExceptHostHeader). Without the allow-listed origin, the CSRF origin check refuses browser logins with *"Request origin not allowed."*. `scripts/aws_deploy.py stack` now sets it from the stack output |
| `STORAGE_BACKEND`, `AUTH_STORE_BACKEND`, `OPS_STORE_BACKEND` | `dynamo` | Data layer |
| `DYNAMO_REGION` / `DYNAMO_TABLE_PREFIX` | `eu-central-1` / `examen-` | Deployed stack |
| `DYNAMO_TENANT_ROLE_ARN` | `arn:aws:iam::301356686376:role/examen-tenant-data` | IAM isolation |
| `AWS_REGION` | `us-east-1` | Bedrock (R2) |
| `GATEKEEPER_PROVIDER` / `REASONER_PROVIDER` and model ids | as in the local `.env` | Same behaviour as tested |
| `EXAMEN_BOOTSTRAP_ADMIN` / `EXAMEN_BOOTSTRAP_ADMIN_PASSWORD` | from `/examen/bootstrap-admin-email` and `/examen/bootstrap-admin-password` (SecureString) | First admin. The password must not contain the e-mail's local part (`password_problem`) |
| `AUTO_START_USER_ORCHESTRATORS` | `true` | Streams resume after a restart |
| `EXAMEN_DATA_DIR` | `/var/lib/examen/data` | Set by `examen.service` |

---

## 5. Runbook

### 5.1 Work that needs no AWS rights (Claude, ≈ 3.5 h, can start now)
1. **`deploy/aws/compute.yaml`**:
   - **Parameters:** `InstanceType` (t3a.small), `ArtifactBucketName`, `BedrockRegion`, `DataStackRuntimePolicyArn` (output of `examen-data`).
   - **Security group:** inbound TCP 8000 only from the managed prefix list `com.amazonaws.global.cloudfront.origin-facing`; no port 22.
   - **Instance role** with:
     - `AmazonSSMManagedInstanceCore`;
     - `bedrock:InvokeModel*` and `bedrock:Converse*` on the used models and inference profiles in `BedrockRegion`;
     - the `examen-runtime-data` managed policy;
     - `s3:GetObject` on the artifact bucket and `ssm:GetParameter` on `/examen/*`.
   - **Instance:** Ubuntu 24.04 AMI from the public SSM parameter `/aws/service/canonical/ubuntu/server/24.04/stable/current/amd64/hvm/ebs-gp3/ami-id`, IMDSv2 required, 20 GB gp3 encrypted, user data calling `bootstrap.sh`.
   - **CloudFront:** custom origin on the instance's public DNS, HTTP port 8000, origin read timeout 60 s. Default behaviour: *CachingDisabled* + *AllViewerExceptHostHeader*, all HTTP methods, HTTPS redirect.
   - **Outputs** and a CloudWatch auto-recover alarm.
   - Validate with `cfn-lint`. A test parses the template like `test_dynamo_schema.py` and checks: no 22/0.0.0.0, IMDSv2, encryption.
2. **`scripts/aws_bundle.sh`**: `scripts/build_ui.sh`, then a `tar` of the tracked code (same excludes as `deploy.sh`) plus `src/web_ui/out` and the `bee` binary. Uploads it to `s3://<bucket>/bundles/<git-sha>.tgz` and moves `bundles/current` to it.
3. **`deploy/aws/bootstrap.sh`** (idempotent, run by cloud-init):
   - apt packages, the `examen` user, `uv` + Python 3.12, `/usr/local/bin/bee`;
   - unpacks the bundle into `/opt/examen`, creates the venv, installs `requirements.txt`;
   - writes the `.env` of §4 (the admin from SSM);
   - installs `deploy/homelab/examen.service`, enables it and starts it;
   - health check on `/api/health`.
4. **`deploy/aws/update.sh`**: downloads `bundles/current`, swaps `/opt/examen` atomically (keeps the previous release), reinstalls dependencies if `requirements.txt` changed, restarts, and runs the health check with rollback (the same logic as the homelab `update.sh`). It is run with `AWS-RunShellScript` through SSM.
5. **Doc 11 / this doc**: commands, smoke list, teardown.

### 5.2 Deployment (needs B1)
| Step | Command / action | Who | Check |
|---|---|---|---|
| 1 | Create the artifact bucket and the SSM parameters `/examen/bootstrap-admin-email`, `/examen/bootstrap-admin-password` (SecureString) | Claude (B1-a) or owner | Parameters readable by the role only |
| 2 | `scripts/aws_bundle.sh` | Claude | `bundles/current` points to the commit |
| 3 | Deploy `compute.yaml` as stack `examen-compute` in eu-central-1 | Claude (B1-a) / owner (B1-b) | `CREATE_COMPLETE`, CloudFront domain in the outputs (≈ 5–10 min for CloudFront) |
| 4 | Wait for the bootstrap (cloud-init, ≈ 5 min); read the log through SSM | Claude | `systemctl is-active examen`; Health `storage: dynamo`, `tenant_isolation: true` |
| 5 | Set `CORS_ALLOWED_ORIGINS` to the CloudFront domain (SSM command + restart) | Claude | Dashboard loads over HTTPS |
| 6 | Smoke list (§6) | Claude, then team | All green |
| 7 | Pair a real Bee from the dashboard (QR) | Team | Live stream in the admin Health view |

### 5.3 Updates after the first deploy
`scripts/aws_bundle.sh`, then:

```bash
aws ssm send-command --document-name AWS-RunShellScript --targets Key=tag:Name,Values=examen \
  --parameters commands='/opt/examen/deploy/aws/update.sh'
```

The equivalent is also available from the console (*Systems Manager → Run Command*).

### 5.4 Phase 2: AgentCore pipeline (≈ 4–6 h, after the first deploy is green)
1. **Code**:
   - `src/pipeline/remote.py`: a `bedrock-agentcore` client `invoke_agent_runtime(agentRuntimeArn, runtimeSessionId=<session_id padded to 33+ chars>, payload)`.
   - `PIPELINE_MODE=local|agentcore` (boot key) in `orchestrator.py`, `backfill.py` and `/api/simulate`. The invocation is never retried (it is not idempotent).
     - If the runtime did not receive the payload (connection, credentials, throttling, other 4xx), it falls back to local, with event code `pipeline.remote_fallback`.
     - If the runtime may have run it (read timeout, dropped connection, 5xx, 424, unreadable answer), nothing runs locally. Event code `pipeline.remote_unknown`. The chunk is marked `failed` in the ledger and the backfill analyses it again. Ids derived from `source_key` (action, task, briefing) make that retry idempotent.
   - The payload already carries `user_id` (checked by `agent_invocation`). The remote store uses the tenant role, and token usage is flushed to ops (already implemented).
2. **Deploy**: AgentCore starter toolkit (`agentcore configure` / `agentcore launch`, ARM64 container built in CodeBuild) in eu-central-1:
   - execution role with `examen-agentcore-data` attached (`AgentCoreRoleName` parameter of the data stack: a stack update) and Bedrock invoke rights;
   - environment: the DynamoDB values of §4, `AUTH_ENABLED=true`.
   - Needs the AgentCore part of Appendix A.
3. **Tests**: unit tests with a stubbed client (fallback, payload, tenant mismatch); then the live smoke with `PIPELINE_MODE=agentcore` on the instance; latency in the admin Health view.
4. **Go / no-go**: if it is not green by Fri 23 Oct 12:00 CEST, the submission ships with the in-process pipeline. AgentCore is then described as the next step (doc 15).

---

## 6. Smoke list (cloud)
1. `https://<domain>/` loads the dashboard; `/api/health` → 200.
2. The bootstrap admin logs in **with the browser's `Origin` header**; the session cookie is `Secure` and `HttpOnly`. A cookie write from a foreign `Origin` gets 403 `origin_not_allowed`.
3. The admin creates a user. Sign-up from the login page is refused (closed).
4. As the user: create a routine, run `/api/simulate` with a completing sentence, and check that the routine is completed and the action appears.
5. The SSE stream stays open more than 2 minutes through CloudFront (keep-alives received).
6. MCP: an access token from *Account → MCP access tokens*; `scripts/test_mcp_client.py` against `https://<domain>/mcp` lists the tools.
7. Admin console: Health shows `storage: dynamo`, `tenant_isolation: true`, no open critical incident; token usage counts the simulate call.
8. GDPR export downloads; erasing a test account leaves its DynamoDB partition empty.
9. Bee pairing by QR on a real device; the live stream reaches the Health view.

### 6.1 Results, 2026-10-21 (through CloudFront)
- HTTP → HTTPS redirect, the dashboard and `/api/health` work.
- Admin login works; the session cookie is `Secure` and `HttpOnly`.
- Public sign-up is refused (403).
- The admin created a user. The user logged in, created a routine, and `/api/simulate` (real Bedrock in us-east-1 + DynamoDB in eu-central-1, 3.1 s) completed it.
- SSE stayed open 75 s (6 keep-alives).
- MCP `initialize` with an access token works (200).
- Health shows `storage: dynamo`, `tenant_isolation: true`; token usage counted 2 calls.
- GDPR export works; erasing the test account leaves only the admin.
- The instance uses the `examen-compute-instance` role: no AWS keys on disk.
- Not yet done: item 9 (pairing a real Bee), which needs the device.
- **Fixed 2026-10-22:** a browser login returned *"Request origin not allowed."* because `CORS_ALLOWED_ORIGINS` was not set (§5.2 step 5 was skipped). The smoke client sent no `Origin` header and missed it. Now set on the host, and the smoke list checks it.

### 6.2 Results, phase 2 (AgentCore)
- Direct invocation with a synthetic user: the remote pipeline completed the user's task in DynamoDB using the **tenant role** (`Scoped DynamoDB credentials issued` in the runtime log). The test data was then erased.
- Through CloudFront with `PIPELINE_MODE=agentcore`: three `/api/simulate` calls (action, scheduled task, safety action) took 8.0 s (cold microVM), then 2.6 s and 2.2 s.
- No `pipeline.remote_fallback` event was logged. Token usage shows the runtime's gatekeeper and extraction calls, flushed to the shared ops table.
- The first host call before logging was enabled took 53 s inside the runtime, and it was never reproduced. Most likely cause: Bedrock throttling on the new account's default quotas (botocore retries with back-off). The runtime now logs `examen.*` to `/aws/bedrock-agentcore/runtimes/examen_pipeline-Vhjiwg2S4f-DEFAULT`.

### 6.3 Operations
| Task | Command |
|---|---|
| New release on the host | `scripts/aws_bundle.py` then `scripts/aws_deploy.py update` |
| New runtime version | `scripts/agentcore_deploy.py deploy` (data-stack policy, role stack, package, runtime update) |
| Pipeline back in-process | `scripts/agentcore_deploy.py disable-host` (`enable-host` switches it back) |
| Host logs | `scripts/aws_deploy.py logs` |
| Change boot-only `.env` keys | `scripts/aws_deploy.py env KEY=VALUE [KEY=]` (empty value removes the key; restart + health check). Runtime settings, such as self-registration, are changed from the admin console instead |
| Admin password | SSM Parameter Store `/examen/bootstrap-admin-password` (eu-central-1) |
| Re-create the compute stack in AgentCore mode | `scripts/aws_deploy.py stack --param PipelineMode=agentcore --param AgentCoreRuntimeArn=<arn>` |

### 6.4 Custom domain (2026-10-22)
1. ACM certificate `b8a993a7-…` for `examen.devgiov.com` in us-east-1, DNS-validated with a CNAME at Cloudflare.
2. Stack update with `DomainName` and `CertificateArn`. `aws_deploy.py stack` then set `CORS_ALLOWED_ORIGINS` to both URLs.
3. Cloudflare: `examen` CNAME `dxovk55s504hk.cloudfront.net`, **DNS only**. A proxied record would put a second CDN in front, which buffers SSE.

Smoke on `https://examen.devgiov.com`: 10/10.
- Browser-style login, with `Secure` + `HttpOnly` cookie.
- `/api/simulate` through AgentCore (8.6 s cold); the routine was completed.
- SSE stayed open more than 60 s.
- MCP worked.
- A foreign `Origin` was refused.
- No remote fallback was logged.
- The test account was erased.
- The CloudFront URL still works.

The first update attempt ended in `UPDATE_ROLLBACK_FAILED`, because the broad managed policies had been removed while the stack needed EC2 rights. The fix was to attach `examen-admin` (Appendix C) and then run `ContinueUpdateRollback`.

## 7. Rollback and teardown
- **Bad update:** `update.sh` keeps the previous release and rolls back when the health check fails.
- **Broken instance:** terminate it and re-create the stack. Data is in DynamoDB (PITR). Only the Bee logins are lost: users pair again.
- **Teardown after the hackathon:** delete `examen-compute` (instance, CloudFront, bucket). The data stack has deletion protection, so it is removed only on purpose.
- **Temporary rights:** remove the Appendix A policy from `Examen` after the deadline.

## 8. Timeline to the deadline
| When (CEST) | Work |
|---|---|
| Wed 21, night | Decide on B1 and M6/M7 |
| Thu 22, morning | §5.1 (artifacts), then §5.2 once B1 is solved: first deploy and smoke |
| Thu 22, afternoon | §5.4 AgentCore (optional), live smoke |
| Fri 23, until 12:00 | Go / no-go on AgentCore, video recording (IAM denial, DynamoDB console, live dashboard), submission checklist (doc 15 §6) |

---

## Appendix A — Temporary deploy policy for `Examen` (B1-a)

Attach as an inline policy and remove it after the deadline. Resources are limited to `examen*` names wherever the service supports it. CloudFront and EC2 `Run`/`Describe` calls do not support resource scoping for every action.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {"Sid": "Stacks", "Effect": "Allow", "Action": "cloudformation:*",
     "Resource": "arn:aws:cloudformation:eu-central-1:301356686376:stack/examen-*/*"},
    {"Sid": "StackRead", "Effect": "Allow", "Action": ["cloudformation:ValidateTemplate", "cloudformation:ListStacks",
     "cloudformation:DescribeStacks"], "Resource": "*"},
    {"Sid": "Compute", "Effect": "Allow", "Action": ["ec2:*", "cloudfront:*", "cloudwatch:PutMetricAlarm",
     "cloudwatch:DeleteAlarms", "cloudwatch:DescribeAlarms"], "Resource": "*"},
    {"Sid": "Roles", "Effect": "Allow", "Action": ["iam:CreateRole", "iam:DeleteRole", "iam:GetRole", "iam:PassRole",
     "iam:TagRole", "iam:PutRolePolicy", "iam:DeleteRolePolicy", "iam:GetRolePolicy", "iam:AttachRolePolicy",
     "iam:DetachRolePolicy", "iam:CreateInstanceProfile", "iam:DeleteInstanceProfile", "iam:GetInstanceProfile",
     "iam:AddRoleToInstanceProfile", "iam:RemoveRoleFromInstanceProfile", "iam:CreateServiceLinkedRole"],
     "Resource": ["arn:aws:iam::301356686376:role/examen-*", "arn:aws:iam::301356686376:instance-profile/examen-*",
                  "arn:aws:iam::301356686376:role/aws-service-role/*"]},
    {"Sid": "DataStackUpdate", "Effect": "Allow", "Action": ["iam:CreatePolicyVersion", "iam:DeletePolicyVersion",
     "iam:GetPolicy", "iam:GetPolicyVersion", "iam:ListPolicyVersions", "iam:AttachUserPolicy", "iam:DetachUserPolicy"],
     "Resource": ["arn:aws:iam::301356686376:policy/examen-*", "arn:aws:iam::301356686376:user/Examen"]},
    {"Sid": "Artifacts", "Effect": "Allow", "Action": "s3:*",
     "Resource": ["arn:aws:s3:::examen-*", "arn:aws:s3:::examen-*/*"]},
    {"Sid": "Ops", "Effect": "Allow", "Action": ["ssm:PutParameter", "ssm:GetParameter", "ssm:DeleteParameter",
     "ssm:SendCommand", "ssm:GetCommandInvocation", "ssm:ListCommandInvocations", "ssm:DescribeInstanceInformation",
     "ssm:StartSession", "ssm:GetParameters"], "Resource": "*"},
    {"Sid": "AgentCorePhase2", "Effect": "Allow", "Action": ["bedrock-agentcore:*", "ecr:*", "codebuild:*",
     "logs:*", "xray:*"], "Resource": "*"}
  ]
}
```

## Appendix B — Missing rights after the 2026-10-21 check

`Examen` now holds `CloudFrontFullAccess`, `AmazonEC2FullAccess`, `IAMFullAccess`, `AmazonS3FullAccess` (plus Bedrock and `examen-runtime-data`). That covers EC2, CloudFront, the instance role and the artifact bucket (`examen-artifacts-301356686376-euc1`, created, bundle uploaded).

Still denied: CloudFormation, SSM (parameters, Run Command, public AMI parameter), CloudWatch Logs, and for phase 2 AgentCore, ECR and CodeBuild. The user already has 9 managed policies (the default quota is 10), so the missing rights go in **one inline policy** (`examen-deploy`):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {"Sid": "Stacks", "Effect": "Allow", "Action": "cloudformation:*",
     "Resource": ["arn:aws:cloudformation:eu-central-1:301356686376:stack/examen-*/*",
                  "arn:aws:cloudformation:eu-central-1:aws:transform/*"]},
    {"Sid": "StackGlobal", "Effect": "Allow", "Action": ["cloudformation:ValidateTemplate", "cloudformation:ListStacks",
     "cloudformation:GetTemplateSummary", "cloudformation:DescribeStacks"], "Resource": "*"},
    {"Sid": "Parameters", "Effect": "Allow", "Action": ["ssm:PutParameter", "ssm:GetParameter", "ssm:GetParameters",
     "ssm:DeleteParameter", "ssm:AddTagsToResource"],
     "Resource": ["arn:aws:ssm:eu-central-1:301356686376:parameter/examen/*",
                  "arn:aws:ssm:eu-central-1::parameter/aws/service/*"]},
    {"Sid": "RunCommand", "Effect": "Allow", "Action": ["ssm:SendCommand", "ssm:GetCommandInvocation",
     "ssm:ListCommandInvocations", "ssm:ListCommands", "ssm:DescribeInstanceInformation", "ssm:StartSession",
     "ssm:TerminateSession", "ssm:ResumeSession"], "Resource": "*"},
    {"Sid": "Logs", "Effect": "Allow", "Action": "logs:*", "Resource": "*"},
    {"Sid": "AgentCorePhase2", "Effect": "Allow", "Action": ["bedrock-agentcore:*", "ecr:*", "codebuild:*", "xray:*"],
     "Resource": "*"}
  ]
}
```

After the deadline, remove this inline policy and the broad managed ones (`IAMFullAccess`, `AmazonEC2FullAccess`, `CloudFrontFullAccess`, `AmazonS3FullAccess`, `AWSCodeDeployFullAccess`, `AmplifyBackendDeployFullAccess`, `AmazonSageMakerCanvasDirectDeployAccess`). The app needs only Bedrock and `examen-runtime-data`; on EC2 it uses the instance role instead.

## Appendix C — Permanent and temporary policies for `Examen` (2026-10-22)

These replace Appendices A and B and the broad AWS-managed policies. They are customer-managed policies rather than inline ones, because an IAM user's inline policies are capped at 2,048 characters **in total**.

| Policy | File | Keep | Grants |
|---|---|---|---|
| `examen-base` | [deploy/aws/iam/examen-base.json](../deploy/aws/iam/examen-base.json) | **Yes** | Bedrock for local and homelab runs; releases: bundle upload, `aws_deploy.py update` / `logs` / `env` through SSM on the `project=examen` instance only; the admin password parameter; runtime logs |
| `examen-admin` | [deploy/aws/iam/examen-admin.json](../deploy/aws/iam/examen-admin.json) | **No**: detach and delete after setup and tests | `examen-*` stacks; EC2, CloudFront, ACM; `examen-*` tables, buckets, roles and policies; SSM parameters and sessions; AgentCore; logs and alarms |
| `examen-runtime-data` | managed by the `examen-data` stack | Yes | DynamoDB auth/ops and the tenant role (homelab/local on DynamoDB) |

The running service needs **none** of these: EC2 uses the `examen-compute-instance` role and AgentCore uses `examen-agentcore-runtime`.
