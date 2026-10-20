import logging
import time
import jwt
import requests

from src import github_http

logger = logging.getLogger(__name__)


def get_installation_token(config: dict) -> str:
    """
    Obtain a GitHub App installation access token using JWT.

    Args:
        config: Dict with keys 'github_app_id', 'github_app_private_key_path',
                'github_app_installation_id', 'github_api_base_url'

    Returns:
        Installation access token string.

    Raises:
        RuntimeError: If the private key file is missing, the request can't
            reach GitHub, or the token endpoint returns a non-2xx status.
    """
    now = int(time.time()) - 60
    exp = now + 480  # real expiry is ~7 min ahead, well under GitHub's 10 min max even with clock drift

    key_path = config["github_app_private_key_path"]
    try:
        with open(key_path, "rb") as f:
            private_key_bytes = f.read()
    except FileNotFoundError:
        logger.error("GitHub App private key file not found: '%s'", key_path)
        raise RuntimeError(f"GitHub App private key file not found: '{key_path}'")

    payload = {
        "iss": config["github_app_id"],
        "iat": now,
        "exp": exp,
    }

    jwt_token = jwt.encode(payload, private_key_bytes, algorithm="RS256")

    url = f"{config['github_api_base_url']}/app/installations/{config['github_app_installation_id']}/access_tokens"

    headers = {
        "Authorization": f"Bearer {jwt_token}",
        "Accept": "application/vnd.github+json",
    }

    logger.info("Requesting GitHub App installation token")
    try:
        response = requests.post(url, headers=headers)
        github_http.record_call("POST", response)
    except requests.exceptions.RequestException as exc:
        github_http.record_call("POST", None)
        logger.error("Could not reach GitHub to get installation token: %s", exc)
        raise RuntimeError(f"Could not reach GitHub to get installation token: {exc}")

    if response.status_code < 200 or response.status_code >= 300:
        logger.error(
            "Failed to get installation token: %s %s", response.status_code, response.text
        )
        raise RuntimeError(
            f"Failed to get installation token: {response.status_code} {response.text}"
        )

    logger.info("Installation token obtained")
    return response.json()["token"]


def make_token_provider(config: dict, ttl_seconds: int = 50 * 60):
    """Return a callable that gives a valid installation token, refreshing it
    before the 1 hour GitHub expiry. `provider.refresh()` forces a new token."""
    cache = {"token": None, "at": 0.0}

    def refresh() -> None:
        cache["token"] = get_installation_token(config)
        cache["at"] = time.monotonic()

    def provide() -> str:
        if cache["token"] is None or time.monotonic() - cache["at"] > ttl_seconds:
            refresh()
        return cache["token"]

    provide.refresh = refresh
    return provide
