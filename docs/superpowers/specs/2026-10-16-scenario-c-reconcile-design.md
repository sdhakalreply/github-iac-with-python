# Scenario C: Reconcile by GET-compare, no state (Design Spec)

Date: 2026-10-16, updated 2026-10-19. Extends `2026-10-05-python-repo-create-design.md`.

## Purpose

`stress_template.yaml` is the desired state. The app keeps no state of its own. The yaml is the only source of truth.

- **Apply** (`python -m src.apply`): for each team and repo in the yaml, GET the live resource, compare, then create it or fix the difference.
- **Webhook** (`python -m src.receiver`): when someone changes a resource on GitHub, GET the live resource, compare with the yaml, and revert the difference.

Scenario C is identical to scenario A (self-managed state) in modules, webhook events, result strings, log format and metrics. The only difference is state: A compares with `state.json`, C compares with GitHub through GET.

This directory has its own org, `vars.env`, port 5003 and tunnel. Nothing is shared with the other copies.

## Scope

Reverted fields:

| Resource | Field | Source in yaml |
|---|---|---|
| Repository | visibility | `repositories[].visibility` (default `private`) |
| Repository | deleted: recreate with teams and properties | `repositories[]` |
| Repository | renamed: rename back | `repositories[].name` |
| Repository | team roles (add, change, remove) | `repositories[].teams` |
| Repository | custom properties | `repositories[].properties` |
| Team | description | `teams[].description` |
| Team | deleted: recreate and re-attach to its repos | `teams` + `repositories[].teams` |

Out of scope: hooks, GIAM/Entra groups, daily sweep, Docker, Cosmos DB, SQLite, state files.

Only resources named in the yaml are touched. Other repos and teams in the org are ignored. The app never lists org resources, so it cannot report what is "not in yaml".

## Modules (same names as scenario A)

- `src/receiver.py`: Flask app, port 5003. `create_app(config, template_path, token_provider)`.
  - `POST /webhook` checks `X-Hub-Signature-256` (`verify_signature`). A bad signature returns 401.
  - `ping` returns 200. Events from the app's own bot are skipped (`webhook_filters.is_self_triggered`).
  - One event at a time (lock), as in A, so `api_calls` per event is exact.
  - Re-parses the yaml only when its mtime changes, so yaml edits apply without restart.
  - Always returns 200 after the signature check. Errors are logged.
  - Log line: `Webhook <event>/<action> for '<resource>': <result> in <ms> ms, api_calls=<n>`.
- `src/reconcile.py`: `build_index(parsed)`, `reconcile_event(event, payload, template, ctx)`, `describe(payload)`.
  - Results: `reverted`, `no_change`, `unknown_resource`, `failed`. Never raises.
  - Handled events (the same three as A): `repository`, `team`, `custom_property_values`. Subscribe the org webhook to these.
  - `repository`: `deleted` recreates the repo. `renamed` renames it back; the old name comes from `changes.repository.name.from` in the payload. Every other action GETs the repo and compares visibility.
  - `team` with a repository: GET repo teams, fix roles, add missing, remove extra. `team` without a repository: `deleted` recreates the team and re-attaches it; any other action GETs the team and compares the description.
  - `custom_property_values`: GET repo properties, PATCH differences. Properties that the yaml does not define are ignored.
- `src/apply.py`: `apply_template(template_path, vars_path)`, `format_summary`. Accepts only `stress_template.yaml`, validated by `src/validator.py`.
- `src/github_http.py`: all GitHub calls go through it. Retries rate-limited responses and counts API calls. Same file as A.
- `src/github_drift.py`, `github_repos.py`, `github_teams.py`, `github_auth.py`, `webhook_filters.py`, `validator.py`, `yaml_parser.py`: same as A.

## Metrics (same shape as A)

`apply_template` returns `teams`, `repositories`, `team_assignments`, `properties`, `api`, `seconds`, and `not_in_yaml`.

- `repositories.adopted` is always 0 (no state to adopt into). `unchanged` means GET showed no difference.
- `not_in_yaml` is `None`. The summary line says `Not in yaml: not tracked (no state)`.
- `api` counts total requests, by method, by status, rate-limited, and quota remaining.

Expected difference from A: A skips unchanged repos without any GET. C needs about 3 GET calls per repo on every apply (repo, teams, properties). The `api` numbers show this.

## Data flow (webhook)

1. GitHub sends the org webhook to the tunnel, then to `localhost:5003`.
2. Receiver checks signature and sender, then loads the yaml index.
3. `reconcile_event` finds the yaml entry for the repo or team in the payload. No entry returns `unknown_resource`.
4. The handler GETs the live resource, compares with the yaml, and fixes differences.
5. Receiver logs one line with result, latency and API calls.

## Config

Same `vars.env` keys as scenario A. The port is the constant `PORT = 5003` in `receiver.py`.

## Testing (TDD)

- `pytest`, no real network. Reconcile and apply tests replace the GitHub helper functions, as in A.
- Receiver tests use signed payloads. Cases: valid and bad signature, bot sender, ping, yaml reload, concurrency, log line.
- Live tests, by you, in your org: apply with no change (expect no writes), update from yaml, change directly on GitHub. Use the plan in scenario A's `scenario-a-test-plan.md`.

## Dependencies

`Flask` in `requirements.txt`.

## Open items

- Org webhook, GitHub App, the 6 org custom properties and the tunnel are created by you.
- Properties revert did not work in an earlier live test on another copy. Cause unknown. `custom_property_values` is now handled as its own event; check this first.
- `scripts/drift_burst.py` still reads `logs/parallel_run_done.txt`, which does not exist. Change it to sample repos from the yaml.
- First `apply` sets every repo to the yaml visibility (default `private`). Check that this is what you want before running it.
