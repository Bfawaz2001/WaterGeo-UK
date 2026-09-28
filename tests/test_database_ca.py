import stat
from pathlib import Path

import pytest

from watergeo.operations.database_ca import CA_ENVIRONMENT_VARIABLE, materialize_database_ca


def test_database_ca_is_materialized_privately_and_removed_from_child_environment() -> None:
    environment = {
        CA_ENVIRONMENT_VARIABLE: "-----BEGIN CERTIFICATE-----\ndata\n-----END CERTIFICATE-----"
    }

    path = materialize_database_ca(environment)

    assert path is not None
    certificate = Path(path)
    try:
        assert certificate.read_text() == (
            "-----BEGIN CERTIFICATE-----\ndata\n-----END CERTIFICATE-----\n"
        )
        assert stat.S_IMODE(certificate.stat().st_mode) == 0o600
        assert CA_ENVIRONMENT_VARIABLE not in environment
    finally:
        certificate.unlink()


@pytest.mark.parametrize("value", ["not-pem", "-----BEGIN CERTIFICATE-----\nmissing-end"])
def test_database_ca_rejects_invalid_values_without_creating_a_path(value: str) -> None:
    environment = {CA_ENVIRONMENT_VARIABLE: value}
    with pytest.raises(ValueError, match="not a PEM certificate"):
        materialize_database_ca(environment)
    assert "WATERGEO_DB_SSLROOTCERT" not in environment


def test_database_ca_is_optional_when_root_path_is_already_mounted() -> None:
    environment = {"WATERGEO_DB_SSLROOTCERT": "/mounted/ca.pem"}
    assert materialize_database_ca(environment) is None
    assert environment["WATERGEO_DB_SSLROOTCERT"] == "/mounted/ca.pem"
