"""
SPIKE -- throwaway load test for the webhook receiver.

Makes a burst of drift changes (visibility, extra team, removed team, changed
team role, edited team description, wrong custom property value) on already
created repos, picked at random from the yaml, using a *user* PAT (so events aren't Bot-sent and the receiver
doesn't skip them), then polls GitHub until each change has been reverted and
reports counts and revert latency. Also summarises the org webhook's
deliveries since the burst started.

Usage:
    ./venv/bin/python scripts/drift_burst.py [COUNT] [TEMPLATE] [VARS]
        defaults: 60 stress_template.yaml vars.env
vars.env needs GITHUB_PAT (org owner; repo, admin:org, admin:org_hook).
Writes logs/drift_burst_<timestamp>.json.
"""
import json
import random
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import requests
import yaml
from dotenv import dotenv_values

POLL_INTERVAL = 10
POLL_TIMEOUT = 180
THREADS = 20
TYPES = ["visibility", "team_add", "team_remove", "team_role", "team_edit", "custom_property"]
TEAMS = {}  # team name -> yaml entry, filled in main()


def api(session, method, path, **kwargs):
    return session.request(method, f"{session.base}{path}", timeout=30, **kwargs)


def pick_repos(entries, count, rng):
    eligible = [
        name for name, entry in entries.items()
        if entry.get("teams") and any(isinstance(v, str) for v in (entry.get("properties") or {}).values())
    ]
    return [entries[name] for name in rng.sample(eligible, min(count, len(eligible)))]


def plan_change(entry, kind, rng):
    declared = entry.get("teams", [])
    if kind == "team_add":
        names = {team["name"] for team in declared}
        return {"rogue": rng.choice([f"team-{i}" for i in range(50) if f"team-{i}" not in names])}
    if kind in ("team_remove", "team_role"):
        team = rng.choice(declared)
        return {"team": team["name"], "role": team["role"]}
    if kind == "team_edit":
        team = TEAMS[rng.choice(sorted(TEAMS))]
        return {"team": team["name"], "description": team["description"]}
    if kind == "custom_property":
        # Only plain string values, so the wrong value is always valid for the property.
        strings = {k: v for k, v in entry["properties"].items() if isinstance(v, str)}
        prop = rng.choice(sorted(strings))
        return {"property": prop, "value": strings[prop]}
    return {}


def fire(session, org, entry, kind, plan):
    name = plan["team"] if kind == "team_edit" else entry["name"]
    if kind == "visibility":
        current = api(session, "GET", f"/repos/{org}/{name}").json().get("visibility")
        plan["desired"] = current
    sent_wall = time.time()
    started = time.monotonic()
    if kind == "visibility":
        target = "internal" if plan["desired"] != "internal" else "private"
        response = api(session, "PATCH", f"/repos/{org}/{name}", json={"visibility": target})
    elif kind == "team_add":
        response = api(
            session, "PUT", f"/orgs/{org}/teams/{plan['rogue']}/repos/{org}/{name}",
            json={"permission": "admin"},
        )
    elif kind == "custom_property":
        response = api(
            session, "PATCH", f"/repos/{org}/{name}/properties/values",
            json={"properties": [{"property_name": plan["property"], "value": "DRIFT"}]},
        )
    elif kind == "team_remove":
        response = api(session, "DELETE", f"/orgs/{org}/teams/{plan['team']}/repos/{org}/{name}")
    elif kind == "team_edit":
        response = api(
            session, "PATCH", f"/orgs/{org}/teams/{plan['team']}", json={"description": "DRIFT"}
        )
    else:
        wrong = "triage" if plan["role"] != "triage" else "pull"
        response = api(
            session, "PUT", f"/orgs/{org}/teams/{plan['team']}/repos/{org}/{name}",
            json={"permission": wrong},
        )
    return {
        "repo": name,
        "kind": kind,
        "plan": plan,
        "sent_at": sent_wall,
        "sent_mono": started,
        "status": response.status_code,
        "ok": 200 <= response.status_code < 300,
        "error": None if response.ok else response.text[:200],
    }


def is_reverted(session, org, change):
    name, kind, plan = change["repo"], change["kind"], change["plan"]
    if kind == "visibility":
        return api(session, "GET", f"/repos/{org}/{name}").json().get("visibility") == plan["desired"]
    if kind == "team_edit":
        team = api(session, "GET", f"/orgs/{org}/teams/{plan['team']}").json()
        return team.get("description") == plan["description"]
    if kind == "custom_property":
        values = api(session, "GET", f"/repos/{org}/{name}/properties/values").json()
        live = {item["property_name"]: item["value"] for item in values}
        return live.get(plan["property"]) == plan["value"]
    teams = {
        team["slug"]: team["permission"]
        for team in api(session, "GET", f"/repos/{org}/{name}/teams").json()
    }
    if kind == "team_add":
        return plan["rogue"] not in teams
    return teams.get(plan["team"]) == plan["role"]


def poll_reverts(session, org, changes):
    pending = [c for c in changes if c["ok"]]
    deadline = time.monotonic() + POLL_TIMEOUT
    with ThreadPoolExecutor(max_workers=5) as pool:
        while pending and time.monotonic() < deadline:
            time.sleep(POLL_INTERVAL)
            results = list(pool.map(lambda c: is_reverted(session, org, c), pending))
            now = time.monotonic()
            still = []
            for change, reverted in zip(pending, results):
                if reverted:
                    change["revert_seconds"] = round(now - change["sent_mono"], 1)
                else:
                    still.append(change)
            pending = still
            print(f"  polling: {len(pending)} still unreverted")


def delivery_summary(session, org, since):
    hooks = api(session, "GET", f"/orgs/{org}/hooks").json()
    if not isinstance(hooks, list) or not hooks:
        return {"error": "no org webhook found or no access"}
    hook_id = hooks[0]["id"]
    seen = []
    cursor = None
    for _ in range(5):
        params = {"per_page": 100, **({"cursor": cursor} if cursor else {})}
        response = api(session, "GET", f"/orgs/{org}/hooks/{hook_id}/deliveries", params=params)
        page = response.json()
        if not isinstance(page, list) or not page:
            break
        seen.extend(page)
        link = response.links.get("next", {}).get("url", "")
        cursor = link.split("cursor=")[-1].split("&")[0] if "cursor=" in link else None
        if not cursor:
            break
    recent = [
        d for d in seen
        if datetime.fromisoformat(d["delivered_at"].replace("Z", "+00:00")).timestamp() >= since
    ]
    codes = {}
    for delivery in recent:
        codes[str(delivery["status_code"])] = codes.get(str(delivery["status_code"]), 0) + 1
    durations = [d["duration"] for d in recent if d.get("duration") is not None]
    return {
        "hook_id": hook_id,
        "deliveries": len(recent),
        "status_codes": codes,
        "avg_duration_s": round(statistics.mean(durations), 2) if durations else None,
        "max_duration_s": round(max(durations), 2) if durations else None,
    }


def percentile(values, pct):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(len(ordered) * pct))]


def main():
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    template_path = sys.argv[2] if len(sys.argv) > 2 else "stress_template.yaml"
    vars_path = sys.argv[3] if len(sys.argv) > 3 else "vars.env"

    env = dotenv_values(vars_path)
    if not env.get("GITHUB_PAT"):
        sys.exit("GITHUB_PAT missing in " + vars_path)
    org = env["GITHUB_ORG"]
    session = requests.Session()
    session.base = env["GITHUB_API_BASE_URL"]
    session.headers.update({
        "Authorization": f"Bearer {env['GITHUB_PAT']}",
        "Accept": "application/vnd.github+json",
    })

    with open(template_path) as f:
        template = yaml.safe_load(f)
    entries = {repo["name"]: repo for repo in template["repositories"]}
    TEAMS.update({team["name"]: team for team in template["teams"]})
    rng = random.Random()
    repos = pick_repos(entries, count, rng)
    jobs = [(entry, TYPES[i % len(TYPES)]) for i, entry in enumerate(repos)]
    jobs = [(entry, kind, plan_change(entry, kind, rng)) for entry, kind in jobs]

    print(f"Firing {len(jobs)} changes with {THREADS} threads ...")
    burst_start = time.time()
    with ThreadPoolExecutor(max_workers=THREADS) as pool:
        changes = list(pool.map(lambda job: fire(session, org, *job), jobs))
    send_seconds = round(time.time() - burst_start, 1)
    print(f"Sent in {send_seconds}s; polling for reverts (max {POLL_TIMEOUT}s) ...")

    poll_reverts(session, org, changes)
    deliveries = delivery_summary(session, org, burst_start)

    summary = {"requested": len(changes), "send_seconds": send_seconds, "by_kind": {}}
    for kind in TYPES:
        group = [c for c in changes if c["kind"] == kind]
        latencies = [c["revert_seconds"] for c in group if "revert_seconds" in c]
        summary["by_kind"][kind] = {
            "sent": len(group),
            "send_failed": sum(1 for c in group if not c["ok"]),
            "reverted": len(latencies),
            "never_reverted": sum(1 for c in group if c["ok"] and "revert_seconds" not in c),
            "revert_p50_s": percentile(latencies, 0.5) if latencies else None,
            "revert_p95_s": percentile(latencies, 0.95) if latencies else None,
            "revert_max_s": max(latencies) if latencies else None,
        }
    summary["deliveries"] = deliveries

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = f"logs/drift_burst_{stamp}.json"
    with open(out_path, "w") as f:
        json.dump({"summary": summary, "changes": changes}, f, indent=2, default=str)
    print(json.dumps(summary, indent=2))
    print(f"Details: {out_path}")


if __name__ == "__main__":
    main()
