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
        (
            "rainfall-refresh.yml",
            "rainfall",
            "27 * * * *",
            "WATERGEO_RAINFALL_SCHEDULE_ENABLED",
            "1800",
        ),
        (
            "flood-refresh.yml",
            "flood-monitoring",
            "2,17,32,47 * * * *",
            "WATERGEO_FLOOD_SCHEDULE_ENABLED",
            "1800",
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
    assert schedules["rainfall-refresh.yml"] == ["27 * * * *"]
    assert schedules["flood-refresh.yml"] == ["2,17,32,47 * * * *"]
    assert schedules["bathing-waters-refresh.yml"] == [
        "31 3 * 5-9 2",
        "31 3 1 1-4,10-12 *",
    ]
    assert schedules["static-preview-build.yml"] == ["19 5 * * *"]


def test_bathing_refresh_is_seasonal_gated_and_durable() -> None:
    path = Path(".github/workflows/bathing-waters-refresh.yml")
    workflow = yaml.load(path.read_text(), Loader=yaml.BaseLoader)  # noqa: S506
    job = workflow["jobs"]["refresh"]
    condition = " ".join(job["if"].split())
    assert "github.repository == 'Bfawaz2001/WaterGeo-UK'" in condition
    assert "github.ref == 'refs/heads/main'" in condition
    assert "vars.WATERGEO_BATHING_WATERS_SCHEDULE_ENABLED == 'true'" in condition
    assert "github.event_name == 'workflow_dispatch'" in condition
    refresh = next(step for step in job["steps"] if step.get("id") == "refresh")
    assert refresh["env"]["WATERGEO_EVIDENCE_BACKEND"] == "s3"
    assert "refresh_sources.py bathing-waters --timeout-seconds 3600" in refresh["run"]


def test_static_preview_build_is_artifact_only_and_opt_in() -> None:
    workflow = yaml.load(
        Path(".github/workflows/static-preview-build.yml").read_text(),
        Loader=yaml.BaseLoader,  # noqa: S506
    )
    job = workflow["jobs"]["build"]
    condition = " ".join(job["if"].split())
    assert "github.repository == 'Bfawaz2001/WaterGeo-UK'" in condition
    assert "github.ref == 'refs/heads/main'" in condition
    assert "vars.WATERGEO_STATIC_PUBLICATION_ENABLED == 'true'" in condition
    assert "vars.WATERGEO_STATIC_EVIDENCE_RELEASE_ID != ''" in condition
    assert "github.event_name == 'workflow_dispatch'" in condition
    assert workflow["permissions"] == {"contents": "read"}
    text = Path(".github/workflows/static-preview-build.yml").read_text()
    assert "watergeo-static-publish" in text
    assert "actions/upload-artifact" in text
    assert "python -m watergeo.operations.public_artifact web/dist" in text
    assert "deploy" not in text.lower()
    assert "actions/setup-node@820762786026740c76f36085b0efc47a31fe5020 # v7.0.0" in text
    assert "node-version-file: .nvmrc" in text
    assert "node-version-file: web/.nvmrc" not in text
    assert "actions/upload-artifact@b7c566a772e6b6bfb58ed0dc250532a479d7789f # v6.0.0" in text
    assert "secrets.WATERGEO_STATIC_EVIDENCE_TOKEN" in text
    assert "${GH_TOKEN:?WATERGEO_STATIC_EVIDENCE_TOKEN is required}" in text
    assert 'release.get("draft") is not True' in text
    assert "WATERGEO_STATIC_EVIDENCE_RUN_ID" not in text
    assert '[[ "$EVIDENCE_RELEASE_ID" =~ ^[0-9]+$ ]]' in text
    assert '[[ "$EVIDENCE_SHA256" =~ ^[0-9a-f]{64}$ ]]' in text
    assert (
        text.index("docker compose up --build --wait db")
        < text.index("uv run --locked alembic upgrade head")
        < text.index("scripts/replay_static_sources.py")
    )
    _assert_playwright_chromium_installed_before_static_acceptance(job)
    _assert_static_build_does_not_change_unit_test_mode(job)


def test_static_pages_is_manual_main_only_and_least_privilege() -> None:
    path = Path(".github/workflows/static-pages.yml")
    workflow = yaml.load(path.read_text(), Loader=yaml.BaseLoader)  # noqa: S506
    assert workflow["on"] == {"workflow_dispatch": ""}
    assert workflow["permissions"] == {"contents": "read"}
    build = workflow["jobs"]["build"]
    assert build["permissions"] == {"contents": "read", "pages": "read"}
    condition = " ".join(build["if"].split())
    assert "github.repository == 'Bfawaz2001/WaterGeo-UK'" in condition
    assert "github.ref == 'refs/heads/main'" in condition
    assert "vars.WATERGEO_STATIC_EVIDENCE_RELEASE_ID != ''" in condition
    deploy = workflow["jobs"]["deploy"]
    assert deploy["permissions"] == {"pages": "write", "id-token": "write"}
    assert deploy["environment"]["name"] == "github-pages"
    text = path.read_text()
    assert "VITE_BASE_PATH: /WaterGeo-UK/" in text
    assert "node-version-file: .nvmrc" in text
    assert "node-version-file: web/.nvmrc" not in text
    assert "python -m watergeo.operations.public_artifact web/dist" in text
    expected_actions = {
        "actions/setup-node": ("820762786026740c76f36085b0efc47a31fe5020", "v7.0.0"),
        "actions/configure-pages": ("45bfe0192ca1faeb007ade9deae92b16b8254a0d", "v6.0.0"),
        "actions/upload-pages-artifact": (
            "fc324d3547104276b827a68afc52ff2a11cc49c9",
            "v5.0.0",
        ),
        "actions/deploy-pages": ("368f82528645a54fb793d4d04e342629a3f51346", "v5.0.1"),
    }
    for action, (commit, version) in expected_actions.items():
        assert f"{action}@{commit} # {version}" in text
    assert "secrets.WATERGEO_STATIC_EVIDENCE_TOKEN" in text
    assert "${GH_TOKEN:?WATERGEO_STATIC_EVIDENCE_TOKEN is required}" in text
    assert 'release.get("draft") is not True' in text
    assert "releases/assets/$asset_id" in text
    _assert_static_build_does_not_change_unit_test_mode(build)
    assert "WATERGEO_STATIC_EVIDENCE_RUN_ID" not in text
    assert '[[ "$EVIDENCE_RELEASE_ID" =~ ^[0-9]+$ ]]' in text
    assert '[[ "$EVIDENCE_SHA256" =~ ^[0-9a-f]{64}$ ]]' in text
    assert (
        text.index("docker compose up --build --wait db")
        < text.index("uv run --locked alembic upgrade head")
        < text.index("scripts/replay_static_sources.py")
    )
    _assert_playwright_chromium_installed_before_static_acceptance(build)
    assert "schedule:" not in text


def _assert_static_build_does_not_change_unit_test_mode(job: dict) -> None:
    assert "VITE_WATERGEO_DATA_MODE" not in job.get("env", {})
    test_step = next(step for step in job["steps"] if "npm test -- --run" in step.get("run", ""))
    assert "VITE_WATERGEO_DATA_MODE" not in test_step.get("env", {})
    build_step = next(step for step in job["steps"] if "npm run build" in step.get("run", ""))
    assert build_step["env"]["VITE_WATERGEO_DATA_MODE"] == "static"
    assert "VITE_BASEMAP_STYLE_URL" not in build_step["env"]


def _assert_playwright_chromium_installed_before_static_acceptance(job: dict) -> None:
    commands = [step.get("run", "") for step in job["steps"]]
    install_index = commands.index("npx playwright install --with-deps chromium")
    acceptance_index = next(
        index for index, command in enumerate(commands) if "npm run test:e2e:static" in command
    )
    assert install_index < acceptance_index


@pytest.mark.parametrize("value", ["43 2 * * * *", "60 2 * * *", "43 24 * * *", "*/0 * * * *"])
def test_cron_validator_rejects_invalid_field_count_ranges_and_steps(value: str) -> None:
    with pytest.raises(AssertionError):
        assert_github_cron(value)
