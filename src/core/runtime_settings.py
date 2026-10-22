"""Runtime settings: admin overrides of the ``.env`` tunables (docs/next_steps/admin_console/02).

    effective value = admin override (ops.db) > environment (.env / process env) > code default

Every module imports the same ``settings`` object, so an override is a validated ``setattr`` on it.
Only keys of the ``REGISTRY`` can be written. Apply modes:

- ``hot``: read at each use, effective immediately;
- ``runtime``: copied when a per-user component is built; the server rebuilds every user's
  engine and orchestrator after the change (open events are rehydrated from the store);
- ``boot``: shown read-only (needs a process restart).

Secrets stay env-only: the console sees configured / missing / derived, never a value.
"""

from __future__ import annotations

import asyncio
import logging
import re
import threading
import time
import typing
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

from pydantic import TypeAdapter, ValidationError

from src.core.config import Settings, settings
from src.core.ops_store import get_ops_store

logger = logging.getLogger("examen.settings")

MODEL_ID = r"^[\w.:/-]{3,200}$"
REGION = r"^[a-z]{2}(-[a-z]+)+-\d$"
HTTPS_URL = r"^https://[^\s]+$"
HTTP_URL = r"^https?://[^\s]+$"
TEST_FRESH_SECONDS = 600
PROBES_PER_WINDOW = 10
PROBE_WINDOW_SECONDS = 600


@dataclass(frozen=True)
class SettingSpec:
    key: str
    group: str
    label: str
    apply: str  # hot | runtime | boot
    help: str = ""
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    choices: Optional[Tuple[Any, ...]] = None
    pattern: Optional[str] = None
    tests: Tuple[str, ...] = ()  # probe groups: gatekeeper | reasoner | embeddings
    risk: Optional[str] = None
    check: Optional[Callable[[Any], Optional[str]]] = None


def _zero_or_at_least(n: float) -> Callable[[Any], Optional[str]]:
    return lambda v: None if v == 0 or v >= n else f"Must be 0 (off) or at least {n:g}"


AI, ENGINE, TOPIC, BACKFILL, BEE, LIMITS, HEALTH, ACCOUNTS = (
    "AI models", "Event engine", "Topic continuity", "Backfill", "Bee ingestion", "Limits & logging",
    "Health checks", "Accounts",
)

_EMBED_RISK = ("Topic similarity thresholds (TOPIC_SIM_*) were calibrated for Titan Text Embeddings V2 at 512 "
               "dimensions: recalibrate with scripts/replay_event_scenarios.py --calibrate")

REGISTRY: Dict[str, SettingSpec] = {s.key: s for s in [
    # --- AI models (hot: a new client per call) ---------------------------------------------------
    SettingSpec("gatekeeper_provider", AI, "Gatekeeper provider", "hot", "Gatekeeper and fast extraction nodes",
                tests=("gatekeeper",)),
    SettingSpec("gatekeeper_model_id", AI, "Gatekeeper model", "hot", "Model id for the selected provider and region",
                pattern=MODEL_ID, tests=("gatekeeper",)),
    SettingSpec("reasoner_provider", AI, "Reasoner provider", "hot", "Topic research synthesis", tests=("reasoner",)),
    SettingSpec("reasoner_model_id", AI, "Reasoner model", "hot", pattern=MODEL_ID, tests=("reasoner",)),
    SettingSpec("mantle_endpoint", AI, "Mantle endpoint", "hot",
                "Empty = regional default https://bedrock-mantle.<region>.api.aws/openai/v1", pattern=HTTPS_URL,
                tests=("mantle",)),
    SettingSpec("aws_region", AI, "AWS region", "hot", "Bedrock and Mantle region (embeddings: runtime)",
                pattern=REGION, tests=("gatekeeper", "reasoner", "embeddings"),
                risk="Model ids are region-scoped: test every role before saving"),
    SettingSpec("embedding_model_id", AI, "Embedding model", "runtime", pattern=MODEL_ID, tests=("embeddings",),
                risk=_EMBED_RISK),
    SettingSpec("embedding_dimensions", AI, "Embedding dimensions", "runtime", choices=(256, 512, 1024),
                tests=("embeddings",), risk=_EMBED_RISK),
    SettingSpec("mock_ai", AI, "Mock AI (heuristics only)", "hot",
                risk="Every extraction becomes heuristic for every user"),
    # --- Deep Topic Event Engine (runtime) ---------------------------------------------------------
    SettingSpec("event_engine_enabled", ENGINE, "Event engine enabled", "runtime"),
    SettingSpec("event_profile", ENGINE, "Event profile", "runtime",
                risk="'demo' compresses timers: real conversations get split"),
    SettingSpec("event_t_soft_seconds", ENGINE, "Soft timeout (s)", "runtime", minimum=30, maximum=7200),
    SettingSpec("event_t_hard_seconds", ENGINE, "Hard timeout (s)", "runtime", minimum=60, maximum=14400),
    SettingSpec("event_t_hard_after_close_cue_seconds", ENGINE, "Hard timeout after a closing cue (s)", "runtime",
                minimum=30, maximum=7200),
    SettingSpec("event_t_hard_transit_seconds", ENGINE, "Hard timeout in transit (s)", "runtime", minimum=30,
                maximum=7200),
    SettingSpec("event_t_checkpoint_seconds", ENGINE, "Checkpoint interval (s)", "runtime", minimum=60, maximum=14400),
    SettingSpec("event_min_segment_words", ENGINE, "Minimum words per segment", "runtime", minimum=20, maximum=5000),
    SettingSpec("event_location_shift_meters", ENGINE, "Location shift (m)", "runtime", minimum=50, maximum=20000),
    SettingSpec("event_tick_seconds", ENGINE, "Tick interval (s)", "runtime", minimum=5, maximum=300),
    SettingSpec("event_synthesis_max_words", ENGINE, "Synthesis max words", "runtime", minimum=500, maximum=50000),
    # --- Topic continuity (runtime) ----------------------------------------------------------------
    SettingSpec("topic_similarity_backend", TOPIC, "Similarity backend", "runtime"),
    SettingSpec("topic_sim_same", TOPIC, "Same-topic threshold", "runtime", minimum=0, maximum=1),
    SettingSpec("topic_sim_different", TOPIC, "Different-topic threshold", "runtime", minimum=0, maximum=1),
    SettingSpec("topic_sim_same_heuristic", TOPIC, "Same-topic threshold (heuristic)", "runtime", minimum=0, maximum=1),
    SettingSpec("topic_sim_different_heuristic", TOPIC, "Different-topic threshold (heuristic)", "runtime",
                minimum=0, maximum=1),
    SettingSpec("topic_window_min_chunks", TOPIC, "Window min chunks", "runtime", minimum=1, maximum=50),
    SettingSpec("topic_window_min_words", TOPIC, "Window min words", "runtime", minimum=10, maximum=2000),
    SettingSpec("topic_pending_max_age_seconds", TOPIC, "Pending window max age (s)", "runtime", minimum=10,
                maximum=3600),
    SettingSpec("topic_drift_windows", TOPIC, "Drift windows", "runtime", minimum=1, maximum=20),
    SettingSpec("topic_drift_min_seconds", TOPIC, "Drift min duration (s)", "runtime", minimum=10, maximum=3600),
    SettingSpec("topic_llm_judge", TOPIC, "LLM judge for ambiguous windows", "runtime"),
    # --- Backfill (hot: read at the next run / step) -----------------------------------------------
    SettingSpec("backfill_enabled", BACKFILL, "Backfill enabled", "hot"),
    SettingSpec("backfill_auto_on_startup", BACKFILL, "Catch up at start-up", "hot"),
    SettingSpec("backfill_auto_on_reconnect", BACKFILL, "Catch up after a reconnect", "hot"),
    SettingSpec("backfill_lookback_days", BACKFILL, "Look-back (days)", "hot", minimum=0, maximum=30),
    SettingSpec("backfill_max_window_days", BACKFILL, "Max window (days)", "hot", minimum=1, maximum=60),
    SettingSpec("backfill_max_utterances_per_run", BACKFILL, "Max utterances per run", "hot", minimum=100,
                maximum=200000),
    SettingSpec("backfill_max_estimated_cost_usd", BACKFILL, "Budget per run (USD)", "hot", minimum=0, maximum=100),
    SettingSpec("backfill_screen_concurrency", BACKFILL, "Screening concurrency", "hot", minimum=1, maximum=16),
    SettingSpec("backfill_screening", BACKFILL, "Screening mode", "hot"),
    SettingSpec("backfill_window_utterances", BACKFILL, "Utterances per window", "hot", minimum=2, maximum=50),
    SettingSpec("backfill_window_max_words", BACKFILL, "Words per window", "hot", minimum=50, maximum=3000),
    SettingSpec("backfill_window_context_utterances", BACKFILL, "Context utterances", "hot", minimum=0, maximum=10),
    SettingSpec("backfill_whole_conversations", BACKFILL, "Whole conversations", "hot"),
    SettingSpec("backfill_cost_per_gatekeeper_call", BACKFILL, "Cost per gatekeeper call (USD)", "hot", minimum=0,
                maximum=1),
    SettingSpec("backfill_cost_per_pipeline_call", BACKFILL, "Cost per pipeline call (USD)", "hot", minimum=0,
                maximum=1),
    SettingSpec("backfill_cost_per_event", BACKFILL, "Cost per event (USD)", "hot", minimum=0, maximum=10),
    SettingSpec("backfill_enrich_contacts_per_run", BACKFILL, "Contacts enriched per run", "hot", minimum=0,
                maximum=200),
    SettingSpec("backfill_ledger_retention_days", BACKFILL, "Ledger retention (days)", "hot", minimum=1,
                maximum=365),
    # --- Bee ingestion (runtime) -------------------------------------------------------------------
    SettingSpec("bee_stream_transport", BEE, "Stream transport", "runtime", choices=("proxy", "cli")),
    SettingSpec("bee_stream_ping_timeout_seconds", BEE, "Ping timeout (s)", "runtime", "Bee pings every 30 s",
                minimum=35, maximum=600),
    SettingSpec("bee_speaker_tag_wait_seconds", BEE, "Speaker tag wait (s)", "runtime", minimum=0, maximum=5),
    SettingSpec("speaker_auto_accept_untagged", BEE, "Accept untagged speech automatically", "hot",
                "Single-user mode; with accounts each user sets it in Account",
                risk="Other people's sentences may become the owner's tasks or close routines"),
    SettingSpec("bee_location_poll_seconds", BEE, "Location poll (s)", "runtime", "0 = off",
                minimum=0, maximum=3600, check=_zero_or_at_least(30)),
    SettingSpec("coverage_flush_seconds", BEE, "Coverage flush (s)", "runtime", minimum=5, maximum=600),
    SettingSpec("coverage_degraded_error_rate", BEE, "Degraded coverage error rate", "runtime", minimum=0, maximum=1),
    # --- Limits & logging (hot) --------------------------------------------------------------------
    SettingSpec("max_concurrent_llm_calls", LIMITS, "Concurrent LLM calls", "hot", minimum=1, maximum=64),
    SettingSpec("max_active_users", LIMITS, "Live Bee streams", "hot",
                "Applies to stream starts; running streams are not stopped", minimum=1, maximum=50),
    SettingSpec("web_search_cache_ttl_seconds", LIMITS, "Web search cache TTL (s)", "hot", minimum=0, maximum=2592000),
    SettingSpec("searxng_url", LIMITS, "SearXNG URL", "hot", "Empty = not used", pattern=HTTP_URL),
    SettingSpec("log_level", LIMITS, "Server log level (journald)", "hot"),
    SettingSpec("service_log_retention_days", LIMITS, "Service log retention (days)", "hot", minimum=1, maximum=365),
    SettingSpec("token_usage_retention_days", LIMITS, "Token usage retention (days)", "hot", minimum=7, maximum=730),
    # --- Health checks (hot) -----------------------------------------------------------------------
    SettingSpec("health_check_interval_seconds", HEALTH, "Check interval (s)", "hot", minimum=15, maximum=600),
    SettingSpec("health_stream_silent_minutes", HEALTH, "Silent stream after (min)", "hot", minimum=2, maximum=1440),
    SettingSpec("health_stream_flaps_per_30min", HEALTH, "Disconnects per 30 min", "hot", minimum=2, maximum=100),
    SettingSpec("health_fallback_rate", HEALTH, "Gatekeeper fallback rate", "hot", minimum=0.01, maximum=1),
    SettingSpec("health_pipeline_error_rate", HEALTH, "Pipeline error rate", "hot", minimum=0.01, maximum=1),
    SettingSpec("health_throttle_per_5min", HEALTH, "Throttling events per 5 min", "hot", minimum=1, maximum=1000),
    SettingSpec("health_gatekeeper_p95_ms", HEALTH, "Gatekeeper p95 latency (ms)", "hot", minimum=500,
                maximum=120000),
    SettingSpec("health_capacity_minutes", HEALTH, "Capacity wait (min)", "hot", minimum=1, maximum=1440),
    SettingSpec("health_llm_saturation", HEALTH, "LLM slot saturation share", "hot", minimum=0.1, maximum=1),
    SettingSpec("health_min_disk_gb", HEALTH, "Min free disk (GB)", "hot", minimum=0.1, maximum=1000),
    SettingSpec("health_memory_fraction", HEALTH, "Memory share of the limit", "hot", minimum=0.1, maximum=1),
    SettingSpec("health_error_burst_per_5min", HEALTH, "Errors per 5 min", "hot", minimum=1, maximum=10000),
    # --- Accounts (hot) ----------------------------------------------------------------------------
    SettingSpec("auth_allow_signup", ACCOUNTS, "Self-registration", "hot"),
    SettingSpec("auth_signup_max_per_ip", ACCOUNTS, "Registrations per address per hour", "hot", minimum=1,
                maximum=100),
    SettingSpec("auth_min_password_length", ACCOUNTS, "Min password length", "hot", "New passwords only",
                minimum=8, maximum=64),
    SettingSpec("auth_max_login_failures", ACCOUNTS, "Failed logins before lockout", "hot", minimum=3, maximum=50),
    SettingSpec("auth_lockout_minutes", ACCOUNTS, "Lockout (min)", "hot", minimum=1, maximum=1440),
    SettingSpec("auth_session_ttl_hours", ACCOUNTS, "Session lifetime (h)", "hot", "New and renewed sessions",
                minimum=1, maximum=2160),
    SettingSpec("auth_audit_retention_days", ACCOUNTS, "Audit retention (days)", "hot", minimum=7, maximum=3650),
]}

BOOT_KEYS = ("mcp_host", "mcp_port", "mcp_streamable_http", "mcp_allowed_hosts", "cors_allowed_origins",
             "auth_enabled", "auth_cookie_secure", "examen_data_dir", "storage_backend", "sqlite_db_path",
             "auth_store_backend", "ops_store_backend", "dynamo_region", "dynamo_table_prefix",
             "dynamo_endpoint_url", "dynamo_tenant_role_arn", "dynamo_telemetry_ttl_days",
             "auto_start_user_orchestrators", "bee_proxy_port", "agentcore_runtime_arn", "privacy_notice_version",
             "pipeline_mode", "agentcore_timeout_seconds")
SECRET_KEYS = ("aws_access_key_id", "aws_secret_access_key", "aws_session_token", "mantle_api_key")

# Probe groups whose candidate values identify a test result
TEST_SIGNATURES = {
    "gatekeeper": ("gatekeeper_provider", "gatekeeper_model_id", "aws_region", "mantle_endpoint"),
    "reasoner": ("reasoner_provider", "reasoner_model_id", "aws_region", "mantle_endpoint"),
    "embeddings": ("embedding_model_id", "embedding_dimensions", "aws_region"),
}


def env_name(key: str) -> str:
    return Settings.model_fields[key].alias or key.upper()


def _annotation(key: str) -> Any:
    return Settings.model_fields[key].annotation


def _choices(spec: SettingSpec) -> Optional[Tuple[Any, ...]]:
    if spec.choices:
        return spec.choices
    args = [a for a in typing.get_args(_annotation(spec.key)) if a is not type(None)]
    if typing.get_origin(_annotation(spec.key)) is typing.Literal:
        return tuple(typing.get_args(_annotation(spec.key)))
    for arg in args:
        if typing.get_origin(arg) is typing.Literal:
            return tuple(typing.get_args(arg))
    return None


def _type_name(key: str) -> str:
    ann = _annotation(key)
    if typing.get_origin(ann) is typing.Literal:
        return "choice"
    base = [a for a in typing.get_args(ann) if a is not type(None)] or [ann]
    if typing.get_origin(base[0]) is typing.Literal:
        return "choice"
    return {bool: "bool", int: "int", float: "float", str: "str"}.get(base[0], "str")


def _optional(key: str) -> bool:
    return type(None) in typing.get_args(_annotation(key))


def secret_status(cfg: Settings = settings) -> Dict[str, str]:
    """configured (set in the env) · derived (instance role / profile, minted Mantle key) · missing."""
    def present(key: str) -> bool:
        value = getattr(cfg, key, None)
        return bool(value and str(value).strip())

    chain = cfg.has_aws_credentials  # env keys, or the default AWS credential chain
    out = {}
    for key in SECRET_KEYS:
        if present(key):
            out[key] = "configured"
        elif key == "aws_session_token":
            out[key] = "not set"
        else:
            out[key] = "derived" if chain else "missing"
    return out


class SettingsError(Exception):
    def __init__(self, code: str, message: str, status: int = 400, errors: Optional[Dict[str, str]] = None):
        super().__init__(message)
        self.code, self.message, self.status, self.errors = code, message, status, errors or {}


# ---------------------------------------------------------------------------
# Probes (02 §5): fixed synthetic text, candidate settings copy
# ---------------------------------------------------------------------------

def probe_gatekeeper(cfg: Settings) -> str:
    from langchain_core.messages import HumanMessage, SystemMessage

    from src.core.models import get_chat_model
    from src.core.schemas import ChunkClassification

    model = get_chat_model(cfg.gatekeeper_provider, cfg.gatekeeper_model_id, cfg=cfg, role="probe")
    result = model.with_structured_output(ChunkClassification).invoke([
        SystemMessage(content="Classify the transcript into the categories social, action, deep_topic, "
                              "scheduled_task or noop."),
        HumanMessage(content='Transcript: "I locked the front door before leaving."'),
    ])
    if not isinstance(result, ChunkClassification):
        raise ValueError("The model did not return a structured classification")
    return f"categories {result.categories}"


def probe_reasoner(cfg: Settings) -> str:
    from src.core.models import get_chat_model

    answer = get_chat_model(cfg.reasoner_provider, cfg.reasoner_model_id, temperature=0.0, cfg=cfg,
                            role="probe").invoke(
        "Reply with the single word OK.")
    text = getattr(answer, "content", "")
    if not str(text).strip():
        raise ValueError("Empty answer")
    return "answered"


def probe_embeddings(cfg: Settings) -> str:
    from src.core.models import get_embedding_model

    vector = get_embedding_model(cfg).embed_query("test")
    if not vector:
        raise ValueError("Empty embedding")
    if cfg.embedding_model_id.startswith("amazon.titan-embed-text-v2") and len(vector) != cfg.embedding_dimensions:
        raise ValueError(f"Expected {cfg.embedding_dimensions} dimensions, got {len(vector)}")
    return f"{len(vector)} dimensions"


PROBES: Dict[str, Callable[[Settings], str]] = {
    "gatekeeper": probe_gatekeeper, "reasoner": probe_reasoner, "embeddings": probe_embeddings,
}
PROBE_TIMEOUTS = {"gatekeeper": 20.0, "reasoner": 30.0, "embeddings": 20.0}


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

@dataclass
class _ChangeRecord:
    at: float
    change_id: str
    keys: Tuple[str, ...]


@dataclass
class SettingsService:
    cfg: Settings = field(default_factory=lambda: settings)
    store_getter: Callable = get_ops_store
    clock: Callable[[], float] = time.time
    # Rebuilds every user's runtime after a ``runtime`` key changed; returns how many (set by the server)
    rebuild_runtimes: Optional[Callable[[], Awaitable[int]]] = None

    def __post_init__(self) -> None:
        keys = list(REGISTRY) + list(BOOT_KEYS)
        self.env_values: Dict[str, Any] = {k: getattr(self.cfg, k) for k in keys}
        self.env_set = set(self.cfg.model_fields_set)
        self.overrides: Dict[str, Dict[str, Any]] = {}
        self.version = 0
        self._lock = threading.Lock()
        self._tests: Dict[Tuple[str, Tuple[Any, ...]], Tuple[float, bool]] = {}
        self._probe_calls: Dict[str, List[float]] = {}
        self._recent: List[_ChangeRecord] = []

    # -- loading ----------------------------------------------------------------

    def load(self) -> List[str]:
        """Start-up (and multi-process sync): apply the stored overrides, reset keys no longer overridden."""
        store = self.store_getter()
        stored = store.list_overrides()
        values: Dict[str, Any] = {}
        for key, entry in stored.items():
            if key not in REGISTRY:
                continue
            try:
                values[key] = self._validate_value(REGISTRY[key], entry["value"])
            except SettingsError as e:
                logger.warning(f"Ignoring stored override of {env_name(key)}: {e.message}",
                               extra={"event_code": "settings.invalid_override"})
        with self._lock:
            for key in set(self.overrides) - set(values):
                setattr(self.cfg, key, self.env_values[key])
            for key, value in values.items():
                setattr(self.cfg, key, value)
            self.overrides = {k: stored[k] for k in values}
            self.version = store.settings_version()
        self._after_apply(set(values))
        return sorted(values)

    async def sync(self) -> bool:
        """Re-reads ops.db when another process saved a change (02 §8)."""
        if self.store_getter().settings_version() == self.version:
            return False
        before = {k: getattr(self.cfg, k) for k in REGISTRY}
        self.load()
        changed = {k for k in REGISTRY if getattr(self.cfg, k) != before[k]}
        if any(REGISTRY[k].apply == "runtime" for k in changed) and self.rebuild_runtimes:
            await self.rebuild_runtimes()
        return True

    # -- description (GET) -------------------------------------------------------

    def describe(self) -> Dict[str, Any]:
        rows = []
        for key, spec in REGISTRY.items():
            override = self.overrides.get(key)
            source = "override" if override else ("env" if key in self.env_set else "default")
            rows.append({
                "key": key, "env": env_name(key), "group": spec.group, "label": spec.label, "help": spec.help,
                "apply": spec.apply, "type": _type_name(key), "optional": _optional(key),
                "choices": list(_choices(spec) or []) or None, "minimum": spec.minimum, "maximum": spec.maximum,
                "pattern": spec.pattern, "tests": [t for t in spec.tests if t != "mantle"] or None,
                "risk": spec.risk, "effective": getattr(self.cfg, key), "source": source,
                "env_value": self.env_values[key],
                "override_by": override["updated_by"] if override else None,
                "override_at": override["updated_at"] if override else None,
            })
        boot = [{"key": k, "env": env_name(k), "effective": getattr(self.cfg, k), "apply": "boot"} for k in BOOT_KEYS]
        secrets = [{"key": k, "env": env_name(k), "status": v} for k, v in secret_status(self.cfg).items()]
        return {"version": self.version, "settings": rows, "read_only": boot, "secrets": secrets}

    # -- validation --------------------------------------------------------------

    def _validate_value(self, spec: SettingSpec, value: Any) -> Any:
        if value is None or (isinstance(value, str) and not value.strip() and _optional(spec.key)):
            if _optional(spec.key):
                return None
            raise SettingsError("invalid_value", "A value is required")
        if _type_name(spec.key) == "bool" and not isinstance(value, bool):
            raise SettingsError("invalid_value", "Must be true or false")
        if _type_name(spec.key) in ("int", "float") and (isinstance(value, bool) or
                                                          not isinstance(value, (int, float))):
            raise SettingsError("invalid_value", "Must be a number")
        try:
            value = TypeAdapter(_annotation(spec.key)).validate_python(value.strip() if isinstance(value, str)
                                                                       else value)
        except ValidationError as e:
            raise SettingsError("invalid_value", e.errors()[0].get("msg", "Invalid value"))
        choices = _choices(spec)
        if choices and value not in choices:
            raise SettingsError("invalid_value", f"Must be one of {', '.join(map(str, choices))}")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if spec.minimum is not None and value < spec.minimum:
                raise SettingsError("invalid_value", f"Must be at least {spec.minimum:g}")
            if spec.maximum is not None and value > spec.maximum:
                raise SettingsError("invalid_value", f"Must be at most {spec.maximum:g}")
        if spec.pattern and isinstance(value, str) and not re.match(spec.pattern, value):
            raise SettingsError("invalid_value", "Invalid format")
        if spec.check:
            problem = spec.check(value)
            if problem:
                raise SettingsError("invalid_value", problem)
        return value

    def validate(self, changes: Dict[str, Any]) -> Dict[str, Any]:
        """``{key: value | None}`` (None removes the override) → validated change set, or SettingsError."""
        if not isinstance(changes, dict) or not changes:
            raise SettingsError("invalid_request", "No changes")
        clean, errors = {}, {}
        for key, value in changes.items():
            spec = REGISTRY.get(key)
            if spec is None:
                errors[key] = "Not an editable setting"
                continue
            if value is None:
                clean[key] = None
                continue
            try:
                clean[key] = self._validate_value(spec, value)
            except SettingsError as e:
                errors[key] = e.message
        if not errors:
            candidate = self.candidate(clean)
            for a, b, label in (("event_t_soft_seconds", "event_t_hard_seconds", "Soft timeout must be below the hard timeout"),
                                ("topic_sim_different", "topic_sim_same", "Different-topic threshold must be below the same-topic one"),
                                ("topic_sim_different_heuristic", "topic_sim_same_heuristic",
                                 "Different-topic threshold must be below the same-topic one")):
                if candidate[a] >= candidate[b] and (a in clean or b in clean):
                    errors[a if a in clean else b] = label
        if errors:
            raise SettingsError("invalid_settings", "Some values are not valid", errors=errors)
        return clean

    def candidate(self, clean: Dict[str, Any]) -> Dict[str, Any]:
        """Effective values after the change set (None → back to the env default)."""
        values = {k: getattr(self.cfg, k) for k in REGISTRY}
        for key, value in clean.items():
            values[key] = self.env_values[key] if value is None else value
        return values

    def required_tests(self, clean: Dict[str, Any]) -> List[str]:
        candidate = self.candidate(clean)
        groups = set()
        for key in clean:
            for group in REGISTRY[key].tests:
                if group == "mantle":
                    if candidate["gatekeeper_provider"] == "mantle":
                        groups.add("gatekeeper")
                    if candidate["reasoner_provider"] == "mantle":
                        groups.add("reasoner")
                elif group == "embeddings" and candidate["topic_similarity_backend"] != "embedding":
                    continue
                else:
                    groups.add(group)
        if candidate["mock_ai"]:
            return []  # no model is called
        return sorted(groups)

    @staticmethod
    def _signature(group: str, candidate: Dict[str, Any]) -> Tuple[Any, ...]:
        return tuple(candidate[k] for k in TEST_SIGNATURES[group])

    # -- test before save ----------------------------------------------------------

    async def test(self, changes: Dict[str, Any], admin_id: str) -> Dict[str, Any]:
        clean = self.validate(changes)
        groups = self.required_tests(clean) or [g for g in ("gatekeeper", "reasoner", "embeddings")
                                                if any(g in REGISTRY[k].tests for k in clean)]
        now = self.clock()
        calls = [t for t in self._probe_calls.get(admin_id, []) if now - t < PROBE_WINDOW_SECONDS]
        if len(calls) + len(groups) > PROBES_PER_WINDOW:
            raise SettingsError("rate_limited", "Too many model tests: wait a few minutes", status=429)
        self._probe_calls[admin_id] = calls + [now] * len(groups)
        candidate = self.candidate(clean)
        cfg = self.cfg.model_copy(update=candidate)
        results = []
        for group in groups:
            started = self.clock()
            try:
                from src.core.limits import llm_slot

                async with llm_slot():
                    detail = await asyncio.wait_for(asyncio.to_thread(PROBES[group], cfg),
                                                    timeout=PROBE_TIMEOUTS[group])
                ok, error_type, message = True, None, detail
            except asyncio.TimeoutError:
                ok, error_type, message = False, "TimeoutError", f"No answer within {PROBE_TIMEOUTS[group]:g} s"
            except Exception as e:
                from src.core.service_log import _error_type, sanitize

                ok, error_type, message = False, _error_type(e), sanitize(f"{type(e).__name__}: {e}")
            self._tests[(group, self._signature(group, candidate))] = (self.clock(), ok)
            results.append({"group": group, "ok": ok, "latency_ms": round((self.clock() - started) * 1000),
                            "error_type": error_type, "message": message})
        return {"results": results, "ok": all(r["ok"] for r in results)}

    def _untested(self, clean: Dict[str, Any]) -> List[str]:
        candidate = self.candidate(clean)
        now = self.clock()
        missing = []
        for group in self.required_tests(clean):
            result = self._tests.get((group, self._signature(group, candidate)))
            if result is None or not result[1] or now - result[0] > TEST_FRESH_SECONDS:
                missing.append(group)
        return missing

    # -- save / revert / reset -------------------------------------------------------

    async def save(self, changes: Dict[str, Any], admin_id: str, *, force: bool = False,
                   base_version: Optional[int] = None, note: Optional[str] = None,
                   require_tests: bool = True, event_code: str = "settings.changed") -> Dict[str, Any]:
        store = self.store_getter()
        if base_version is not None and int(base_version) != store.settings_version():
            raise SettingsError("settings_changed_meanwhile", "Settings were changed meanwhile: reload them",
                                status=409)
        clean = self.validate(changes)
        untested = self._untested(clean) if require_tests else []
        if untested and not force:
            raise SettingsError("test_required", f"Test {', '.join(untested)} before saving (or force)", status=409,
                                errors={"tests": ", ".join(untested)})
        old = {k: (self.overrides[k]["value"] if k in self.overrides else None) for k in clean}
        test_result = {"forced": bool(untested), "untested": untested} if untested else None
        change_id = store.save_change_set(clean, old, admin_id, test_result=test_result, note=note)
        with self._lock:
            for key, value in clean.items():
                setattr(self.cfg, key, self.env_values[key] if value is None else value)
            self.overrides = store.list_overrides()
            self.version = store.settings_version()
        keys = tuple(sorted(clean))
        self._recent.append(_ChangeRecord(self.clock(), change_id, keys))
        self._recent = self._recent[-50:]
        self._after_apply(set(clean))
        await self._notify_limits(clean)
        rebuilt = 0
        if any(REGISTRY[k].apply == "runtime" for k in clean) and self.rebuild_runtimes:
            rebuilt = await self.rebuild_runtimes()
        self._audit(admin_id, event_code, change_id, keys)
        from src.core.service_log import report_event

        report_event(event_code, "info", f"Settings {event_code.split('.')[-1]}: {', '.join(env_name(k) for k in keys)}",
                     component="settings", user_id=None, change_id=change_id, count=len(keys))
        if untested:
            report_event("settings.forced_untested", "warning",
                         f"Saved without a passing test: {', '.join(untested)}", component="settings",
                         user_id=None, change_id=change_id)
        return {"change_id": change_id, "applied": list(keys), "rebuilt_runtimes": rebuilt,
                "forced_untested": untested, "version": self.version}

    async def revert(self, change_id: str, admin_id: str) -> Dict[str, Any]:
        rows = self.store_getter().get_change_set(change_id)
        if not rows:
            raise SettingsError("not_found", "Unknown change", status=404)
        inverse = {r["key"]: r["old"] for r in rows if r["key"] in REGISTRY}
        # Returning to the previous state must stay one click during an incident: no probe required
        return await self.save(inverse, admin_id, require_tests=False, note=f"revert {change_id}",
                               event_code="settings.reverted")

    async def reset(self, admin_id: str, key: Optional[str] = None) -> Dict[str, Any]:
        keys = [key] if key else list(self.overrides)
        if key and key not in REGISTRY:
            raise SettingsError("not_found", "Not an editable setting", status=404)
        if not keys:
            return {"change_id": None, "applied": [], "rebuilt_runtimes": 0, "forced_untested": [],
                    "version": self.version}
        return await self.save({k: None for k in keys}, admin_id, require_tests=False,
                               note="reset to defaults", event_code="settings.reset")

    def history(self, limit: int = 50) -> List[Dict[str, Any]]:
        return self.store_getter().list_history(limit)

    def recent_ai_change(self, within: float = 600.0) -> Optional[str]:
        """Most recent change set touching an AI model setting within ``within`` seconds (health incidents)."""
        now = self.clock()
        for record in reversed(self._recent):
            if now - record.at > within:
                break
            if any(REGISTRY[k].group == AI for k in record.keys if k in REGISTRY):
                return record.change_id
        return None

    # -- side effects ----------------------------------------------------------------

    def _after_apply(self, keys: set) -> None:
        if "log_level" in keys or not keys:
            from src.core.logging_setup import set_log_level

            set_log_level(self.cfg.log_level)

    async def _notify_limits(self, clean: Dict[str, Any]) -> None:
        if "max_concurrent_llm_calls" in clean:
            from src.core.limits import notify_llm_limit_changed

            await notify_llm_limit_changed()

    @staticmethod
    def _audit(admin_id: str, event: str, change_id: str, keys: Tuple[str, ...]) -> None:
        try:
            from src.core.auth import get_auth_store

            get_auth_store().audit(event.replace(".", "_"), actor_id=admin_id,
                                   detail={"change_id": change_id, "keys": [env_name(k) for k in keys]})
        except Exception as e:  # pragma: no cover - audit must not block the change
            logger.warning(f"Settings audit failed: {e}")


_service: Optional[SettingsService] = None
_service_lock = threading.Lock()


def get_settings_service() -> SettingsService:
    global _service
    with _service_lock:
        if _service is None:
            _service = SettingsService()
        return _service


def reset_settings_service(service: Optional[SettingsService] = None) -> None:
    """Test seam."""
    global _service
    with _service_lock:
        _service = service
