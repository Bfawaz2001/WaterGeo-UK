import stat
from pathlib import Path

import pytest
import yaml

from watergeo.operations.production_preflight import database_endpoint_checks, local_checks
from watergeo.operations.production_spec import render, write_private


def deployment_environment() -> dict[str, str]:
    digest = "sha256:" + "a" * 64
    return {
        "WATERGEO_DEPLOY_COMMIT": "b" * 40,
        "WATERGEO_API_IMAGE_DIGEST": digest,
        "WATERGEO_OPERATOR_IMAGE_DIGEST": digest,
        "WATERGEO_WEB_IMAGE_DIGEST": digest,
        "WATERGEO_DO_DATABASE_CLUSTER_ID": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        "WATERGEO_DO_DATABASE_CLUSTER_NAME": "watergeo-db-lon1",
        "WATERGEO_DO_VPC_ID": "11111111-2222-3333-4444-555555555555",
        "WATERGEO_DB_PRIVATE_HOST": "private-watergeo-db.example",
        "WATERGEO_DB_PORT": "25060",
        "WATERGEO_DB_PASSWORD": "app-password-value",
        "WATERGEO_MIGRATION_PASSWORD": "migration-password-value",
        "WATERGEO_INGESTION_PASSWORD": "ingestion-password-value",
        "WATERGEO_EVIDENCE_S3_ENDPOINT": "https://lon1.digitaloceanspaces.com",
        "WATERGEO_EVIDENCE_S3_REGION": "lon1",
        "WATERGEO_EVIDENCE_S3_BUCKET": "watergeo-evidence-example",
        "WATERGEO_EVIDENCE_S3_ACCESS_KEY_ID": "operator-access-key",
        "WATERGEO_EVIDENCE_S3_SECRET_ACCESS_KEY": "operator-secret-key",
    }


def component_environment(component: dict[str, object]) -> dict[str, dict[str, str]]:
    return {item["key"]: item for item in component.get("envs", [])}  # type: ignore[union-attr]


def test_app_spec_exposes_only_edge_and_preserves_identity_boundaries() -> None:
    spec = yaml.safe_load(render(deployment_environment(), include_bootstrap=False))
    services = {component["name"]: component for component in spec["services"]}
    jobs = {component["name"]: component for component in spec["jobs"]}

    assert spec["region"] == "lon"
    assert spec["vpc"] == {"id": "11111111-2222-3333-4444-555555555555"}
    assert spec["maintenance"] == {"enabled": True}
    assert spec["ingress"]["rules"] == [
        {"match": {"path": {"prefix": "/"}}, "component": {"name": "edge"}}
    ]
    assert services["edge"]["http_port"] == 8080
    assert "http_port" not in services["api"]
    assert services["api"]["internal_ports"] == [8000]
    assert jobs["migrate"]["kind"] == "PRE_DEPLOY"
    assert all(job.get("kind") != "SCHEDULED" for job in jobs.values())

    api = component_environment(services["api"])
    migration = component_environment(jobs["migrate"])
    assert api["WATERGEO_DB_USER"]["value"] == "watergeo_app"
    assert api["WATERGEO_DB_HOST"]["value"] == "private-watergeo-db.example"
    assert "WATERGEO_MIGRATION_PASSWORD" not in api
    assert "WATERGEO_INGESTION_PASSWORD" not in api
    assert not any("EVIDENCE" in name for name in api)
    assert migration["WATERGEO_MIGRATION_USER"]["value"] == "watergeo_migrator"
    assert "WATERGEO_DB_PASSWORD" not in migration
    assert api["WATERGEO_DB_SSLMODE"]["value"] == "verify-full"
    assert api["WATERGEO_TRUSTED_HOSTS"]["value"] == '["${APP_DOMAIN}","health.internal"]'
    assert "*" not in api["WATERGEO_TRUSTED_HOSTS"]["value"]
    assert component_environment(services["edge"]) == {
        "WATERGEO_PUBLIC_HOSTS": {
            "key": "WATERGEO_PUBLIC_HOSTS",
            "scope": "RUN_TIME",
            "value": "${APP_DOMAIN}",
        }
    }


def test_optional_bootstrap_is_post_deploy_operator_job_with_only_ingestion_secrets() -> None:
    spec = yaml.safe_load(render(deployment_environment(), include_bootstrap=True))
    bootstrap = next(job for job in spec["jobs"] if job["name"] == "bootstrap")
    environment = component_environment(bootstrap)
    assert bootstrap["kind"] == "POST_DEPLOY"
    assert bootstrap["image"]["repository"] == "watergeo-uk-operator"
    assert environment["WATERGEO_INGESTION_USER"]["value"] == "watergeo_ingest"
    assert "WATERGEO_DB_PASSWORD" not in environment
    assert "WATERGEO_MIGRATION_PASSWORD" not in environment
    assert "WATERGEO_EVIDENCE_S3_ACCESS_KEY_ID" in environment
    assert "WATERGEO_EVIDENCE_S3_SECRET_ACCESS_KEY" in environment


def test_public_render_only_changes_the_maintenance_gate() -> None:
    spec = yaml.safe_load(render(deployment_environment(), include_bootstrap=False, public=True))
    assert spec["maintenance"] == {"enabled": False}


def test_every_rendered_image_is_digest_pinned() -> None:
    spec = yaml.safe_load(render(deployment_environment(), include_bootstrap=True))
    components = [*spec["services"], *spec["jobs"]]
    assert all(component["image"].get("tag") is None for component in components)
    assert all(component["image"].get("registry_credentials") is None for component in components)
    assert all(component["image"]["digest"] == "sha256:" + "a" * 64 for component in components)


def test_render_rejects_non_digest_image_reference() -> None:
    environment = deployment_environment()
    environment["WATERGEO_API_IMAGE_DIGEST"] = "latest"
    with pytest.raises(ValueError, match="immutable sha256"):
        render(environment, include_bootstrap=False)


def test_render_rejects_database_url_in_place_of_private_hostname() -> None:
    environment = deployment_environment()
    environment["WATERGEO_DB_PRIVATE_HOST"] = "postgresql://admin:secret@public.example/db"
    with pytest.raises(ValueError, match="hostname without credentials"):
        render(environment, include_bootstrap=False)


def test_render_rejects_invalid_vpc_id() -> None:
    environment = deployment_environment()
    environment["WATERGEO_DO_VPC_ID"] = "lon1"
    with pytest.raises(ValueError, match="must be a UUID"):
        render(environment, include_bootstrap=False)


def test_rendered_spec_is_created_exclusively_with_private_permissions(tmp_path: Path) -> None:
    destination = tmp_path / "app.yaml"
    write_private(destination, "secret material")
    assert stat.S_IMODE(destination.stat().st_mode) == 0o600
    with pytest.raises(FileExistsError):
        write_private(destination, "replacement")


def test_local_preflight_reports_names_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("watergeo.operations.production_preflight.shutil.which", lambda _: None)
    monkeypatch.setattr(
        "watergeo.operations.production_preflight._run",
        lambda command: {"status": "", "branch": "main\n", "rev-parse": "c" * 40 + "\n"}[
            command[1]
        ],
    )
    failures = local_checks({})
    combined = " ".join(failures)
    assert "WATERGEO_DB_PASSWORD" in combined
    assert "doctl is not installed" in combined
    assert "app-password-value" not in combined


def test_database_endpoint_matches_exact_selected_cluster_private_connection() -> None:
    environment = deployment_environment()
    assert (
        database_endpoint_checks(
            "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee\twatergeo-db-lon1\tpg\tlon1\n",
            "private-watergeo-db.example\t25060\n",
            "public-watergeo-db.example\t25060\n",
            environment,
        )
        == []
    )


@pytest.mark.parametrize(
    ("identity", "private", "public", "expected"),
    [
        (
            "ffffffff-bbbb-cccc-dddd-eeeeeeeeeeee other-db pg lon1",
            "private-other-db.example 25060",
            "public-other-db.example 25060",
            "identity",
        ),
        (
            "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee other-db pg lon1",
            "private-watergeo-db.example 25060",
            "public-watergeo-db.example 25060",
            "name does not match",
        ),
        (
            "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee watergeo-db-lon1 mysql lon1",
            "private-watergeo-db.example 25060",
            "public-watergeo-db.example 25060",
            "not PostgreSQL",
        ),
        (
            "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee watergeo-db-lon1 pg nyc3",
            "private-watergeo-db.example 25060",
            "public-watergeo-db.example 25060",
            "not in lon1",
        ),
        (
            "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee watergeo-db-lon1 pg lon1",
            "private-other-db.example 25060",
            "public-watergeo-db.example 25060",
            "not the selected cluster private endpoint",
        ),
        (
            "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee watergeo-db-lon1 pg lon1",
            "private-watergeo-db.example 25061",
            "private-watergeo-db.example 25060",
            "public endpoint",
        ),
        (
            "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee watergeo-db-lon1 pg lon1",
            "private-watergeo-db.example 25061",
            "public-watergeo-db.example 25060",
            "port does not match",
        ),
    ],
)
def test_database_endpoint_rejects_wrong_cluster_region_host_or_port(
    identity: str, private: str, public: str, expected: str
) -> None:
    failures = database_endpoint_checks(identity, private, public, deployment_environment())
    assert any(expected in failure for failure in failures)
    assert not any("postgresql://" in failure or "password" in failure for failure in failures)


def test_database_endpoint_rejects_unexpected_provider_output_without_echoing_it() -> None:
    secret = "postgresql://user:secret@private-watergeo-db.example:25060/defaultdb"
    with pytest.raises(
        ValueError, match="Unexpected private database connection response"
    ) as error:
        database_endpoint_checks(
            "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee watergeo-db-lon1 pg lon1",
            secret,
            "public-watergeo-db.example 25060",
            deployment_environment(),
        )
    assert secret not in str(error.value)


def test_edge_rejects_unknown_hosts_before_preserving_the_reviewed_host() -> None:
    nginx = Path("deploy/nginx.conf").read_text()
    assert "listen 8080 default_server;" in nginx
    assert 'server_name "";' in nginx
    assert "return 444;" in nginx
    assert "server_name ${WATERGEO_PUBLIC_HOSTS};" in nginx
    assert "proxy_set_header Host $host;" in nginx
    assert "Access-Control-Allow-Origin *" not in nginx


def test_api_container_health_uses_exact_internal_only_host() -> None:
    dockerfile = Path("Dockerfile").read_text()
    assert "headers={'Host':'health.internal'}" in dockerfile
    assert "--no-proxy-headers" in dockerfile
