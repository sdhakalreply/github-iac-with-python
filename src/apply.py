import logging
import os
import sys
import time

from src import github_drift, github_http, github_repos, github_teams
from src.config import load_config
from src.github_auth import make_token_provider
from src.github_properties import ensure_property_schema
from src.validator import validate_file
from src.yaml_parser import parse_template

logger = logging.getLogger(__name__)

LOG_EVERY = 100


def _normalize(value):
    return sorted(value) if isinstance(value, list) else value


def diff_repo(desired: dict, actual: dict) -> dict:
    """Compare yaml-defined teams and properties with GitHub. Both args are
    {"teams": {slug: role}, "properties": {name: value}}. Keys the yaml does
    not define are ignored for properties; extra teams are drift."""
    teams_to_set = {
        slug: role for slug, role in desired["teams"].items()
        if actual["teams"].get(slug) != role
    }
    teams_to_remove = [slug for slug in actual["teams"] if slug not in desired["teams"]]
    properties_to_set = {
        name: value for name, value in desired["properties"].items()
        if _normalize(actual["properties"].get(name)) != _normalize(value)
    }
    return {
        "teams_to_set": teams_to_set,
        "teams_to_remove": teams_to_remove,
        "properties_to_set": properties_to_set,
    }


def _has_changes(diff: dict) -> bool:
    return bool(diff["teams_to_set"] or diff["teams_to_remove"] or diff["properties_to_set"])


def _apply_teams(org, token, base, team_entries) -> dict:
    counts = {"total": len(team_entries), "created": 0, "updated": 0, "unchanged": 0}
    for entry in team_entries:
        name = entry["name"]
        desired_description = entry["description"]
        team = github_teams.find_team(org, token, name, base)
        if team is None:
            logger.info("Team '%s' not found, creating", name)
            github_teams.create_team(org, token, entry, base)
            counts["created"] += 1
        elif (team.get("description") or "") != desired_description:
            logger.info("Team '%s' description differs, updating", name)
            github_drift.update_team_description(org, token, team["slug"], desired_description, base)
            counts["updated"] += 1
        else:
            counts["unchanged"] += 1
    return counts


def _apply_repo(org, token, base, entry: dict):
    """Bring one repo in line with the yaml by comparing with GitHub.
    Returns (outcome label, diff)."""
    name = entry["name"]
    desired = {
        "teams": {team["name"]: team["role"] for team in entry["teams"]},
        "properties": entry["properties"],
    }

    created = github_repos.get_repo(org, token, name, base) is None
    if created:
        github_repos.create_repo(org, token, {"name": name}, base)

    actual = {
        "teams": github_drift.list_repo_teams(org, token, name, base),
        "properties": github_drift.get_repo_properties(org, token, name, base),
    }
    diff = diff_repo(desired, actual)
    for slug, role in diff["teams_to_set"].items():
        github_repos.attach_team_to_repo(org, token, name, slug, role, base)
    for slug in diff["teams_to_remove"]:
        github_drift.remove_team_from_repo(org, token, name, slug, base)
    if diff["properties_to_set"]:
        github_repos.set_repo_properties(org, token, name, diff["properties_to_set"], base)

    if created:
        return "created", diff
    return ("updated" if _has_changes(diff) else "unchanged"), diff


def apply_template(template_path: str, vars_path: str = "vars.env") -> dict:
    if os.path.basename(template_path) == "template.yaml":
        raise ValueError("Scenario C uses stress_template.yaml only")

    started = time.monotonic()
    validate_file(template_path)
    github_http.reset_stats()
    config = load_config(vars_path)
    token = make_token_provider(config)
    org = config["github_org"]
    base = config["github_api_base_url"]
    parsed = parse_template(template_path)

    ensure_property_schema(org, token(), parsed["property_definitions"], base)
    repos = parsed["repositories"]
    metrics = {
        "teams": _apply_teams(org, token, base, parsed["teams"]),
        "repositories": {
            "total": len(repos), "created": 0, "adopted": 0, "updated": 0, "unchanged": 0, "failed": 0,
        },
        "team_assignments": {
            "total": sum(len(r["teams"]) for r in repos), "set": 0, "removed": 0,
        },
        "properties": {
            "definitions": len(parsed["property_definitions"]),
            "values_total": sum(len(r["properties"]) for r in repos),
            "values_set": 0,
        },
    }
    repo_counts = metrics["repositories"]
    for index, entry in enumerate(repos, start=1):
        try:
            outcome, diff = _apply_repo(org, token, base, entry)
        except Exception as exc:
            logger.error("Failed to apply repo '%s': %s", entry["name"], exc)
            repo_counts["failed"] += 1
            continue
        repo_counts[outcome] += 1
        metrics["team_assignments"]["set"] += len(diff["teams_to_set"])
        metrics["team_assignments"]["removed"] += len(diff["teams_to_remove"])
        metrics["properties"]["values_set"] += len(diff["properties_to_set"])
        if index % LOG_EVERY == 0:
            logger.info("Applied %d/%d repos", index, len(repos))

    # Without state, the app cannot know what used to be in the yaml.
    metrics["not_in_yaml"] = None
    metrics["api"] = github_http.get_stats()
    metrics["seconds"] = round(time.monotonic() - started, 1)
    return metrics


def _format_api(api: dict) -> str:
    methods = ", ".join(f"{m} {n}" for m, n in sorted(api["by_method"].items()))
    quota = api["rate_limit_remaining"] if api["rate_limit_remaining"] is not None else "unknown"
    return (
        f"API requests: {api['total']} total ({methods}), "
        f"{api['rate_limited']} rate-limited, quota remaining {quota}"
    )


def format_summary(metrics: dict) -> str:
    teams, repos = metrics["teams"], metrics["repositories"]
    assignments, props = metrics["team_assignments"], metrics["properties"]
    return "\n".join([
        f"Teams: {teams['total']} total, {teams['created']} created, {teams['updated']} updated, {teams['unchanged']} unchanged",
        f"Repositories: {repos['total']} total, {repos['created']} created, {repos['adopted']} adopted, "
        f"{repos['updated']} updated, {repos['unchanged']} unchanged, {repos['failed']} failed",
        f"Team assignments: {assignments['total']} total, {assignments['set']} set, {assignments['removed']} removed",
        f"Properties: {props['definitions']} definitions, {props['values_total']} values total, {props['values_set']} values set",
        _format_api(metrics["api"]),
        "Not in yaml: not tracked (no state)",
        f"Time: {metrics['seconds']} s",
    ])


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    template = sys.argv[1] if len(sys.argv) > 1 else "stress_template.yaml"
    try:
        print(format_summary(apply_template(template, "vars.env")))
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
