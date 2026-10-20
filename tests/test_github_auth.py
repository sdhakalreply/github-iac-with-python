import responses
import pytest
import requests
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

from src.github_auth import get_installation_token


@pytest.fixture
def test_private_key_pem():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()


@responses.activate
def test_get_installation_token_success(tmp_path, test_private_key_pem):
    key_path = tmp_path / "key.pem"
    key_path.write_text(test_private_key_pem)
    config = {
        "github_app_id": "123",
        "github_app_private_key_path": str(key_path),
        "github_app_installation_id": "456",
        "github_api_base_url": "https://api.github.com",
    }
    responses.add(
        responses.POST,
        "https://api.github.com/app/installations/456/access_tokens",
        json={"token": "ghs_abc123", "expires_at": "2099-01-01T00:00:00Z"},
        status=201,
    )
    token = get_installation_token(config)
    assert token == "ghs_abc123"
    sent_auth_header = responses.calls[0].request.headers["Authorization"]
    assert sent_auth_header.startswith("Bearer ")
    assert len(sent_auth_header) > len("Bearer ")


@responses.activate
def test_get_installation_token_sends_generated_jwt_in_auth_header(tmp_path, test_private_key_pem, monkeypatch):
    # Pin the exact Authorization value to the JWT the function generates,
    # so a regression to a hard-coded/placeholder header is caught even
    # though "Bearer <nonempty>" alone would not catch it.
    key_path = tmp_path / "key.pem"
    key_path.write_text(test_private_key_pem)
    config = {
        "github_app_id": "123",
        "github_app_private_key_path": str(key_path),
        "github_app_installation_id": "456",
        "github_api_base_url": "https://api.github.com",
    }
    import src.github_auth as github_auth_module
    monkeypatch.setattr(github_auth_module.jwt, "encode", lambda payload, key, algorithm: "sentinel-jwt-token")
    responses.add(
        responses.POST,
        "https://api.github.com/app/installations/456/access_tokens",
        json={"token": "ghs_abc123", "expires_at": "2099-01-01T00:00:00Z"},
        status=201,
    )
    get_installation_token(config)
    sent_auth_header = responses.calls[0].request.headers["Authorization"]
    assert sent_auth_header == "Bearer sentinel-jwt-token"


@responses.activate
def test_get_installation_token_failure_raises(tmp_path, test_private_key_pem):
    key_path = tmp_path / "key.pem"
    key_path.write_text(test_private_key_pem)
    config = {
        "github_app_id": "123",
        "github_app_private_key_path": str(key_path),
        "github_app_installation_id": "456",
        "github_api_base_url": "https://api.github.com",
    }
    responses.add(
        responses.POST,
        "https://api.github.com/app/installations/456/access_tokens",
        json={"message": "Bad credentials"},
        status=401,
    )
    with pytest.raises(RuntimeError, match="401"):
        get_installation_token(config)


def test_get_installation_token_missing_key_file_raises_clear_error(tmp_path):
    config = {
        "github_app_id": "123",
        "github_app_private_key_path": str(tmp_path / "does-not-exist.pem"),
        "github_app_installation_id": "456",
        "github_api_base_url": "https://api.github.com",
    }
    with pytest.raises(RuntimeError, match="private key file not found"):
        get_installation_token(config)


@responses.activate
def test_get_installation_token_connection_error_raises_clear_error(tmp_path, test_private_key_pem):
    key_path = tmp_path / "key.pem"
    key_path.write_text(test_private_key_pem)
    config = {
        "github_app_id": "123",
        "github_app_private_key_path": str(key_path),
        "github_app_installation_id": "456",
        "github_api_base_url": "https://api.github.com",
    }
    responses.add(
        responses.POST,
        "https://api.github.com/app/installations/456/access_tokens",
        body=requests.exceptions.ConnectionError("connection refused"),
    )
    with pytest.raises(RuntimeError, match="[Cc]ould not reach"):
        get_installation_token(config)
