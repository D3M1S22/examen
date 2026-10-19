# 02 — Identity, Authentication & Bee Accounts

> Part of the [Multi-User Support](00_overview.md) specification. Decisions D1, D3–D6, D8 of [00](00_overview.md) §3.

---

## 1. Entities (System DB)

The System DB holds user-agnostic data only. Locally it is `data/system.db` (SQLite); on AWS it is a DynamoDB table set ([04](04_serving_api_ui_aws.md) §5).

```sql
CREATE TABLE users (
    user_id        TEXT PRIMARY KEY,           -- "usr_" + 16 hex, never reused
    username       TEXT NOT NULL UNIQUE COLLATE NOCASE,
    display_name   TEXT,
    password_hash  TEXT,                       -- Argon2id; NULL for external identities (Cognito)
    external_sub   TEXT UNIQUE,                -- Cognito `sub` (AWS), NULL locally
    is_admin       INTEGER NOT NULL DEFAULT 0,
    status         TEXT NOT NULL DEFAULT 'active',   -- active | disabled | erasing
    timezone       TEXT,                       -- from Bee `me.timezone` once linked
    created_at     TEXT NOT NULL,
    last_login_at  TEXT
);

CREATE TABLE web_sessions (
    session_hash   TEXT PRIMARY KEY,           -- sha256 of the cookie value (the raw value is never stored)
    user_id        TEXT NOT NULL REFERENCES users(user_id),
    created_at     TEXT NOT NULL,
    expires_at     TEXT NOT NULL,              -- sliding, default 14 days
    user_agent     TEXT,
    revoked        INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE api_tokens (                      -- personal access tokens for MCP clients
    token_hash     TEXT PRIMARY KEY,           -- sha256(token); shown once at creation
    user_id        TEXT NOT NULL REFERENCES users(user_id),
    name           TEXT NOT NULL,              -- e.g. "Alexa dev skill", "Claude Desktop"
    scopes         TEXT NOT NULL DEFAULT 'mcp',
    created_at     TEXT NOT NULL,
    last_used_at   TEXT,
    revoked        INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE bee_links (
    user_id        TEXT PRIMARY KEY REFERENCES users(user_id),
    bee_user_id    INTEGER UNIQUE,             -- `bee me` → id: one Bee account ↔ one EXAMEN user (D1)
    bee_first_name TEXT,                       -- wearer name for tagged-utterance / REST speakers
    state          TEXT NOT NULL,              -- unlinked | pairing | linked | invalid
    pairing_url    TEXT, pairing_expires_at TEXT,
    linked_at      TEXT, last_ok_at TEXT, last_error TEXT
);

CREATE TABLE audit_log (                       -- security-relevant events, no speech content
    id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, user_id TEXT, actor_user_id TEXT,
    action TEXT NOT NULL, detail_json TEXT
);
```

`UserContext` (Pydantic, `src/core/identity.py`): `{user_id: str, is_admin: bool, auth_method: Literal["session", "api_token", "oauth", "system"]}`. It is immutable and is the only way user identity crosses module boundaries.

---

## 2. Authentication

### 2.1 Provider interface

```python
class AuthProvider(Protocol):
    async def authenticate(self, request: Request) -> Optional[UserContext]: ...   # cookie / bearer / JWT
    async def login(self, username: str, password: str) -> UserContext: ...        # local only
    async def logout(self, request: Request) -> None: ...
```

| Provider | Where | Mechanism |
|---|---|---|
| `LocalAuthProvider` | local dev, homelab | `POST /api/auth/login {username, password}` → Argon2id verify → random 32-byte session id in an `examen_session` cookie (`HttpOnly`, `SameSite=Lax`, `Secure` when served over HTTPS, `Path=/`). Bearer personal access tokens for `/mcp` |
| `CognitoAuthProvider` | AWS | Hosted UI / OAuth code flow; the backend validates the Cognito JWT (JWKS cache) from a cookie (dashboard) or `Authorization: Bearer` (Alexa, MCP clients) and maps `sub` → `users.external_sub`. Self-registration becomes Cognito self sign-up (`/api/auth/signup` is not used) |

Selected by `AUTH_PROVIDER=local|cognito`. Both resolve to the same `UserContext`.

### 2.2 Accounts

- **Bootstrap admin:** at start-up, while **no admin exists**, `EXAMEN_BOOTSTRAP_ADMIN=<username>` creates an admin and prints a one-time password to the log (or reads `EXAMEN_BOOTSTRAP_ADMIN_PASSWORD`). If that username already belongs to a self-registered account, nothing happens and an error is logged: a registered user is never promoted, since anyone could have picked the name. The bootstrap runs before the server accepts requests, so on a fresh instance the name cannot be taken first. Local dev uses the same path; there is no unauthenticated mode (D10).
- **Self-registration** (`AUTH_ALLOW_SIGNUP=true`, the default): the sign-in page has a *Create account* tab → `POST /api/auth/signup {username, password, display_name?}`. The new account is active, **never an admin** (any `is_admin` in the body is ignored), starts with an empty scoped store and is signed in right away (same cookie as the login, `201`). Limit: 5 accounts per IP per hour (`429`). `AUTH_ALLOW_SIGNUP=false` → `403 signup_disabled`, and the tab is hidden.
- **Admin-created users:** an admin can still create accounts (`POST /api/admin/users`) with a one-time initial password, disable them or reset their password, including self-registered ones.
- **Password policy:** ≥ 12 characters; Argon2id (`argon2-cffi`); login rate limit 5 attempts / 15 min per username and per IP. Usernames: 3–32 of `[A-Za-z0-9._-]`, unique case-insensitively.
- **CSRF:** cookie-authenticated state-changing requests require the `X-Requested-With: examen` header (or a double-submit token). Bearer requests are exempt.

### 2.3 What disappears

`_user_sessions`, `x-user-id` / `user_id` trust, the `localStorage` profile directory and `GET /api/auth/users` (replaced by admin-only `GET /api/admin/users`).

---

## 3. Authorisation rules

1. Every route except `/api/auth/login`, `/api/auth/signup`, `/api/auth/session`, `/api/health` and static assets requires a `UserContext`.
2. A handler never receives a `user_id` from the client. It always uses `ctx.user_id`. Ids in paths (`/api/sessions/{id}`) are resolved **inside the user's scoped store**, so another user's id simply does not exist (`404`, never `403`, to avoid confirming existence).
3. Admin routes (`/api/admin/*`) need `ctx.is_admin`. Admins **cannot** read other users' speech-derived data through the API; they manage accounts and Bee link status only.
4. Background work runs with `UserContext(auth_method="system")` for the user that owns it ([03](03_tenant_isolation_and_runtime.md) §3).

---

## 4. Bee account linking per user

### 4.1 Credential isolation (verified in bee-cli `secureStore.ts`)

bee-cli reads its token from `BEE_CONFIG_DIR` (default `~/.bee`) and uses the OS keychain unless `BEE_FORCE_FILE_STORE=1`. The keychain entry name is fixed (`bee-cli` / `token:<env>`), so **per-user directories only isolate tokens when the file store is forced**.

Every Bee subprocess for a user is therefore started with:

```
BEE_CONFIG_DIR=<data_dir>/users/<user_id>/bee      (mode 0700, owned by the service user)
BEE_FORCE_FILE_STORE=1
```

`BeeClient` gains a `config_dir` argument and passes this environment to `stream`, `proxy`, `login`, `status`, `me`, `locations` and `conversations` calls. The global `get_bee_binary_path()` resolution is unchanged.

### 4.2 Pairing flow

```
UI "Connect Bee" ──► POST /api/bee/link
                       │  bee login --no-wait   (user's BEE_CONFIG_DIR, fresh pairing file)
                       ▼
                 {state: "pairing", pairing_url, expires_at}   ← real link only; never a fabricated URL
                       │  user approves in the Bee app
UI polls ──────► GET /api/bee/link  ──► bee status → "Verified as …"  ──► bee me --json
                       │  bee_user_id already linked to another user? → bee logout in this dir, state=invalid, 409
                       ▼
                 state=linked, bee_first_name, timezone ──► UserRuntimeManager.start(user_id)
```

- The pairing file (`pairing-prod.json`) is deleted before a new `bee login --no-wait`, so an expired link is never reused (observed: otherwise bee-cli resumes the old request).
- If `bee login` fails, the API returns an error. It never returns a placeholder link (today's fallback in `_initiate_bee_login_pairing` is removed).
- `bee_links.state` becomes `invalid` when `bee status` stops verifying (token revoked in the Bee app); the runtime stops and the UI asks to re-link.

### 4.3 Wearer identity

`WearerIdentity` is created per user from `bee_links.bee_first_name` (no singleton). `role_for_person()` and the backfill `speaker_role_for()` take the user's identity explicitly ([03](03_tenant_isolation_and_runtime.md) §3).

### 4.4 Token storage on AWS

The ingestion worker never keeps tokens on a shared disk. After pairing, the token file content is moved to **AWS Secrets Manager** (`examen/bee/<user_id>`), and the worker writes it into a private tmpfs `BEE_CONFIG_DIR` at runtime start. Open verification **MU-V1**: confirm that `bee login --token-stdin` accepts the content of `token-prod` written by the interactive flow, so the worker can restore it without the file format.

---

## 5. Logout, disconnect & erasure (D8)

| Action | Endpoint | Effect |
|---|---|---|
| Logout | `POST /api/auth/logout` | Revokes the current web session (cookie). Bee stays linked and ingestion continues |
| Log out everywhere | `POST /api/auth/sessions/revoke-all` | Revokes all web sessions and API tokens of the user |
| Disconnect Bee | `POST /api/bee/unlink` | Stops the user's runtime, runs `bee logout` **in that user's `BEE_CONFIG_DIR`**, deletes the directory, `state=unlinked`. Data is kept |
| Erase my data (GDPR Art. 17) | `POST /api/account/erase` (re-authentication required) | Stops the runtime, unlinks Bee, deletes the user's scoped database (SQLite file / DynamoDB partition / AgentCore Memory namespace), sessions and tokens; marks the user `erasing` → deletes the row; writes an audit entry without content |

This replaces decision **C11** of [10](../../10_bee_cli_reference.md) §10 (dashboard logout = host-wide `bee logout`), which only made sense with one shared Bee account. Its intent (logging out also disconnects the device) is still available as "Disconnect Bee", but scoped to the user.
