import re
from pathlib import Path

import yaml

PATH = Path(".github/workflows/container-image.yml")


def load_workflow():
    return yaml.load(PATH.read_text(), Loader=yaml.BaseLoader)  # noqa: S506


def test_container_workflow_has_bounded_release_triggers_and_permissions():
    workflow = load_workflow()
    assert set(workflow["on"]) == {"push", "pull_request", "workflow_dispatch"}
    assert workflow["on"]["push"] == {"branches": ["main"], "tags": ["v*"]}
    assert workflow["permissions"] == {"contents": "read"}
    assert "permissions" not in workflow["jobs"]["build"]
    assert workflow["jobs"]["publish"]["permissions"] == {
        "contents": "read",
        "packages": "write",
    }
    condition = " ".join(workflow["jobs"]["publish"]["if"].split())
    assert "github.repository == 'Bfawaz2001/WaterGeo-UK'" in condition
    assert "github.ref == 'refs/heads/main'" in condition
    assert "github.event_name == 'workflow_dispatch'" in condition
    assert "refs/tags/v" in condition


def test_container_workflow_pins_actions_and_checkout_credentials():
    workflow = load_workflow()
    for job in workflow["jobs"].values():
        for step in job["steps"]:
            if "uses" in step:
                assert re.fullmatch(r"[\w/-]+@[0-9a-f]{40}", step["uses"])
            if step.get("uses", "").startswith("actions/checkout@"):
                assert step["with"]["persist-credentials"] == "false"


def test_pull_request_build_cannot_publish_or_receive_credentials():
    workflow = load_workflow()
    build = workflow["jobs"]["build"]
    assert all("login-action" not in step.get("uses", "") for step in build["steps"])
    build_step = build["steps"][-1]
    assert build_step["with"]["push"] == "false"
    assert "secrets." not in str(build)


def test_published_image_is_multi_architecture_traceable_and_attested():
    workflow = load_workflow()
    publish = workflow["jobs"]["publish"]
    metadata = next(step for step in publish["steps"] if step.get("id") == "metadata")
    tags = metadata["with"]["tags"]
    assert metadata["with"]["images"] == "ghcr.io/bfawaz2001/watergeo-uk"
    assert "type=sha,prefix=sha-,format=long" in tags
    assert "type=ref,event=tag" in tags
    assert "latest" in tags and "refs/tags/v" in tags
    image = publish["steps"][-1]["with"]
    assert image["platforms"] == "linux/amd64,linux/arm64"
    assert image["push"] == "true"
    assert image["provenance"] == "mode=max"
    assert image["sbom"] == "true"


def test_container_bases_are_digest_pinned_and_context_excludes_secrets():
    dockerfiles = [Path("Dockerfile"), Path("docker/postgres/Dockerfile")]
    from_lines = [
        line
        for dockerfile in dockerfiles
        for line in dockerfile.read_text().splitlines()
        if line.startswith("FROM ")
    ]
    assert from_lines
    assert all(re.search(r"@sha256:[0-9a-f]{64}(?:\s|$)", line) for line in from_lines)
    ignored = Path(".dockerignore").read_text().splitlines()
    assert ignored[1] == "**"
    assert not any(line in {"!.env", "!data/**"} for line in ignored)
