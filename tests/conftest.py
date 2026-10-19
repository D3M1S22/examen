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

    monkeypatch.setattr(settings, "auth_enabled", False)
    monkeypatch.setattr(settings, "examen_data_dir", str(tmp_path / "examen-data"))
    reset_auth_store(None)
    login_limiter.reset()
    yield
    reset_auth_store(None)
