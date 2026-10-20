# Python GitHub Repo/Team Creator — Design Spec

## Purpose

Parse `template.yaml` (a declarative description of GitHub teams,
repositories, repository forks, repo properties, and webhooks) and use the
GitHub REST API to create those resources in a GitHub Enterprise Cloud
(GHEC) organization.

## template.yaml Shape

`template.yaml` is a single mapping with two top-level keys:

```yaml
teams:
  - name: jenkins-team
    description: ...
    group: ...        # GIAM/Entra sync group (deferred, not used in v1)
    owners: [...]      # (deferred, not used in v1)
  - name: cicd-admins
    group: ...
    owners: [...]

repositories:
  - name: docker-jenkins
    teams:              # grants listed teams access to this repo
      - name: jenkins-team
        role: read/triage/write/maintain/cicd
      - name: cicd-admins
        role: read/triage/write/maintain/cicd
    properties: {...}   # optional, repo custom properties
    hooks: [...]        # optional, repo webhooks
  - type: repository-fork   # child entry inside `repositories:`, marked
    name: docker-jenkins    # with this field to pick a different create
    source: owner/upstream-repo  # mechanic (fork vs. new repo)
    teams: [...]
```

Plain `repository` entries have no `type` key (default); fork entries
are distinguished by `type: repository-fork` and carry a `source`
(`owner/repo`) field naming what to fork from.

## Scope (v1)

Support all resource types present in `template.yaml`:

- `teams` (top-level list)
- `repositories` (top-level list), including:
  - plain `repository` entries (no `type` key)
  - `repository-fork` child entries (`type: repository-fork` + `source`)
  - nested `properties` and `hooks` under any repository entry
- a repository's `teams:` list grants the named (already-defined) team
  access to that repo via `role`

Out of scope for v1:

- GIAM/Entra ID group sync for teams (deferred — user must confirm how
  this integrates; assume it is handled by an external/upstream system
  for now)
- Cloud WAF / Apigee webhook registration and IP whitelisting (deferred
  for the same reason — assume external/manual for now)
- Idempotency / upsert logic (v1 is create-only, run once; revisit later)
- Team hierarchy (parent/child teams) — `template.yaml` currently
  describes two flat, independent teams. User wants to verify whether
  GitHub's `parent_team_id` nesting should be used instead. v1 keeps
  the flat model; extending to parent/child is a follow-up once
  confirmed.
- Retry logic for failed API calls

## Target Environment

- GitHub Enterprise Cloud (GHEC), i.e. `https://api.github.com`
- Auth: GitHub App (JWT → installation access token flow). User creates
  the GitHub App and supplies its credentials.

## Coding Style

- No classes unless strictly necessary. Plain functions operating on
  dicts/primitives throughout, to keep the codebase approachable for a
  developer who is not yet confident in Python.
- Standard library + a small number of well-known third-party packages
  (`requests`, `PyYAML`, `python-dotenv`, `PyJWT`, `cryptography`).

## File Layout

```
python-project-repo-create/
  src/
    main.py              # entry point, orchestrates the whole run
    yaml_parser.py       # load + validate template.yaml
    github_auth.py       # GitHub App JWT -> installation token
    github_teams.py       # create team functions
    github_repos.py       # create repo, set properties, add teams
    github_hooks.py       # create webhooks
    config.py            # load vars.env (org name etc.) + .env (secrets)
  tests/
    test_yaml_parser.py
    test_github_teams.py
    test_github_repos.py
    test_github_hooks.py
    test_config.py
  template.yaml
  vars.env              # repo-related vars, non-secret (like .tfvars)
  .env                  # GitHub App credentials + webhook secrets (gitignored)
  requirements.txt
  README.md
  .gitignore
```

Each `github_*.py` module has one responsibility (team ops, repo ops, hook
ops), making each one independently readable and testable.

## Data Flow

1. `main.py` loads `vars.env` (org name, API base URL) and `.env`
   (GitHub App credentials, webhook secrets) via `config.py`. No
   network calls yet.
2. `yaml_parser.py` loads and validates `template.yaml`. Fail fast on
   malformed/invalid input, before any network/auth work happens.
3. `github_auth.py` builds a JWT from the GitHub App's private key,
   calls `POST /app/installations/{installation_id}/access_tokens`,
   and returns a short-lived installation access token.
4. `main.py` first processes the whole `teams:` list — each entry →
   `github_teams.create_team(entry, token, org)` — then processes the
   whole `repositories:` list in order. For each repository entry:
   - if `entry.get("type") == "repository-fork"` →
     `github_repos.create_repo_fork(entry, token, org)` (uses
     `entry["source"]`, the `owner/repo` to fork from)
   - otherwise (plain repository) →
     `github_repos.create_repo(entry, token, org)`
   - either way, then attach each team listed in `entry["teams"]` (by
     name + role) to the new repo, then set custom `properties` if
     present, then `github_hooks.create_hook(...)` for each entry
     under `hooks` if present.
5. Fail-fast: the first API error raises an exception, a clear message
   is printed (what failed and why), and the process exits non-zero.
   No continue-on-error behavior in v1.

## Config Files

`vars.env` — repo-related, non-secret, `.tfvars`-style:

```
GITHUB_ORG=my-org-name
GITHUB_API_BASE_URL=https://api.github.com
```

`.env` — secrets, **gitignored**:

```
GITHUB_APP_ID=123456
GITHUB_APP_PRIVATE_KEY_PATH=./app-private-key.pem
GITHUB_APP_INSTALLATION_ID=789012
MY_GITHUB_SECRET=xxxx
```

Both are loaded with `python-dotenv`. `.env` and any private key file
are listed in `.gitignore`.

## Error Handling & Logging

- Fail-fast: raise an exception on the first error encountered.
- Print a clear, human-readable message describing what failed and why,
  then `sys.exit(1)`.
- Simple progress logging via the standard `logging` module (e.g.
  `Creating team: jenkins-team... OK`).
- No retries in v1.

## Testing

- `pytest`, following the existing TDD workflow (write failing tests
  first, then implement).
- Mock all GitHub API calls (e.g. with `responses` or
  `unittest.mock`) — no real network calls in tests.
- One test file per module; cover the happy path plus at least one
  failure path that exercises fail-fast behavior.

## Containerization

The script runs inside a container (not on bare metal/local python only).

- `Dockerfile` using a slim official Python base image (e.g.
  `python:3.12-slim`).
- Install `requirements.txt` deps at build time.
- Copy `src/` and `template.yaml` into the image.
- `.env` and `vars.env` are **not baked into the image**; they are
  supplied at `docker run` time via `--env-file .env --env-file vars.env`
  (or mounted as a volume), keeping secrets out of the image.
- Entry point: `python src/main.py`.
- No orchestration (Compose/K8s) needed for v1 — just a single
  container run.

## Idempotency

The script is safe to rerun against the same `template.yaml` without
manual cleanup:

- **Teams** (`create_team`): checks `GET /orgs/{org}/teams/{team_name}`
  first; if found, returns the existing slug and skips the `POST`.
- **Repositories** (`create_repo`): checks `GET /repos/{org}/{name}`
  first; if found, skips the `POST` but still runs team attachment and
  property sync so permissions/properties stay in sync on rerun.
- **Team-repo attachment** (`attach_team_to_repo`): the underlying
  `PUT` permission endpoint is naturally idempotent (upsert); no extra
  check needed.
- **Webhooks** (`create_hook`): checks `GET
  /repos/{org}/{repo}/hooks` and matches on `config.url`; skips the
  `POST` if a hook with the same delivery URL already exists, avoiding
  duplicate hooks on rerun.
- Forked repos (`create_repo_fork`) and custom properties
  (`set_repo_properties`) are not separately exist-checked in v1 —
  assumes org-level custom property schema is pre-defined (see Open
  Items below).

Trade-off: each idempotency check adds one extra `GET` per
repo/team/hook. Negligible for typical template sizes (tens of
entries); would need batching/caching if scaled to hundreds.

## Open Items Deferred to Later Iterations

- GIAM/Entra ID group sync integration
- Cloud WAF / Apigee webhook registration + IP whitelisting
- Team parent/child hierarchy (pending user confirmation)
- Org-level custom property schema definition: v1 assumes the schema
  (`service-offering-number`, `adoit-service-id`, `repo-category`,
  `euc-flag`, `deployment-branches`, `jira-project-key`, etc.) already
  exists in the target org (defined via `PATCH
  /orgs/{org}/properties/schema`); setting values for undefined
  properties returns `403 Resource not accessible by integration`.
  Production orgs are expected to have this schema defined ahead of
  time, so the script does not pre-flight-create it.
