import json

import pytest
import responses

from src.github_repos import (
    attach_team_to_repo,
    create_repo,
    create_repo_fork,
    delete_repo,
    set_repo_properties,
)


@responses.activate
def test_create_repo_posts_to_org_repos():
    responses.add(
        responses.GET,
        "https://api.github.com/repos/my-org/docker-jenkins",
        json={"message": "Not Found"},
        status=404,
    )
    responses.add(
        responses.POST,
        "https://api.github.com/orgs/my-org/repos",
        json={"name": "docker-jenkins"},
        status=201,
    )
    entry = {"name": "docker-jenkins"}
    create_repo("my-org", "ghs_abc123", entry, "https://api.github.com")
    assert responses.calls[1].request.url == "https://api.github.com/orgs/my-org/repos"


@responses.activate
def test_create_repo_failure_raises():
    responses.add(
        responses.GET,
        "https://api.github.com/repos/my-org/docker-jenkins",
        json={"message": "Not Found"},
        status=404,
    )
    responses.add(
        responses.POST,
        "https://api.github.com/orgs/my-org/repos",
        json={"message": "name already exists"},
        status=422,
    )
    entry = {"name": "docker-jenkins"}
    with pytest.raises(RuntimeError, match="422"):
        create_repo("my-org", "ghs_abc123", entry, "https://api.github.com")


@responses.activate
def test_create_repo_fork_posts_to_source_forks():
    responses.add(
        responses.POST,
        "https://api.github.com/repos/some-org/docker-jenkins-upstream/forks",
        json={"name": "docker-jenkins"},
        status=202,
    )
    entry = {
        "type": "repository-fork",
        "name": "docker-jenkins",
        "source": "some-org/docker-jenkins-upstream",
    }
    create_repo_fork("my-org", "ghs_abc123", entry, "https://api.github.com")
    assert responses.calls[0].request.url == "https://api.github.com/repos/some-org/docker-jenkins-upstream/forks"


@responses.activate
def test_create_repo_fork_failure_raises():
    responses.add(
        responses.POST,
        "https://api.github.com/repos/some-org/docker-jenkins-upstream/forks",
        json={"message": "not found"},
        status=404,
    )
    entry = {
        "type": "repository-fork",
        "name": "docker-jenkins",
        "source": "some-org/docker-jenkins-upstream",
    }
    with pytest.raises(RuntimeError, match="404"):
        create_repo_fork("my-org", "ghs_abc123", entry, "https://api.github.com")


@responses.activate
def test_attach_team_to_repo_puts_permission():
    responses.add(
        responses.PUT,
        "https://api.github.com/orgs/my-org/teams/jenkins-team/repos/my-org/docker-jenkins",
        status=204,
    )
    attach_team_to_repo("my-org", "ghs_abc123", "docker-jenkins", "jenkins-team", "maintain", "https://api.github.com")
    assert responses.calls[0].request.url.endswith("/teams/jenkins-team/repos/my-org/docker-jenkins")


@responses.activate
def test_set_repo_properties_patches_values():
    responses.add(
        responses.PATCH,
        "https://api.github.com/repos/my-org/docker-jenkins/properties/values",
        status=204,
    )
    set_repo_properties("my-org", "ghs_abc123", "docker-jenkins", {"euc-flag": "true"}, "https://api.github.com")
    assert responses.calls[0].request.url.endswith("/properties/values")


@responses.activate
def test_set_repo_properties_clears_removed_value():
    responses.add(
        responses.PATCH,
        "https://api.github.com/repos/my-org/docker-jenkins/properties/values",
        status=204,
    )
    set_repo_properties(
        "my-org", "ghs_abc123", "docker-jenkins", {"euc-flag": None}, "https://api.github.com"
    )
    assert json.loads(responses.calls[0].request.body)["properties"] == [
        {"property_name": "euc-flag", "value": None}
    ]


@responses.activate
def test_delete_repo_uses_repository_delete_endpoint():
    responses.add(
        responses.DELETE,
        "https://api.github.com/repos/my-org/docker-jenkins",
        status=204,
    )
    delete_repo("my-org", "ghs_abc123", "docker-jenkins", "https://api.github.com")
    assert responses.calls[0].request.method == "DELETE"


@responses.activate
def test_delete_repo_is_idempotent_when_already_missing():
    responses.add(
        responses.DELETE,
        "https://api.github.com/repos/my-org/docker-jenkins",
        json={"message": "Not Found"},
        status=404,
    )
    delete_repo("my-org", "ghs_abc123", "docker-jenkins", "https://api.github.com")


@responses.activate
def test_create_repo_skips_post_when_repo_already_exists():
    responses.add(
        responses.GET,
        "https://api.github.com/repos/my-org/docker-jenkins",
        json={"name": "docker-jenkins"},
        status=200,
    )
    entry = {"name": "docker-jenkins"}
    create_repo("my-org", "ghs_abc123", entry, "https://api.github.com")
    methods = [call.request.method for call in responses.calls]
    assert "POST" not in methods


@responses.activate
def test_create_repo_posts_when_repo_missing():
    responses.add(
        responses.GET,
        "https://api.github.com/repos/my-org/docker-jenkins",
        json={"message": "Not Found"},
        status=404,
    )
    responses.add(
        responses.POST,
        "https://api.github.com/orgs/my-org/repos",
        json={"name": "docker-jenkins"},
        status=201,
    )
    entry = {"name": "docker-jenkins"}
    create_repo("my-org", "ghs_abc123", entry, "https://api.github.com")
    methods = [call.request.method for call in responses.calls]
    assert "POST" in methods


@responses.activate
def test_create_repo_attaches_teams_and_properties():
    responses.add(responses.GET, "https://api.github.com/repos/my-org/docker-jenkins", json={"message": "Not Found"}, status=404)
    responses.add(responses.POST, "https://api.github.com/orgs/my-org/repos", json={"name": "docker-jenkins"}, status=201)
    responses.add(responses.PUT, "https://api.github.com/orgs/my-org/teams/jenkins-team/repos/my-org/docker-jenkins", status=204)
    responses.add(responses.PATCH, "https://api.github.com/repos/my-org/docker-jenkins/properties/values", status=204)
    entry = {
        "name": "docker-jenkins",
        "teams": [{"name": "jenkins-team", "role": "maintain"}],
        "properties": {"euc-flag": "true"},
    }
    create_repo("my-org", "ghs_abc123", entry, "https://api.github.com")
    assert len(responses.calls) == 4


@responses.activate
def test_create_repo_connection_error_raises_clear_error():
    import requests
    responses.add(
        responses.GET,
        "https://api.github.com/repos/my-org/docker-jenkins",
        body=requests.exceptions.ConnectionError("connection refused"),
    )
    entry = {"name": "docker-jenkins"}
    with pytest.raises(RuntimeError, match="[Cc]ould not reach"):
        create_repo("my-org", "ghs_abc123", entry, "https://api.github.com")


@responses.activate
def test_get_repo_returns_repo_json_with_id():
    from src.github_repos import get_repo

    responses.add(
        responses.GET,
        "https://api.github.com/repos/my-org/docker-jenkins",
        json={"name": "docker-jenkins", "id": 999111, "private": True},
        status=200,
    )
    result = get_repo("my-org", "ghs_abc123", "docker-jenkins", "https://api.github.com")
    assert result == {"name": "docker-jenkins", "id": 999111, "private": True}


@responses.activate
def test_get_repo_missing_returns_none(caplog):
    from src.github_repos import get_repo

    responses.add(
        responses.GET,
        "https://api.github.com/repos/my-org/docker-jenkins",
        json={"message": "Not Found"},
        status=404,
    )
    assert get_repo("my-org", "ghs_abc123", "docker-jenkins", "https://api.github.com") is None
    assert "ERROR" not in caplog.text


@responses.activate
def test_get_repo_failure_raises():
    from src.github_repos import get_repo

    responses.add(
        responses.GET,
        "https://api.github.com/repos/my-org/docker-jenkins",
        json={"message": "boom"},
        status=500,
    )
    with pytest.raises(RuntimeError, match="500"):
        get_repo("my-org", "ghs_abc123", "docker-jenkins", "https://api.github.com")
