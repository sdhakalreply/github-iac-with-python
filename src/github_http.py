import copy
import logging
import threading
import time

import requests

logger = logging.getLogger(__name__)

MAX_BACKOFF_SECONDS = 60

_stats_lock = threading.Lock()


def _empty_stats() -> dict:
    return {
        "total": 0, "by_method": {}, "by_status": {},
        "rate_limited": 0, "rate_limit_remaining": None,
    }


_stats = _empty_stats()


def reset_stats() -> None:
    global _stats
    with _stats_lock:
        _stats = _empty_stats()


def get_stats() -> dict:
    with _stats_lock:
        return copy.deepcopy(_stats)


def record_call(method: str, response) -> None:
    """Count one API request. `response` is None for a connection failure."""
    with _stats_lock:
        _stats["total"] += 1
        _stats["by_method"][method] = _stats["by_method"].get(method, 0) + 1
        status = "error" if response is None else str(response.status_code)
        _stats["by_status"][status] = _stats["by_status"].get(status, 0) + 1
        if response is not None:
            if _is_rate_limited(response):
                _stats["rate_limited"] += 1
            remaining = response.headers.get("X-RateLimit-Remaining")
            if remaining is not None and remaining.isdigit():
                _stats["rate_limit_remaining"] = int(remaining)


def _wait_seconds(response: requests.Response, attempt: int) -> float:
    retry_after = response.headers.get("Retry-After")
    if retry_after:
        try:
            return min(float(retry_after), MAX_BACKOFF_SECONDS)
        except ValueError:
            pass
    return min(2 ** attempt, MAX_BACKOFF_SECONDS)


def _is_rate_limited(response: requests.Response) -> bool:
    if response.status_code == 429:
        return True
    return response.status_code == 403 and response.headers.get("X-RateLimit-Remaining") == "0"


def request(
    method: str,
    url: str,
    token,
    action: str,
    max_retries: int = 5,
    *,
    accept: str = "application/vnd.github+json",
    **kwargs,
) -> requests.Response:
    """GitHub API request. `token` is a string or a callable returning one (a
    callable with a `refresh` attribute is refreshed once on a 401). Retries
    rate-limited responses with backoff and wraps connection failures in a
    RuntimeError."""
    attempt = 0
    refreshed = False
    while True:
        headers = {
            "Authorization": f"Bearer {token() if callable(token) else token}",
            "Accept": accept,
        }
        try:
            response = requests.request(method, url, headers=headers, **kwargs)
        except requests.exceptions.RequestException as exc:
            record_call(method, None)
            logger.error("Could not reach GitHub while %s: %s", action, exc)
            raise RuntimeError(f"Could not reach GitHub while {action}: {exc}")
        record_call(method, response)
        if response.status_code == 401 and hasattr(token, "refresh") and not refreshed:
            logger.warning("Token rejected while %s, refreshing", action)
            token.refresh()
            refreshed = True
            continue
        if not _is_rate_limited(response) or attempt >= max_retries:
            return response
        wait = _wait_seconds(response, attempt)
        logger.warning("Rate limited while %s, retrying in %ss", action, wait)
        time.sleep(wait)
        attempt += 1
