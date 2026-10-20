import time

from src import github_auth


def test_provider_caches_until_ttl(monkeypatch):
    calls = []
    monkeypatch.setattr(github_auth, "get_installation_token", lambda c: calls.append(1) or f"tok{len(calls)}")
    provider = github_auth.make_token_provider({})
    assert provider() == "tok1"
    assert provider() == "tok1"
    assert len(calls) == 1


def test_provider_refreshes_after_ttl(monkeypatch):
    calls = []
    monkeypatch.setattr(github_auth, "get_installation_token", lambda c: calls.append(1) or f"tok{len(calls)}")
    now = {"t": 1000.0}
    monkeypatch.setattr(github_auth.time, "monotonic", lambda: now["t"])
    provider = github_auth.make_token_provider({}, ttl_seconds=100)
    provider()
    now["t"] += 101
    assert provider() == "tok2"


def test_refresh_forces_new_token(monkeypatch):
    calls = []
    monkeypatch.setattr(github_auth, "get_installation_token", lambda c: calls.append(1) or f"tok{len(calls)}")
    provider = github_auth.make_token_provider({})
    provider()
    provider.refresh()
    assert provider() == "tok2"
