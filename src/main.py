import sys

from src.config import load_config
from src.yaml_parser import parse_template
from src.github_auth import get_installation_token
from src.github_teams import create_team
from src.github_repos import create_repo, create_repo_fork
from src.github_hooks import create_hook


def run(template_path, vars_path):
    config = load_config(vars_path)
    parsed = parse_template(template_path)
    token = get_installation_token(config)
    base = config["github_api_base_url"]
    org = config["github_org"]

    for team_entry in parsed["teams"]:
        create_team(org, token, team_entry, base)

    for repo_entry in parsed["repositories"]:
        if repo_entry.get("type") == "repository-fork":
            create_repo_fork(org, token, repo_entry, base)
        else:
            create_repo(org, token, repo_entry, base)
        for hook_entry in repo_entry.get("hooks", []):
            create_hook(org, token, repo_entry["name"], hook_entry, config["webhook_secret"], base)


if __name__ == "__main__":
    try:
        run("template.yaml", "vars.env")
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
