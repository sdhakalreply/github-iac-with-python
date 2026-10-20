# Scenario C GitOps Design

## Goal

Use Git as Scenario C's desired-state source. GitHub Actions applies only
template changes on pushes to `feature/gitops-state`. The webhook receiver
restores drift using local `stress_template.yaml`, like Scenario A.

## Decisions

- `stress_template.yaml` is the only desired-state file.
- Each repository has a required, unique, immutable `id`; the existing 5,000
  repositories receive their current name as the initial ID.
- Pushes to `feature/gitops-state` trigger GitHub Actions.
- Actions validates the template and compares it with the last successfully
  applied GitHub Deployment commit.
- Actions applies only changed teams and repositories.
- The first run records the current commit as the baseline. It makes no changes
  to GitHub resources.
- A failed apply does not advance the successful deployment marker. A later
  push compares against the last successful commit and retries unapplied
  changes.
- Removed repository and team entries are deleted from GitHub.
- Removed repository property values are cleared. Org-wide property
  definitions remain.
- Actions uses the existing GitHub App credentials stored as Actions secrets
  to edit org resources.
- The `GITHUB_TOKEN` writes deployment records only. No marker branch or file
  is used.
- For each authenticated webhook, the receiver reads and validates local
  `stress_template.yaml` before reconciling.

## GitHub Actions flow

1. Trigger on pushes to `feature/gitops-state`.
2. Serialize workflow runs so an older run cannot apply after a newer run.
3. Check out the pushed commit and validate `stress_template.yaml`.
4. Find the latest successful GitHub Deployment for the dedicated Scenario C
   environment.
5. If no successful deployment exists, create a successful baseline deployment
   for the pushed commit and stop without changing org resources.
6. Otherwise, load the template at the last successful deployment commit and
   diff it against the pushed template by team name and repository ID.
7. Apply additions and changed entries. Delete removed repos and teams.
   Clear removed property values; retain property definitions.
8. Mark the pushed commit as successfully deployed only after all changes
   succeed. Any apply failure fails the workflow and leaves the prior marker
   unchanged.
9. Write a GitHub Actions job summary with changed resource counts and names,
   plus total GitHub API calls.

## Diff and apply behavior

- Team changes include creation, description updates, and deletion.
- Repository changes include creation, team assignment changes, and property
  value changes.
- Added or changed property definitions are applied; removed definitions stay
  in the organization.
- Repositories are matched by immutable `id`. A changed `name` uses GitHub's
  rename operation to preserve the existing repository.
- Unchanged entries do not call GitHub APIs.
- First run does not perform a full reconcile. The existing org is assumed to
  match the baseline template; webhooks continue to handle later drift.
- All removals are limited to entries present in the prior successful template
  and absent from the new template.

## Webhook flow

1. Verify the webhook signature.
2. Ignore self-triggered bot events as today.
3. Read and validate local `stress_template.yaml`.
4. Reconcile only the event's resource.
5. On read or parse failure, log an error and do not reconcile.

## Credentials and permissions

- Install the GitHub App on the target organization. Grant repository
  administration read/write, organization members read/write, and
  organization custom properties read/write.
- Add these GitHub Actions secrets: `APP_ID`, `APP_INSTALLATION_ID`, and
  `APP_PRIVATE_KEY`.
- Add the Actions variable `TARGET_ORG` with the target organization name.
- The workflow grants `GITHUB_TOKEN` `contents: read` and
  `deployments: write`. The App installation token performs org-resource
  changes.
- Deployment history uses the GitHub Deployment environment name
  `scenario-c-gitops`. The first successful run records a baseline only and
  makes no org-resource changes.
- Repository `id` values are required and unique. Keep an existing ID when
  renaming its repository; the ID links the new name to the existing GitHub
  repository.

## Failure handling

- Validate before any GitHub write.
- If any changed resource operation fails, fail the workflow and do not update
  the successful deployment marker.
- The next workflow run retries all changes since the last successful commit.
- Webhook template read failures return an error response and do not reconcile.
- Deployment lookup or record failures fail the workflow.
- Successful runs write a GitHub Actions job summary with their changes and
  API-call total.

## Success criteria

- A push that changes one repo does not read or write all 5,000 repos.
- A push with no template changes makes no org API writes.
- Failed partial applies are retried from the last successful commit.
- Removed resources are deleted only when they existed in the previous
  successful template.
- First workflow run creates a baseline without changing GitHub resources.
- Webhooks always reconcile against the deployed local template.
- Existing receiver result strings, logs, and API call metrics remain
  consistent where applicable.

## Out of scope

- Polling GitHub for template changes.
- Full drift scans during Actions runs.
- Changes to Scenario A.
- Docker.
- Changes to the `drift_burst.py` load test.
