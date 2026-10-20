import pytest

from src import validator

DEFS = [
    {"name": "k", "type": "string"},
    {"name": "cat", "type": "multi_select", "allowed_values": ["a", "b"]},
    {"name": "env", "type": "single_select", "allowed_values": ["dev", "prod"]},
    {"name": "flag", "type": "true_false"},
]


def good():
    return {
        "property_definitions": [dict(d) for d in DEFS],
        "teams": [{"name": "t1", "description": "d"}, {"name": "t2"}],
        "repositories": [
            {"id": "repo-1", "name": "r1", "teams": [{"name": "t1", "role": "push"}], "properties": {"k": "v", "cat": ["a"]}},
        ],
    }


def test_valid_template_has_no_errors():
    assert validator.validate_template(good()) == []


def test_duplicate_team_is_reported():
    data = good()
    data["teams"].append({"name": "t1"})
    errors = validator.validate_template(data)
    assert any("duplicate team 't1'" in e for e in errors)


def test_duplicate_team_is_case_insensitive():
    data = good()
    data["teams"].append({"name": "T1"})
    assert any("duplicate team" in e for e in validator.validate_template(data))


def test_duplicate_repo_is_reported():
    data = good()
    data["repositories"].append({"id": "repo-2", "name": "r1", "teams": [], "properties": {}})
    assert any("duplicate repository 'r1'" in e for e in validator.validate_template(data))


def test_repository_id_is_required():
    data = good()
    del data["repositories"][0]["id"]
    assert any("missing 'id'" in e for e in validator.validate_template(data))


def test_repository_id_must_not_be_empty():
    data = good()
    data["repositories"][0]["id"] = " "
    assert any("invalid 'id'" in e for e in validator.validate_template(data))


def test_duplicate_repository_id_is_reported():
    data = good()
    data["repositories"].append({"id": "repo-1", "name": "r2", "teams": [], "properties": {}})
    assert any("duplicate repository id 'repo-1'" in e for e in validator.validate_template(data))


def test_distinct_ids_allow_repo_name_change():
    data = good()
    data["repositories"][0]["name"] = "renamed"
    assert validator.validate_template(data) == []


def test_unknown_team_reference():
    data = good()
    data["repositories"][0]["teams"].append({"name": "ghost", "role": "pull"})
    assert any("unknown team 'ghost'" in e for e in validator.validate_template(data))


def test_same_team_twice_on_one_repo():
    data = good()
    data["repositories"][0]["teams"].append({"name": "t1", "role": "pull"})
    assert any("team 't1' listed twice" in e for e in validator.validate_template(data))


def test_invalid_role():
    data = good()
    data["repositories"][0]["teams"][0]["role"] = "owner"
    assert any("invalid role 'owner'" in e for e in validator.validate_template(data))


def test_missing_role():
    data = good()
    del data["repositories"][0]["teams"][0]["role"]
    assert any("missing role" in e for e in validator.validate_template(data))


def test_undefined_property():
    data = good()
    data["repositories"][0]["properties"]["nope"] = "x"
    assert any("property 'nope' is not defined" in e for e in validator.validate_template(data))


def test_multi_select_must_be_list_of_allowed_values():
    data = good()
    data["repositories"][0]["properties"]["cat"] = "a"
    assert any("'cat' must be a list" in e for e in validator.validate_template(data))
    data["repositories"][0]["properties"]["cat"] = ["a", "zzz"]
    assert any("'zzz' is not an allowed value" in e for e in validator.validate_template(data))


def test_single_select_must_be_allowed_value():
    data = good()
    data["repositories"][0]["properties"] = {"env": "staging"}
    assert any("'staging' is not an allowed value" in e for e in validator.validate_template(data))


def test_string_property_must_be_string():
    data = good()
    data["repositories"][0]["properties"] = {"k": True}
    assert any("'k' must be a string" in e for e in validator.validate_template(data))


def test_true_false_property_must_be_true_or_false_string():
    data = good()
    data["repositories"][0]["properties"] = {"flag": "maybe"}
    assert any("'flag' must be 'true' or 'false'" in e for e in validator.validate_template(data))


def test_duplicate_property_definition():
    data = good()
    data["property_definitions"].append({"name": "k", "type": "string"})
    assert any("duplicate property definition 'k'" in e for e in validator.validate_template(data))


def test_all_errors_reported_at_once():
    data = good()
    data["teams"].append({"name": "t1"})
    data["repositories"].append({"name": "r1", "teams": [], "properties": {}})
    assert len(validator.validate_template(data)) >= 2


def test_missing_sections_reported():
    errors = validator.validate_template({})
    assert any("'teams'" in e for e in errors) and any("'repositories'" in e for e in errors)


def test_lint_reports_yaml_syntax_error_with_line(tmp_path):
    path = tmp_path / "t.yaml"
    path.write_text("teams:\n  - name: a\n   bad: indent\n")
    with pytest.raises(ValueError, match="line"):
        validator.validate_file(str(path))


def test_lint_reports_duplicate_keys_with_line(tmp_path):
    path = tmp_path / "t.yaml"
    path.write_text("property_definitions: []\nteams: []\nrepositories: []\nteams: []\n")
    with pytest.raises(ValueError, match="line 4: duplicate key 'teams'"):
        validator.validate_file(str(path))


def test_validate_file_raises_with_all_errors(tmp_path):
    path = tmp_path / "t.yaml"
    path.write_text(
        "property_definitions: []\nteams:\n- name: t1\n- name: t1\nrepositories:\n- name: r1\n  properties: {}\n  teams:\n  - {name: x, role: push}\n"
    )
    with pytest.raises(ValueError) as exc:
        validator.validate_file(str(path))
    assert "duplicate team 't1'" in str(exc.value) and "unknown team 'x'" in str(exc.value)


def test_validate_file_ok(tmp_path):
    import yaml
    path = tmp_path / "t.yaml"
    path.write_text(yaml.safe_dump(good()))
    validator.validate_file(str(path))
