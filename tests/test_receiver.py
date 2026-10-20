import hashlib
import hmac
import json
import threading
import time

import pytest

from src import receiver
from src.validator import validate_content

SECRET = "s3cret"
CONFIG = {
    "github_org": "o",
    "github_api_base_url": "https://api.github.com",
    "webhook_secret": SECRET,
}
TEMPLATE = (
    "property_definitions: []\n"
    "teams:\n"
    "  - name: t1\n"
    "    description: d\n"
    "repositories:\n"
    "  - id: r1\n"
    "    name: r1\n"
    "    teams: []\n"
    "    properties: {}\n"
)


def sign(body: bytes, secret=SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


@pytest.fixture
def client(monkeypatch):
    calls = []
    template_reads = []
    monkeypatch.setattr(
        receiver, "validate_file",
        lambda path: template_reads.append(path) or validate_content(TEMPLATE, path),
    )
    monkeypatch.setattr(
        receiver.reconcile, "reconcile_event",
        lambda event, payload, template, ctx: calls.append((event, template, ctx)) or "reverted",
    )
    app = receiver.create_app(CONFIG, token_provider=lambda: "tok")
    c = app.test_client()
    c.calls = calls
    c.template_reads = template_reads
    return c


def post(client, payload, event="repository", signature="auto"):
    body = json.dumps(payload).encode()
    headers = {"X-GitHub-Event": event, "Content-Type": "application/json"}
    if signature == "auto":
        headers["X-Hub-Signature-256"] = sign(body)
    elif signature:
        headers["X-Hub-Signature-256"] = signature
    return client.post("/webhook", data=body, headers=headers)


def test_verify_signature():
    body = b"{}"
    assert receiver.verify_signature(SECRET, body, sign(body))
    assert not receiver.verify_signature(SECRET, body, sign(body, "other"))
    assert not receiver.verify_signature(SECRET, body, None)


def test_bad_signature_401(client):
    assert post(client, {}, signature="sha256=bad").status_code == 401
    assert client.calls == []


def test_missing_signature_401(client):
    assert post(client, {}, signature=None).status_code == 401


def test_ping_200(client):
    assert post(client, {"zen": "x"}, event="ping").status_code == 200
    assert client.calls == []


def test_bot_event_skipped_without_reconcile(client):
    resp = post(client, {"sender": {"type": "Bot", "login": "app[bot]"}, "repository": {"name": "r"}})
    assert resp.status_code == 200
    assert resp.get_json() == {"skipped": "bot"}
    assert client.calls == []


def test_user_event_is_reconciled_against_local_yaml_index_and_ctx(client):
    resp = post(client, {"sender": {"type": "User"}, "repository": {"name": "r1"}})
    assert resp.status_code == 200
    event, template, ctx = client.calls[0]
    assert event == "repository"
    assert set(template["repositories"]) == {"r1"}
    assert set(template["teams"]) == {"t1"}
    assert ctx["org"] == "o"
    assert ctx["base"] == "https://api.github.com"
    assert ctx["token"]() == "tok"
    assert client.template_reads == ["stress_template.yaml"]


def test_local_yaml_is_read_on_every_webhook(client, monkeypatch):
    updated = TEMPLATE + "  - id: r2\n    name: r2\n    teams: []\n    properties: {}\n"
    templates = iter([TEMPLATE, updated])
    reads = []

    def read(path):
        reads.append(path)
        return validate_content(next(templates), path)

    monkeypatch.setattr(receiver, "validate_file", read)
    post(client, {"sender": {"type": "User"}})
    post(client, {"sender": {"type": "User"}})
    assert set(client.calls[0][1]["repositories"]) == {"r1"}
    assert set(client.calls[1][1]["repositories"]) == {"r1", "r2"}
    assert reads == ["stress_template.yaml", "stress_template.yaml"]


def test_local_yaml_is_validated_for_each_event(monkeypatch):
    reads = []
    monkeypatch.setattr(
        receiver, "validate_file",
        lambda path: reads.append(path) or validate_content(TEMPLATE, path),
    )
    monkeypatch.setattr(receiver.reconcile, "reconcile_event", lambda *a: "no_change")
    client = receiver.create_app(CONFIG, token_provider=lambda: "tok").test_client()
    post(client, {"sender": {"type": "User"}})
    post(client, {"sender": {"type": "User"}})
    assert reads == ["stress_template.yaml", "stress_template.yaml"]


def test_exception_in_reconcile_returns_error(monkeypatch):
    def boom(*a):
        raise RuntimeError("bad")

    monkeypatch.setattr(receiver.reconcile, "reconcile_event", boom)
    app = receiver.create_app(CONFIG, token_provider=lambda: "tok")
    assert post(app.test_client(), {"sender": {"type": "User"}}).status_code == 502


def test_local_template_read_failure_returns_error_without_reconcile(monkeypatch):
    calls = []
    monkeypatch.setattr(receiver, "validate_file", lambda *args: (_ for _ in ()).throw(RuntimeError("not found")))
    monkeypatch.setattr(receiver.reconcile, "reconcile_event", lambda *args: calls.append(args))
    app = receiver.create_app(CONFIG, token_provider=lambda: "tok")
    response = post(app.test_client(), {"sender": {"type": "User"}})
    assert response.status_code == 502
    assert calls == []


def test_invalid_local_yaml_returns_error_without_reconcile(monkeypatch):
    calls = []
    monkeypatch.setattr(receiver, "validate_file", lambda *args: (_ for _ in ()).throw(ValueError("invalid yaml")))
    monkeypatch.setattr(receiver.reconcile, "reconcile_event", lambda *a: calls.append(a))
    app = receiver.create_app(CONFIG, token_provider=lambda: "tok")
    response = post(app.test_client(), {"sender": {"type": "User"}})
    assert response.status_code == 502
    assert calls == []


def test_concurrent_events_do_not_overlap(monkeypatch):
    active = {"now": 0, "max": 0}

    def slow(*a):
        active["now"] += 1
        active["max"] = max(active["max"], active["now"])
        time.sleep(0.05)
        active["now"] -= 1
        return "reverted"

    monkeypatch.setattr(receiver.reconcile, "reconcile_event", slow)
    monkeypatch.setattr(
        receiver, "validate_file",
        lambda path: validate_content(TEMPLATE, path),
    )
    app = receiver.create_app(CONFIG, token_provider=lambda: "tok")
    threads = [
        threading.Thread(target=post, args=(app.test_client(), {"sender": {"type": "User"}}))
        for _ in range(4)
    ]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert active["max"] == 1


def test_log_line_reports_api_calls(monkeypatch, caplog):
    from src import github_http

    def fake(event, payload, template, ctx):
        github_http.record_call("GET", None)
        github_http.record_call("PATCH", None)
        return "reverted"

    monkeypatch.setattr(receiver, "validate_file", lambda *args: (
        github_http.record_call("GET", None),
        validate_content(TEMPLATE, "stress_template.yaml"),
    )[1])
    monkeypatch.setattr(receiver.reconcile, "reconcile_event", fake)
    app = receiver.create_app(CONFIG, token_provider=lambda: "tok")
    with caplog.at_level("INFO", logger="src.receiver"):
        post(app.test_client(), {"sender": {"type": "User"}, "repository": {"name": "r"}})
    assert any("api_calls=3" in r.getMessage() for r in caplog.records)
