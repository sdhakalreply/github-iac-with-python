import pytest
import responses
from src.github_teams import create_team, delete_team


@responses.activate
def test_create_team_success():
    responses.add(
        responses.GET,
        "https://api.github.com/orgs/my-org/teams/jenkins-team",
        json={"message": "Not Found"},
        status=404,
    )
    responses.add(
        responses.POST,
        "https://api.github.com/orgs/my-org/teams",
        json={"slug": "jenkins-team"},
        status=201,
    )
    entry = {"name": "jenkins-team", "description": "team manages jenkins service"}
    slug = create_team("my-org", "ghs_abc123", entry, "https://api.github.com")
    assert slug == "jenkins-team"


@responses.activate
def test_create_team_failure_raises():
    responses.add(
        responses.GET,
        "https://api.github.com/orgs/my-org/teams/jenkins-team",
        json={"message": "Not Found"},
        status=404,
    )
    responses.add(
        responses.POST,
        "https://api.github.com/orgs/my-org/teams",
        json={"message": "Name already exists"},
        status=422,
    )
    entry = {"name": "jenkins-team"}
    with pytest.raises(RuntimeError, match="422"):
        create_team("my-org", "ghs_abc123", entry, "https://api.github.com")


@responses.activate
def test_create_team_authorization_header():
    """Test that the Authorization header uses exact token value."""
    token = "ghs_abc123def456"
    responses.add(
        responses.GET,
        "https://api.github.com/orgs/my-org/teams/test-team",
        json={"message": "Not Found"},
        status=404,
    )
    responses.add(
        responses.POST,
        "https://api.github.com/orgs/my-org/teams",
        json={"slug": "test-team"},
        status=201,
    )
    entry = {"name": "test-team"}
    create_team("my-org", token, entry, "https://api.github.com")
    
    # Verify the request was made with the exact Authorization header
    request = responses.calls[1].request
    expected_auth = f"Bearer {token}"
    assert request.headers["Authorization"] == expected_auth


@responses.activate
def test_create_team_skips_post_when_team_already_exists():
    responses.add(
        responses.GET,
        "https://api.github.com/orgs/my-org/teams/jenkins-team",
        json={"slug": "jenkins-team"},
        status=200,
    )
    entry = {"name": "jenkins-team"}
    slug = create_team("my-org", "ghs_abc123", entry, "https://api.github.com")
    methods = [call.request.method for call in responses.calls]
    assert "POST" not in methods
    assert slug == "jenkins-team"


@responses.activate
def test_create_team_posts_when_team_missing():
    responses.add(
        responses.GET,
        "https://api.github.com/orgs/my-org/teams/jenkins-team",
        json={"message": "Not Found"},
        status=404,
    )
    responses.add(
        responses.POST,
        "https://api.github.com/orgs/my-org/teams",
        json={"slug": "jenkins-team"},
        status=201,
    )
    entry = {"name": "jenkins-team"}
    slug = create_team("my-org", "ghs_abc123", entry, "https://api.github.com")
    methods = [call.request.method for call in responses.calls]
    assert "POST" in methods
    assert slug == "jenkins-team"


@responses.activate
def test_create_team_connection_error_raises_clear_error():
    import requests
    responses.add(
        responses.GET,
        "https://api.github.com/orgs/my-org/teams/jenkins-team",
        body=requests.exceptions.ConnectionError("connection refused"),
    )
    entry = {"name": "jenkins-team"}
    with pytest.raises(RuntimeError, match="[Cc]ould not reach"):
        create_team("my-org", "ghs_abc123", entry, "https://api.github.com")


@responses.activate
def test_get_team_returns_team_json_with_id():
    from src.github_teams import get_team

    responses.add(
        responses.GET,
        "https://api.github.com/orgs/my-org/teams/jenkins-team",
        json={"name": "jenkins-team", "id": 7001, "slug": "jenkins-team"},
        status=200,
    )
    result = get_team("my-org", "ghs_abc123", "jenkins-team", "https://api.github.com")
    assert result == {"name": "jenkins-team", "id": 7001, "slug": "jenkins-team"}


@responses.activate
def test_get_team_failure_raises():
    from src.github_teams import get_team

    responses.add(
        responses.GET,
        "https://api.github.com/orgs/my-org/teams/jenkins-team",
        json={"message": "Not Found"},
        status=404,
    )
    with pytest.raises(RuntimeError, match="404"):
        get_team("my-org", "ghs_abc123", "jenkins-team", "https://api.github.com")


@responses.activate
def test_delete_team_uses_team_delete_endpoint():
    responses.add(
        responses.DELETE,
        "https://api.github.com/orgs/my-org/teams/jenkins-team",
        status=204,
    )
    delete_team("my-org", "ghs_abc123", "jenkins-team", "https://api.github.com")
    assert responses.calls[0].request.method == "DELETE"


@responses.activate
def test_delete_team_is_idempotent_when_already_missing():
    responses.add(
        responses.DELETE,
        "https://api.github.com/orgs/my-org/teams/jenkins-team",
        json={"message": "Not Found"},
        status=404,
    )
    delete_team("my-org", "ghs_abc123", "jenkins-team", "https://api.github.com")
