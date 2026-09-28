"""Render a secure, immutable DigitalOcean App Platform specification."""

import argparse
import json
import os
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from uuid import UUID

TEMPLATE = Path("deploy/digitalocean/app.yaml")
IMAGE_PATTERN = re.compile(r"sha256:[0-9a-f]{64}\Z")

SUBSTITUTIONS = {
    "__DATABASE_CLUSTER_NAME__": "WATERGEO_DO_DATABASE_CLUSTER_NAME",
    "__VPC_ID__": "WATERGEO_DO_VPC_ID",
    "__DATABASE_PRIVATE_HOST__": "WATERGEO_DB_PRIVATE_HOST",
    "__API_IMAGE_DIGEST__": "WATERGEO_API_IMAGE_DIGEST",
    "__WEB_IMAGE_DIGEST__": "WATERGEO_WEB_IMAGE_DIGEST",
    "__APP_DATABASE_PASSWORD__": "WATERGEO_DB_PASSWORD",
    "__MIGRATION_DATABASE_PASSWORD__": "WATERGEO_MIGRATION_PASSWORD",
}


def _bootstrap_job(environment: Mapping[str, str]) -> str:
    required = {
        "__OPERATOR_IMAGE_DIGEST__": "WATERGEO_OPERATOR_IMAGE_DIGEST",
        "__DATABASE_PRIVATE_HOST__": "WATERGEO_DB_PRIVATE_HOST",
        "__INGESTION_DATABASE_PASSWORD__": "WATERGEO_INGESTION_PASSWORD",
        "__EVIDENCE_ENDPOINT__": "WATERGEO_EVIDENCE_S3_ENDPOINT",
        "__EVIDENCE_REGION__": "WATERGEO_EVIDENCE_S3_REGION",
        "__EVIDENCE_BUCKET__": "WATERGEO_EVIDENCE_S3_BUCKET",
        "__EVIDENCE_ACCESS_KEY__": "WATERGEO_EVIDENCE_S3_ACCESS_KEY_ID",
        "__EVIDENCE_SECRET_KEY__": "WATERGEO_EVIDENCE_S3_SECRET_ACCESS_KEY",
    }
    job = Path("deploy/digitalocean/bootstrap-job.yaml").read_text()
    return _replace(job, required, environment).rstrip()


def _replace(template: str, names: Mapping[str, str], environment: Mapping[str, str]) -> str:
    missing = [name for name in names.values() if not environment.get(name)]
    if missing:
        raise ValueError("Missing required environment names: " + ", ".join(missing))
    rendered = template
    for placeholder, name in names.items():
        rendered = rendered.replace(placeholder, json.dumps(environment[name]))
    return rendered


def render(environment: Mapping[str, str], *, include_bootstrap: bool, public: bool = False) -> str:
    template = TEMPLATE.read_text()
    rendered = _replace(template, SUBSTITUTIONS, environment)
    bootstrap = _bootstrap_job(environment) if include_bootstrap else ""
    rendered = rendered.replace("# __BOOTSTRAP_JOB__", bootstrap)
    rendered = rendered.replace("__MAINTENANCE_ENABLED__", "false" if public else "true")
    for name in (
        "WATERGEO_API_IMAGE_DIGEST",
        "WATERGEO_WEB_IMAGE_DIGEST",
        *(("WATERGEO_OPERATOR_IMAGE_DIGEST",) if include_bootstrap else ()),
    ):
        if not IMAGE_PATTERN.fullmatch(environment[name]):
            raise ValueError(f"{name} must be an immutable sha256 digest")
    private_host = environment["WATERGEO_DB_PRIVATE_HOST"]
    if "://" in private_host or "/" in private_host or any(c.isspace() for c in private_host):
        raise ValueError("WATERGEO_DB_PRIVATE_HOST must be a hostname without credentials")
    try:
        UUID(environment["WATERGEO_DO_VPC_ID"])
    except ValueError as error:
        raise ValueError("WATERGEO_DO_VPC_ID must be a UUID") from error
    if re.search(r"__[A-Z0-9_]+__", rendered):
        raise ValueError("Rendered app spec still contains a placeholder")
    return rendered


def write_private(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as output:
        output.write(content)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--include-bootstrap", action="store_true")
    parser.add_argument(
        "--public", action="store_true", help="disable maintenance mode after acceptance"
    )
    arguments = parser.parse_args(argv)
    output = arguments.output.resolve()
    repository = Path.cwd().resolve()
    if output == repository or repository in output.parents:
        parser.error("output must be outside the repository")
    rendered = render(
        os.environ, include_bootstrap=arguments.include_bootstrap, public=arguments.public
    )
    write_private(output, rendered)
    print(f"Rendered private app spec at {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
