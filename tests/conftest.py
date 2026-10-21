"""Shared test isolation.

The suite must never reach the developer's real Bee account: several endpoints run `bee logout`
(dashboard logout, Bee disconnect, GDPR purge), and the probes call `bee status` / `bee me` over the
network. Every test therefore sees "no Bee binary" and a stub command that always fails; tests that
need Bee output patch `BeeClient._build_cmd` / `run_json` themselves.
"""

import sys

import pytest


@pytest.fixture(autouse=True)
def _no_real_bee_cli(monkeypatch):
    from src.ingestion import bee_identity, stream_convo

    monkeypatch.setattr(stream_convo, "get_bee_binary_path", lambda: None)
    monkeypatch.setattr(
        stream_convo.BeeClient, "_build_cmd",
        lambda self, args: [sys.executable, "-c", "import sys; sys.exit(3)"],
    )
    # Fresh wearer identity per test (the singleton caches `bee me`)
    monkeypatch.setattr(bee_identity, "_identity", None)
    yield


@pytest.fixture(autouse=True)
def _single_user_mode(monkeypatch, tmp_path):
    """Existing tests exercise the single-user code paths (no login). Multi-user tests
    (tests/test_accounts.py) turn AUTH_ENABLED on themselves. Account data never touches ./data."""
    from src.core.auth import reset_auth_store
    from src.core.auth.rate_limit import login_limiter
    from src.core.config import settings

    from src.core.metrics import metrics
    from src.core.ops_store import reset_ops_store
    from src.core.runtime_settings import REGISTRY, reset_settings_service
    from src.core.service_log import reset_sink

    monkeypatch.setattr(settings, "auth_enabled", False)
    monkeypatch.setattr(settings, "examen_data_dir", str(tmp_path / "examen-data"))
    reset_auth_store(None)
    login_limiter.reset()
    # Admin console state: own ops.db, empty service log queue and counters, no runtime overrides
    reset_ops_store(None)
    reset_sink()
    metrics.reset()
    from src.core import token_usage

    token_usage.reset()
    reset_settings_service(None)
    saved = {key: getattr(settings, key) for key in REGISTRY}
    yield
    for key, value in saved.items():  # settings overrides applied by a test never leak into the next
        setattr(settings, key, value)
    reset_settings_service(None)
    reset_ops_store(None)
    reset_auth_store(None)
