"""Filters for deciding whether an incoming GitHub webhook event should be
reconciled, or skipped because this tool's own API call caused it.
"""


def is_self_triggered(payload: dict, app_bot_login: str | None = None) -> bool:
    """Return True if the event's sender looks like this tool's own GitHub App.

    If `app_bot_login` is given, require an exact login match (e.g.
    "my-github-app[bot]"). Otherwise, treat any bot sender as self-triggered.
    """
    sender = payload.get("sender") or {}
    if sender.get("type") != "Bot":
        return False
    if app_bot_login is None:
        return True
    return sender.get("login") == app_bot_login
