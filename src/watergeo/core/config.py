"""Validated configuration; credentials never live in a connection string setting."""

from typing import Literal, Self

from pydantic import Field, SecretStr, field_validator, model_validator
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
    service_environment: Literal["development", "production"] = "development"
    db_sslmode: Literal["verify-full"] | None = None
    db_sslrootcert: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def require_verified_production_database_tls(self) -> Self:
        if self.db_sslrootcert and self.db_sslmode != "verify-full":
            raise ValueError("A database CA requires verify-full TLS mode")
        if self.service_environment == "production" and (
            self.db_sslmode != "verify-full" or not self.db_sslrootcert
        ):
            raise ValueError("production requires verify-full database TLS and a trusted CA")
        return self

    @property
    def database_url(self) -> URL:
        return URL.create(
            "postgresql+psycopg",
            username=self.db_user,
            password=self.db_password.get_secret_value(),
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
            query=(
                {
                    "sslmode": self.db_sslmode,
                    **({"sslrootcert": self.db_sslrootcert} if self.db_sslrootcert else {}),
                }
                if self.db_sslmode
                else {}
            ),
        )


class Settings(DatabaseSettings):
    trusted_hosts: list[str] = Field(default_factory=list)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    hydrology_retrieval_max_age_seconds: int | None = Field(default=None, ge=1, le=31536000)
    hydrology_observation_max_age_seconds: int | None = Field(default=None, ge=1, le=31536000)
    water_quality_retrieval_max_age_seconds: int | None = Field(default=None, ge=1, le=31536000)

    @field_validator(
        "hydrology_retrieval_max_age_seconds",
        "hydrology_observation_max_age_seconds",
        "water_quality_retrieval_max_age_seconds",
        mode="before",
    )
    @classmethod
    def optional_age_limit(cls, value: object) -> object:
        return None if value == "" else value

    @field_validator("trusted_hosts")
    @classmethod
    def valid_trusted_hosts(cls, hosts: list[str]) -> list[str]:
        for host in hosts:
            if (
                not host
                or "*" in host
                or any(character.isspace() for character in host)
                or "://" in host
                or "/" in host
            ):
                raise ValueError("trusted hosts must be explicit hostnames")
        return hosts

    @model_validator(mode="after")
    def production_is_fail_closed(self) -> Self:
        if self.service_environment != "production":
            return self
        if not self.trusted_hosts:
            raise ValueError("production requires at least one trusted host")
        return self


class MigrationSettings(DatabaseSettings):
    db_user: str = Field(default="watergeo_migrator", validation_alias="WATERGEO_MIGRATION_USER")
    db_password: SecretStr = Field(min_length=16, validation_alias="WATERGEO_MIGRATION_PASSWORD")


class IngestionSettings(DatabaseSettings):
    """Least-privilege identity for canonical ingestion jobs."""

    db_user: str = Field(
        default="watergeo_ingest",
        validation_alias="WATERGEO_INGESTION_USER",
    )
    db_password: SecretStr = Field(
        min_length=16,
        validation_alias="WATERGEO_INGESTION_PASSWORD",
    )
