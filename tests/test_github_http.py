import pytest
import requests
import responses

from src import github_http

URL = "https://api.github.com/x"


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    sleeps = []
    monkeypatch.setattr(github_http.time, "sleep", sleeps.append)
    return sleeps


@responses.activate
def test_retries_on_429_then_succeeds(no_sleep):
    responses.add(responses.GET, URL, status=429)
    responses.add(responses.GET, URL, status=429)
    responses.add(responses.GET, URL, json={"ok": 1}, status=200)
    resp = github_http.request("GET", URL, "t", "testing")
    assert resp.status_code == 200
    assert len(responses.calls) == 3


@responses.activate
def test_honors_retry_after_header(no_sleep):
    responses.add(responses.GET, URL, status=429, headers={"Retry-After": "7"})
    responses.add(responses.GET, URL, status=200)
    github_http.request("GET", URL, "t", "testing")
    assert no_sleep == [7]


@responses.activate
def test_retries_on_403_with_rate_limit_remaining_zero():
    responses.add(responses.GET, URL, status=403, headers={"X-RateLimit-Remaining": "0"})
    responses.add(responses.GET, URL, status=200)
    assert github_http.request("GET", URL, "t", "testing").status_code == 200


@responses.activate
def test_plain_403_is_not_retried():
    responses.add(responses.GET, URL, status=403)
    assert github_http.request("GET", URL, "t", "testing").status_code == 403
    assert len(responses.calls) == 1


@responses.activate
def test_request_allows_raw_accept_media_type():
    responses.add(responses.GET, URL, body=b"yaml", status=200)
    response = github_http.request(
        "GET", URL, "token", "fetching raw content",
        accept="application/vnd.github.raw+json",
    )
    assert response.content == b"yaml"
    assert responses.calls[0].request.headers["Accept"] == "application/vnd.github.raw+json"


@responses.activate
def test_gives_up_after_max_retries():
    responses.add(responses.GET, URL, status=429)
    resp = github_http.request("GET", URL, "t", "testing", max_retries=2)
    assert resp.status_code == 429
    assert len(responses.calls) == 3


@responses.activate
def test_422_is_not_retried():
    responses.add(responses.GET, URL, status=422)
    github_http.request("GET", URL, "t", "testing")
    assert len(responses.calls) == 1


@responses.activate
def test_connection_error_raises_runtime_error():
    responses.add(responses.GET, URL, body=requests.exceptions.ConnectionError("boom"))
    with pytest.raises(RuntimeError, match="Could not reach GitHub while testing"):
        github_http.request("GET", URL, "t", "testing")


@responses.activate
def test_callable_token_is_resolved_per_request():
    responses.add(responses.GET, URL, status=200)
    github_http.request("GET", URL, lambda: "fresh", "testing")
    assert responses.calls[0].request.headers["Authorization"] == "Bearer fresh"


@responses.activate
def test_401_refreshes_token_and_retries_once():
    tokens = ["old", "new"]
    provider = lambda: tokens[0]
    provider.refresh = lambda: tokens.pop(0)
    responses.add(responses.GET, URL, status=401)
    responses.add(responses.GET, URL, status=200)
    assert github_http.request("GET", URL, provider, "testing").status_code == 200
    assert responses.calls[1].request.headers["Authorization"] == "Bearer new"


@responses.activate
def test_401_with_plain_string_token_is_returned():
    responses.add(responses.GET, URL, status=401)
    assert github_http.request("GET", URL, "t", "testing").status_code == 401
    assert len(responses.calls) == 1


@responses.activate
def test_401_after_refresh_is_returned_without_looping():
    provider = lambda: "x"
    provider.refresh = lambda: None
    responses.add(responses.GET, URL, status=401)
    assert github_http.request("GET", URL, provider, "testing").status_code == 401
    assert len(responses.calls) == 2


@responses.activate
def test_stats_count_requests_by_method_and_status():
    github_http.reset_stats()
    responses.add(responses.GET, URL, status=200)
    responses.add(responses.PATCH, URL, status=422)
    github_http.request("GET", URL, "t", "testing")
    github_http.request("GET", URL, "t", "testing")
    github_http.request("PATCH", URL, "t", "testing")
    stats = github_http.get_stats()
    assert stats["total"] == 3
    assert stats["by_method"] == {"GET": 2, "PATCH": 1}
    assert stats["by_status"] == {"200": 2, "422": 1}


@responses.activate
def test_stats_count_every_retry_attempt(no_sleep):
    github_http.reset_stats()
    responses.add(responses.GET, URL, status=429)
    responses.add(responses.GET, URL, status=429)
    responses.add(responses.GET, URL, status=200)
    github_http.request("GET", URL, "t", "testing")
    stats = github_http.get_stats()
    assert stats["total"] == 3
    assert stats["rate_limited"] == 2


@responses.activate
def test_stats_capture_rate_limit_remaining():
    github_http.reset_stats()
    responses.add(responses.GET, URL, status=200, headers={"X-RateLimit-Remaining": "4321"})
    github_http.request("GET", URL, "t", "testing")
    assert github_http.get_stats()["rate_limit_remaining"] == 4321


@responses.activate
def test_stats_count_connection_errors():
    github_http.reset_stats()
    responses.add(responses.GET, URL, body=requests.exceptions.ConnectionError("boom"))
    with pytest.raises(RuntimeError):
        github_http.request("GET", URL, "t", "testing")
    stats = github_http.get_stats()
    assert stats["total"] == 1 and stats["by_status"] == {"error": 1}


def test_get_stats_returns_a_copy():
    github_http.reset_stats()
    snapshot = github_http.get_stats()
    snapshot["total"] = 99
    assert github_http.get_stats()["total"] == 0


@responses.activate
def test_installation_token_request_is_counted(tmp_path):
    from src import github_auth
    key = tmp_path / "k.pem"
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization
    pem = rsa.generate_private_key(public_exponent=65537, key_size=2048).private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    key.write_bytes(pem)
    responses.add(responses.POST, "https://api.github.com/app/installations/9/access_tokens", json={"token": "x"}, status=201)
    github_http.reset_stats()
    github_auth.get_installation_token({
        "github_app_id": "1", "github_app_private_key_path": str(key),
        "github_app_installation_id": "9", "github_api_base_url": "https://api.github.com",
    })
    assert github_http.get_stats()["by_method"] == {"POST": 1}
