"""Configuration module for EXAMEN."""

from typing import Literal, Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # AWS & Bedrock
    aws_region: str = Field(default="us-east-1", alias="AWS_REGION")
    aws_access_key_id: str | None = Field(default=None, alias="AWS_ACCESS_KEY_ID")
    aws_secret_access_key: str | None = Field(default=None, alias="AWS_SECRET_ACCESS_KEY")
    aws_session_token: str | None = Field(default=None, alias="AWS_SESSION_TOKEN")

    # Provider Selection: "bedrock" or "mantle" (independently configurable!)
    gatekeeper_provider: Literal["bedrock", "mantle"] = Field(
        default="bedrock", alias="GATEKEEPER_PROVIDER"
    )
    reasoner_provider: Literal["bedrock", "mantle"] = Field(
        default="bedrock", alias="REASONER_PROVIDER"
    )

    # Bedrock Mantle Endpoint & Credentials
    mantle_endpoint: str | None = Field(default=None, alias="BEDROCK_MANTLE_ENDPOINT")
    mantle_api_key: str | None = Field(default=None, alias="BEDROCK_MANTLE_API_KEY")

    # Bedrock Foundation Models
    gatekeeper_model_id: str = Field(
        default="openai.gpt-5.6-luna",
        alias="BEDROCK_GATEKEEPER_MODEL"
    )
    reasoner_model_id: str = Field(
        default="anthropic.claude-3-5-sonnet-20241022-v2:0",
        alias="BEDROCK_REASONER_MODEL"
    )

    # Storage Backend
    storage_backend: Literal["sqlite", "dynamo", "agentcore_memory"] = Field(
        default="sqlite",
        alias="STORAGE_BACKEND"
    )
    sqlite_db_path: str = Field(default="examen.db", alias="SQLITE_DB_PATH")

    # Development & Testing
    mock_ai: bool = Field(default=False, alias="MOCK_AI")
    agentcore_runtime_arn: str | None = Field(default=None, alias="AGENTCORE_RUNTIME_ARN")

    # Deep Topic Event Engine (docs/next_steps/deep_topic_event_engine/)
    event_engine_enabled: bool = Field(default=True, alias="EVENT_ENGINE_ENABLED")
    event_profile: Literal["default", "demo"] = Field(default="default", alias="EVENT_PROFILE")
    event_t_soft_seconds: float = Field(default=300.0, alias="EVENT_T_SOFT_SECONDS")
    event_t_hard_seconds: float = Field(default=1800.0, alias="EVENT_T_HARD_SECONDS")
    event_t_hard_after_close_cue_seconds: float = Field(
        default=300.0, alias="EVENT_T_HARD_AFTER_CLOSE_CUE_SECONDS"
    )
    event_t_hard_transit_seconds: float = Field(default=120.0, alias="EVENT_T_HARD_TRANSIT_SECONDS")
    event_t_checkpoint_seconds: float = Field(default=1200.0, alias="EVENT_T_CHECKPOINT_SECONDS")
    event_min_segment_words: int = Field(default=300, alias="EVENT_MIN_SEGMENT_WORDS")
    event_location_shift_meters: float = Field(default=400.0, alias="EVENT_LOCATION_SHIFT_METERS")
    event_tick_seconds: float = Field(default=15.0, alias="EVENT_TICK_SECONDS")
    event_synthesis_max_words: int = Field(default=6000, alias="EVENT_SYNTHESIS_MAX_WORDS")
    web_search_cache_ttl_seconds: int = Field(default=86400, alias="WEB_SEARCH_CACHE_TTL_SECONDS")

    # Topic continuity (Deep Topic Event Engine, Phase C)
    topic_similarity_backend: Literal["embedding", "heuristic", "none"] = Field(
        default="embedding", alias="TOPIC_SIMILARITY_BACKEND"
    )
    embedding_model_id: str = Field(default="amazon.titan-embed-text-v2:0", alias="BEDROCK_EMBEDDING_MODEL")
    embedding_dimensions: int = Field(default=512, alias="BEDROCK_EMBEDDING_DIMENSIONS")
    # Titan Text Embeddings V2 (512 dims), calibrated 2026-10-13 on resources/event_scenarios.json:
    # same-event windows 0.43-0.68, different-event windows 0.23-0.36
    topic_sim_same: float = Field(default=0.42, alias="TOPIC_SIM_SAME")
    topic_sim_different: float = Field(default=0.37, alias="TOPIC_SIM_DIFFERENT")
    # Calibrated 2026-10-13 on resources/event_scenarios.json (scripts/replay_event_scenarios.py)
    topic_sim_same_heuristic: float = Field(default=0.20, alias="TOPIC_SIM_SAME_HEURISTIC")
    topic_sim_different_heuristic: float = Field(default=0.10, alias="TOPIC_SIM_DIFFERENT_HEURISTIC")
    topic_window_min_chunks: int = Field(default=3, alias="TOPIC_WINDOW_MIN_CHUNKS")
    topic_window_min_words: int = Field(default=120, alias="TOPIC_WINDOW_MIN_WORDS")
    topic_pending_max_age_seconds: float = Field(default=90.0, alias="TOPIC_PENDING_MAX_AGE_SECONDS")
    topic_drift_windows: int = Field(default=3, alias="TOPIC_DRIFT_WINDOWS")
    topic_drift_min_seconds: float = Field(default=120.0, alias="TOPIC_DRIFT_MIN_SECONDS")
    topic_llm_judge: bool = Field(default=True, alias="TOPIC_LLM_JUDGE")

    # Historical Transcript Backfill (docs/next_steps/historical_backfill/)
    backfill_enabled: bool = Field(default=True, alias="BACKFILL_ENABLED")
    backfill_auto_on_startup: bool = Field(default=True, alias="BACKFILL_AUTO_ON_STARTUP")
    backfill_auto_on_reconnect: bool = Field(default=True, alias="BACKFILL_AUTO_ON_RECONNECT")
    backfill_lookback_days: float = Field(default=2.0, alias="BACKFILL_LOOKBACK_DAYS")
    backfill_first_run_days: float = Field(default=0.0, alias="BACKFILL_FIRST_RUN_DAYS")
    backfill_startup_delay_seconds: float = Field(default=60.0, alias="BACKFILL_STARTUP_DELAY_SECONDS")
    backfill_min_gap_seconds: float = Field(default=60.0, alias="BACKFILL_MIN_GAP_SECONDS")
    backfill_reconnect_debounce_seconds: float = Field(default=600.0, alias="BACKFILL_RECONNECT_DEBOUNCE_SECONDS")
    backfill_reconnect_delay_seconds: float = Field(default=900.0, alias="BACKFILL_RECONNECT_DELAY_SECONDS")
    backfill_max_window_days: float = Field(default=14.0, alias="BACKFILL_MAX_WINDOW_DAYS")
    backfill_max_utterances_per_run: int = Field(default=20000, alias="BACKFILL_MAX_UTTERANCES_PER_RUN")
    backfill_max_estimated_cost_usd: float = Field(default=1.0, alias="BACKFILL_MAX_ESTIMATED_COST_USD")
    backfill_screen_concurrency: int = Field(default=4, alias="BACKFILL_SCREEN_CONCURRENCY")
    backfill_screen_with_event_hint: bool = Field(default=False, alias="BACKFILL_SCREEN_WITH_EVENT_HINT")
    # Conversation-level history analysis (docs/next_steps/historical_backfill/07_conversation_windows.md)
    # window = screen each Bee conversation in windows of consecutive utterances (one gatekeeper call per
    # window, look-back + look-ahead context) and drill down to single utterances only where a window has
    # signal; utterance = legacy one call per utterance with 3 lines of look-back
    backfill_screening: Literal["window", "utterance"] = Field(default="window", alias="BACKFILL_SCREENING")
    backfill_window_utterances: int = Field(default=10, alias="BACKFILL_WINDOW_UTTERANCES")
    backfill_window_max_words: int = Field(default=450, alias="BACKFILL_WINDOW_MAX_WORDS")
    backfill_window_context_utterances: int = Field(default=3, alias="BACKFILL_WINDOW_CONTEXT_UTTERANCES")
    # Analyse every un-analysed utterance of each conversation that overlaps the window, not only the
    # part inside it (a recording is one unit: its start may precede the gap)
    backfill_whole_conversations: bool = Field(default=True, alias="BACKFILL_WHOLE_CONVERSATIONS")
    backfill_match_window_seconds: float = Field(default=300.0, alias="BACKFILL_MATCH_WINDOW_SECONDS")
    backfill_span_merge_seconds: float = Field(default=20.0, alias="BACKFILL_SPAN_MERGE_SECONDS")
    backfill_fuzzy_threshold: float = Field(default=0.6, alias="BACKFILL_FUZZY_THRESHOLD")
    backfill_final_transcript_grace_minutes: float = Field(
        default=30.0, alias="BACKFILL_FINAL_TRANSCRIPT_GRACE_MINUTES"
    )
    backfill_lookback_margin_hours: float = Field(default=6.0, alias="BACKFILL_LOOKBACK_MARGIN_HOURS")
    backfill_enrich_contacts_per_run: int = Field(default=10, alias="BACKFILL_ENRICH_CONTACTS_PER_RUN")
    backfill_ledger_retention_days: float = Field(default=14.0, alias="BACKFILL_LEDGER_RETENTION_DAYS")
    backfill_history_concurrency: int = Field(default=4, alias="BACKFILL_HISTORY_CONCURRENCY")
    # Cost model used by the preview estimate (USD per call, measured on the live benchmark)
    backfill_cost_per_gatekeeper_call: float = Field(default=0.000005, alias="BACKFILL_COST_PER_GATEKEEPER_CALL")
    backfill_cost_per_pipeline_call: float = Field(default=0.0003, alias="BACKFILL_COST_PER_PIPELINE_CALL")
    backfill_cost_per_event: float = Field(default=0.003, alias="BACKFILL_COST_PER_EVENT")
    # Share of a final utterance's span already spoken live (same conversation) above which it is a live duplicate
    backfill_live_coverage_fraction: float = Field(default=0.5, alias="BACKFILL_LIVE_COVERAGE_FRACTION")
    coverage_flush_seconds: float = Field(default=30.0, alias="COVERAGE_FLUSH_SECONDS")
    coverage_degraded_error_rate: float = Field(default=0.2, alias="COVERAGE_DEGRADED_ERROR_RATE")

    # Bee CLI integration (observed contract: docs/10_bee_cli_reference.md, plan: docs/next_steps/07)
    # proxy = raw SSE through a private `bee proxy` (sees the 30 s pings); cli = `bee stream --json`
    bee_stream_transport: str = Field(default="proxy", alias="BEE_STREAM_TRANSPORT")
    # Port of the private proxy on 127.0.0.1 (0 = first free port from 8787)
    bee_proxy_port: int = Field(default=0, alias="BEE_PROXY_PORT")
    bee_stream_ping_timeout_seconds: float = Field(default=90.0, alias="BEE_STREAM_PING_TIMEOUT_SECONDS")
    # Max wait after receipt for a `tagged-utterance` (speaker identity, ~1 s after the utterance)
    bee_speaker_tag_wait_seconds: float = Field(default=1.5, alias="BEE_SPEAKER_TAG_WAIT_SECONDS")
    # Wearer first name (default: `bee me` first_name)
    bee_wearer_name: Optional[str] = Field(default=None, alias="BEE_WEARER_NAME")
    # `bee locations current` polling period while streaming (0 disables)
    bee_location_poll_seconds: float = Field(default=120.0, alias="BEE_LOCATION_POLL_SECONDS")

    # Serving & MCP
    mcp_host: str = Field(default="0.0.0.0", alias="MCP_HOST")
    mcp_port: int = Field(default=8000, alias="MCP_PORT")
    mcp_streamable_http: bool = Field(default=True, alias="MCP_STREAMABLE_HTTP")

    # Multi-user accounts (docs/13_multi_user_accounts.md)
    # false = legacy single-user mode: no login, SQLITE_DB_PATH and the host's bee-cli login
    auth_enabled: bool = Field(default=True, alias="AUTH_ENABLED")
    # Root of auth.db and of the per-user folders (users/<user_id>/examen.db, users/<user_id>/bee/)
    examen_data_dir: str = Field(default="data", alias="EXAMEN_DATA_DIR")
    auth_session_ttl_hours: float = Field(default=24.0 * 14, alias="AUTH_SESSION_TTL_HOURS")
    # auto = Secure cookie when the request arrived over HTTPS (directly or via X-Forwarded-Proto)
    auth_cookie_secure: Literal["auto", "true", "false"] = Field(default="auto", alias="AUTH_COOKIE_SECURE")
    auth_min_password_length: int = Field(default=10, alias="AUTH_MIN_PASSWORD_LENGTH")
    auth_max_login_failures: int = Field(default=5, alias="AUTH_MAX_LOGIN_FAILURES")
    auth_lockout_minutes: float = Field(default=15.0, alias="AUTH_LOCKOUT_MINUTES")
    # Self-registration from the sign-in page (false = accounts are created by an admin or the CLI)
    auth_allow_signup: bool = Field(default=True, alias="AUTH_ALLOW_SIGNUP")
    # Successful registrations per client address per hour (mass account creation guard)
    auth_signup_max_per_ip: int = Field(default=5, alias="AUTH_SIGNUP_MAX_PER_IP")
    # Security audit log (no email, name or IP) is purged after this many days
    auth_audit_retention_days: int = Field(default=90, alias="AUTH_AUDIT_RETENTION_DAYS")
    # Created at start-up while no admin exists (password from the next variable, or printed once)
    examen_bootstrap_admin: Optional[str] = Field(default=None, alias="EXAMEN_BOOTSTRAP_ADMIN")
    examen_bootstrap_admin_password: Optional[str] = Field(default=None, alias="EXAMEN_BOOTSTRAP_ADMIN_PASSWORD")
    # Version of the privacy notice users accept at registration (bump it to ask again)
    privacy_notice_version: str = Field(default="2026-10-20", alias="PRIVACY_NOTICE_VERSION")
    # Comma-separated browser origins allowed to call the API with cookies (the dashboard's own
    # origin is always allowed). Example: http://localhost:3000
    cors_allowed_origins: str = Field(default="http://localhost:3000,http://127.0.0.1:3000", alias="CORS_ALLOWED_ORIGINS")
    # Host headers accepted on /mcp (DNS-rebinding protection). Add your public hostname, e.g.
    # examen.example.com or examen.deggio.local:* ("*" disables the check).
    mcp_allowed_hosts: str = Field(default="localhost:*,127.0.0.1:*,localhost,127.0.0.1", alias="MCP_ALLOWED_HOSTS")
    # Start every paired user's ingestion at server start (ambient listening without the dashboard open)
    auto_start_user_orchestrators: bool = Field(default=True, alias="AUTO_START_USER_ORCHESTRATORS")
    # Live Bee streams running at once (each is a private `bee proxy` + stream; 2 GB homelab ≈ 5)
    max_active_users: int = Field(default=5, alias="MAX_ACTIVE_USERS")
    # Concurrent LLM calls (gatekeeper + pipeline, live and backfill) across all users
    max_concurrent_llm_calls: int = Field(default=8, alias="MAX_CONCURRENT_LLM_CALLS")

    # SearXNG instance for web search (empty: skipped in the provider chain)
    searxng_url: Optional[str] = Field(default=None, alias="SEARXNG_URL")

    # Logging and admin console (docs/next_steps/admin_console/)
    # Level of the stdout handler (journald); the admin service log always keeps WARNING and above
    log_level: Literal["DEBUG", "INFO", "WARNING"] = Field(default="INFO", alias="LOG_LEVEL")
    service_log_retention_days: int = Field(default=30, alias="SERVICE_LOG_RETENTION_DAYS")
    service_log_max_events: int = Field(default=50000, alias="SERVICE_LOG_MAX_EVENTS")
    # Hourly token usage per model / role / user (admin console Health) is kept this long
    token_usage_retention_days: int = Field(default=90, alias="TOKEN_USAGE_RETENTION_DAYS")
    # Health monitor rules (admin_console/03 §5)
    health_check_interval_seconds: float = Field(default=60.0, alias="HEALTH_CHECK_INTERVAL_SECONDS")
    health_stream_silent_minutes: float = Field(default=15.0, alias="HEALTH_STREAM_SILENT_MINUTES")
    health_stream_flaps_per_30min: int = Field(default=6, alias="HEALTH_STREAM_FLAPS_PER_30MIN")
    health_fallback_rate: float = Field(default=0.2, alias="HEALTH_FALLBACK_RATE")
    health_pipeline_error_rate: float = Field(default=0.2, alias="HEALTH_PIPELINE_ERROR_RATE")
    health_throttle_per_5min: int = Field(default=5, alias="HEALTH_THROTTLE_PER_5MIN")
    health_gatekeeper_p95_ms: float = Field(default=8000.0, alias="HEALTH_GATEKEEPER_P95_MS")
    health_capacity_minutes: float = Field(default=10.0, alias="HEALTH_CAPACITY_MINUTES")
    health_llm_saturation: float = Field(default=0.8, alias="HEALTH_LLM_SATURATION")
    health_min_disk_gb: float = Field(default=1.0, alias="HEALTH_MIN_DISK_GB")
    health_memory_fraction: float = Field(default=0.75, alias="HEALTH_MEMORY_FRACTION")
    health_error_burst_per_5min: int = Field(default=20, alias="HEALTH_ERROR_BURST_PER_5MIN")

    @property
    def has_aws_credentials(self) -> bool:
        if self.aws_access_key_id and self.aws_secret_access_key:
            return True
        try:
            import boto3
            session = boto3.Session(
                aws_access_key_id=self.aws_access_key_id,
                aws_secret_access_key=self.aws_secret_access_key,
                aws_session_token=self.aws_session_token,
                region_name=self.aws_region
            )
            return session.get_credentials() is not None
        except Exception:
            return False

    @property
    def has_mantle_credentials(self) -> bool:
        if self.mantle_api_key and self.mantle_api_key.strip():
            return True
        return self.has_aws_credentials

    def get_mantle_endpoint(self) -> str:
        """Returns configured Mantle endpoint or default regional AWS endpoint."""
        if self.mantle_endpoint and self.mantle_endpoint.strip():
            return self.mantle_endpoint.strip()
        return f"https://bedrock-mantle.{self.aws_region}.api.aws/openai/v1"

    def get_mantle_api_key(self) -> str:
        """Returns static Mantle API key, or dynamically mints a short-term key from IAM role.

        The region and the configured keys are passed explicitly (no process environment writes), so a
        runtime region override also applies to minted tokens (docs/next_steps/admin_console/01 P1)."""
        if self.mantle_api_key and self.mantle_api_key.strip():
            return self.mantle_api_key.strip()
        try:
            from aws_bedrock_token_generator import provide_token

            provider = None
            if self.aws_access_key_id and self.aws_secret_access_key:
                from botocore.credentials import Credentials

                creds = Credentials(self.aws_access_key_id, self.aws_secret_access_key, self.aws_session_token)

                class _StaticProvider:
                    def load(self):
                        return creds

                provider = _StaticProvider()
            return provide_token(region=self.aws_region, aws_credentials_provider=provider)
        except Exception as e:
            raise ValueError(
                f"No BEDROCK_MANTLE_API_KEY configured and failed to mint token from IAM credentials: {e}"
            )


settings = Settings()

