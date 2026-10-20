import logging

import yaml

logger = logging.getLogger(__name__)


def parse_template(path: str) -> dict:
    """
    Parse and validate a template.yaml file.
    
    Returns a dict with "teams" and "repositories" keys.
    Raises ValueError if the file is missing, invalid YAML, or the structure
    is invalid.
    """
    logger.info("Parsing template '%s'", path)
    try:
        with open(path, 'r') as f:
            data = yaml.safe_load(f)
    except FileNotFoundError:
        logger.error("Template file not found: '%s'", path)
        raise ValueError(f"Template file not found: '{path}'")
    except yaml.YAMLError as exc:
        logger.error("Template file '%s' has invalid YAML: %s", path, exc)
        raise ValueError(f"Template file '{path}' has invalid YAML: {exc}")
    
    if not isinstance(data, dict):
        raise ValueError("template.yaml: root must be a mapping")
    
    if "teams" not in data:
        raise ValueError("template.yaml: missing 'teams' key")
    
    if "repositories" not in data:
        raise ValueError("template.yaml: missing 'repositories' key")
    
    # Validate teams
    teams = data["teams"]
    if not isinstance(teams, list):
        raise ValueError("template.yaml: 'teams' must be a list")
    
    for i, team in enumerate(teams):
        if not isinstance(team, dict) or "name" not in team:
            raise ValueError(f"Team {i}: missing 'name'")
    
    # Validate repositories
    repositories = data["repositories"]
    if not isinstance(repositories, list):
        raise ValueError("template.yaml: 'repositories' must be a list")
    
    for i, repo in enumerate(repositories):
        if not isinstance(repo, dict) or "name" not in repo:
            raise ValueError(f"Repository {i}: missing 'name'")
        
        if repo.get("type") == "repository-fork":
            if "source" not in repo:
                raise ValueError(f"Repository {i} ({repo['name']}): missing 'source'")
    
    logger.info(
        "Template '%s' parsed OK: %d team(s), %d repositor(y/ies)",
        path, len(teams), len(repositories),
    )
    definitions = data["property_definitions"]
    if not isinstance(definitions, list):
        raise ValueError("template.yaml: 'property_definitions' must be a list")

    return {
        "teams": data["teams"],
        "repositories": data["repositories"],
        "property_definitions": definitions,
    }
