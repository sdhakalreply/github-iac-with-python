# What I remember (2026-10-15)

Everything below is in my memory right now. In **Keep?**, type **Y** (keep), **N** (remove from memory) or **C** (change, with a note).

## 1. Project

| # | Item | Keep? |
|---|---|---|
| 1.1 | The project is called Octokeeper: a GitHub (GHEC) reconciliation automation | | y
| 1.2 | The yaml file is the desired state. Only relevant values go in it, like Terraform or Helm | | y
| 1.3 | A webhook detects a change made directly on GitHub, and the app reverts it to match the yaml | | y
| 1.4 | Everything defined in the yaml is reverted, including custom properties | | y
| 1.5 | Target: 5K repos at most. New resources will be created for the tests | | y
| 1.6 | Reconciliation is the goal. Self-healing and disaster recovery are by-products | | y
| 1.7 | "State file" is the term for the JSON source of truth | | y

## 2. Scenarios - y

| # | Item | Keep? |
|---|---|---|
| 2.1 | Scenario A: no state. On a webhook, GET the resource from GitHub, compare with the yaml, revert | |
| 2.2 | Scenario B: state with Terraform and the GitHub provider. Terraform keeps its own state. HCL is probable | |
| 2.3 | Scenario C: state in a flat JSON file | |
| 2.4 | Tests for each: create from yaml, update from yaml, change directly on GitHub | |
| 2.5 | Performance and response are measured. Metrics are still to be defined | |
| 2.6 | The three scenarios should be developed in parallel, connected but without interfering | |

## 3. GitHub facts

| # | Item | Keep? |
|---|---|---|
| 3.1 | A GitHub App on GHEC: 15,000 requests/hour | |
| 3.2 | About 80 content-generating requests per minute and 500 per hour | |
| 3.3 | Up to 100 concurrent requests | |
| 3.4 | A per-repo read costs about 3 GETs. Listing 5K repos takes about 50 requests | |
| 3.5 | GitHub fires webhooks for the app's own API calls. They are skipped using `sender.type == "Bot"` | |
| 3.6 | Repo events need an org webhook. You will create and provide a new one | |
| 3.7 | The org needs 6 custom properties defined, or repo creation fails with `422 Unexpected property` | |
| 3.8 | `GET /repos/{org}/{repo}/teams` returns each team's slug and permission | |
| 3.9 | `team` events that include a repository are repo-to-team changes. Without one, they are team changes | |
| 3.10 | Terraform's plan/apply is not event-driven, and its state is not queryable | | not relevant

## 4. Facts about a flat JSON state file

| # | Item | Keep? |
|---|---|---|
| 4.1 | Synthetic test at 5K repos: 10.6 MB, about 296 ms per update, about 12,200 updates/hour | |
| 4.2 | A single file has a single writer, no querying, and durability left to our own code | |

## 5. Code knowledge (on other branches or not in `main`)

| # | Item | Keep? |
|---|---|---|
| 5.1 | `feature/cosmos-state` holds the Cosmos state store and webhook receiver work | | y
| 5.2 | The receiver reverted visibility, repo-to-team roles and team description in a live test | | not relevant, clean up
| 5.3 | The property revert never worked in a live test, and the cause is unknown | | not relevant, clean up
| 5.4 | Bulk create with parallel workers and throttling was built, at about 40 repos per minute | | y
| 5.5 | Deleting a team was never reverted. A design existed: recreate it and re-attach it | | y
| 5.6 | `main` now has a Dockerfile, a docker-compose file, `template.yaml`, `todo.md`, `thisneedstobethere` and `scripts/` untracked | | y

## 6. Held for later

| # | Item | Keep? |
|---|---|---|
| 6.1 | Daily sweep comparing GitHub with the yaml. Probably not coming back | | y
| 6.2 | GIAM and Entra integration: team `group` and `owners` aren't GitHub objects. Out of scope for now | | y
| 6.3 | Five open questions that you told me to ask later, not today | | y

## 7. How we work

| # | Item | Keep? |
|---|---|---|
| 7.1 | Step by step. No actions and no questions until you ask | | y
| 7.2 | Ask before editing or deleting files, and show the wording first | | y
| 7.3 | Never commit unless asked | | y
| 7.4 | Chat replies are terse (caveman style). Documents are normal prose and short | |y
| 7.5 | Use real files for output. Use the create and edit tools only | |y
| 7.6 | Never show secrets (`vars.env`, `private-key.pem`, tokens) | |y
| 7.7 | Don't delete your files without asking, even if they look irrelevant | |y
