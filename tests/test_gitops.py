import json
import os
import subprocess

import pytest
import responses

from src import gitops
from src.gitops import plan_changes


def test_action_settings_use_unreserved_environment_names():
    from scripts.run_gitops import load_action_settings

    settings = load_action_settings({
        "TARGET_ORG": "target-org",
        "API_BASE_URL": "https://api.github.com",
        "APP_ID": "123",
        "APP_INSTALLATION_ID": "456",
        "APP_PRIVATE_KEY": "private-key",
        "DEPLOYMENT_TOKEN": "token",
    })

    assert settings == {
        "github_org": "target-org",
        "github_api_base_url": "https://api.github.com",
        "github_app_id": "123",
        "github_app_installation_id": "456",
        "github_app_private_key": "private-key",
        "deployment_token": "token",
    }


def test_plan_changes_limits_work_to_yaml_differences():
    previous = {
        "property_definitions": [
            {"name": "category", "type": "single_select", "allowed_values": ["old"]},
            {"name": "kept", "type": "string"},
        ],
        "teams": [
            {"name": "team-a", "description": "old"},
            {"name": "team-b", "description": "same"},
        ],
        "repositories": [
            {
                "id": "repo-1",
                "name": "repo-old",
                "teams": [{"name": "team-a", "role": "pull"}],
                "properties": {"category": "old", "kept": "value", "removed": "x"},
            },
            {"id": "repo-2", "name": "repo-2", "teams": [], "properties": {}},
            {"id": "repo-3", "name": "repo-3", "teams": [], "properties": {}},
        ],
    }
    current = {
        "property_definitions": [
            {"name": "category", "type": "single_select", "allowed_values": ["new"]},
            {"name": "kept", "type": "string"},
            {"name": "added", "type": "string"},
        ],
        "teams": [
            {"name": "team-a", "description": "new"},
            {"name": "team-c", "description": "new"},
        ],
        "repositories": [
            {
                "id": "repo-1",
                "name": "repo-new",
                "teams": [{"name": "team-a", "role": "push"}, {"name": "team-c", "role": "pull"}],
                "properties": {"category": "new", "kept": "value"},
            },
            {"id": "repo-2", "name": "repo-2", "teams": [], "properties": {}},
            {"id": "repo-4", "name": "repo-4", "teams": [], "properties": {}},
        ],
    }

    plan = plan_changes(previous, current)

    assert plan["teams_upsert"] == [{"name": "team-a", "description": "new"}, {"name": "team-c", "description": "new"}]
    assert plan["teams_removed"] == ["team-b"]
    assert [change["after"]["id"] for change in plan["repos_upsert"]] == ["repo-1", "repo-4"]
    assert plan["repos_upsert"][0]["before"]["name"] == "repo-old"
    assert plan["repos_removed"] == ["repo-3"]
    assert plan["definitions_upsert"] == [
        {"name": "category", "type": "single_select", "allowed_values": ["new"]},
        {"name": "added", "type": "string"},
    ]


def test_plan_changes_empty_for_identical_templates():
    template = {
        "property_definitions": [{"name": "p", "type": "string"}],
        "teams": [{"name": "team-a", "description": "same"}],
        "repositories": [
            {"id": "repo-1", "name": "repo-1", "teams": [], "properties": {"p": "v"}},
        ],
    }
    assert plan_changes(template, template) == {
        "teams_upsert": [],
        "teams_removed": [],
        "repos_upsert": [],
        "repos_removed": [],
        "definitions_upsert": [],
    }


def test_apply_changes_touches_only_changed_entries(monkeypatch):
    previous = {
        "property_definitions": [{"name": "category", "type": "string"}],
        "teams": [
            {"name": "team-a", "description": "old"},
            {"name": "team-b", "description": "same"},
        ],
        "repositories": [
            {
                "id": "repo-1",
                "name": "repo-old",
                "teams": [{"name": "team-a", "role": "pull"}, {"name": "team-b", "role": "push"}],
                "properties": {"category": "old", "removed": "x"},
            },
            {"id": "repo-2", "name": "repo-2", "teams": [], "properties": {}},
            {"id": "repo-3", "name": "repo-3", "teams": [], "properties": {}},
        ],
    }
    current = {
        "property_definitions": [
            {"name": "category", "type": "string", "description": "updated"},
        ],
        "teams": [
            {"name": "team-a", "description": "new"},
            {"name": "team-c", "description": "new"},
        ],
        "repositories": [
            {
                "id": "repo-1",
                "name": "repo-new",
                "teams": [{"name": "team-a", "role": "push"}, {"name": "team-c", "role": "pull"}],
                "properties": {"category": "new"},
            },
            {"id": "repo-2", "name": "repo-2", "teams": [], "properties": {}},
            {"id": "repo-4", "name": "repo-4", "teams": [], "properties": {}},
        ],
    }
    calls = []

    monkeypatch.setattr(gitops, "ensure_property_schema", lambda *args: calls.append(("schema", args[2])))
    monkeypatch.setattr(gitops.github_teams, "find_team", lambda o, t, name, b: (
        {"slug": name, "description": "old" if name == "team-a" else "same"}
        if name in {"team-a", "team-b"} else None
    ))
    monkeypatch.setattr(gitops.github_teams, "create_team", lambda o, t, entry, b: calls.append(("create_team", entry["name"])))
    monkeypatch.setattr(gitops.github_teams, "delete_team", lambda o, t, name, b: calls.append(("delete_team", name)))
    monkeypatch.setattr(gitops.github_drift, "update_team_description", lambda o, t, slug, desc, b: calls.append(("team_description", slug, desc)))
    monkeypatch.setattr(gitops.github_drift, "rename_repo", lambda o, t, old, new, b: calls.append(("rename_repo", old, new)))
    monkeypatch.setattr(gitops.github_drift, "remove_team_from_repo", lambda o, t, repo, team, b: calls.append(("remove_team", repo, team)))
    monkeypatch.setattr(gitops.github_repos, "attach_team_to_repo", lambda o, t, repo, team, role, b: calls.append(("attach_team", repo, team, role)))
    monkeypatch.setattr(gitops.github_repos, "set_repo_properties", lambda o, t, repo, values, b: calls.append(("properties", repo, values)))
    monkeypatch.setattr(gitops.github_repos, "create_repo", lambda o, t, entry, b: calls.append(("create_repo", entry["id"])))
    monkeypatch.setattr(gitops.github_repos, "delete_repo", lambda o, t, name, b: calls.append(("delete_repo", name)))

    result = gitops.apply_changes(previous, current, {
        "github_org": "org",
        "github_api_base_url": "https://api.github.com",
    }, lambda: "token")

    assert result["repos_removed"] == ["repo-3"]
    assert ("rename_repo", "repo-old", "repo-new") in calls
    assert ("attach_team", "repo-new", "team-a", "push") in calls
    assert ("remove_team", "repo-new", "team-b") in calls
    assert ("properties", "repo-new", {"category": "new", "removed": None}) in calls
    assert ("create_repo", "repo-4") in calls
    assert ("delete_repo", "repo-3") in calls
    assert ("delete_team", "team-b") in calls
    assert not any("repo-2" in call for call in calls if len(call) > 1)


def test_apply_changes_stops_after_first_operation_fails(monkeypatch):
    previous = {
        "property_definitions": [],
        "teams": [],
        "repositories": [],
    }
    current = {
        "property_definitions": [],
        "teams": [{"name": "team-a", "description": "new"}],
        "repositories": [],
    }
    calls = []

    def fail_create(*args):
        calls.append("create")
        raise RuntimeError("GitHub denied team creation")

    monkeypatch.setattr(gitops.github_teams, "find_team", lambda *args: None)
    monkeypatch.setattr(gitops.github_teams, "create_team", fail_create)
    monkeypatch.setattr(gitops.github_repos, "delete_repo", lambda *args: calls.append("delete"))

    import pytest

    with pytest.raises(RuntimeError, match="denied"):
        gitops.apply_changes(previous, current, {
            "github_org": "org",
            "github_api_base_url": "https://api.github.com",
        }, lambda: "token")
    assert calls == ["create"]


def test_repository_replacement_deletes_old_identity_before_create(monkeypatch):
    previous = {
        "property_definitions": [],
        "teams": [],
        "repositories": [{"id": "old-id", "name": "repo", "teams": [], "properties": {}}],
    }
    current = {
        "property_definitions": [],
        "teams": [],
        "repositories": [{"id": "new-id", "name": "repo", "teams": [], "properties": {}}],
    }
    calls = []
    monkeypatch.setattr(gitops.github_repos, "delete_repo", lambda o, t, name, b: calls.append(("delete", name)))
    monkeypatch.setattr(gitops.github_repos, "create_repo", lambda o, t, entry, b: calls.append(("create", entry["name"])))

    gitops.apply_changes(previous, current, {
        "github_org": "org",
        "github_api_base_url": "https://api.github.com",
    }, lambda: "token")

    assert calls == [("delete", "repo"), ("create", "repo")]


@responses.activate
def test_latest_successful_deployment_returns_none_when_no_deployments():
    responses.add(
        responses.GET,
        "https://api.github.com/repos/acme/config/deployments",
        json=[],
        status=200,
    )
    assert gitops.latest_successful_deployment_commit("acme", "config", "scenario-c", "token") is None


@responses.activate
def test_latest_successful_deployment_skips_newer_failure():
    responses.add(
        responses.GET,
        "https://api.github.com/repos/acme/config/deployments",
        json=[
            {"id": 12, "sha": "failed-sha"},
            {"id": 11, "sha": "success-sha"},
            {"id": 10, "sha": "older-sha"},
        ],
        status=200,
    )
    responses.add(
        responses.GET,
        "https://api.github.com/repos/acme/config/deployments/12/statuses",
        json=[{"state": "failure"}],
        status=200,
    )
    responses.add(
        responses.GET,
        "https://api.github.com/repos/acme/config/deployments/11/statuses",
        json=[{"state": "success"}],
        status=200,
    )
    assert gitops.latest_successful_deployment_commit("acme", "config", "scenario-c", "token") == "success-sha"
    assert len(responses.calls) == 3


@responses.activate
def test_latest_successful_deployment_skips_pending_and_finds_older_success():
    responses.add(
        responses.GET,
        "https://api.github.com/repos/acme/config/deployments",
        json=[{"id": 12, "sha": "pending-sha"}, {"id": 11, "sha": "success-sha"}],
        status=200,
    )
    responses.add(
        responses.GET,
        "https://api.github.com/repos/acme/config/deployments/12/statuses",
        json=[{"state": "in_progress"}],
        status=200,
    )
    responses.add(
        responses.GET,
        "https://api.github.com/repos/acme/config/deployments/11/statuses",
        json=[{"state": "success"}],
        status=200,
    )
    assert gitops.latest_successful_deployment_commit("acme", "config", "scenario-c", "token") == "success-sha"


@responses.activate
def test_deployment_lookup_raises_on_github_error():
    responses.add(
        responses.GET,
        "https://api.github.com/repos/acme/config/deployments",
        json={"message": "Forbidden"},
        status=403,
    )
    with pytest.raises(RuntimeError, match="403"):
        gitops.latest_successful_deployment_commit("acme", "config", "scenario-c", "token")


@responses.activate
def test_record_deployment_creates_commit_and_success_status():
    responses.add(
        responses.POST,
        "https://api.github.com/repos/acme/config/deployments",
        json={"id": 12},
        status=201,
    )
    responses.add(
        responses.POST,
        "https://api.github.com/repos/acme/config/deployments/12/statuses",
        json={"state": "success"},
        status=201,
    )
    gitops.record_deployment("acme", "config", "scenario-c", "commit-sha", "success", "token")
    assert json.loads(responses.calls[0].request.body) == {
        "ref": "commit-sha",
        "environment": "scenario-c",
        "auto_merge": False,
        "required_contexts": [],
    }
    assert json.loads(responses.calls[1].request.body) == {
        "state": "success",
        "auto_inactive": False,
    }


def test_runner_first_deployment_records_baseline_without_apply(monkeypatch, tmp_path):
    from scripts import run_gitops

    template = {
        "property_definitions": [],
        "teams": [],
        "repositories": [],
    }
    records = []
    monkeypatch.setattr(run_gitops, "validate_file", lambda path: template)
    monkeypatch.setattr(run_gitops.gitops, "latest_successful_deployment_commit", lambda *args: None)
    monkeypatch.setattr(run_gitops.gitops, "apply_changes", lambda *args: pytest.fail("baseline must not apply"))
    monkeypatch.setattr(run_gitops.gitops, "record_deployment", lambda *args: records.append(args))

    result = run_gitops.run(
        str(tmp_path / "stress_template.yaml"), "current-sha", "acme", "config", "workflow-token",
        {"github_org": "org", "github_api_base_url": "https://api.github.com"},
        lambda: "app-token",
    )

    assert result == {"baseline": True}
    assert records == [("acme", "config", "scenario-c-gitops", "current-sha", "success", "workflow-token")]


def test_runner_applies_diff_then_records_success(monkeypatch, tmp_path):
    from scripts import run_gitops

    current = {"property_definitions": [], "teams": [], "repositories": []}
    previous = {"property_definitions": [], "teams": [], "repositories": []}
    records = []
    applied = []
    loaded = []
    provider = lambda: "app-token"
    monkeypatch.setattr(run_gitops, "validate_file", lambda path: current)
    monkeypatch.setattr(run_gitops.gitops, "latest_successful_deployment_commit", lambda *args: "previous-sha")
    monkeypatch.setattr(run_gitops, "load_template_at_commit", lambda sha, path, cwd: loaded.append((sha, path, cwd)) or previous)
    monkeypatch.setattr(run_gitops.gitops, "apply_changes", lambda *args: applied.append(args) or {"repos_upsert": []})
    monkeypatch.setattr(run_gitops.gitops, "record_deployment", lambda *args: records.append(args))

    result = run_gitops.run(
        str(tmp_path / "stress_template.yaml"), "current-sha", "acme", "config", "workflow-token",
        {"github_org": "org", "github_api_base_url": "https://api.github.com"},
        provider,
    )

    assert result == {"baseline": False, "changes": {"repos_upsert": []}}
    assert applied[0][:3] == (
        previous, current, {"github_org": "org", "github_api_base_url": "https://api.github.com"}
    )
    assert applied[0][3] is provider
    assert loaded == [("previous-sha", str(tmp_path / "stress_template.yaml"), os.getcwd())]
    assert records == [("acme", "config", "scenario-c-gitops", "current-sha", "success", "workflow-token")]


def test_runner_records_failure_without_success_marker(monkeypatch, tmp_path):
    from scripts import run_gitops

    template = {"property_definitions": [], "teams": [], "repositories": []}
    records = []
    monkeypatch.setattr(run_gitops, "validate_file", lambda path: template)
    monkeypatch.setattr(run_gitops.gitops, "latest_successful_deployment_commit", lambda *args: "previous-sha")
    monkeypatch.setattr(run_gitops, "load_template_at_commit", lambda sha, path, cwd: template)
    monkeypatch.setattr(run_gitops.gitops, "apply_changes", lambda *args: (_ for _ in ()).throw(RuntimeError("apply failed")))
    monkeypatch.setattr(run_gitops.gitops, "record_deployment", lambda *args: records.append(args))

    with pytest.raises(RuntimeError, match="apply failed"):
        run_gitops.run(
            str(tmp_path / "stress_template.yaml"), "current-sha", "acme", "config", "workflow-token",
            {"github_org": "org", "github_api_base_url": "https://api.github.com"},
            lambda: "app-token",
        )

    assert records == [("acme", "config", "scenario-c-gitops", "current-sha", "failure", "workflow-token")]


def test_load_template_at_commit_reads_and_validates_git_blob(tmp_path):
    from scripts import run_gitops

    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "Test"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.email", "test@example.com"], check=True)
    template_text = (
        "property_definitions:\n"
        "- name: category\n"
        "  type: string\n"
        "teams:\n"
        "- name: team-a\n"
        "  description: Team A\n"
        "repositories:\n"
        "- id: repo-id\n"
        "  name: repo-a\n"
        "  teams:\n"
        "  - name: team-a\n"
        "    role: push\n"
        "  properties:\n"
        "    category: service\n"
    )
    (tmp_path / "stress_template.yaml").write_text(template_text)
    subprocess.run(["git", "-C", str(tmp_path), "add", "stress_template.yaml"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-qm", "fixture"], check=True)
    commit = subprocess.run(
        ["git", "-C", str(tmp_path), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    template = run_gitops.load_template_at_commit(
        commit, str(tmp_path / "stress_template.yaml"), cwd=str(tmp_path)
    )

    assert template == {
        "property_definitions": [{"name": "category", "type": "string"}],
        "teams": [{"name": "team-a", "description": "Team A"}],
        "repositories": [
            {
                "id": "repo-id",
                "name": "repo-a",
                "teams": [{"name": "team-a", "role": "push"}],
                "properties": {"category": "service"},
            }
        ],
    }
