import logging

from src import github_drift, github_repos, github_teams

logger = logging.getLogger(__name__)


def _norm(value):
    return sorted(value) if isinstance(value, list) else value


def build_index(parsed: dict) -> dict:
    """Index the parsed yaml by name. The yaml is the only source of truth."""
    return {
        "teams": {t["name"]: t for t in parsed["teams"]},
        "repositories": {r["name"]: r for r in parsed["repositories"]},
    }


def _wanted_teams(entry: dict) -> dict:
    return {team["name"]: team["role"] for team in entry["teams"]}


def _sync_teams(ctx, repo_name, wanted) -> bool:
    """Make GitHub's team list for a repo equal to `wanted` ({slug: role})."""
    org, token, base = ctx["org"], ctx["token"], ctx["base"]
    actual = github_drift.list_repo_teams(org, token, repo_name, base)
    changed = False
    for slug, role in wanted.items():
        if actual.get(slug) != role:
            github_repos.attach_team_to_repo(org, token, repo_name, slug, role, base)
            changed = True
    for slug in actual:
        if slug not in wanted:
            github_drift.remove_team_from_repo(org, token, repo_name, slug, base)
            changed = True
    return changed


def _sync_properties(ctx, repo_name, wanted) -> bool:
    org, token, base = ctx["org"], ctx["token"], ctx["base"]
    actual = github_drift.get_repo_properties(org, token, repo_name, base)
    diff = {k: v for k, v in wanted.items() if _norm(actual.get(k)) != _norm(v)}
    if diff:
        github_repos.set_repo_properties(org, token, repo_name, diff, base)
    return bool(diff)


def _handle_repository(payload, template, ctx) -> str:
    repo = payload["repository"]
    action = payload.get("action")
    org, token, base = ctx["org"], ctx["token"], ctx["base"]

    # Without state, the old name of a renamed repo comes from the payload.
    old_name = (((payload.get("changes") or {}).get("repository") or {}).get("name") or {}).get("from")
    name = old_name if action == "renamed" and old_name else repo["name"]
    entry = template["repositories"].get(name)
    if entry is None:
        return "unknown_resource"

    if action == "deleted":
        github_repos.create_repo(org, token, {"name": name}, base)
        _sync_teams(ctx, name, _wanted_teams(entry))
        _sync_properties(ctx, name, entry["properties"])
        return "reverted"

    changed = False
    if repo["name"] != name:
        github_drift.rename_repo(org, token, repo["name"], name, base)
        changed = True
    return "reverted" if changed else "no_change"


def _recreate_team(ctx, template, entry) -> None:
    org, token, base = ctx["org"], ctx["token"], ctx["base"]
    slug = github_teams.create_team(org, token, entry, base)
    for repo_name, repo_entry in template["repositories"].items():
        for team in repo_entry["teams"]:
            if team["name"] == entry["name"]:
                github_repos.attach_team_to_repo(org, token, repo_name, slug, team["role"], base)


def _handle_team(payload, template, ctx) -> str:
    team = payload["team"]
    org, token, base = ctx["org"], ctx["token"], ctx["base"]
    repo = payload.get("repository")

    if repo is not None:
        entry = template["repositories"].get(repo["name"])
        if entry is None:
            return "unknown_resource"
        return "reverted" if _sync_teams(ctx, repo["name"], _wanted_teams(entry)) else "no_change"

    entry = template["teams"].get(team["name"])
    if entry is None:
        return "unknown_resource"

    if payload.get("action") == "deleted":
        _recreate_team(ctx, template, entry)
        return "reverted"

    actual = github_teams.find_team(org, token, entry["name"], base)
    if actual is None:
        _recreate_team(ctx, template, entry)
        return "reverted"
    desired = entry["description"]
    if (actual.get("description") or "") != desired:
        github_drift.update_team_description(org, token, actual["slug"], desired, base)
        return "reverted"
    return "no_change"


def _handle_properties(payload, template, ctx) -> str:
    entry = template["repositories"].get(payload["repository"]["name"])
    if entry is None:
        return "unknown_resource"
    changed = _sync_properties(ctx, entry["name"], entry["properties"])
    return "reverted" if changed else "no_change"


HANDLERS = {
    "repository": _handle_repository,
    "team": _handle_team,
    "custom_property_values": _handle_properties,
}


def reconcile_event(event_type: str, payload: dict, template: dict, ctx: dict) -> str:
    """Compare a webhook event with the yaml (via GET on GitHub) and revert
    GitHub on mismatch. Never raises."""
    handler = HANDLERS.get(event_type)
    if handler is None:
        return "no_change"
    try:
        return handler(payload, template, ctx)
    except Exception as exc:
        logger.error("Failed to reconcile %s event for %s: %s", event_type, describe(payload), exc)
        return "failed"


def describe(payload: dict) -> str:
    repo = (payload.get("repository") or {}).get("name")
    team = (payload.get("team") or {}).get("name")
    return repo or team or "unknown"
