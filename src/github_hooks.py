import logging

import requests

logger = logging.getLogger(__name__)


def _request(method: str, url: str, token: str, action: str, **kwargs) -> requests.Response:
    """Make a GitHub API request, wrapping connection-level failures in a
    clear RuntimeError instead of letting a raw requests exception escape."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    }
    try:
        return requests.request(method, url, headers=headers, **kwargs)
    except requests.exceptions.RequestException as exc:
        logger.error("Could not reach GitHub while %s: %s", action, exc)
        raise RuntimeError(f"Could not reach GitHub while {action}: {exc}")


def _hook_url_registered(org: str, token: str, repo_name: str, delivery_url: str, api_base_url: str) -> bool:
    response = _request(
        "GET",
        f"{api_base_url}/repos/{org}/{repo_name}/hooks",
        token,
        f"checking existing hooks for repo '{repo_name}'",
    )
    if response.status_code != 200:
        return False
    return any(hook.get("config", {}).get("url") == delivery_url for hook in response.json())


def create_hook(
    org: str,
    token: str,
    repo_name: str,
    hook_entry: dict,
    default_secret: str,
    api_base_url: str,
) -> None:
    delivery_url = hook_entry.get("url") or hook_entry.get("target_url")
    if not delivery_url:
        raise ValueError(f"Hook '{hook_entry.get('name')}' has no url or target_url")

    if _hook_url_registered(org, token, repo_name, delivery_url, api_base_url):
        logger.info(
            "Hook '%s' already registered for repo '%s', will not create",
            hook_entry.get("name"),
            repo_name,
        )
        return

    # YAML literal MY_GITHUB_SECRET names env var; use resolved config secret instead.
    secret = hook_entry["secret"] if (hook_entry.get("secret") and hook_entry["secret"] != "MY_GITHUB_SECRET") else default_secret

    logger.info("Creating hook '%s' on repo '%s'", hook_entry.get("name"), repo_name)
    payload = {
        "name": "web",
        "active": True,
        "events": hook_entry.get("events", ["push"]),
        "config": {
            "url": delivery_url,
            "content_type": "json",
            "secret": secret,
        },
    }

    response = _request(
        "POST",
        f"{api_base_url}/repos/{org}/{repo_name}/hooks",
        token,
        f"creating hook '{hook_entry.get('name')}' on repo '{repo_name}'",
        json=payload,
    )

    if response.status_code < 200 or response.status_code >= 300:
        logger.error(
            "Failed to create hook '%s' for repo '%s': %s %s",
            hook_entry["name"], repo_name, response.status_code, response.text,
        )
        raise RuntimeError(
            f"Failed to create hook '{hook_entry['name']}' for repo '{repo_name}': {response.status_code} {response.text}"
        )

    logger.info("Hook '%s' created on repo '%s'", hook_entry["name"], repo_name)
