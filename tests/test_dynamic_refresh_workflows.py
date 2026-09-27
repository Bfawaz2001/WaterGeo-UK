from pathlib import Path

import pytest
import yaml

CRON_LIMITS = ((0, 59), (0, 23), (1, 31), (1, 12), (0, 7))


def valid_part(part: str, lower: int, upper: int) -> bool:
    base, separator, step = part.partition("/")
    if separator and (not step.isdigit() or not 1 <= int(step) <= upper):
        return False
    if base == "*":
        return True
    start, separator, end = base.partition("-")
    if not start.isdigit() or (separator and not end.isdigit()):
        return False
    first = int(start)
    last = int(end) if separator else first
    return lower <= first <= last <= upper


def assert_github_cron(value: str) -> None:
    """Check the five-field numeric syntax accepted by scheduled Actions workflows."""
    fields = value.split()
    assert len(fields) == 5, f"GitHub Actions cron must have five fields: {value!r}"
    assert all(
        field and all(valid_part(part, *limits) for part in field.split(","))
        for field, limits in zip(fields, CRON_LIMITS, strict=True)
    ), f"invalid cron syntax: {value!r}"


@pytest.mark.parametrize(
    ("name", "source", "cron", "variable", "timeout"),
    [
        (
            "thames-refresh.yml",
            "thames-discharge-status",
            "7,22,37,52 * * * *",
            "WATERGEO_THAMES_SCHEDULE_ENABLED",
            "900",
        ),
        (
            "water-quality-refresh.yml",
            "water-quality",
            "43 2 * * *",
            "WATERGEO_WATER_QUALITY_SCHEDULE_ENABLED",
            "3600",
        ),
    ],
)
def test_dynamic_refresh_workflow_is_gated_and_durable(
    name: str, source: str, cron: str, variable: str, timeout: str
) -> None:
    path = Path(".github/workflows") / name
    workflow = yaml.load(path.read_text(), Loader=yaml.BaseLoader)  # noqa: S506
    assert workflow["on"]["schedule"] == [{"cron": cron}]
    assert_github_cron(cron)
    job = workflow["jobs"]["refresh"]
    condition = " ".join(job["if"].split())
    assert "github.repository == 'Bfawaz2001/WaterGeo-UK'" in condition
    assert "github.ref == 'refs/heads/main'" in condition
    assert f"vars.{variable} == 'true'" in condition
    assert "github.event_name == 'workflow_dispatch'" in condition
    refresh = next(step for step in job["steps"] if step.get("id") == "refresh")
    assert refresh["env"]["WATERGEO_SERVICE_ENVIRONMENT"] == "production"
    assert refresh["env"]["WATERGEO_EVIDENCE_BACKEND"] == "s3"
    assert "WATERGEO_EVIDENCE_S3_SECRET_ACCESS_KEY" in refresh["env"]
    assert f"refresh_sources.py {source} --timeout-seconds {timeout}" in refresh["run"]
    assert any("--extra evidence-s3" in step.get("run", "") for step in job["steps"])


def test_every_scheduled_workflow_uses_five_field_cron() -> None:
    schedules: dict[str, list[str]] = {}
    for path in sorted(Path(".github/workflows").glob("*.yml")):
        workflow = yaml.load(path.read_text(), Loader=yaml.BaseLoader)  # noqa: S506
        entries = workflow.get("on", {}).get("schedule", [])
        schedules[path.name] = [entry["cron"] for entry in entries]
        for entry in entries:
            assert_github_cron(entry["cron"])

    assert schedules["hydrology-refresh.yml"] == ["17 * * * *"]
    assert schedules["thames-refresh.yml"] == ["7,22,37,52 * * * *"]
    assert schedules["water-quality-refresh.yml"] == ["43 2 * * *"]


@pytest.mark.parametrize("value", ["43 2 * * * *", "60 2 * * *", "43 24 * * *", "*/0 * * * *"])
def test_cron_validator_rejects_invalid_field_count_ranges_and_steps(value: str) -> None:
    with pytest.raises(AssertionError):
        assert_github_cron(value)
