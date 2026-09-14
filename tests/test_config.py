import pytest
from pydantic import SecretStr, ValidationError

from watergeo.core.config import MigrationSettings, Settings


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
