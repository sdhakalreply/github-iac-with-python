import logging

import requests

from src import github_http

logger = logging.getLogger(__name__)


def _request(method: str, url: str, token: str, action: str, **kwargs) -> requests.Response:
    return github_http.request(method, url, token, action, **kwargs)


def _attach_teams_and_properties(org: str, token: str, entry: dict, api_base_url: str) -> None:
    for team in entry.get("teams", []):
        attach_team_to_repo(
            org,
            token,
            entry["name"],
            team["name"],
            team["role"],
            api_base_url,
        )

    if entry.get("properties"):
        set_repo_properties(
            org,
            token,
            entry["name"],
            entry["properties"],
            api_base_url,
        )


def _repo_exists(org: str, token: str, repo_name: str, api_base_url: str) -> bool:
    response = _request(
        "GET",
        f"{api_base_url}/repos/{org}/{repo_name}",
        token,
        f"checking if repo '{repo_name}' exists",
    )
    return response.status_code == 200


def get_repo(org: str, token: str, repo_name: str, api_base_url: str) -> dict:
    """Return the repo dict, or None if it does not exist (404). Other
    failures raise RuntimeError."""
    response = _request(
        "GET",
        f"{api_base_url}/repos/{org}/{repo_name}",
        token,
        f"fetching repo '{repo_name}'",
    )
    if response.status_code == 404:
        return None
    if response.status_code < 200 or response.status_code >= 300:
        logger.error(
            "Failed to fetch repo '%s': %s %s", repo_name, response.status_code, response.text
        )
        raise RuntimeError(
            f"Failed to fetch repo '{repo_name}': {response.status_code} {response.text}"
        )
    return response.json()


def create_repo(org: str, token: str, entry: dict, api_base_url: str) -> None:
    if _repo_exists(org, token, entry["name"], api_base_url):
        logger.info("Repo '%s' already exists, will not create", entry["name"])
    else:
        logger.info("Creating repo '%s'", entry["name"])
        payload = {"name": entry["name"]}

        response = _request(
            "POST",
            f"{api_base_url}/orgs/{org}/repos",
            token,
            f"creating repo '{entry['name']}'",
            json=payload,
        )

        if response.status_code < 200 or response.status_code >= 300:
            logger.error(
                "Failed to create repo '%s': %s %s",
                entry["name"], response.status_code, response.text,
            )
            raise RuntimeError(
                f"Failed to create repo '{entry['name']}': {response.status_code} {response.text}"
            )
        logger.info("Repo '%s' created", entry["name"])

    _attach_teams_and_properties(org, token, entry, api_base_url)


def delete_repo(org: str, token: str, repo_name: str, api_base_url: str) -> None:
    response = _request(
        "DELETE",
        f"{api_base_url}/repos/{org}/{repo_name}",
        token,
        f"deleting repo '{repo_name}'",
    )
    if response.status_code == 404:
        logger.info("Repo '%s' already absent", repo_name)
        return
    if response.status_code < 200 or response.status_code >= 300:
        raise RuntimeError(
            f"Failed to delete repo '{repo_name}': {response.status_code} {response.text}"
        )
    logger.info("Repo '%s' deleted", repo_name)


def create_repo_fork(org: str, token: str, entry: dict, api_base_url: str) -> None:
    logger.info("Forking repo '%s' as '%s'", entry["source"], entry["name"])
    payload = {
        "organization": org,
        "name": entry["name"],
    }

    response = _request(
        "POST",
        f"{api_base_url}/repos/{entry['source']}/forks",
        token,
        f"forking repo '{entry['source']}' as '{entry['name']}'",
        json=payload,
    )

    if response.status_code < 200 or response.status_code >= 300:
        logger.error(
            "Failed to fork repo '%s' as '%s': %s %s",
            entry["source"], entry["name"], response.status_code, response.text,
        )
        raise RuntimeError(
            f"Failed to fork repo '{entry['source']}' as '{entry['name']}': {response.status_code} {response.text}"
        )

    logger.info("Repo '%s' forked from '%s'", entry["name"], entry["source"])
    _attach_teams_and_properties(org, token, entry, api_base_url)


def set_repo_visibility(
    org: str,
    token: str,
    repo_name: str,
    private: bool,
    api_base_url: str,
) -> None:
    logger.info("Setting visibility for repo '%s' to private=%s", repo_name, private)
    payload = {"private": private}

    response = _request(
        "PATCH",
        f"{api_base_url}/repos/{org}/{repo_name}",
        token,
        f"setting visibility for repo '{repo_name}'",
        json=payload,
    )

    if response.status_code < 200 or response.status_code >= 300:
        logger.error(
            "Failed to set visibility for repo '%s': %s %s",
            repo_name, response.status_code, response.text,
        )
        raise RuntimeError(
            f"Failed to set visibility for repo '{repo_name}': {response.status_code} {response.text}"
        )

    logger.info("Visibility for repo '%s' set to private=%s", repo_name, private)


def attach_team_to_repo(
    org: str,
    token: str,
    repo_name: str,
    team_slug: str,
    role: str,
    api_base_url: str,
) -> None:
    logger.info("Attaching team '%s' to repo '%s' with role '%s'", team_slug, repo_name, role)
    payload = {"permission": role}

    response = _request(
        "PUT",
        f"{api_base_url}/orgs/{org}/teams/{team_slug}/repos/{org}/{repo_name}",
        token,
        f"attaching team '{team_slug}' to repo '{repo_name}'",
        json=payload,
    )

    if response.status_code < 200 or response.status_code >= 300:
        logger.error(
            "Failed to attach team '%s' to repo '%s': %s %s",
            team_slug, repo_name, response.status_code, response.text,
        )
        raise RuntimeError(
            f"Failed to attach team '{team_slug}' to repo '{repo_name}': {response.status_code} {response.text}"
        )

    logger.info("Team '%s' attached to repo '%s'", team_slug, repo_name)


def set_repo_properties(
    org: str,
    token: str,
    repo_name: str,
    properties: dict,
    api_base_url: str,
) -> None:
    logger.info("Setting properties for repo '%s': %s", repo_name, list(properties.keys()))
    payload = {
        "properties": [
            {"property_name": key, "value": value}
            for key, value in properties.items()
        ]
    }

    response = _request(
        "PATCH",
        f"{api_base_url}/repos/{org}/{repo_name}/properties/values",
        token,
        f"setting properties for repo '{repo_name}'",
        json=payload,
    )

    if response.status_code < 200 or response.status_code >= 300:
        logger.error(
            "Failed to set properties for repo '%s': %s %s",
            repo_name, response.status_code, response.text,
        )
        raise RuntimeError(
            f"Failed to set properties for repo '{repo_name}': {response.status_code} {response.text}"
        )

    logger.info("Properties set for repo '%s'", repo_name)
