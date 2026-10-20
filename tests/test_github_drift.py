import json

import pytest
import responses

from src import github_drift

BASE = "https://api.github.com"


@responses.activate
def test_list_repo_teams_maps_slug_to_permission():
    responses.add(
        responses.GET, f"{BASE}/repos/o/r/teams",
        json=[{"slug": "a", "permission": "push"}, {"slug": "b", "permission": "pull"}],
    )
    assert github_drift.list_repo_teams("o", "t", "r", BASE) == {"a": "push", "b": "pull"}


@responses.activate
def test_list_repo_teams_paginates():
    full = [{"slug": f"t{i}", "permission": "pull"} for i in range(100)]
    responses.add(responses.GET, f"{BASE}/repos/o/r/teams", json=full)
    responses.add(responses.GET, f"{BASE}/repos/o/r/teams", json=[{"slug": "last", "permission": "push"}])
    result = github_drift.list_repo_teams("o", "t", "r", BASE)
    assert len(result) == 101 and result["last"] == "push"


@responses.activate
def test_get_repo_properties_skips_null_values():
    responses.add(
        responses.GET, f"{BASE}/repos/o/r/properties/values",
        json=[{"property_name": "a", "value": "x"}, {"property_name": "b", "value": None}],
    )
    assert github_drift.get_repo_properties("o", "t", "r", BASE) == {"a": "x"}


@responses.activate
def test_remove_team_from_repo_sends_delete():
    responses.add(responses.DELETE, f"{BASE}/orgs/o/teams/a/repos/o/r", status=204)
    github_drift.remove_team_from_repo("o", "t", "r", "a", BASE)
    assert len(responses.calls) == 1


@responses.activate
def test_rename_repo_sends_new_name():
    responses.add(responses.PATCH, f"{BASE}/repos/o/old", json={})
    github_drift.rename_repo("o", "t", "old", "new", BASE)
    assert json.loads(responses.calls[0].request.body) == {"name": "new"}


@responses.activate
def test_update_team_description_failure_raises():
    responses.add(responses.PATCH, f"{BASE}/orgs/o/teams/a", status=404, json={})
    with pytest.raises(RuntimeError, match="update team 'a'"):
        github_drift.update_team_description("o", "t", "a", "d", BASE)
