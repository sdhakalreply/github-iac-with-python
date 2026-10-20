import sys

import yaml

VALID_ROLES = {"pull", "triage", "push", "maintain", "admin"}
VALUE_TYPES = {"string", "single_select", "multi_select", "true_false"}


class _UniqueKeyLoader(yaml.SafeLoader):
    """SafeLoader that records duplicate mapping keys instead of silently
    keeping the last one."""

    duplicates: list


def _construct_mapping(loader, node, deep=False):
    seen = set()
    for key_node, _ in node.value:
        key = loader.construct_object(key_node, deep=True)
        if key in seen:
            loader.duplicates.append(
                f"line {key_node.start_mark.line + 1}: duplicate key '{key}'"
            )
        seen.add(key)
    return yaml.SafeLoader.construct_mapping(loader, node, deep)


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping
)


def _load_yaml_text(text: str, source: str):
    loader = _UniqueKeyLoader(text)
    loader.duplicates = []
    try:
        data = loader.get_single_data()
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        where = f"line {mark.line + 1}, column {mark.column + 1}" if mark else "unknown line"
        problem = getattr(exc, "problem", None) or str(exc)
        return None, [f"{source}: YAML syntax error at {where}: {problem}"]
    finally:
        loader.dispose()
    return data, loader.duplicates


def load_yaml(path: str):
    """Return (data, errors). Errors cover syntax problems and duplicate keys."""
    with open(path, encoding="utf-8") as f:
        return _load_yaml_text(f.read(), path)


def _check_duplicates(items, label: str, errors: list) -> dict:
    first_seen = {}
    for index, item in enumerate(items):
        name = item.get("name") if isinstance(item, dict) else None
        if not name:
            errors.append(f"{label}[{index}]: missing 'name'")
            continue
        key = str(name).lower()
        if key in first_seen:
            errors.append(
                f"{label}[{index}]: duplicate {label[:-1] if label == 'teams' else 'repository'} "
                f"'{name}' (first at {label}[{first_seen[key]}])"
            )
        else:
            first_seen[key] = index
    return first_seen


def _check_property_value(name, value, definition, where, errors) -> None:
    value_type = definition["type"]
    allowed = definition.get("allowed_values")
    if value_type == "string":
        if not isinstance(value, str):
            errors.append(f"{where}: property '{name}' must be a string")
    elif value_type == "true_false":
        if value not in ("true", "false"):
            errors.append(f"{where}: property '{name}' must be 'true' or 'false' (quoted string)")
    elif value_type == "single_select":
        if value not in allowed:
            errors.append(f"{where}: '{value}' is not an allowed value for property '{name}'")
    elif value_type == "multi_select":
        if not isinstance(value, list):
            errors.append(f"{where}: property '{name}' must be a list")
        else:
            for item in value:
                if item not in allowed:
                    errors.append(f"{where}: '{item}' is not an allowed value for property '{name}'")


def validate_template(data) -> list:
    """Return a list of error strings. An empty list means the template is valid."""
    errors = []
    if not isinstance(data, dict):
        return ["root must be a mapping"]
    for section in ("teams", "repositories"):
        if not isinstance(data.get(section), list):
            errors.append(f"missing or invalid '{section}' list")
    if errors:
        return errors

    definitions = {}
    for index, definition in enumerate(data["property_definitions"]):
        name = definition.get("name") if isinstance(definition, dict) else None
        if not name:
            errors.append(f"property_definitions[{index}]: missing 'name'")
            continue
        if name in definitions:
            errors.append(f"property_definitions[{index}]: duplicate property definition '{name}'")
            continue
        if definition["type"] not in VALUE_TYPES:
            errors.append(f"property_definitions[{index}]: invalid type for '{name}'")
        definitions[name] = definition

    teams = _check_duplicates(data["teams"], "teams", errors)
    _check_duplicates(data["repositories"], "repositories", errors)

    repository_ids = set()
    for r_index, repo in enumerate(data["repositories"]):
        if not isinstance(repo, dict):
            continue
        repo_id = repo.get("id")
        if "id" not in repo:
            errors.append(f"repositories[{r_index}]: missing 'id'")
            continue
        if not isinstance(repo_id, str) or not repo_id.strip():
            errors.append(f"repositories[{r_index}]: missing or invalid 'id'")
            continue
        if repo_id in repository_ids:
            errors.append(f"repositories[{r_index}]: duplicate repository id '{repo_id}'")
        repository_ids.add(repo_id)

    for r_index, repo in enumerate(data["repositories"]):
        if not isinstance(repo, dict) or not repo.get("name"):
            continue
        where = f"repositories[{r_index}] '{repo['name']}'"
        listed = set()
        for team in repo["teams"]:
            team_name = team.get("name") if isinstance(team, dict) else None
            if team_name is None:
                errors.append(f"{where}: team entry without 'name'")
                continue
            if str(team_name).lower() not in teams:
                errors.append(f"{where}: unknown team '{team_name}'")
            if team_name in listed:
                errors.append(f"{where}: team '{team_name}' listed twice")
            listed.add(team_name)
            role = team.get("role")
            if role is None:
                errors.append(f"{where}: team '{team_name}' missing role")
            elif role not in VALID_ROLES:
                errors.append(f"{where}: invalid role '{role}' for team '{team_name}'")
        for prop, value in repo["properties"].items():
            if prop not in definitions:
                errors.append(f"{where}: property '{prop}' is not defined in property_definitions")
            else:
                _check_property_value(prop, value, definitions[prop], where, errors)
    return errors


def validate_content(content: bytes | str, source: str) -> dict:
    """Validate template content and raise ValueError listing every problem."""
    if isinstance(content, bytes):
        try:
            content = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(f"{source} is not valid UTF-8: {exc}") from exc
    data, errors = _load_yaml_text(content, source)
    if data is not None:
        errors = errors + validate_template(data)
    if errors:
        raise ValueError(
            f"{source} is invalid ({len(errors)} problem(s)):\n" + "\n".join(f"  - {e}" for e in errors)
        )
    return data


def validate_file(path: str) -> dict:
    """Lint and validate a template file. Makes no network call."""
    with open(path, encoding="utf-8") as f:
        return validate_content(f.read(), path)


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "stress_template.yaml"
    try:
        validate_file(target)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        sys.exit(1)
    print(f"{target}: OK")
