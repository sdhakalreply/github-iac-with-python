from src.main import run


def test_run_creates_all_teams_then_all_repositories(monkeypatch):
    calls = []
    monkeypatch.setattr("src.main.load_config", lambda v: {"github_org": "my-org", "github_api_base_url": "https://api.github.com", "webhook_secret": "shh"})
    monkeypatch.setattr("src.main.parse_template", lambda p: {
        "teams": [{"name": "jenkins-team"}, {"name": "cicd-admins"}],
        "repositories": [{"name": "docker-jenkins"}],
    })
    monkeypatch.setattr("src.main.get_installation_token", lambda c: "ghs_abc123")
    monkeypatch.setattr("src.main.create_team", lambda org, token, entry, base: calls.append(("team", entry["name"])))
    monkeypatch.setattr("src.main.create_repo", lambda org, token, entry, base: calls.append(("repository", entry["name"])))

    run("template.yaml", "vars.env")

    assert calls == [("team", "jenkins-team"), ("team", "cicd-admins"), ("repository", "docker-jenkins")]


def test_run_dispatches_repository_fork_to_create_repo_fork(monkeypatch):
    calls = []
    monkeypatch.setattr("src.main.load_config", lambda v: {"github_org": "my-org", "github_api_base_url": "https://api.github.com", "webhook_secret": "shh"})
    monkeypatch.setattr("src.main.parse_template", lambda p: {
        "teams": [],
        "repositories": [{"type": "repository-fork", "name": "docker-jenkins", "source": "some-org/upstream"}],
    })
    monkeypatch.setattr("src.main.get_installation_token", lambda c: "ghs_abc123")
    monkeypatch.setattr("src.main.create_repo_fork", lambda org, token, entry, base: calls.append(entry["name"]))

    run("template.yaml", "vars.env")

    assert calls == ["docker-jenkins"]


def test_run_creates_hooks_for_repository(monkeypatch):
    calls = []
    monkeypatch.setattr("src.main.load_config", lambda v: {"github_org": "my-org", "github_api_base_url": "https://api.github.com", "webhook_secret": "shh"})
    monkeypatch.setattr("src.main.parse_template", lambda p: {
        "teams": [],
        "repositories": [{"name": "docker-jenkins", "hooks": [{"name": "argocd-webhook", "url": "https://argocd.example/hook"}]}],
    })
    monkeypatch.setattr("src.main.get_installation_token", lambda c: "ghs_abc123")
    monkeypatch.setattr("src.main.create_repo", lambda org, token, entry, base: None)
    monkeypatch.setattr("src.main.create_hook", lambda org, token, repo_name, hook_entry, default_secret, base: calls.append((repo_name, hook_entry["name"])))

    run("template.yaml", "vars.env")

    assert calls == [("docker-jenkins", "argocd-webhook")]
