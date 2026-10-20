import logging
import os
import subprocess
import tempfile

from src import gitops
from src.github_auth import make_token_provider
from src.validator import validate_file

logger = logging.getLogger(__name__)
ENVIRONMENT = "scenario-c-gitops"
TEMPLATE_PATH = "stress_template.yaml"


def load_action_settings(environ=None) -> dict:
    environment = os.environ if environ is None else environ
    return {
        "github_org": environment["TARGET_ORG"],
        "github_api_base_url": environment["API_BASE_URL"],
        "github_app_id": environment["APP_ID"],
        "github_app_installation_id": environment["APP_INSTALLATION_ID"],
        "github_app_private_key": environment["APP_PRIVATE_KEY"],
        "deployment_token": environment["DEPLOYMENT_TOKEN"],
    }


def load_template_at_commit(commit_sha: str, template_path: str, cwd: str) -> dict:
    repository_path = os.path.relpath(template_path, cwd)
    result = subprocess.run(
        ["git", "show", f"{commit_sha}:{repository_path}"],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml") as temporary:
        temporary.write(result.stdout)
        temporary.flush()
        return validate_file(temporary.name)


def run(
    template_path: str,
    current_commit: str,
    owner: str,
    repository: str,
    deployment_token: str,
    app_config: dict,
    token_provider,
) -> dict:
    current = validate_file(template_path)
    previous_commit = gitops.latest_successful_deployment_commit(
        owner, repository, ENVIRONMENT, deployment_token
    )
    if previous_commit is None:
        gitops.record_deployment(
            owner, repository, ENVIRONMENT, current_commit, "success", deployment_token
        )
        return {"baseline": True}

    previous = load_template_at_commit(
        previous_commit, template_path, os.getcwd()
    )
    try:
        changes = gitops.apply_changes(previous, current, app_config, token_provider)
    except Exception:
        try:
            gitops.record_deployment(
                owner, repository, ENVIRONMENT, current_commit, "failure", deployment_token
            )
        except Exception:
            logger.exception("Could not record failed GitHub Deployment")
        raise

    gitops.record_deployment(
        owner, repository, ENVIRONMENT, current_commit, "success", deployment_token
    )
    return {"baseline": False, "changes": changes}


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    owner, repository = os.environ["GITHUB_REPOSITORY"].split("/", maxsplit=1)
    settings = load_action_settings()
    with tempfile.NamedTemporaryFile(mode="w", delete=False) as private_key:
        os.chmod(private_key.name, 0o600)
        private_key.write(settings["github_app_private_key"])
        key_path = private_key.name
    app_config = {
        "github_org": settings["github_org"],
        "github_api_base_url": settings["github_api_base_url"],
        "github_app_id": settings["github_app_id"],
        "github_app_installation_id": settings["github_app_installation_id"],
        "github_app_private_key_path": key_path,
    }
    try:
        result = run(
            TEMPLATE_PATH,
            os.environ["GITHUB_SHA"],
            owner,
            repository,
            settings["deployment_token"],
            app_config,
            make_token_provider(app_config),
        )
        logger.info("GitOps run completed: %s", result)
    finally:
        os.unlink(key_path)


if __name__ == "__main__":
    main()
