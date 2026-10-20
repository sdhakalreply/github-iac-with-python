import pytest

from src import reconcile

CTX = {"org": "o", "token": "t", "base": "https://api.github.com"}


@pytest.fixture
def gh(monkeypatch):
    class G:
        writes = []
        repos = {}
        teams = {}
        repo_teams = {}
        repo_props = {}
        fail = False

    g = G()
    g.writes = []
    g.repos = {"r1": {"private": True}}
    g.teams = {"t1": {"slug": "t1", "description": "d"}}
    g.repo_teams = {}
    g.repo_props = {}

    def rec(kind):
        def f(*args):
            if g.fail:
                raise RuntimeError("boom")
            g.writes.append((kind,) + tuple(args[2:-1]))
        return f

    def get_repo(o, t, name, b):
        if g.fail:
            raise RuntimeError("boom")
        if name not in g.repos:
            raise RuntimeError("Failed to fetch repo: 404")
        return dict(g.repos[name])

    m = monkeypatch.setattr
    m(reconcile.github_repos, "get_repo", get_repo)
    m(reconcile.github_repos, "attach_team_to_repo", rec("attach"))
    m(reconcile.github_repos, "set_repo_properties", rec("props"))
    m(reconcile.github_repos, "create_repo", rec("create_repo"))
    m(reconcile.github_teams, "find_team", lambda o, t, n, b: g.teams.get(n))
    m(reconcile.github_teams, "create_team", lambda o, t, e, b: (g.writes.append(("create_team", e["name"], e["description"])), e["name"])[1])
    m(reconcile.github_drift, "rename_repo", rec("rename"))
    m(reconcile.github_drift, "remove_team_from_repo", rec("remove"))
    m(reconcile.github_drift, "update_team_description", rec("team_desc"))
    m(reconcile.github_drift, "list_repo_teams", lambda o, t, r, b: dict(g.repo_teams.get(r, {})))
    m(reconcile.github_drift, "get_repo_properties", lambda o, t, r, b: dict(g.repo_props.get(r, {})))
    return g


@pytest.fixture
def template():
    return reconcile.build_index({
        "teams": [{"name": "t1", "description": "d"}],
        "repositories": [
            {"name": "r1", "teams": [{"name": "t1", "role": "push"}], "properties": {"k": "v"}},
            {"name": "r2", "teams": [], "properties": {}},
        ],
    })


def test_repository_not_in_yaml_is_unknown(gh, template):
    payload = {"action": "publicized", "repository": {"name": "stranger"}}
    assert reconcile.reconcile_event("repository", payload, template, CTX) == "unknown_resource"
    assert gh.writes == []


def test_repository_renamed_is_renamed_back_using_old_name_from_payload(gh, template):
    payload = {
        "action": "renamed",
        "repository": {"name": "new-name"},
        "changes": {"repository": {"name": {"from": "r1"}}},
    }
    assert reconcile.reconcile_event("repository", payload, template, CTX) == "reverted"
    assert ("rename", "new-name", "r1") in gh.writes


def test_repository_renamed_from_unknown_name_is_unknown(gh, template):
    payload = {
        "action": "renamed",
        "repository": {"name": "new-name"},
        "changes": {"repository": {"name": {"from": "stranger"}}},
    }
    assert reconcile.reconcile_event("repository", payload, template, CTX) == "unknown_resource"
    assert gh.writes == []


def test_repository_deleted_is_recreated_with_teams_and_properties(gh, template):
    payload = {"action": "deleted", "repository": {"name": "r1"}}
    assert reconcile.reconcile_event("repository", payload, template, CTX) == "reverted"
    assert ("create_repo", {"name": "r1"}) in gh.writes
    assert ("attach", "r1", "t1", "push") in gh.writes
    assert ("props", "r1", {"k": "v"}) in gh.writes


def test_team_event_with_repo_attaches_missing_and_removes_extra(gh, template):
    gh.repo_teams["r1"] = {"extra": "pull"}
    payload = {"action": "added_to_repository", "team": {"name": "x", "slug": "x"}, "repository": {"name": "r1"}}
    assert reconcile.reconcile_event("team", payload, template, CTX) == "reverted"
    assert ("attach", "r1", "t1", "push") in gh.writes
    assert ("remove", "r1", "extra") in gh.writes


def test_team_event_with_repo_wrong_role_is_fixed(gh, template):
    gh.repo_teams["r1"] = {"t1": "admin"}
    payload = {"action": "edited", "team": {"name": "t1", "slug": "t1"}, "repository": {"name": "r1"}}
    assert reconcile.reconcile_event("team", payload, template, CTX) == "reverted"
    assert gh.writes == [("attach", "r1", "t1", "push")]


def test_team_event_with_repo_matching_yaml_is_no_change(gh, template):
    gh.repo_teams["r1"] = {"t1": "push"}
    payload = {"action": "edited", "team": {"name": "t1", "slug": "t1"}, "repository": {"name": "r1"}}
    assert reconcile.reconcile_event("team", payload, template, CTX) == "no_change"
    assert gh.writes == []


def test_team_event_with_repo_not_in_yaml_is_unknown(gh, template):
    payload = {"action": "edited", "team": {"name": "t1", "slug": "t1"}, "repository": {"name": "stranger"}}
    assert reconcile.reconcile_event("team", payload, template, CTX) == "unknown_resource"


def test_team_description_changed_is_reverted(gh, template):
    gh.teams["t1"] = {"slug": "t1", "description": "changed"}
    payload = {"action": "edited", "team": {"name": "t1", "slug": "t1"}}
    assert reconcile.reconcile_event("team", payload, template, CTX) == "reverted"
    assert ("team_desc", "t1", "d") in gh.writes


def test_team_description_matching_yaml_is_no_change(gh, template):
    payload = {"action": "edited", "team": {"name": "t1", "slug": "t1"}}
    assert reconcile.reconcile_event("team", payload, template, CTX) == "no_change"
    assert gh.writes == []


def test_team_deleted_is_recreated_and_reattached(gh, template):
    del gh.teams["t1"]
    payload = {"action": "deleted", "team": {"name": "t1", "slug": "t1"}}
    assert reconcile.reconcile_event("team", payload, template, CTX) == "reverted"
    assert ("create_team", "t1", "d") in gh.writes
    assert ("attach", "r1", "t1", "push") in gh.writes
    assert not any(w[0] == "attach" and w[1] == "r2" for w in gh.writes)


def test_team_not_in_yaml_is_unknown(gh, template):
    payload = {"action": "deleted", "team": {"name": "stranger", "slug": "stranger"}}
    assert reconcile.reconcile_event("team", payload, template, CTX) == "unknown_resource"
    assert gh.writes == []


def test_custom_property_drift_is_reverted(gh, template):
    gh.repo_props["r1"] = {"k": "wrong"}
    payload = {"action": "updated", "repository": {"name": "r1"}}
    assert reconcile.reconcile_event("custom_property_values", payload, template, CTX) == "reverted"
    assert ("props", "r1", {"k": "v"}) in gh.writes


def test_custom_property_matching_yaml_is_no_change(gh, template):
    gh.repo_props["r1"] = {"k": "v", "other": "x"}
    payload = {"action": "updated", "repository": {"name": "r1"}}
    assert reconcile.reconcile_event("custom_property_values", payload, template, CTX) == "no_change"
    assert gh.writes == []


def test_custom_property_multi_select_order_is_ignored(gh):
    template = reconcile.build_index({"teams": [], "repositories": [{"name": "r1", "teams": [], "properties": {"c": ["a", "b"]}}]})
    gh.repo_props["r1"] = {"c": ["b", "a"]}
    payload = {"action": "updated", "repository": {"name": "r1"}}
    assert reconcile.reconcile_event("custom_property_values", payload, template, CTX) == "no_change"


def test_custom_property_repo_not_in_yaml_is_unknown(gh, template):
    payload = {"action": "updated", "repository": {"name": "stranger"}}
    assert reconcile.reconcile_event("custom_property_values", payload, template, CTX) == "unknown_resource"


def test_unhandled_event_is_no_change(gh, template):
    assert reconcile.reconcile_event("star", {"repository": {"name": "r1"}}, template, CTX) == "no_change"
    assert gh.writes == []


def test_github_failure_returns_failed_and_does_not_raise(gh, template):
    gh.fail = True
    payload = {"action": "deleted", "repository": {"name": "r1"}}
    assert reconcile.reconcile_event("repository", payload, template, CTX) == "failed"


def test_describe_names_repo_then_team():
    assert reconcile.describe({"repository": {"name": "r1"}, "team": {"name": "t1"}}) == "r1"
    assert reconcile.describe({"team": {"name": "t1"}}) == "t1"
    assert reconcile.describe({}) == "unknown"
