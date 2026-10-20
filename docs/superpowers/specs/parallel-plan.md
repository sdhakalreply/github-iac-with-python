# Parallel plan for scenarios A, B and C (2026-10-15)

Each scenario gets its own org, its own branch in its own worktree, and its own chat window. All of them start from the shared brief, `docs/superpowers/specs/current-state-and-memory.md`.

## What stays the same across scenarios

- The same yaml template and the same repo count, so results can be compared.
- The same three tests: create from yaml, update from yaml, change directly on GitHub.
- Common code (yaml parsing, GitHub helpers, bulk create) lives on `main`. Branches add only what is specific to their scenario.

## Steps (environment, everything except the GitHub part)

1. **Commit the shared brief to `main`.** Commit `current-state-and-memory.md` (and this plan) so every branch starts with the same ground understanding. Done by you, or by me when you ask.
2. **Create the three branches and worktrees**, from the repo root:

   ```
   git worktree add ../octokeeper-a -b scenario-a main
   git worktree add ../octokeeper-b -b scenario-b main
   git worktree add ../octokeeper-c -b scenario-c main
   ```

3. **Create one virtual environment per worktree:**

   ```
   cd ../octokeeper-a && python3 -m venv venv && ./venv/bin/pip install -r requirements.txt
   ```

   Repeat in `octokeeper-b` and `octokeeper-c`. Scenario B also needs Terraform installed once on the machine.
4. **Create one `vars.env` per worktree**, copied from `vars.env.example`. Each holds its own org name, GitHub App ID, private key path and webhook secret. These files are never committed.
5. **Give each scenario its own receiver port and tunnel**, for example 5001, 5002 and 5003, each with its own tunnel URL. The org webhook in each org points to its own tunnel.
6. **Add a notes file in each worktree** (for example `NOTES.md`) for that scenario's decisions, so the chat windows do not mix their findings.
7. **Open one chat window per worktree**, and start each by asking the agent to read `docs/superpowers/specs/current-state-and-memory.md`.

## What you do on GitHub

- Create the three orgs.
- Create and install a GitHub App in each, with the permissions it needs.
- Define the 6 custom properties in each org.
- Add the org webhook in each org, pointing at that scenario's tunnel URL and secret.

## Rules for working in parallel

- Never share a `vars.env`, port, tunnel or org between scenarios.
- Changes to common code are made on `main` and then merged into the branches.
- Clean up scenario repos in their own org only.
