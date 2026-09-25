import re
from pathlib import Path

import yaml


def load(path: str):
    return yaml.load(Path(path).read_text(), Loader=yaml.BaseLoader)  # noqa: S506


def test_frontend_workflow_is_locked_read_only_and_complete():
    workflow = load(".github/workflows/frontend.yml")
    assert workflow["permissions"] == {"contents": "read"}
    job = workflow["jobs"]["quality"]
    assert job["defaults"]["run"]["working-directory"] == "web"
    actions = [step for step in job["steps"] if "uses" in step]
    assert all(re.fullmatch(r"[\w/-]+@[0-9a-f]{40}", step["uses"]) for step in actions)
    checkout = actions[0]
    assert checkout["with"]["persist-credentials"] == "false"
    node = actions[1]
    assert node["with"] == {
        "node-version": "24.15.0",
        "cache": "npm",
        "cache-dependency-path": "web/package-lock.json",
    }
    commands = [step["run"] for step in job["steps"] if "run" in step]
    assert commands == [
        "npm ci",
        "npm run lint",
        "npm run typecheck",
        "npm test -- --run",
        "npm run build",
    ]
    assert "permissions" not in job


def test_npm_dependabot_and_javascript_codeql_are_enabled_without_extra_permissions():
    dependabot = load(".github/dependabot.yml")
    npm = [entry for entry in dependabot["updates"] if entry["package-ecosystem"] == "npm"]
    assert npm == [
        {
            "package-ecosystem": "npm",
            "directory": "/web",
            "schedule": {"interval": "weekly"},
            "open-pull-requests-limit": "5",
        }
    ]
    security = load(".github/workflows/security.yml")
    codeql = security["jobs"]["codeql"]
    initialize = next(step for step in codeql["steps"] if "github/codeql-action/init@" in step.get("uses", ""))
    assert initialize["with"]["languages"] == "python,javascript-typescript"
    assert codeql["permissions"] == {"contents": "read", "security-events": "write"}
    frontend = security["jobs"]["frontend-dependencies"]
    assert "permissions" not in frontend
    assert frontend["steps"][-1]["run"] == "npm audit --audit-level=high"
