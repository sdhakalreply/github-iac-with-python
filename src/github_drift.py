import logging

from src import github_http

logger = logging.getLogger(__name__)


def _check(response, what: str) -> None:
    if response.status_code < 200 or response.status_code >= 300:
        raise RuntimeError(f"Failed to {what}: {response.status_code} {response.text}")


def list_repo_teams(org: str, token: str, repo_name: str, api_base_url: str) -> dict:
    """Return {team_slug: permission} for the teams attached to a repo."""
    teams = {}
    page = 1
    while True:
        response = github_http.request(
            "GET",
            f"{api_base_url}/repos/{org}/{repo_name}/teams",
            token,
            f"listing teams of repo '{repo_name}'",
            params={"per_page": 100, "page": page},
        )
        _check(response, f"list teams of repo '{repo_name}'")
        batch = response.json()
        for team in batch:
            teams[team["slug"]] = team["permission"]
        if len(batch) < 100:
            return teams
        page += 1


def get_repo_properties(org: str, token: str, repo_name: str, api_base_url: str) -> dict:
    """Return {property_name: value} for properties that have a value."""
    response = github_http.request(
        "GET",
        f"{api_base_url}/repos/{org}/{repo_name}/properties/values",
        token,
        f"fetching properties of repo '{repo_name}'",
    )
    _check(response, f"fetch properties of repo '{repo_name}'")
    return {
        item["property_name"]: item["value"]
        for item in response.json()
        if item.get("value") is not None
    }


def remove_team_from_repo(org: str, token: str, repo_name: str, team_slug: str, api_base_url: str) -> None:
    response = github_http.request(
        "DELETE",
        f"{api_base_url}/orgs/{org}/teams/{team_slug}/repos/{org}/{repo_name}",
        token,
        f"removing team '{team_slug}' from repo '{repo_name}'",
    )
    _check(response, f"remove team '{team_slug}' from repo '{repo_name}'")


def rename_repo(org: str, token: str, current_name: str, new_name: str, api_base_url: str) -> None:
    response = github_http.request(
        "PATCH",
        f"{api_base_url}/repos/{org}/{current_name}",
        token,
        f"renaming repo '{current_name}'",
        json={"name": new_name},
    )
    _check(response, f"rename repo '{current_name}' to '{new_name}'")


def update_team_description(org: str, token: str, team_slug: str, description: str, api_base_url: str) -> None:
    response = github_http.request(
        "PATCH",
        f"{api_base_url}/orgs/{org}/teams/{team_slug}",
        token,
        f"updating team '{team_slug}'",
        json={"description": description},
    )
    _check(response, f"update team '{team_slug}'")
