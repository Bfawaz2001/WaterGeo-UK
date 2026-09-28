"""Read-only preflight checks for the first hosted WaterGeo preview."""

import argparse
import json
import os
import shutil
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path

APP_REGION = "lon"
RESOURCE_REGION = "lon1"
INSTANCE_SIZE = "apps-s-1vcpu-0.5gb"
DATABASE_SIZE = "db-s-1vcpu-1gb"
REQUIRED_ENVIRONMENT = (
    "WATERGEO_DEPLOY_COMMIT",
    "WATERGEO_API_IMAGE_DIGEST",
    "WATERGEO_OPERATOR_IMAGE_DIGEST",
    "WATERGEO_WEB_IMAGE_DIGEST",
    "WATERGEO_DO_DATABASE_CLUSTER_ID",
    "WATERGEO_DO_DATABASE_CLUSTER_NAME",
    "WATERGEO_DO_VPC_ID",
    "WATERGEO_DB_PRIVATE_HOST",
    "WATERGEO_DB_PORT",
    "WATERGEO_DB_PASSWORD",
    "WATERGEO_MIGRATION_PASSWORD",
    "WATERGEO_INGESTION_PASSWORD",
    "WATERGEO_EVIDENCE_S3_ENDPOINT",
    "WATERGEO_EVIDENCE_S3_REGION",
    "WATERGEO_EVIDENCE_S3_BUCKET",
    "WATERGEO_EVIDENCE_S3_ACCESS_KEY_ID",
    "WATERGEO_EVIDENCE_S3_SECRET_ACCESS_KEY",
)


def _fields(output: str, count: int, description: str) -> tuple[str, ...]:
    fields = tuple(output.strip().split())
    if len(fields) != count:
        raise ValueError(f"Unexpected {description} response")
    return fields


def database_endpoint_checks(
    identity_output: str,
    private_output: str,
    public_output: str,
    environment: Mapping[str, str],
) -> list[str]:
    """Compare non-secret provider fields with the selected deployment inputs."""
    cluster_id, name, engine, region = _fields(identity_output, 4, "database identity")
    private_host, private_port = _fields(private_output, 2, "private database connection")
    public_host, _public_port = _fields(public_output, 2, "public database connection")
    failures: list[str] = []
    if cluster_id != environment.get("WATERGEO_DO_DATABASE_CLUSTER_ID"):
        failures.append("Selected database cluster identity does not match")
    if name != environment.get("WATERGEO_DO_DATABASE_CLUSTER_NAME"):
        failures.append("Selected database cluster name does not match")
    if engine != "pg":
        failures.append("Selected database cluster is not PostgreSQL")
    if region != RESOURCE_REGION:
        failures.append("Selected database cluster is not in lon1")
    configured_host = environment.get("WATERGEO_DB_PRIVATE_HOST", "")
    if configured_host == public_host:
        failures.append("Configured database host is the public endpoint")
    elif configured_host != private_host:
        failures.append("Configured database host is not the selected cluster private endpoint")
    if environment.get("WATERGEO_DB_PORT") != private_port:
        failures.append("Configured database port does not match the selected private endpoint")
    return failures


def _run(command: Sequence[str]) -> str:
    result = subprocess.run(command, check=False, capture_output=True, text=True)  # noqa: S603
    if result.returncode != 0:
        raise RuntimeError(f"Read-only command failed: {' '.join(command[:3])}")
    return result.stdout


def local_checks(environment: Mapping[str, str]) -> list[str]:
    failures: list[str] = []
    missing = [name for name in REQUIRED_ENVIRONMENT if not environment.get(name)]
    if missing:
        failures.append("missing environment names: " + ", ".join(missing))
    if shutil.which("doctl") is None:
        failures.append("doctl is not installed (macOS: brew install doctl)")
    status = _run(("git", "status", "--porcelain"))
    if status:
        failures.append("repository is not clean")
    branch = _run(("git", "branch", "--show-current")).strip()
    if branch != "main":
        failures.append("deployment source must be reviewed main")
    head = _run(("git", "rev-parse", "HEAD")).strip()
    expected = environment.get("WATERGEO_DEPLOY_COMMIT", "")
    if expected and (len(expected) != 40 or expected != head):
        failures.append("WATERGEO_DEPLOY_COMMIT does not equal the full current commit")
    endpoint = environment.get("WATERGEO_EVIDENCE_S3_ENDPOINT", "")
    if endpoint and endpoint != f"https://{RESOURCE_REGION}.digitaloceanspaces.com":
        failures.append("Spaces endpoint does not match lon1")
    return failures


def provider_checks(spec: Path, environment: Mapping[str, str]) -> list[str]:
    failures: list[str] = []
    try:
        _run(("doctl", "account", "get", "--output", "json"))
        regions = json.loads(_run(("doctl", "apps", "list-regions", "--output", "json")))
        london = next((region for region in regions if region.get("slug") == APP_REGION), None)
        if london is None or london.get("disabled"):
            failures.append("App Platform London region is unavailable")
        sizes = json.loads(
            _run(("doctl", "apps", "tier", "instance-size", "list", "--output", "json"))
        )
        if not any(size.get("slug") == INSTANCE_SIZE for size in sizes):
            failures.append(f"App Platform size {INSTANCE_SIZE} is unavailable")
        database_regions = json.loads(
            _run(("doctl", "databases", "options", "regions", "--engine", "pg", "--output", "json"))
        )
        if RESOURCE_REGION not in json.dumps(database_regions):
            failures.append("Managed PostgreSQL is unavailable in lon1")
        database_sizes = json.loads(
            _run(("doctl", "databases", "options", "slugs", "--engine", "pg", "--output", "json"))
        )
        if DATABASE_SIZE not in json.dumps(database_sizes):
            failures.append(f"Managed PostgreSQL size {DATABASE_SIZE} is unavailable")
        cluster_id = environment["WATERGEO_DO_DATABASE_CLUSTER_ID"]
        identity = _run(
            (
                "doctl",
                "databases",
                "get",
                cluster_id,
                "--format",
                "ID,Name,Engine,Region",
                "--no-header",
            )
        )
        private_connection = _run(
            (
                "doctl",
                "databases",
                "connection",
                cluster_id,
                "--private",
                "--format",
                "Host,Port",
                "--no-header",
            )
        )
        public_connection = _run(
            (
                "doctl",
                "databases",
                "connection",
                cluster_id,
                "--format",
                "Host,Port",
                "--no-header",
            )
        )
        failures.extend(
            database_endpoint_checks(identity, private_connection, public_connection, environment)
        )
        vpc = json.loads(
            _run(("doctl", "vpcs", "get", environment["WATERGEO_DO_VPC_ID"], "--output", "json"))
        )
        if RESOURCE_REGION not in json.dumps(vpc):
            failures.append("Selected VPC is not in lon1")
        _run(("doctl", "apps", "spec", "validate", str(spec)))
        images = {
            "watergeo-uk": environment.get("WATERGEO_API_IMAGE_DIGEST", ""),
            "watergeo-uk-operator": environment.get("WATERGEO_OPERATOR_IMAGE_DIGEST", ""),
            "watergeo-uk-web": environment.get("WATERGEO_WEB_IMAGE_DIGEST", ""),
        }
        for repository, digest in images.items():
            _run(("docker", "manifest", "inspect", f"ghcr.io/bfawaz2001/{repository}@{digest}"))
    except (RuntimeError, ValueError, json.JSONDecodeError) as error:
        failures.append(str(error))
    return failures


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--online", action="store_true", help="run read-only provider checks")
    parser.add_argument("--spec", type=Path, help="private rendered spec required with --online")
    arguments = parser.parse_args(argv)
    if arguments.online and arguments.spec is None:
        parser.error("--online requires --spec")

    print("Planned inventory: London App Platform edge + private API, managed PostgreSQL, Spaces")
    print(
        "Estimated baseline: USD 30.15/month before tax, transfer, storage overages and job runtime"
    )
    failures = local_checks(os.environ)
    if arguments.online and arguments.spec is not None:
        failures.extend(provider_checks(arguments.spec, os.environ))
    for failure in failures:
        print(f"FAIL: {failure}")
    if failures:
        return 1
    print("Production preflight passed without modifying cloud resources.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
