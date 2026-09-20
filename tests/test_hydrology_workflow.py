"""Semantic workflow checks plus execution of its actual shell with a stub CLI."""

import ast
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

PATH = Path(".github/workflows/hydrology-refresh.yml")


@pytest.fixture
def workflow():
    # BaseLoader preserves GitHub's `on` key rather than YAML 1.1 boolean coercion.
    return yaml.load(PATH.read_text(), Loader=yaml.BaseLoader)  # noqa: S506 -- strings-only loader


def test_triggers_and_execution_boundary(workflow):
    assert set(workflow["on"]) == {"workflow_dispatch", "schedule"}
    assert workflow["on"]["schedule"] == [{"cron": "17 * * * *"}]
    assert not workflow["on"]["workflow_dispatch"]
    job = workflow["jobs"]["refresh"]
    assert "github.repository == 'Bfawaz2001/WaterGeo-UK'" in job["if"]
    assert "github.ref == 'refs/heads/main'" in job["if"]
    assert "vars.WATERGEO_HYDROLOGY_SCHEDULE_ENABLED == 'true'" in job["if"]
    assert job["runs-on"] == "ubuntu-24.04"
    assert job["environment"] == "hydrology-refresh"
    assert 30 < int(job["timeout-minutes"]) <= 60
    assert workflow["concurrency"] == {
        "group": "hydrology-latest-refresh",
        "cancel-in-progress": "false",
    }


@pytest.mark.parametrize("repository", ["Bfawaz2001/WaterGeo-UK", "fork/WaterGeo-UK"])
@pytest.mark.parametrize("ref", ["refs/heads/main", "refs/heads/feature"])
@pytest.mark.parametrize("event", ["workflow_dispatch", "schedule", "push"])
@pytest.mark.parametrize("enabled", ["true", "false", ""])
def test_job_condition_truth_table(workflow, repository, ref, event, enabled):
    expression = " ".join(workflow["jobs"]["refresh"]["if"].split())
    for name, value in {
        "github.repository": repository,
        "github.ref": ref,
        "github.event_name": event,
        "vars.WATERGEO_HYDROLOGY_SCHEDULE_ENABLED": enabled,
    }.items():
        expression = expression.replace(name, repr(value))
    expression = expression.replace("&&", "and").replace("||", "or")

    def evaluate(node):
        # Interpret only this condition's boolean/equality grammar, never execute code.
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.BoolOp):
            values = [evaluate(value) for value in node.values]
            assert isinstance(node.op, (ast.And, ast.Or))
            return all(values) if isinstance(node.op, ast.And) else any(values)
        assert isinstance(node, ast.Compare) and len(node.ops) == 1
        assert isinstance(node.ops[0], ast.Eq)
        return evaluate(node.left) == evaluate(node.comparators[0])

    actual = evaluate(ast.parse(expression, mode="eval").body)
    expected = (
        repository == "Bfawaz2001/WaterGeo-UK"
        and ref == "refs/heads/main"
        and (event == "workflow_dispatch" or (event == "schedule" and enabled == "true"))
    )
    assert actual == expected


def test_permissions_pins_and_no_shell_expressions(workflow):
    assert workflow["permissions"] == {"contents": "read"}
    for job in workflow["jobs"].values():
        assert "permissions" not in job
        for step in job["steps"]:
            assert "continue-on-error" not in step
            if "uses" in step:
                assert re.fullmatch(r"[\w/-]+@[0-9a-f]{40}", step["uses"])
            if "run" in step:
                assert "${{" not in step["run"]
            for key, value in step.get("env", {}).items():
                if key in {
                    "WATERGEO_DB_HOST",
                    "WATERGEO_DB_PORT",
                    "WATERGEO_DB_NAME",
                    "WATERGEO_INGESTION_USER",
                    "WATERGEO_INGESTION_PASSWORD",
                    "WATERGEO_DB_CA_PEM",
                }:
                    assert value == "${{ secrets." + key + " }}"
    checkout = workflow["jobs"]["refresh"]["steps"][0]
    assert checkout["with"]["persist-credentials"] == "false"


def test_only_hydrology_cli_and_verified_tls(workflow):
    steps = workflow["jobs"]["refresh"]["steps"]
    refresh = next(step for step in steps if step.get("id") == "refresh")
    commands = re.findall(
        r"uv run --locked python scripts/refresh_sources.py ([\w-]+)", refresh["run"]
    )
    assert commands == ["hydrology"]
    assert "--timeout-seconds 1800" in refresh["run"]
    assert refresh["env"]["WATERGEO_DB_SSLMODE"] == "verify-full"
    assert "WATERGEO_DB_CA_PEM" in refresh["env"]
    assert not re.search(
        r"refresh_sources.py (?:ofwat|catchments|hydrology-history)", PATH.read_text()
    )
    assert "printenv" not in PATH.read_text()
    assert "POSTGRES_PASSWORD" not in PATH.read_text()


def test_artifacts_are_explicit_and_bounded(workflow):
    steps = workflow["jobs"]["refresh"]["steps"]
    uploads = [
        step for step in steps if step.get("uses", "").startswith("actions/upload-artifact@")
    ]
    assert len(uploads) == 1
    upload = uploads[0]
    assert upload["if"] == "always()"
    assert upload["with"]["path"] == "${{ runner.temp }}/hydrology-logs/refresh.jsonl"
    assert upload["with"]["include-hidden-files"] == "false"
    assert upload["with"]["if-no-files-found"] == "error"
    assert int(upload["with"]["retention-days"]) == 14
    assert steps[-1]["if"] == "always()"


@pytest.mark.parametrize(
    "code,scenario", [(n, "normal") for n in range(6)] + [(2, "missing"), (0, "tee_failure")]
)
def test_actual_shell_preserves_cli_exit_and_only_captures_operational_stdout(
    workflow, tmp_path, code, scenario
):
    scripts = tmp_path / "bin"
    scripts.mkdir()
    uv = scripts / "uv"
    uv.write_text(
        "#!/bin/sh\n"
        'expected="run --locked python scripts/refresh_sources.py '
        'hydrology --timeout-seconds 1800"\n'
        'test "$*" = "$expected" || exit 99\n'
        'printf \'%s\\n\' \'{"event":"refresh_complete","source":"hydrology"}\'\n'
        'echo "private stderr diagnostic" >&2\n'
        'exit "$FAKE_CODE"\n'
    )
    uv.chmod(0o700)
    env = {
        **os.environ,
        "PATH": f"{scripts}:{Path(sys.executable).parent}:{os.environ['PATH']}",
        "RUNNER_TEMP": str(tmp_path),
        "GITHUB_OUTPUT": str(tmp_path / "output"),
        "GITHUB_STEP_SUMMARY": str(tmp_path / "summary"),
        "GITHUB_RUN_ID": "123",
        "GITHUB_RUN_ATTEMPT": "1",
        "FAKE_CODE": str(code),
        "WATERGEO_DB_HOST": "$(touch unexpected-file)",
        "WATERGEO_DB_PORT": "5432",
        "WATERGEO_DB_NAME": "synthetic",
        "WATERGEO_INGESTION_USER": "watergeo_ingest",
        "WATERGEO_INGESTION_PASSWORD": "synthetic-password",
        "WATERGEO_DB_CA_PEM": "synthetic CA",
        "WATERGEO_DB_SSLROOTCERT": str(tmp_path / "ca.pem"),
    }
    steps = workflow["jobs"]["refresh"]["steps"]
    if scenario == "missing":
        del env["WATERGEO_INGESTION_PASSWORD"]
    if scenario == "tee_failure":
        tee = scripts / "tee"
        tee.write_text("#!/bin/sh\ncat >/dev/null\nexit 1\n")
        tee.chmod(0o700)
    initialize = next(
        step["run"] for step in steps if step.get("name") == "Initialize operational log"
    )
    refresh = next(step["run"] for step in steps if step.get("id") == "refresh")
    script = tmp_path / "run.sh"
    script.write_text(initialize + "\n" + refresh)
    result = subprocess.run(  # noqa: S603 -- execute repository workflow with synthetic environment
        ["/bin/bash", "--noprofile", "--norc", "-eo", "pipefail", str(script)],
        env=env,
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == (1 if scenario == "tee_failure" else code)
    assert (tmp_path / "output").read_text() == f"exit_code={code}\n"
    logs = (tmp_path / "hydrology-logs/refresh.jsonl").read_text()
    assert len([json.loads(line) for line in logs.splitlines()]) == (
        1 if scenario == "tee_failure" else 2
    )
    assert "private" not in logs + result.stdout + result.stderr
    assert "synthetic-password" not in logs + result.stdout + result.stderr
    assert not (tmp_path / "unexpected-file").exists()
    succeeded = code == 0 and scenario == "normal"
    env.update(REFRESH_EXIT_CODE=str(code), REFRESH_OUTCOME="success" if succeeded else "failure")
    script.write_text(steps[-1]["run"])
    result = subprocess.run(  # noqa: S603 -- trusted summary script
        ["/bin/bash", str(script)], env=env, capture_output=True, text=True, timeout=10
    )
    assert result.returncode == 0
    summary = (tmp_path / "summary").read_text()
    assert f"Exit code: {code}" in summary
    assert f"Refresh succeeded: {'yes' if succeeded else 'no'}" in summary
    assert "hydrology-refresh-123-1" in summary
