import pytest

from watergeo.operations import production_database
from watergeo.operations.production_database import ConnectionParameters, role_passwords


def test_connection_parameters_require_admin_environment_names() -> None:
    with pytest.raises(ValueError, match="WATERGEO_DB_ADMIN_PASSWORD"):
        ConnectionParameters.from_environment({})


def test_connection_parameters_preserve_verify_full_inputs() -> None:
    parameters = ConnectionParameters.from_environment(
        {
            "WATERGEO_DB_HOST": "private-db.example",
            "WATERGEO_DB_PORT": "25060",
            "WATERGEO_DB_ADMIN_USER": "doadmin",
            "WATERGEO_DB_ADMIN_PASSWORD": "administrator-secret",
            "WATERGEO_DB_SSLROOTCERT": "/secure/provider-ca.pem",
        }
    )
    assert parameters.host == "private-db.example"
    assert parameters.port == 25060
    assert parameters.sslrootcert == "/secure/provider-ca.pem"


def test_role_passwords_are_only_accepted_from_named_environment_values() -> None:
    environment = {
        "WATERGEO_MIGRATION_PASSWORD": "m" * 16,
        "WATERGEO_DB_PASSWORD": "a" * 16,
        "WATERGEO_INGESTION_PASSWORD": "i" * 16,
    }
    assert role_passwords(environment) == {
        "watergeo_migrator": "m" * 16,
        "watergeo_app": "a" * 16,
        "watergeo_ingest": "i" * 16,
    }


def test_role_passwords_reject_missing_or_short_values_without_echoing_them() -> None:
    with pytest.raises(ValueError, match="WATERGEO_DB_PASSWORD") as error:
        role_passwords(
            {
                "WATERGEO_MIGRATION_PASSWORD": "m" * 16,
                "WATERGEO_DB_PASSWORD": "short-secret",
                "WATERGEO_INGESTION_PASSWORD": "i" * 16,
            }
        )
    assert "short-secret" not in str(error.value)


def test_managed_provisioning_preserves_local_bootstrap_privilege_contract() -> None:
    source = production_database.provision.__code__.co_consts
    statements = " ".join(item for item in source if isinstance(item, str))
    assert "REVOKE ALL ON DATABASE" in statements
    assert "REVOKE CREATE ON SCHEMA public FROM PUBLIC" in statements
    assert "ALTER DEFAULT PRIVILEGES FOR ROLE watergeo_migrator" in statements
    assert "GRANT SELECT ON TABLES TO watergeo_app" in statements
    assert "default_transaction_read_only = on" in statements
