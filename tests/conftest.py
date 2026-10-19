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
