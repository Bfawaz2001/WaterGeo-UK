"""Validated configuration; credentials never live in a connection string setting."""

from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class DatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="WATERGEO_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # The local dotenv file also contains Compose-only settings.
        hide_input_in_errors=True,
    )

    db_host: str = Field(default="127.0.0.1", min_length=1)
    db_port: int = Field(default=5432, ge=1, le=65535)
    db_name: str = Field(default="watergeo", min_length=1)
    db_user: str = Field(default="watergeo_app", min_length=1)
    db_password: SecretStr = Field(min_length=16)

    @property
    def database_url(self) -> URL:
        return URL.create(
            "postgresql+psycopg",
            username=self.db_user,
            password=self.db_password.get_secret_value(),
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
        )


class Settings(DatabaseSettings):
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"


class MigrationSettings(DatabaseSettings):
    db_user: str = Field(default="watergeo_migrator", validation_alias="WATERGEO_MIGRATION_USER")
    db_password: SecretStr = Field(min_length=16, validation_alias="WATERGEO_MIGRATION_PASSWORD")
