import pytest
import responses

from src.github_hooks import create_hook


@responses.activate
def test_create_hook_with_url_field():
    responses.add(
        responses.GET,
        "https://api.github.com/repos/my-org/docker-jenkins/hooks",
        json=[],
        status=200,
    )
    responses.add(
        responses.POST,
        "https://api.github.com/repos/my-org/docker-jenkins/hooks",
        status=201,
    )
    hook_entry = {
        "name": "argocd-webhook",
        "url": "https://argocd.platform.cloud.allianz.io/hook",
        "events": ["push", "pull_request"],
        "secret": "MY_GITHUB_SECRET",
    }
    create_hook("my-org", "ghs_abc123", "docker-jenkins", hook_entry, "fallback-secret", "https://api.github.com")
    body = responses.calls[1].request.body
    assert b"argocd.platform.cloud.allianz.io" in body


@responses.activate
def test_create_hook_with_target_url_field():
    responses.add(
        responses.GET,
        "https://api.github.com/repos/my-org/docker-jenkins/hooks",
        json=[],
        status=200,
    )
    responses.add(
        responses.POST,
        "https://api.github.com/repos/my-org/docker-jenkins/hooks",
        status=201,
    )
    hook_entry = {
        "name": "jenkins-webhook_v2",
        "source_url": "https://jenkins-source.example/github-webhook/",
        "target_url": "https://jenkins-target.example/github-webhook/",
        "events": ["push", "pull_request"],
    }
    create_hook("my-org", "ghs_abc123", "docker-jenkins", hook_entry, "fallback-secret", "https://api.github.com")
    body = responses.calls[1].request.body
    assert b"jenkins-target.example" in body


def test_create_hook_missing_url_raises():
    hook_entry = {"name": "broken-hook", "events": ["push"]}
    with pytest.raises(ValueError, match="no url or target_url"):
        create_hook("my-org", "ghs_abc123", "docker-jenkins", hook_entry, "fallback-secret", "https://api.github.com")


@responses.activate
def test_create_hook_failure_raises():
    responses.add(
        responses.GET,
        "https://api.github.com/repos/my-org/docker-jenkins/hooks",
        json=[],
        status=200,
    )
    responses.add(
        responses.POST,
        "https://api.github.com/repos/my-org/docker-jenkins/hooks",
        json={"message": "Validation failed"},
        status=422,
    )
    hook_entry = {"name": "argocd-webhook", "url": "https://argocd.example/hook", "events": ["push"]}
    with pytest.raises(RuntimeError, match="422"):
        create_hook("my-org", "ghs_abc123", "docker-jenkins", hook_entry, "fallback-secret", "https://api.github.com")


@responses.activate
def test_create_hook_skips_post_when_url_already_registered():
    responses.add(
        responses.GET,
        "https://api.github.com/repos/my-org/docker-jenkins/hooks",
        json=[{"id": 1, "config": {"url": "https://argocd.example/hook"}}],
        status=200,
    )
    hook_entry = {"name": "argocd-webhook", "url": "https://argocd.example/hook", "events": ["push"]}
    create_hook("my-org", "ghs_abc123", "docker-jenkins", hook_entry, "fallback-secret", "https://api.github.com")
    methods = [call.request.method for call in responses.calls]
    assert "POST" not in methods


@responses.activate
def test_create_hook_posts_when_url_not_registered():
    responses.add(
        responses.GET,
        "https://api.github.com/repos/my-org/docker-jenkins/hooks",
        json=[{"id": 1, "config": {"url": "https://other.example/hook"}}],
        status=200,
    )
    responses.add(
        responses.POST,
        "https://api.github.com/repos/my-org/docker-jenkins/hooks",
        status=201,
    )
    hook_entry = {"name": "argocd-webhook", "url": "https://argocd.example/hook", "events": ["push"]}
    create_hook("my-org", "ghs_abc123", "docker-jenkins", hook_entry, "fallback-secret", "https://api.github.com")
    methods = [call.request.method for call in responses.calls]
    assert "POST" in methods


@responses.activate
def test_create_hook_connection_error_raises_clear_error():
    import requests
    responses.add(
        responses.GET,
        "https://api.github.com/repos/my-org/docker-jenkins/hooks",
        body=requests.exceptions.ConnectionError("connection refused"),
    )
    hook_entry = {"name": "argocd-webhook", "url": "https://argocd.example/hook", "events": ["push"]}
    with pytest.raises(RuntimeError, match="[Cc]ould not reach"):
        create_hook("my-org", "ghs_abc123", "docker-jenkins", hook_entry, "fallback-secret", "https://api.github.com")
