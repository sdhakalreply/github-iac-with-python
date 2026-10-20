# Scenario C results

## Run 1: first bulk create (2026-10-19)

Command: `python -m src.apply stress_template.yaml` against `suman-test-scenario-c`.

```
Repositories: 5000 total, 2 created, 0 adopted, 1384 updated, 3611 unchanged, 3 failed
Team assignments: 10000 total, 1866 set, 0 removed
Properties: 6 definitions, 30000 values total, 8316 values set
API requests: 18281 total (GET 15021, PATCH 1386, POST 8, PUT 1866), 0 rate-limited, quota remaining 11061
```

Notes:
- GET 15021 is about 3 per repo (repo, teams, properties), as expected without state.
- 3 repos failed; the cause has not been looked into yet.

## Next

- Update run (edit the yaml, then apply)
- Small create
- Webhooks (revert tests)

## GitOps setup

The workflow runs on pushes to `feature/gitops-state`. Configure the
`GITHUB_ORG` Actions variable and these Actions secrets:
`GITHUB_APP_ID`, `GITHUB_APP_INSTALLATION_ID`, and
`GITHUB_APP_PRIVATE_KEY`. Install the GitHub App on the target organization
and the config repository. Grant repository administration, organization
members, and organization custom properties read/write permissions.

The workflow records its successful commit in GitHub Deployments under
`scenario-c-gitops`. Its first run records a baseline and does not change
org resources. Later runs compare against the last successful deployment.
Keep each repository's unique `id` unchanged when renaming it.

The webhook receiver reads local `stress_template.yaml`, like Scenario A.
