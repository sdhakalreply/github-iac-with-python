# Scenario C GitOps Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Apply only `stress_template.yaml` changes pushed to `feature/gitops-state`, and reconcile webhooks against the local yaml like Scenario A.

**Architecture:** GitHub Actions validates each push and diffs its yaml against the last successful GitHub Deployment. A focused GitOps module applies only changed fields and additions/removals; the first run records a baseline only. The receiver reads and validates local `stress_template.yaml` on each authenticated webhook.

**Tech Stack:** Python, PyYAML, Flask, GitHub REST API, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-10-20-scenario-c-gitops-design.md`

## Global Constraints

- Only Scenario C changes; do not touch Scenario A.
- `stress_template.yaml` is the sole desired-state file.
- Push trigger branch is `feature/gitops-state`.
- First Actions run records baseline and makes no org-resource changes.
- GitHub App credentials edit org resources; `GITHUB_TOKEN` records deployments only.
- Removed repos and teams are deleted; removed repo property values are cleared; property definitions remain.
- Repo rename preserves the GitHub repo by matching immutable yaml `id`.
- Webhooks read and validate local `stress_template.yaml` per event, like Scenario A.
- No Docker.

## Review Focus

- Missing or duplicate repo IDs could target the wrong resource; validate every `id` as required and unique.
- A failed partial apply must not advance the successful deployment; retry from the prior deployment.
- A failed deployment status must not be mistaken for the last successful commit.
- Removed-resource processing must delete only IDs/names present in prior yaml and absent in new yaml.
- Template read or validation failure must stop webhook reconciliation.

---

### Task 1: Stable repository identity

**Files:**
- Modify: `src/validator.py`
- Modify: `stress_template.yaml`
- Test: `tests/test_validator.py`

**Interfaces:**
- Produces: valid repository entries contain unique, non-empty `id` and mutable `name`.
- Existing repositories receive `id` equal to their current `name`; preserve existing names and all other yaml values.

- [ ] **Step 1: Write failing validation tests**

Add tests that reject missing, empty, and duplicate repository IDs, and accept distinct IDs with duplicate-check behavior unchanged for names.

- [ ] **Step 2: Run tests to verify they fail**

Run: `./venv/bin/python -m pytest tests/test_validator.py -q`
Expected: new ID validation tests fail.

- [ ] **Step 3: Implement ID validation**

Require a non-empty string `id` for every repository and report duplicate IDs with the repository index/name.

- [ ] **Step 4: Add stable IDs to the 5,000 existing repository entries**

Set each new `id` to that entry's current `name`; do not alter any other yaml field.

- [ ] **Step 5: Verify yaml and validation**

Run: `./venv/bin/python -c "from src.validator import validate_file; validate_file('stress_template.yaml')"`
Expected: exits 0; all 5,000 IDs are present and unique.

Run: `./venv/bin/python -m pytest tests/test_validator.py -q`
Expected: PASS.

### Task 2: Targeted GitOps diff and apply

**Files:**
- Create: `src/gitops.py`
- Modify: `src/github_repos.py`
- Modify: `src/github_teams.py`
- Modify: `src/github_drift.py`
- Modify: `src/github_properties.py`
- Test: `tests/test_gitops.py`
- Test: `tests/test_github_repos.py`
- Test: `tests/test_github_teams.py`
- Test: `tests/test_github_properties.py`

**Interfaces:**
- `plan_changes(previous: dict, current: dict) -> dict` returns changed teams, changed repos keyed by stable repo `id`, removed team names, and removed repo IDs.
- `apply_changes(previous: dict, current: dict, config: dict, token_provider) -> dict` applies only that plan and raises if any operation fails.
- `github_repos.delete_repo(org, token, repo_name, api_base_url) -> None`
- `github_teams.delete_team(org, token, team_slug, api_base_url) -> None`

- [ ] **Step 1: Write failing diff-planning tests**

Test additions, description edits, repo rename by stable ID, role changes, property additions/edits/removals, unchanged entries, and removed IDs/names. Assert unchanged entries are absent from the plan.

- [ ] **Step 2: Run tests to verify they fail**

Run: `./venv/bin/python -m pytest tests/test_gitops.py -q`
Expected: import/function failures.

- [ ] **Step 3: Implement pure `plan_changes`**

Diff parsed templates by team name and repo `id`; compare repo fields independently. Include added or changed property definitions, but never plan definition deletion. Treat `name` change on the same ID as rename, not delete/create.

- [ ] **Step 4: Write failing GitHub operation tests**

Test repository/team DELETE endpoints, property clear payloads using `null`, and changed-field calls without GETs for unchanged entries.

- [ ] **Step 5: Implement `apply_changes` and API helpers**

Apply only changed fields. Create added entries; rename repos by stable ID; delete only previous entries absent from current yaml. Detach removed team assignments before deleting teams. Add or update changed property definitions; send `null` for removed repo property values and retain definitions. Stop and raise on the first failed operation.

- [ ] **Step 6: Run focused tests**

Run: `./venv/bin/python -m pytest tests/test_gitops.py tests/test_github_repos.py tests/test_github_teams.py tests/test_github_properties.py -q`
Expected: PASS.

### Task 3: Deployment baseline and Actions workflow

**Files:**
- Modify: `src/gitops.py`
- Create: `scripts/run_gitops.py`
- Create: `.github/workflows/scenario-c-gitops.yml`
- Modify: `.github/workflows/ci.yml`
- Test: `tests/test_gitops.py`

**Interfaces:**
- `latest_successful_deployment_commit(owner: str, repo: str, environment: str, token: str) -> str | None`
- `record_deployment(owner: str, repo: str, environment: str, commit_sha: str, state: str, token: str) -> None`
- Runner accepts current template path, current commit SHA, GitHub repo identity, and GitHub App credentials from environment.

- [ ] **Step 1: Write failing deployment-selection tests**

Test no deployments, latest successful deployment, newer failed deployment, and deployment API errors. Failed or pending records must not replace last successful commit.

- [ ] **Step 2: Run tests to verify they fail**

Run: `./venv/bin/python -m pytest tests/test_gitops.py -q`
Expected: deployment helper tests fail.

- [ ] **Step 3: Implement deployment lookup and recording**

Use GitHub Deployments API with one dedicated Scenario C environment. Query deployment statuses and select the newest successful deployment only. Record success only after all applies succeed; record failure without advancing the successful baseline.

- [ ] **Step 4: Write runner tests**

Test first run records baseline and performs no resource writes; later run loads prior deployment commit's yaml, applies diff, and leaves successful baseline unchanged after apply failure.

- [ ] **Step 5: Implement `scripts/run_gitops.py`**

Validate current yaml before writes. If no prior successful deployment exists, record baseline and exit. Otherwise load prior yaml from Git history, call `apply_changes`, then record success. Exit nonzero on validation, API, or apply error.

- [ ] **Step 6: Add Actions workflow**

Trigger only on pushes to `feature/gitops-state`. Use serialized concurrency, checkout full Git history, install requirements, validate/run the runner, and set `GITHUB_TOKEN` permission to `deployments: write`. Read `GITHUB_APP_ID`, `GITHUB_APP_INSTALLATION_ID`, and `GITHUB_APP_PRIVATE_KEY` from Actions secrets. Write the private key to a restricted temporary file; never print it.

- [ ] **Step 7: Verify workflow and runner**

Run: `./venv/bin/python -m pytest tests/test_gitops.py -q`
Expected: PASS.

Run: `./venv/bin/python -m pytest -q`
Expected: full suite PASS.

### Task 4: Use local yaml for webhooks

**Files:**
- Modify: `src/config.py`
- Modify: `src/receiver.py`
- Test: `tests/test_config.py`
- Test: `tests/test_receiver.py`
- Modify: `vars.env.example`

**Interfaces:**
- Receiver reads and validates local `stress_template.yaml`, matching Scenario A.
- No GitHub repository, branch, or template path settings are needed.

- [ ] **Step 1: Write failing receiver tests**

Test local yaml reaching reconciliation, rereading for each event, and read/parse failure returning an error without calling reconciliation.

- [ ] **Step 2: Run tests to verify they fail**

Run: `./venv/bin/python -m pytest tests/test_receiver.py tests/test_config.py -q`
Expected: local-source and configuration tests fail.

- [ ] **Step 3: Implement local template loading**

Read and validate `stress_template.yaml` for each webhook. Propagate read and validation failures.

- [ ] **Step 4: Implement webhook integration**

After signature verification and bot filtering, load local yaml under the existing event lock. On failure, log and return an error response without reconciling.

- [ ] **Step 5: Add required configuration and verify**

Remove remote GitOps source settings from configuration and `vars.env.example`.

Run: `./venv/bin/python -m pytest tests/test_config.py tests/test_receiver.py -q`
Expected: PASS.

Run: `./venv/bin/python -m pytest -q`
Expected: full suite PASS.

### Task 5: Update operating documentation

**Files:**
- Modify: `docs/superpowers/specs/2026-10-20-scenario-c-gitops-design.md`
- Modify: `docs/superpowers/specs/scenario-c-results.md`

- [ ] **Step 1: Document stable IDs and Actions setup**

Document required Actions secret names, required GitHub App permissions/install scope, deployment environment name, baseline-only first run, webhook GitOps config, and rename behavior.

- [ ] **Step 2: Verify documentation matches implementation**

Check workflow secret references, config key names, and deployment environment against code and workflow.
