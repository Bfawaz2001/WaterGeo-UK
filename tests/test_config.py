import pytest
from pydantic import SecretStr, ValidationError

from watergeo.core.config import IngestionSettings, MigrationSettings, Settings


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    import os

    for key in os.environ:
        if key.startswith("WATERGEO_"):
            monkeypatch.delenv(key)


def test_password_is_required_and_errors_do_not_reveal_inputs() -> None:
    with pytest.raises(ValidationError, match="db_password"):
        Settings(_env_file=None)
    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None, db_password=SecretStr("sensitive"))
    assert "sensitive" not in str(error.value)


def test_connection_url_preserves_special_characters_without_exposing_password() -> None:
    secret = "special:@/?#% password"
    settings = Settings(_env_file=None, db_password=SecretStr(secret))
    assert settings.database_url.password == secret
    assert secret not in repr(settings)
    assert secret not in str(settings.database_url)


@pytest.mark.parametrize("port", [0, 65536])
def test_invalid_port_is_rejected(port: int) -> None:
    with pytest.raises(ValidationError, match="db_port"):
        Settings(_env_file=None, db_password=SecretStr("test-password-long"), db_port=port)


def test_environment_overrides_dotenv(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    dotenv = tmp_path / ".env"
    dotenv.write_text("WATERGEO_DB_HOST=from-file\nPOSTGRES_PASSWORD=compose-only\n")
    monkeypatch.setenv("WATERGEO_DB_HOST", "from-environment")
    monkeypatch.setenv("WATERGEO_DB_PASSWORD", "app-password-long")
    settings = Settings(_env_file=dotenv)
    assert settings.db_host == "from-environment"


def test_migrations_require_separate_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WATERGEO_DB_PASSWORD", "app-password-long")
    with pytest.raises(ValidationError, match="WATERGEO_MIGRATION_PASSWORD"):
        MigrationSettings(_env_file=None)
    monkeypatch.setenv("WATERGEO_MIGRATION_PASSWORD", "migration-password-long")
    settings = MigrationSettings(_env_file=None)
    assert settings.db_user == "watergeo_migrator"
    assert settings.db_password.get_secret_value() == "migration-password-long"


def test_local_database_connection_options_are_unchanged():
    settings = Settings(_env_file=None, db_password=SecretStr("synthetic-password"))
    assert dict(settings.database_url.query) == {}


def test_ingestion_tls_environment_contract(monkeypatch, tmp_path):
    monkeypatch.setenv("WATERGEO_INGESTION_PASSWORD", "synthetic-password")
    monkeypatch.setenv("WATERGEO_DB_SSLMODE", "verify-full")
    monkeypatch.setenv("WATERGEO_DB_SSLROOTCERT", str(tmp_path / "ca.pem"))
    settings = IngestionSettings(_env_file=None)
    assert dict(settings.database_url.query) == {
        "sslmode": "verify-full",
        "sslrootcert": str(tmp_path / "ca.pem"),
    }
    assert settings.db_user == "watergeo_ingest"
    from watergeo.db.engine import create_database_engine

    engine = create_database_engine(settings)
    try:
        _, parameters = engine.dialect.create_connect_args(engine.url)
        assert parameters["sslmode"] == "verify-full"
        assert parameters["sslrootcert"] == str(tmp_path / "ca.pem")
    finally:
        engine.dispose()


@pytest.mark.parametrize("mode", ["disable", "allow", "prefer", "require", "verify-ca"])
def test_explicit_tls_cannot_disable_certificate_and_hostname_verification(mode):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, db_password=SecretStr("synthetic-password"), db_sslmode=mode)


def test_ca_cannot_silently_be_ignored():
    with pytest.raises(ValidationError, match="requires verify-full"):
        Settings(
            _env_file=None, db_password=SecretStr("synthetic-password"), db_sslrootcert="ca.pem"
        )


def test_production_requires_trusted_hosts_and_verified_database_tls():
    with pytest.raises(ValidationError, match="trusted host"):
        Settings(
            _env_file=None,
            db_password=SecretStr("synthetic-password"),
            service_environment="production",
        )
    with pytest.raises(ValidationError, match="verify-full"):
        Settings(
            _env_file=None,
            db_password=SecretStr("synthetic-password"),
            service_environment="production",
            trusted_hosts=["api.example.org"],
        )


def test_production_configuration_accepts_explicit_hosts_and_verified_tls():
    settings = Settings(
        _env_file=None,
        db_password=SecretStr("synthetic-password"),
        service_environment="production",
        trusted_hosts=["api.example.org", "*.ondigitalocean.app"],
        db_sslmode="verify-full",
        db_sslrootcert="/run/secrets/database-ca.pem",
    )
    assert settings.trusted_hosts == ["api.example.org", "*.ondigitalocean.app"]


@pytest.mark.parametrize(
    "host", ["*", "https://api.example.org", "api.example.org/path", "api example.org", "bad*host"]
)
def test_trusted_hosts_reject_ambiguous_values(host: str):
    with pytest.raises(ValidationError, match="explicit hostnames"):
        Settings(
            _env_file=None,
            db_password=SecretStr("synthetic-password"),
            trusted_hosts=[host],
        )
