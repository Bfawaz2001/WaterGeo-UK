from pathlib import Path

import pytest
import yaml


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
            "43 2 * * * *",
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
