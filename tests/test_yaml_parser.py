import pytest
from src.yaml_parser import parse_template


def test_parse_template_returns_teams_and_repositories(tmp_path):
    yaml_file = tmp_path / "template.yaml"
    yaml_file.write_text(
        "property_definitions: []\n"
        "teams:\n"
        "  - name: jenkins-team\n"
        "repositories:\n"
        "  - name: docker-jenkins\n"
        "    teams:\n"
        "      - name: jenkins-team\n"
        "        role: maintain\n"
    )
    result = parse_template(str(yaml_file))
    assert result["teams"][0]["name"] == "jenkins-team"
    assert result["repositories"][0]["name"] == "docker-jenkins"


def test_parse_template_missing_teams_key_raises(tmp_path):
    yaml_file = tmp_path / "template.yaml"
    yaml_file.write_text("repositories:\n  - name: docker-jenkins\n")
    with pytest.raises(ValueError, match="missing 'teams'"):
        parse_template(str(yaml_file))


def test_parse_template_missing_repositories_key_raises(tmp_path):
    yaml_file = tmp_path / "template.yaml"
    yaml_file.write_text("teams:\n  - name: jenkins-team\n")
    with pytest.raises(ValueError, match="missing 'repositories'"):
        parse_template(str(yaml_file))


def test_parse_template_team_missing_name_raises(tmp_path):
    yaml_file = tmp_path / "template.yaml"
    yaml_file.write_text("teams:\n  - description: no name here\nrepositories: []\n")
    with pytest.raises(ValueError, match="Team 0: missing 'name'"):
        parse_template(str(yaml_file))


def test_parse_template_repo_missing_name_raises(tmp_path):
    yaml_file = tmp_path / "template.yaml"
    yaml_file.write_text("teams: []\nrepositories:\n  - teams: []\n")
    with pytest.raises(ValueError, match="Repository 0: missing 'name'"):
        parse_template(str(yaml_file))


def test_parse_template_fork_missing_source_raises(tmp_path):
    yaml_file = tmp_path / "template.yaml"
    yaml_file.write_text(
        "teams: []\n"
        "repositories:\n"
        "  - type: repository-fork\n"
        "    name: docker-jenkins\n"
    )
    with pytest.raises(ValueError, match="Repository 0.*missing 'source'"):
        parse_template(str(yaml_file))


def test_parse_template_teams_not_a_list_raises(tmp_path):
    yaml_file = tmp_path / "template.yaml"
    yaml_file.write_text("teams:\n  name: not-a-list\nrepositories: []\n")
    with pytest.raises(ValueError, match="'teams' must be a list"):
        parse_template(str(yaml_file))


def test_parse_template_repositories_not_a_list_raises(tmp_path):
    yaml_file = tmp_path / "template.yaml"
    yaml_file.write_text("teams: []\nrepositories:\n  name: not-a-list\n")
    with pytest.raises(ValueError, match="'repositories' must be a list"):
        parse_template(str(yaml_file))


def test_parse_template_missing_file_raises_clear_error(tmp_path):
    missing_path = tmp_path / "does-not-exist.yaml"
    with pytest.raises(ValueError, match="not found"):
        parse_template(str(missing_path))


def test_parse_template_invalid_yaml_syntax_raises_clear_error(tmp_path):
    yaml_file = tmp_path / "template.yaml"
    yaml_file.write_text("teams: [\n  - this is not: valid: yaml\n")
    with pytest.raises(ValueError, match="invalid YAML"):
        parse_template(str(yaml_file))
