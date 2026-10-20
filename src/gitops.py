from src import github_drift, github_repos, github_teams
from src import github_http
from src.github_properties import ensure_property_schema

GITHUB_API = "https://api.github.com"
DEPLOYMENT_PAGE_SIZE = 100


def _check(response, operation: str) -> None:
    if response.status_code < 200 or response.status_code >= 300:
        raise RuntimeError(
            f"Failed to {operation}: {response.status_code} {response.text}"
        )


def latest_successful_deployment_commit(
    owner: str,
    repo: str,
    environment: str,
    token: str,
) -> str | None:
    page = 1
    while True:
        response = github_http.request(
            "GET",
            f"{GITHUB_API}/repos/{owner}/{repo}/deployments",
            token,
            f"listing deployments for '{environment}'",
            params={
                "environment": environment,
                "per_page": DEPLOYMENT_PAGE_SIZE,
                "page": page,
            },
        )
        _check(response, f"list deployments for '{environment}'")
        deployments = response.json()
        for deployment in deployments:
            statuses = github_http.request(
                "GET",
                f"{GITHUB_API}/repos/{owner}/{repo}/deployments/{deployment['id']}/statuses",
                token,
                f"listing deployment statuses for '{environment}'",
                params={"per_page": DEPLOYMENT_PAGE_SIZE},
            )
            _check(statuses, f"list deployment statuses for '{environment}'")
            status_list = statuses.json()
            if status_list and status_list[0]["state"] == "success":
                return deployment["sha"]
        if len(deployments) < DEPLOYMENT_PAGE_SIZE:
            return None
        page += 1


def record_deployment(
    owner: str,
    repo: str,
    environment: str,
    commit_sha: str,
    state: str,
    token: str,
) -> None:
    if state not in {"success", "failure"}:
        raise ValueError("Deployment state must be 'success' or 'failure'")
    url = f"{GITHUB_API}/repos/{owner}/{repo}/deployments"
    response = github_http.request(
        "POST",
        url,
        token,
        f"creating deployment for '{environment}'",
        json={
            "ref": commit_sha,
            "environment": environment,
            "auto_merge": False,
            "required_contexts": [],
        },
    )
    _check(response, f"create deployment for '{environment}'")
    deployment_id = response.json()["id"]
    status = github_http.request(
        "POST",
        f"{url}/{deployment_id}/statuses",
        token,
        f"recording deployment {state} for '{environment}'",
        json={"state": state, "auto_inactive": False},
    )
    _check(status, f"record deployment {state} for '{environment}'")


def _repo_fields(entry: dict) -> dict:
    return {
        "name": entry["name"],
        "teams": {team["name"]: team["role"] for team in entry["teams"]},
        "properties": entry["properties"],
        "type": entry.get("type"),
        "source": entry.get("source"),
    }


def _same_properties(first: dict, second: dict) -> bool:
    def normalize(value):
        return sorted(value) if isinstance(value, list) else value

    return first.keys() == second.keys() and all(
        normalize(first[name]) == normalize(second[name]) for name in first
    )


def _repo_changed(previous: dict, current: dict) -> bool:
    before, after = _repo_fields(previous), _repo_fields(current)
    return (
        before["name"] != after["name"]
        or before["teams"] != after["teams"]
        or before["type"] != after["type"]
        or before["source"] != after["source"]
        or not _same_properties(before["properties"], after["properties"])
    )


def plan_changes(previous: dict, current: dict) -> dict:
    previous_teams = {team["name"]: team for team in previous["teams"]}
    current_teams = {team["name"]: team for team in current["teams"]}
    previous_repos = {repo["id"]: repo for repo in previous["repositories"]}
    current_repos = {repo["id"]: repo for repo in current["repositories"]}
    previous_definitions = {
        definition["name"]: definition for definition in previous["property_definitions"]
    }
    current_definitions = {
        definition["name"]: definition for definition in current["property_definitions"]
    }

    return {
        "teams_upsert": [
            team for team in current["teams"]
            if previous_teams.get(team["name"]) != team
        ],
        "teams_removed": [
            team["name"] for team in previous["teams"]
            if team["name"] not in current_teams
        ],
        "repos_upsert": [
            {
                "before": previous_repos.get(repo["id"]),
                "after": repo,
            }
            for repo in current["repositories"]
            if repo["id"] not in previous_repos
            or _repo_changed(previous_repos[repo["id"]], repo)
        ],
        "repos_removed": [
            repo["id"] for repo in previous["repositories"]
            if repo["id"] not in current_repos
        ],
        "definitions_upsert": [
            definition for definition in current["property_definitions"]
            if previous_definitions.get(definition["name"]) != definition
        ],
    }


def _team_map(entry: dict) -> dict:
    return {team["name"]: team["role"] for team in entry["teams"]}


def _apply_repo_change(org: str, token: str, base: str, before: dict, after: dict) -> None:
    if before["name"] != after["name"]:
        github_drift.rename_repo(org, token, before["name"], after["name"], base)

    before_teams, after_teams = _team_map(before), _team_map(after)
    for team_name in before_teams.keys() - after_teams.keys():
        github_drift.remove_team_from_repo(org, token, after["name"], team_name, base)
    for team_name, role in after_teams.items():
        if before_teams.get(team_name) != role:
            github_repos.attach_team_to_repo(
                org, token, after["name"], team_name, role, base
            )

    changed_properties = {
        name: after["properties"][name]
        for name in after["properties"]
        if name not in before["properties"]
        or not _same_properties(
            {name: before["properties"][name]},
            {name: after["properties"][name]},
        )
    }
    changed_properties.update({
        name: None
        for name in before["properties"]
        if name not in after["properties"]
    })
    if changed_properties:
        github_repos.set_repo_properties(
            org, token, after["name"], changed_properties, base
        )


def apply_changes(
    previous: dict,
    current: dict,
    config: dict,
    token_provider,
) -> dict:
    plan = plan_changes(previous, current)
    if not any(plan.values()):
        return plan

    org, base = config["github_org"], config["github_api_base_url"]
    token = token_provider()
    if plan["definitions_upsert"]:
        ensure_property_schema(org, token, plan["definitions_upsert"], base)

    for entry in plan["teams_upsert"]:
        actual = github_teams.find_team(org, token, entry["name"], base)
        if actual is None:
            github_teams.create_team(org, token, entry, base)
        elif actual.get("description") != entry["description"]:
            github_drift.update_team_description(
                org, token, actual["slug"], entry["description"], base
            )

    previous_repos = {repo["id"]: repo for repo in previous["repositories"]}
    for repo_id in plan["repos_removed"]:
        github_repos.delete_repo(
            org, token, previous_repos[repo_id]["name"], base
        )

    for change in plan["repos_upsert"]:
        before, after = change["before"], change["after"]
        if before is None:
            github_repos.create_repo(org, token, after, base)
        else:
            _apply_repo_change(org, token, base, before, after)

    for team_name in plan["teams_removed"]:
        actual = github_teams.find_team(org, token, team_name, base)
        if actual is not None:
            github_teams.delete_team(org, token, actual["slug"], base)

    return plan
