"""Materialize provider database CA data for one ephemeral workload."""

import argparse
import os
import stat
import tempfile
from collections.abc import Sequence

CA_ENVIRONMENT_VARIABLE = "WATERGEO_DB_CA_CERT"


def materialize_database_ca(environment: dict[str, str]) -> str | None:
    """Write a supplied PEM to a private temporary file without logging its value."""
    pem = environment.pop(CA_ENVIRONMENT_VARIABLE, None)
    if pem is None:
        return None
    if not pem.startswith("-----BEGIN CERTIFICATE-----") or "-----END CERTIFICATE-----" not in pem:
        raise ValueError(f"{CA_ENVIRONMENT_VARIABLE} is not a PEM certificate")
    if len(pem.encode()) > 64 * 1024:
        raise ValueError(f"{CA_ENVIRONMENT_VARIABLE} exceeds 64 KiB")

    descriptor, path = tempfile.mkstemp(prefix="watergeo-db-ca-", suffix=".pem")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as certificate:
            os.fchmod(certificate.fileno(), stat.S_IRUSR | stat.S_IWUSR)
            certificate.write(pem)
            if not pem.endswith("\n"):
                certificate.write("\n")
    except BaseException:
        os.unlink(path)
        raise
    environment["WATERGEO_DB_SSLROOTCERT"] = path
    return path


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run a command after securely materializing WATERGEO_DB_CA_CERT."
    )
    parser.add_argument("command", nargs=argparse.REMAINDER)
    arguments = parser.parse_args(argv)
    command = arguments.command
    if command[:1] == ["--"]:
        command = command[1:]
    if not command:
        parser.error("a command is required after --")

    environment = dict(os.environ)
    materialize_database_ca(environment)
    os.execvpe(command[0], command, environment)  # noqa: S606
    return 127  # pragma: no cover - exec replaces the process


if __name__ == "__main__":
    raise SystemExit(main())
