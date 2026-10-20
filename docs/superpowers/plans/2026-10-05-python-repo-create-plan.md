# Python GitHub Repo/Team Creator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Parse `template.yaml` (top-level `teams:` + `repositories:`
lists) and create the described GitHub teams, repositories (including
forks), custom properties, and webhooks via the GitHub REST API,
authenticating as a GitHub App, running as a container.

**Architecture:** A set of small, single-responsibility function modules
(no classes) under `src/`: config loading, yaml parsing/validation,
GitHub App auth, and three GitHub API modules (teams, repos, hooks).
`main.py` wires them together in a fixed, fail-fast sequence: load
config → parse yaml → authenticate → create all teams → create all
repositories (plain or fork) → attach teams/properties/hooks per repo.

**Tech Stack:** Python 3.12, `requests`, `PyYAML`, `python-dotenv`,
`PyJWT`, `cryptography`, `pytest`, `responses` (HTTP mocking). Packaged
with a `Dockerfile` (slim base image).

**Spec:** `docs/superpowers/specs/2026-10-05-python-repo-create-design.md`

## Global Constraints

- No classes unless strictly necessary — plain functions over dicts.
- Target: GitHub Enterprise Cloud (`https://api.github.com`), org-scoped.
- Auth: GitHub App JWT → installation access token (not PAT).
- Fail-fast: first error raises, prints a clear message, exits non-zero.
  No retries, no continue-on-error.
- Secrets come from `.env` (gitignored); non-secret repo/org vars come
  from `vars.env` (`.tfvars`-style). Both loaded with `python-dotenv`.
- No real network calls in tests — mock all GitHub API calls.
- v1 is create-only (no idempotency/upsert check).
- GIAM/Entra ID sync (`group`/`owners` fields on team entries) and
  Cloud WAF/Apigee webhook registration are out of scope — not
  implemented, not called.
- Team hierarchy (parent/child) is out of scope for v1 — teams are
  created flat/independent as listed under `template.yaml`'s `teams:`.
- `template.yaml` top-level shape is a mapping with `teams:` (list) and
  `repositories:` (list). A repository entry is a plain repo unless it
  has `type: repository-fork`, in which case it also carries a
  `source` field (`owner/repo`) naming what to fork from.
- Runs as a container: `Dockerfile` with slim Python base image;
  `.env`/`vars.env` passed at `docker run` time, never baked into the
  image.

## Review Focus

- **Malformed/incomplete yaml entry** (a team or repository entry
  missing required `name`) — parser should raise a clear validation
  error naming the offending entry's index, not a raw `KeyError`.
- **`template.yaml` missing a top-level key** (no `teams:` or no
  `repositories:` key at all) — parser should fail fast with a clear
  message rather than crash with `KeyError` deep in `main.py`.
- **GitHub API non-2xx response** (e.g. team/repo name already exists,
  HTTP 422) — every API-calling function should raise with the response
  status code and body included, so the fail-fast message is
  actionable.
- **Missing required env var** (e.g. `GITHUB_APP_PRIVATE_KEY_PATH` not
  set, or private key file not found) — config loading should fail
  fast with a clear message naming the missing variable/file, before
  any network call.
- **Hook entry shape variation** — `template.yaml` has hooks with a
  `url` field (`argocd-webhook`) and hooks with `source_url`/`target_url`
  fields (`jenkins-webhook_v2`). `create_hook` must handle both shapes
  without crashing on whichever fields are absent.

---

## Task 1: Project Scaffolding & Config Loading

**Files:**
- Create: `requirements.txt`
- Create: `.gitignore`
- Create: `src/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `load_config(vars_path: str = "vars.env", secrets_path: str = ".env") -> dict`
  returns a dict with keys: `github_org` (str), `github_api_base_url`
  (str), `github_app_id` (str), `github_app_private_key_path` (str),
  `github_app_installation_id` (str), `webhook_secret` (str, from
  `MY_GITHUB_SECRET`). Raises `ValueError` naming the missing variable
  if any required key is absent from either file.

- [ ] **Step 1: Create `requirements.txt`**

Pin these packages (exact versions left to implementer, use latest
stable at implementation time): `requests`, `PyYAML`, `python-dotenv`,
`PyJWT`, `cryptography`, `pytest`, `responses`.

- [ ] **Step 2: Create `.gitignore`**

Must ignore: `.env`, `*.pem`, `__pycache__/`, `*.pyc`, `.pytest_cache/`,
`venv/`.

- [ ] **Step 3: Write the failing test for `load_config`**

```python
def test_load_config_reads_both_files(tmp_path):
    vars_file = tmp_path / "vars.env"
    vars_file.write_text("GITHUB_ORG=my-org\nGITHUB_API_BASE_URL=https://api.github.com\n")
    secrets_file = tmp_path / ".env"
    secrets_file.write_text(
        "GITHUB_APP_ID=123\n"
        "GITHUB_APP_PRIVATE_KEY_PATH=./key.pem\n"
        "GITHUB_APP_INSTALLATION_ID=456\n"
        "MY_GITHUB_SECRET=supersecret\n"
    )
    config = load_config(str(vars_file), str(secrets_file))
    assert config["github_org"] == "my-org"
    assert config["github_api_base_url"] == "https://api.github.com"
    assert config["github_app_id"] == "123"
    assert config["github_app_private_key_path"] == "./key.pem"
    assert config["github_app_installation_id"] == "456"
    assert config["webhook_secret"] == "supersecret"


def test_load_config_missing_var_raises(tmp_path):
    vars_file = tmp_path / "vars.env"
    vars_file.write_text("GITHUB_ORG=my-org\n")  # missing GITHUB_API_BASE_URL
    secrets_file = tmp_path / ".env"
    secrets_file.write_text("GITHUB_APP_ID=123\n")
    with pytest.raises(ValueError, match="GITHUB_API_BASE_URL"):
        load_config(str(vars_file), str(secrets_file))
```

- [ ] **Step 4: Run test to verify it fails**

Run: `pytest tests/test_config.py -v`
Expected: FAIL with "load_config not defined" (or ModuleNotFoundError)

- [ ] **Step 5: Implement `load_config` in `src/config.py`**

Use `dotenv.dotenv_values(path)` to read each file into a dict without
mutating `os.environ`. Merge both dicts, check each required key is
present and non-empty, raise `ValueError(f"Missing required variable: {key}")`
on the first missing one. Required keys: `GITHUB_ORG`,
`GITHUB_API_BASE_URL`, `GITHUB_APP_ID`, `GITHUB_APP_PRIVATE_KEY_PATH`,
`GITHUB_APP_INSTALLATION_ID`, `MY_GITHUB_SECRET`. Return the lower-snake-case
dict as shown in the test.

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest tests/test_config.py -v`
Expected: PASS (2 tests)

- [ ] **Step 7: Commit**

```bash
git add requirements.txt .gitignore src/config.py tests/test_config.py
git commit -m "feat: add config loading from vars.env and .env"
```

---

## Task 2: YAML Parsing & Validation

**Files:**
- Create: `src/yaml_parser.py`
- Test: `tests/test_yaml_parser.py`

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces: `parse_template(path: str) -> dict` — returns
  `{"teams": [...], "repositories": [...]}` exactly as parsed (each a
  list of dicts), after validation. Raises `ValueError` if:
  - the top-level yaml is not a mapping with both `teams` and
    `repositories` keys (message must mention the missing key name)
  - any team entry is missing `name`
  - any repository entry is missing `name`
  - a repository entry has `type: repository-fork` but no `source`
    field

- [ ] **Step 1: Write the failing tests**

```python
def test_parse_template_returns_teams_and_repositories(tmp_path):
    yaml_file = tmp_path / "template.yaml"
    yaml_file.write_text(
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_yaml_parser.py -v`
Expected: FAIL (function not defined)

- [ ] **Step 3: Implement `parse_template` in `src/yaml_parser.py`**

Load the file with `yaml.safe_load`. Validate the loaded value is a
dict with `"teams" in data` else raise
`ValueError("template.yaml: missing 'teams' key")`; same for
`"repositories"`. For each team entry (index `i`), validate
`"name" in entry` else raise
`ValueError(f"Team {i}: missing 'name'")`. For each repository entry
(index `i`): validate `"name" in entry` else raise
`ValueError(f"Repository {i}: missing 'name'")`; if
`entry.get("type") == "repository-fork"`, validate `"source" in entry`
else raise
`ValueError(f"Repository {i} ({entry['name']}): missing 'source'")`.
Return `{"teams": data["teams"], "repositories": data["repositories"]}`
unchanged otherwise (nested `properties`/`hooks`/`teams` sub-lists are
not further validated at this layer).

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_yaml_parser.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add src/yaml_parser.py tests/test_yaml_parser.py
git commit -m "feat: add template.yaml parsing and validation for teams/repositories shape"
```

---

## Task 3: GitHub App Authentication

**Files:**
- Create: `src/github_auth.py`
- Test: `tests/test_github_auth.py`

**Interfaces:**
- Consumes: `config` dict shape from Task 1
  (`github_app_id`, `github_app_private_key_path`,
  `github_app_installation_id`, `github_api_base_url`).
- Produces: `get_installation_token(config: dict) -> str` — returns the
  installation access token string. Raises `RuntimeError` including the
  HTTP status code and response body if the token endpoint does not
  return 2xx.

- [ ] **Step 1: Write the failing tests**

```python
import responses
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization


@pytest.fixture
def test_private_key_pem():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()


@responses.activate
def test_get_installation_token_success(tmp_path, test_private_key_pem):
    key_path = tmp_path / "key.pem"
    key_path.write_text(test_private_key_pem)
    config = {
        "github_app_id": "123",
        "github_app_private_key_path": str(key_path),
        "github_app_installation_id": "456",
        "github_api_base_url": "https://api.github.com",
    }
    responses.add(
        responses.POST,
        "https://api.github.com/app/installations/456/access_tokens",
        json={"token": "ghs_abc123", "expires_at": "2099-01-01T00:00:00Z"},
        status=201,
    )
    token = get_installation_token(config)
    assert token == "ghs_abc123"


@responses.activate
def test_get_installation_token_failure_raises(tmp_path, test_private_key_pem):
    key_path = tmp_path / "key.pem"
    key_path.write_text(test_private_key_pem)
    config = {
        "github_app_id": "123",
        "github_app_private_key_path": str(key_path),
        "github_app_installation_id": "456",
        "github_api_base_url": "https://api.github.com",
    }
    responses.add(
        responses.POST,
        "https://api.github.com/app/installations/456/access_tokens",
        json={"message": "Bad credentials"},
        status=401,
    )
    with pytest.raises(RuntimeError, match="401"):
        get_installation_token(config)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_github_auth.py -v`
Expected: FAIL (function not defined)

- [ ] **Step 3: Implement `get_installation_token` in `src/github_auth.py`**

Build the JWT: `iat = int(time.time()) - 60`, `exp = iat + 600 + 60`,
`iss = config["github_app_id"]`, encode with
`jwt.encode(payload, private_key_bytes, algorithm="RS256")` (read
private key bytes from `github_app_private_key_path`). POST to
`f'{config["github_api_base_url"]}/app/installations/{config["github_app_installation_id"]}/access_tokens'`
with header `Authorization: Bearer {jwt_token}` and
`Accept: application/vnd.github+json`. On non-2xx, raise
`RuntimeError(f"Failed to get installation token: {response.status_code} {response.text}")`.
On success, return `response.json()["token"]`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_github_auth.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add src/github_auth.py tests/test_github_auth.py
git commit -m "feat: add GitHub App JWT auth and installation token fetch"
```

---

## Task 4: Team Creation

**Files:**
- Create: `src/github_teams.py`
- Test: `tests/test_github_teams.py`

**Interfaces:**
- Consumes: `token: str` (from Task 3), `org: str` (from Task 1's
  `config["github_org"]`).
- Produces: `create_team(org: str, token: str, entry: dict, api_base_url: str) -> str` —
  `entry` is a team dict from the parsed `teams:` list (`name`,
  optional `description`). Returns the created team's `slug` (str).
  Raises `RuntimeError` including status code and body on non-2xx.

Note: `group` (GIAM/Entra sync) and `owners` fields on the team entry
are intentionally not used in v1 — out of scope per spec.

- [ ] **Step 1: Write the failing tests**

```python
@responses.activate
def test_create_team_success():
    responses.add(
        responses.POST,
        "https://api.github.com/orgs/my-org/teams",
        json={"slug": "jenkins-team"},
        status=201,
    )
    entry = {"name": "jenkins-team", "description": "team manages jenkins service"}
    slug = create_team("my-org", "ghs_abc123", entry, "https://api.github.com")
    assert slug == "jenkins-team"


@responses.activate
def test_create_team_failure_raises():
    responses.add(
        responses.POST,
        "https://api.github.com/orgs/my-org/teams",
        json={"message": "Name already exists"},
        status=422,
    )
    entry = {"name": "jenkins-team"}
    with pytest.raises(RuntimeError, match="422"):
        create_team("my-org", "ghs_abc123", entry, "https://api.github.com")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_github_teams.py -v`
Expected: FAIL (function not defined)

- [ ] **Step 3: Implement `create_team` in `src/github_teams.py`**

POST to `f"{api_base_url}/orgs/{org}/teams"` with headers
`Authorization: Bearer {token}`, `Accept: application/vnd.github+json`,
body `{"name": entry["name"], "description": entry.get("description", "")}`.
On non-2xx raise `RuntimeError(f"Failed to create team '{entry['name']}': {response.status_code} {response.text}")`.
On success return `response.json()["slug"]`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_github_teams.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add src/github_teams.py tests/test_github_teams.py
git commit -m "feat: add GitHub team creation"
```

---

## Task 5: Repository Creation (Plain & Fork), Team Attachment & Custom Properties

**Files:**
- Create: `src/github_repos.py`
- Test: `tests/test_github_repos.py`

**Interfaces:**
- Consumes: `token: str`, `org: str`, `api_base_url: str` (same as
  Task 4).
- Produces:
  - `create_repo(org: str, token: str, entry: dict, api_base_url: str) -> None` —
    plain repository entry (no `type` key, or `type` != `repository-fork`).
    `entry` has `name` and optional `teams` (list of
    `{"name": str, "role": str}`) and `properties` (dict). Creates the
    repo via `POST /orgs/{org}/repos`, then attaches each team, then
    sets properties, in that order. Raises `RuntimeError` (status +
    body) on any non-2xx.
  - `create_repo_fork(org: str, token: str, entry: dict, api_base_url: str) -> None` —
    `entry` has `name`, `source` (`owner/repo` to fork), and optional
    `teams`/`properties` same as `create_repo`. Creates the fork via
    `POST /repos/{source}/forks` with body `{"organization": org, "name": entry["name"]}`,
    then attaches teams and sets properties exactly like `create_repo`.
  - `attach_team_to_repo(org: str, token: str, repo_name: str, team_slug: str, role: str, api_base_url: str) -> None`
  - `set_repo_properties(org: str, token: str, repo_name: str, properties: dict, api_base_url: str) -> None`

Note: `entry["teams"][i]["name"]` in `template.yaml` is the **team
name**, not slug — assume name and slug are identical for v1 (GitHub
slugifies simple lowercase-hyphen names like `jenkins-team` to
themselves). `role` strings like `"read/triage/write/maintain/cicd"`
are passed straight through to the GitHub `permission` field as-is;
no parsing/translation in v1 (document this as a known limitation in
the README).

To avoid duplicating the "attach teams, then set properties" logic
between `create_repo` and `create_repo_fork`, factor it into a small
internal helper (e.g. `_attach_teams_and_properties(org, token, entry, api_base_url)`)
that both call after their respective repo-creation POST succeeds.

- [ ] **Step 1: Write the failing tests**

```python
@responses.activate
def test_create_repo_posts_to_org_repos():
    responses.add(
        responses.POST,
        "https://api.github.com/orgs/my-org/repos",
        json={"name": "docker-jenkins"},
        status=201,
    )
    entry = {"name": "docker-jenkins"}
    create_repo("my-org", "ghs_abc123", entry, "https://api.github.com")
    assert responses.calls[0].request.url == "https://api.github.com/orgs/my-org/repos"


@responses.activate
def test_create_repo_failure_raises():
    responses.add(
        responses.POST,
        "https://api.github.com/orgs/my-org/repos",
        json={"message": "name already exists"},
        status=422,
    )
    entry = {"name": "docker-jenkins"}
    with pytest.raises(RuntimeError, match="422"):
        create_repo("my-org", "ghs_abc123", entry, "https://api.github.com")


@responses.activate
def test_create_repo_fork_posts_to_source_forks():
    responses.add(
        responses.POST,
        "https://api.github.com/repos/some-org/docker-jenkins-upstream/forks",
        json={"name": "docker-jenkins"},
        status=202,
    )
    entry = {
        "type": "repository-fork",
        "name": "docker-jenkins",
        "source": "some-org/docker-jenkins-upstream",
    }
    create_repo_fork("my-org", "ghs_abc123", entry, "https://api.github.com")
    assert responses.calls[0].request.url == "https://api.github.com/repos/some-org/docker-jenkins-upstream/forks"


@responses.activate
def test_create_repo_fork_failure_raises():
    responses.add(
        responses.POST,
        "https://api.github.com/repos/some-org/docker-jenkins-upstream/forks",
        json={"message": "not found"},
        status=404,
    )
    entry = {
        "type": "repository-fork",
        "name": "docker-jenkins",
        "source": "some-org/docker-jenkins-upstream",
    }
    with pytest.raises(RuntimeError, match="404"):
        create_repo_fork("my-org", "ghs_abc123", entry, "https://api.github.com")


@responses.activate
def test_attach_team_to_repo_puts_permission():
    responses.add(
        responses.PUT,
        "https://api.github.com/orgs/my-org/teams/jenkins-team/repos/my-org/docker-jenkins",
        status=204,
    )
    attach_team_to_repo("my-org", "ghs_abc123", "docker-jenkins", "jenkins-team", "maintain", "https://api.github.com")
    assert responses.calls[0].request.url.endswith("/teams/jenkins-team/repos/my-org/docker-jenkins")


@responses.activate
def test_set_repo_properties_patches_values():
    responses.add(
        responses.PATCH,
        "https://api.github.com/repos/my-org/docker-jenkins/properties/values",
        status=204,
    )
    set_repo_properties("my-org", "ghs_abc123", "docker-jenkins", {"euc-flag": "true"}, "https://api.github.com")
    assert responses.calls[0].request.url.endswith("/properties/values")


@responses.activate
def test_create_repo_attaches_teams_and_properties():
    responses.add(responses.POST, "https://api.github.com/orgs/my-org/repos", json={"name": "docker-jenkins"}, status=201)
    responses.add(responses.PUT, "https://api.github.com/orgs/my-org/teams/jenkins-team/repos/my-org/docker-jenkins", status=204)
    responses.add(responses.PATCH, "https://api.github.com/repos/my-org/docker-jenkins/properties/values", status=204)
    entry = {
        "name": "docker-jenkins",
        "teams": [{"name": "jenkins-team", "role": "maintain"}],
        "properties": {"euc-flag": "true"},
    }
    create_repo("my-org", "ghs_abc123", entry, "https://api.github.com")
    assert len(responses.calls) == 3
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_github_repos.py -v`
Expected: FAIL (functions not defined)

- [ ] **Step 3: Implement `create_repo`, `create_repo_fork`, `attach_team_to_repo`, `set_repo_properties`, and the internal `_attach_teams_and_properties` helper in `src/github_repos.py`**

- `_attach_teams_and_properties(org, token, entry, api_base_url)`: loop
  `entry.get("teams", [])` calling
  `attach_team_to_repo(org, token, entry["name"], t["name"], t["role"], api_base_url)`
  for each; then if `entry.get("properties")`, call
  `set_repo_properties(org, token, entry["name"], entry["properties"], api_base_url)`.
- `create_repo`: POST `f"{api_base_url}/orgs/{org}/repos"` with body
  `{"name": entry["name"]}`. Raise
  `RuntimeError(f"Failed to create repo '{entry['name']}': {response.status_code} {response.text}")`
  on non-2xx. On success call `_attach_teams_and_properties(...)`.
- `create_repo_fork`: POST `f"{api_base_url}/repos/{entry['source']}/forks"`
  with body `{"organization": org, "name": entry["name"]}`. Raise
  `RuntimeError(f"Failed to fork repo '{entry['source']}' as '{entry['name']}': {response.status_code} {response.text}")`
  on non-2xx (GitHub returns 202 on success for forks). On success call
  `_attach_teams_and_properties(...)`.
- `attach_team_to_repo`: PUT
  `f"{api_base_url}/orgs/{org}/teams/{team_slug}/repos/{org}/{repo_name}"`
  with body `{"permission": role}`. Raise on non-2xx/204.
- `set_repo_properties`: PATCH
  `f"{api_base_url}/repos/{org}/{repo_name}/properties/values"` with
  body `{"properties": [{"property_name": k, "value": v} for k, v in properties.items()]}`.
  Raise on non-2xx/204.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_github_repos.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add src/github_repos.py tests/test_github_repos.py
git commit -m "feat: add repo creation (plain + fork), team attachment, and custom properties"
```

---

## Task 6: Webhook Creation

**Files:**
- Create: `src/github_hooks.py`
- Test: `tests/test_github_hooks.py`

**Interfaces:**
- Consumes: `token: str`, `org: str`, `api_base_url: str` (same as
  Task 4/5), `webhook_secret: str` (from Task 1's
  `config["webhook_secret"]`, used as fallback if a hook entry has no
  resolvable secret value).
- Produces: `create_hook(org: str, token: str, repo_name: str, hook_entry: dict, default_secret: str, api_base_url: str) -> None`.
  Raises `RuntimeError` (status + body) on non-2xx.

Per Review Focus: `hook_entry` may have a `url` key (e.g.
`argocd-webhook`) or `target_url`/`source_url` keys (e.g.
`jenkins-webhook_v2`). Resolve the delivery URL as
`hook_entry.get("url") or hook_entry.get("target_url")`; if neither is
present raise `ValueError(f"Hook '{hook_entry.get('name')}' has no url or target_url")`.

- [ ] **Step 1: Write the failing tests**

```python
@responses.activate
def test_create_hook_with_url_field():
    responses.add(
        responses.POST,
        "https://api.github.com/repos/my-org/docker-jenkins/hooks",
        status=201,
    )
    hook_entry = {
        "name": "argocd-webhook",
        "url": "https://argocd.platform.cloud.allianz.io/hook",
        "events": ["push", "pull_request"],
        "secret": "MY_GITHUB_SECRET",
    }
    create_hook("my-org", "ghs_abc123", "docker-jenkins", hook_entry, "fallback-secret", "https://api.github.com")
    body = responses.calls[0].request.body
    assert b"argocd.platform.cloud.allianz.io" in body


@responses.activate
def test_create_hook_with_target_url_field():
    responses.add(
        responses.POST,
        "https://api.github.com/repos/my-org/docker-jenkins/hooks",
        status=201,
    )
    hook_entry = {
        "name": "jenkins-webhook_v2",
        "source_url": "https://jenkins-source.example/github-webhook/",
        "target_url": "https://jenkins-target.example/github-webhook/",
        "events": ["push", "pull_request"],
    }
    create_hook("my-org", "ghs_abc123", "docker-jenkins", hook_entry, "fallback-secret", "https://api.github.com")
    body = responses.calls[0].request.body
    assert b"jenkins-target.example" in body


def test_create_hook_missing_url_raises():
    hook_entry = {"name": "broken-hook", "events": ["push"]}
    with pytest.raises(ValueError, match="no url or target_url"):
        create_hook("my-org", "ghs_abc123", "docker-jenkins", hook_entry, "fallback-secret", "https://api.github.com")


@responses.activate
def test_create_hook_failure_raises():
    responses.add(
        responses.POST,
        "https://api.github.com/repos/my-org/docker-jenkins/hooks",
        json={"message": "Validation failed"},
        status=422,
    )
    hook_entry = {"name": "argocd-webhook", "url": "https://argocd.example/hook", "events": ["push"]}
    with pytest.raises(RuntimeError, match="422"):
        create_hook("my-org", "ghs_abc123", "docker-jenkins", hook_entry, "fallback-secret", "https://api.github.com")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_github_hooks.py -v`
Expected: FAIL (function not defined)

- [ ] **Step 3: Implement `create_hook` in `src/github_hooks.py`**

Resolve `delivery_url` as described above (raise `ValueError` if
missing). Resolve
`secret = hook_entry["secret"] if (hook_entry.get("secret") and hook_entry["secret"] != "MY_GITHUB_SECRET") else default_secret`
(the yaml's literal `secret: MY_GITHUB_SECRET` is an env-var *name*
placeholder, not a literal value — fall back to `default_secret`, the
resolved value from config, whenever the yaml value is that
placeholder or absent; add a one-line comment explaining this). POST
to `f"{api_base_url}/repos/{org}/{repo_name}/hooks"` with body
`{"name": "web", "active": True, "events": hook_entry.get("events", ["push"]), "config": {"url": delivery_url, "content_type": "json", "secret": secret}}`.
Raise `RuntimeError` with status + body on non-2xx.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_github_hooks.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/github_hooks.py tests/test_github_hooks.py
git commit -m "feat: add webhook creation supporting url and target_url shapes"
```

---

## Task 7: Main Orchestration (End-to-End Dispatch)

**Files:**
- Create: `src/main.py`
- Test: `tests/test_main.py`

**Interfaces:**
- Consumes: `load_config` (Task 1), `parse_template` (Task 2),
  `get_installation_token` (Task 3), `create_team` (Task 4),
  `create_repo`/`create_repo_fork` (Task 5), `create_hook` (Task 6).
- Produces: `run(template_path: str, vars_path: str, secrets_path: str) -> None` —
  the full orchestration entry point. Raises whatever the first failing
  step raises (fail-fast; no catching/wrapping beyond what each module
  already does). A `if __name__ == "__main__":` block calls
  `run("template.yaml", "vars.env", ".env")` and on any exception
  prints `f"ERROR: {exc}"` to stderr and calls `sys.exit(1)`.

- [ ] **Step 1: Write the failing tests**

```python
def test_run_creates_all_teams_then_all_repositories(monkeypatch):
    calls = []
    monkeypatch.setattr("src.main.load_config", lambda v, s: {"github_org": "my-org", "github_api_base_url": "https://api.github.com", "webhook_secret": "shh"})
    monkeypatch.setattr("src.main.parse_template", lambda p: {
        "teams": [{"name": "jenkins-team"}, {"name": "cicd-admins"}],
        "repositories": [{"name": "docker-jenkins"}],
    })
    monkeypatch.setattr("src.main.get_installation_token", lambda c: "ghs_abc123")
    monkeypatch.setattr("src.main.create_team", lambda org, token, entry, base: calls.append(("team", entry["name"])))
    monkeypatch.setattr("src.main.create_repo", lambda org, token, entry, base: calls.append(("repository", entry["name"])))

    run("template.yaml", "vars.env", ".env")

    assert calls == [("team", "jenkins-team"), ("team", "cicd-admins"), ("repository", "docker-jenkins")]


def test_run_dispatches_repository_fork_to_create_repo_fork(monkeypatch):
    calls = []
    monkeypatch.setattr("src.main.load_config", lambda v, s: {"github_org": "my-org", "github_api_base_url": "https://api.github.com", "webhook_secret": "shh"})
    monkeypatch.setattr("src.main.parse_template", lambda p: {
        "teams": [],
        "repositories": [{"type": "repository-fork", "name": "docker-jenkins", "source": "some-org/upstream"}],
    })
    monkeypatch.setattr("src.main.get_installation_token", lambda c: "ghs_abc123")
    monkeypatch.setattr("src.main.create_repo_fork", lambda org, token, entry, base: calls.append(entry["name"]))

    run("template.yaml", "vars.env", ".env")

    assert calls == ["docker-jenkins"]


def test_run_creates_hooks_for_repository(monkeypatch):
    calls = []
    monkeypatch.setattr("src.main.load_config", lambda v, s: {"github_org": "my-org", "github_api_base_url": "https://api.github.com", "webhook_secret": "shh"})
    monkeypatch.setattr("src.main.parse_template", lambda p: {
        "teams": [],
        "repositories": [{"name": "docker-jenkins", "hooks": [{"name": "argocd-webhook", "url": "https://argocd.example/hook"}]}],
    })
    monkeypatch.setattr("src.main.get_installation_token", lambda c: "ghs_abc123")
    monkeypatch.setattr("src.main.create_repo", lambda org, token, entry, base: None)
    monkeypatch.setattr("src.main.create_hook", lambda org, token, repo_name, hook_entry, default_secret, base: calls.append((repo_name, hook_entry["name"])))

    run("template.yaml", "vars.env", ".env")

    assert calls == [("docker-jenkins", "argocd-webhook")]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_main.py -v`
Expected: FAIL (function not defined)

- [ ] **Step 3: Implement `run` in `src/main.py`**

```python
def run(template_path, vars_path, secrets_path):
    config = load_config(vars_path, secrets_path)
    parsed = parse_template(template_path)
    token = get_installation_token(config)
    base = config.get("github_api_base_url", "https://api.github.com")
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
```

(Signature and body shown here since the tests' `monkeypatch` calls pin
the exact attribute names `src.main.load_config` etc. — implementer
wires imports accordingly, e.g. `from src.config import load_config`
then referenced at module scope as `load_config` so monkeypatch targets
resolve.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_main.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Add the `if __name__ == "__main__":` CLI entry block to `src/main.py`**

```python
if __name__ == "__main__":
    import sys
    try:
        run("template.yaml", "vars.env", ".env")
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
```

- [ ] **Step 6: Commit**

```bash
git add src/main.py tests/test_main.py
git commit -m "feat: add main orchestration with fail-fast team/repo/hook dispatch"
```

---

## Task 8: Containerization & README

**Files:**
- Create: `Dockerfile`
- Create: `README.md`
- Create: `vars.env.example`
- Create: `.env.example`

**Interfaces:**
- Consumes: `requirements.txt` (Task 1), `src/` (Tasks 1-7),
  `template.yaml` (existing, repo root).
- Produces: a buildable Docker image that runs `python src/main.py` as
  its entry point.

- [ ] **Step 1: Write `Dockerfile`**

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src/ ./src/
COPY template.yaml .
ENTRYPOINT ["python", "src/main.py"]
```

- [ ] **Step 2: Build the image to verify it builds**

Run: `docker build -t repo-create .`
Expected: build completes with exit code 0

- [ ] **Step 3: Write `vars.env.example` and `.env.example`**

`vars.env.example`:
```
GITHUB_ORG=my-org-name
GITHUB_API_BASE_URL=https://api.github.com
```

`.env.example`:
```
GITHUB_APP_ID=
GITHUB_APP_PRIVATE_KEY_PATH=./app-private-key.pem
GITHUB_APP_INSTALLATION_ID=
MY_GITHUB_SECRET=
```

- [ ] **Step 4: Write `README.md`**

Cover: what the project does, prerequisites (GitHub App + its
installation ID, private key file), how to copy `.env.example`/`vars.env.example`
to real `.env`/`vars.env` and fill them in, `template.yaml`'s shape
(`teams:` + `repositories:`, fork entries via `type: repository-fork` +
`source`), how to run locally
(`pip install -r requirements.txt && python src/main.py`), how to run
via Docker (`docker build -t repo-create . && docker run --env-file .env --env-file vars.env -v $(pwd)/app-private-key.pem:/app/app-private-key.pem repo-create`),
and the known v1 limitations (no idempotency, no GIAM/Entra sync, no
Cloud WAF registration, flat team model, `role` string passed through
as-is to GitHub's `permission` field without translation).

- [ ] **Step 5: Smoke-test the container runs and fails fast on missing config**

Run: `docker run --rm repo-create` (no env files mounted)
Expected: exits non-zero, prints an `ERROR:` message naming a missing
required variable (proves fail-fast works inside the container too).

- [ ] **Step 6: Commit**

```bash
git add Dockerfile README.md vars.env.example .env.example
git commit -m "feat: add containerization and README"
```

---

## Addendum: Idempotency (post-implementation)

Added after initial implementation, in response to real-run testing
against a live GitHub org (rerunning the script hit `422` on
duplicate team/repo creation).

- **Task 4 (`create_team`)**: added `_get_existing_team_slug` —
  `GET /orgs/{org}/teams/{team_name}` before `POST`; returns existing
  slug if found, skips creation.
- **Task 5 (`create_repo`)**: added `_repo_exists` —
  `GET /repos/{org}/{name}` before `POST`; skips creation if found,
  still runs `_attach_teams_and_properties` so permissions/properties
  stay in sync on rerun. `attach_team_to_repo`'s `PUT` was already
  idempotent (no change needed).
- **Task 6 (`create_hook`)**: added `_hook_url_registered` —
  `GET /repos/{org}/{repo}/hooks`, matches existing hooks by
  `config.url`; skips creation if a hook with the same delivery URL
  already exists, avoiding duplicate webhooks on rerun.
- Tests updated/added in `tests/test_github_teams.py`,
  `tests/test_github_repos.py`, `tests/test_github_hooks.py` following
  TDD (failing test added first, then implementation).
- See design spec's "Idempotency" section for full rationale and
  trade-offs.

---

## Final Full-Suite Check

- [ ] Run: `pytest -v`
- [ ] Expected: all tests across all 7 test files pass, 0 failures
