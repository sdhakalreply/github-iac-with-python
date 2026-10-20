import logging

import requests

from src import github_http

logger = logging.getLogger(__name__)


def _request(method: str, url: str, token: str, action: str, **kwargs) -> requests.Response:
    return github_http.request(method, url, token, action, **kwargs)


def _get_existing_team_slug(org: str, token: str, team_name: str, api_base_url: str):
    response = _request(
        "GET",
        f"{api_base_url}/orgs/{org}/teams/{team_name}",
        token,
        f"checking if team '{team_name}' exists",
    )
    if response.status_code == 200:
        return response.json()["slug"]
    return None


def get_team(org: str, token: str, team_name: str, api_base_url: str) -> dict:
    """Fetch a team's current GitHub state (includes its immutable numeric
    `id`), used to record state right after create."""
    response = _request(
        "GET",
        f"{api_base_url}/orgs/{org}/teams/{team_name}",
        token,
        f"fetching team '{team_name}'",
    )
    if response.status_code < 200 or response.status_code >= 300:
        logger.error(
            "Failed to fetch team '%s': %s %s", team_name, response.status_code, response.text
        )
        raise RuntimeError(
            f"Failed to fetch team '{team_name}': {response.status_code} {response.text}"
        )
    return response.json()


def find_team(org: str, token: str, team_name: str, api_base_url: str):
    """Return the team dict, or None if it does not exist (404). Other
    failures raise RuntimeError."""
    response = _request(
        "GET",
        f"{api_base_url}/orgs/{org}/teams/{team_name}",
        token,
        f"looking up team '{team_name}'",
    )
    if response.status_code == 404:
        return None
    if response.status_code < 200 or response.status_code >= 300:
        logger.error(
            "Failed to look up team '%s': %s %s", team_name, response.status_code, response.text
        )
        raise RuntimeError(
            f"Failed to look up team '{team_name}': {response.status_code} {response.text}"
        )
    return response.json()


def create_team(org: str, token: str, entry: dict, api_base_url: str) -> str:
    """
    Create a team in a GitHub organization.
    
    Args:
        org: GitHub organization name
        token: GitHub installation token
        entry: Team dict with 'name' and optional 'description'
        api_base_url: GitHub API base URL (e.g., https://api.github.com)
    
    Returns:
        The created team's slug
    
    Raises:
        RuntimeError: If GitHub can't be reached, or the API returns a
            non-2xx status code.
    """
    existing_slug = _get_existing_team_slug(org, token, entry["name"], api_base_url)
    if existing_slug is not None:
        logger.info("Team '%s' already exists, will not create", entry["name"])
        return existing_slug

    logger.info("Creating team '%s'", entry["name"])
    payload = {
        "name": entry["name"],
        "description": entry.get("description", ""),
    }

    response = _request(
        "POST",
        f"{api_base_url}/orgs/{org}/teams",
        token,
        f"creating team '{entry['name']}'",
        json=payload,
    )

    if response.status_code >= 400:
        logger.error(
            "Failed to create team '%s': %s %s", entry["name"], response.status_code, response.text
        )
        raise RuntimeError(
            f"Failed to create team '{entry['name']}': {response.status_code} {response.text}"
        )

    logger.info("Team '%s' created", entry["name"])
    return response.json()["slug"]


def delete_team(org: str, token: str, team_slug: str, api_base_url: str) -> None:
    response = _request(
        "DELETE",
        f"{api_base_url}/orgs/{org}/teams/{team_slug}",
        token,
        f"deleting team '{team_slug}'",
    )
    if response.status_code == 404:
        logger.info("Team '%s' already absent", team_slug)
        return
    if response.status_code < 200 or response.status_code >= 300:
        raise RuntimeError(
            f"Failed to delete team '{team_slug}': {response.status_code} {response.text}"
        )
    logger.info("Team '%s' deleted", team_slug)
