import pytest

from src import apply

CONFIG = {"github_org": "o", "github_api_base_url": "https://api.github.com"}


class FakeGitHub:
    """Records writes; serves reads from dicts."""

    def __init__(self, repos=None, teams=None, repo_teams=None, repo_props=None, team_desc="d"):
        self.repos = repos or {}
        self.teams = teams if teams is not None else {"t1", "t2"}
        self.repo_teams = repo_teams or {}
        self.repo_props = repo_props or {}
        self.team_desc = team_desc
        self.writes = []
        self.fail_repo = None

    def install(self, monkeypatch):
        m = monkeypatch.setattr
        m(apply.github_teams, "find_team", self.find_team)
        m(apply.github_teams, "create_team", self.create_team)
        m(apply.github_drift, "update_team_description", lambda o, t, s, d, b: self.writes.append(("team_desc", s, d)))
        m(apply.github_repos, "get_repo", self.get_repo)
        m(apply.github_repos, "create_repo", self.create_repo)
        m(apply.github_repos, "attach_team_to_repo", lambda o, t, r, s, role, b: self.writes.append(("attach", r, s, role)))
        m(apply.github_repos, "set_repo_properties", lambda o, t, r, p, b: self.writes.append(("props", r, p)))
        m(apply.github_drift, "remove_team_from_repo", lambda o, t, r, s, b: self.writes.append(("remove", r, s)))
        m(apply.github_drift, "list_repo_teams", lambda o, t, r, b: dict(self.repo_teams.get(r, {})))
        m(apply.github_drift, "get_repo_properties", lambda o, t, r, b: dict(self.repo_props.get(r, {})))
        m(apply, "ensure_property_schema", lambda *a, **k: self.writes.append(("schema",)))

    def find_team(self, org, token, name, base):
        if name not in self.teams:
            return None
        return {"slug": name, "description": self.team_desc}

    def create_team(self, org, token, entry, base):
        self.writes.append(("create_team", entry["name"]))
        self.teams.add(entry["name"])
        return entry["name"]

    def get_repo(self, org, token, name, base):
        if name == self.fail_repo:
            raise RuntimeError("boom 500")
        if name not in self.repos:
            return None
        return {"private": self.repos[name]}

    def create_repo(self, org, token, entry, base):
        self.writes.append(("create_repo", entry["name"]))
        self.repos[entry["name"]] = True


def parsed(repos):
    return {
        "teams": [{"name": "t1", "description": "d"}, {"name": "t2", "description": "d"}],
        "repositories": repos,
        "property_definitions": [{"name": "k", "type": "string"}],
    }


REPO = {"name": "r1", "teams": [{"name": "t1", "role": "push"}], "properties": {"k": "v"}}


def run(monkeypatch, gh, repos):
    gh.install(monkeypatch)
    monkeypatch.setattr(apply, "load_config", lambda p: CONFIG)
    monkeypatch.setattr(apply, "make_token_provider", lambda c: (lambda: "tok"))
    monkeypatch.setattr(apply, "validate_file", lambda p: None)
    monkeypatch.setattr(apply, "parse_template", lambda p: parsed(repos))
    return apply.apply_template("stress_template.yaml", "vars.env")


def matching_github(**extra):
    return FakeGitHub(
        repos={"r1": True}, repo_teams={"r1": {"t1": "push"}}, repo_props={"r1": {"k": "v"}}, **extra
    )


def test_template_yaml_is_refused():
    with pytest.raises(ValueError, match="stress_template.yaml only"):
        apply.apply_template("some/dir/template.yaml", "vars.env")


def test_diff_repo_only_yaml_keys():
    desired = {"teams": {"t1": "push"}, "properties": {"k": "v"}}
    actual = {"teams": {"t1": "push"}, "properties": {"k": "v", "other": "x"}}
    assert apply.diff_repo(desired, actual) == {
        "teams_to_set": {}, "teams_to_remove": [], "properties_to_set": {},
    }


def test_diff_repo_detects_role_change_and_removed_team():
    desired = {"teams": {"t1": "push"}, "properties": {}}
    actual = {"teams": {"t1": "pull", "t2": "pull"}, "properties": {}}
    diff = apply.diff_repo(desired, actual)
    assert diff["teams_to_set"] == {"t1": "push"}
    assert diff["teams_to_remove"] == ["t2"]


def test_diff_repo_multi_select_order_insensitive():
    desired = {"teams": {}, "properties": {"c": ["a", "b"]}}
    actual = {"teams": {}, "properties": {"c": ["b", "a"]}}
    assert apply.diff_repo(desired, actual)["properties_to_set"] == {}


def test_matching_repo_is_unchanged_and_makes_no_writes(monkeypatch):
    gh = matching_github()
    metrics = run(monkeypatch, gh, [REPO])
    assert metrics["repositories"]["unchanged"] == 1
    assert [w for w in gh.writes if w[0] != "schema"] == []


def test_drift_is_fixed_and_counted_as_updated(monkeypatch):
    gh = FakeGitHub(repos={"r1": True}, repo_teams={"r1": {"t1": "push"}}, repo_props={"r1": {"k": "wrong"}})
    metrics = run(monkeypatch, gh, [REPO])
    assert ("props", "r1", {"k": "v"}) in gh.writes
    assert metrics["repositories"]["updated"] == 1
    assert metrics["repositories"]["adopted"] == 0


def test_missing_repo_is_created_with_teams_and_properties(monkeypatch):
    gh = FakeGitHub()
    metrics = run(monkeypatch, gh, [REPO])
    assert metrics["repositories"]["created"] == 1
    assert ("create_repo", "r1") in gh.writes
    assert ("attach", "r1", "t1", "push") in gh.writes
    assert ("props", "r1", {"k": "v"}) in gh.writes


def test_one_failure_does_not_stop_run(monkeypatch):
    gh = FakeGitHub(repos={"r1": True, "r2": True})
    gh.fail_repo = "r1"
    repos = [REPO, {"name": "r2", "teams": [], "properties": {}}]
    metrics = run(monkeypatch, gh, repos)
    assert metrics["repositories"]["failed"] == 1
    assert metrics["repositories"]["unchanged"] == 1


def test_second_run_makes_no_writes(monkeypatch):
    gh = FakeGitHub(repos={}, repo_teams={"r1": {}}, repo_props={"r1": {}})
    run(monkeypatch, gh, [REPO])
    gh.repo_teams["r1"] = {"t1": "push"}
    gh.repo_props["r1"] = {"k": "v"}
    gh.writes.clear()
    metrics = run(monkeypatch, gh, [REPO])
    assert metrics["repositories"]["unchanged"] == 1
    assert [w for w in gh.writes if w[0] != "schema"] == []


def test_team_description_drift_is_fixed_and_counted(monkeypatch):
    gh = FakeGitHub(team_desc="old")
    metrics = run(monkeypatch, gh, [])
    assert ("team_desc", "t1", "d") in gh.writes
    assert metrics["teams"]["updated"] == 2 and metrics["teams"]["created"] == 0


def test_new_team_is_created_and_counted(monkeypatch):
    gh = FakeGitHub(teams={"t1"})
    metrics = run(monkeypatch, gh, [])
    assert ("create_team", "t2") in gh.writes
    assert metrics["teams"]["created"] == 1


def test_summary_counts_every_component(monkeypatch):
    gh = FakeGitHub(
        teams={"t1"},
        repos={"r1": True},
        repo_teams={"r1": {"t1": "pull", "extra": "push"}},
        repo_props={"r1": {"k": "wrong"}},
    )
    metrics = run(monkeypatch, gh, [REPO])
    assert metrics["teams"] == {"total": 2, "created": 1, "updated": 0, "unchanged": 1}
    assert metrics["repositories"]["total"] == 1
    assert metrics["team_assignments"] == {"total": 1, "set": 1, "removed": 1}
    assert metrics["properties"] == {"definitions": 1, "values_total": 1, "values_set": 1}
    assert metrics["not_in_yaml"] is None
    assert "api" in metrics and "seconds" in metrics


def test_format_summary_lists_components():
    metrics = {
        "teams": {"total": 31, "created": 2, "updated": 1, "unchanged": 28},
        "repositories": {"total": 5000, "created": 0, "adopted": 0, "updated": 3, "unchanged": 4997, "failed": 0},
        "team_assignments": {"total": 10000, "set": 3, "removed": 0},
        "properties": {"definitions": 6, "values_total": 30000, "values_set": 3},
        "api": {"total": 1, "by_method": {"GET": 1}, "by_status": {"200": 1},
                "rate_limited": 0, "rate_limit_remaining": None},
        "not_in_yaml": None,
        "seconds": 12.5,
    }
    text = apply.format_summary(metrics)
    assert "Teams: 31 total, 2 created, 1 updated, 28 unchanged" in text
    assert "Repositories: 5000 total, 0 created, 0 adopted, 3 updated, 4997 unchanged, 0 failed" in text
    assert "Team assignments: 10000 total, 3 set, 0 removed" in text
    assert "Properties: 6 definitions, 30000 values total, 3 values set" in text
    assert "API requests: 1 total (GET 1)" in text
    assert "Not in yaml: not tracked (no state)" in text
    assert "Time: 12.5 s" in text
