"""
Generate stress_template.yaml: N repos spread over a fixed set of teams.

Usage:
    ./venv/bin/python scripts/gen_stress_template.py [REPO_COUNT] [TEAM_COUNT] [OUTPUT]
        defaults: 5000 20 stress_template.yaml

Each repo gets two teams (different roles) and the 6 custom properties.
No per-repo hooks: the org webhook delivers the events.
"""
import random
import sys

import yaml

ROLES = ["pull", "triage", "push", "maintain"]
CATEGORIES = ["service", "infra", "library", "tool"]
PROPERTY_DEFINITIONS = [
    {"name": "service-offering-number", "type": "string"},
    {"name": "adoit-service-id", "type": "string"},
    {"name": "repo-category", "type": "multi_select", "allowed_values": CATEGORIES},
    {"name": "euc-flag", "type": "string"},
    {"name": "deployment-branches", "type": "string"},
    {"name": "jira-project-key", "type": "string"},
]


def build(repo_count, team_count):
    rng = random.Random(42)  # fixed seed so the file is reproducible
    teams = [
        {"name": f"stress-team-{i:03d}", "description": f"stress team {i:03d}"}
        for i in range(1, team_count + 1)
    ]
    repos = []
    for i in range(1, repo_count + 1):
        first, second = rng.sample(teams, 2)
        repos.append({
            "name": f"stress-repo-{i:05d}",
            "teams": [
                {"name": first["name"], "role": "push"},
                {"name": second["name"], "role": rng.choice(ROLES)},
            ],
            "properties": {
                "service-offering-number": f"SVC-{i:05d}",
                "adoit-service-id": f"ADOIT-{i:05d}",
                "repo-category": rng.sample(CATEGORIES, 2),
                "euc-flag": rng.choice(["true", "false"]),
                "deployment-branches": "main",
                "jira-project-key": f"JIRA-{i % 100:02d}",
            },
        })
    return {"property_definitions": PROPERTY_DEFINITIONS, "teams": teams, "repositories": repos}


def main():
    repo_count = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    team_count = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    output = sys.argv[3] if len(sys.argv) > 3 else "stress_template.yaml"
    with open(output, "w") as f:
        yaml.safe_dump(build(repo_count, team_count), f, sort_keys=False)
    print(f"Wrote {repo_count} repos and {team_count} teams to {output}")


if __name__ == "__main__":
    main()
