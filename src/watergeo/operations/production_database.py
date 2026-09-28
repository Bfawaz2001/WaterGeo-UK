"""Provision and verify WaterGeo roles in a managed PostgreSQL cluster."""

import argparse
import os
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass

import psycopg
from psycopg import Connection, sql
from psycopg.errors import InsufficientPrivilege, ReadOnlySqlTransaction

DATABASE_NAME = "watergeo"
ROLES = ("watergeo_migrator", "watergeo_app", "watergeo_ingest")


@dataclass(frozen=True)
class ConnectionParameters:
    host: str
    port: int
    admin_database: str
    admin_user: str
    admin_password: str
    sslrootcert: str

    @classmethod
    def from_environment(cls, environment: Mapping[str, str]) -> "ConnectionParameters":
        required = (
            "WATERGEO_DB_HOST",
            "WATERGEO_DB_ADMIN_USER",
            "WATERGEO_DB_ADMIN_PASSWORD",
            "WATERGEO_DB_SSLROOTCERT",
        )
        missing = [name for name in required if not environment.get(name)]
        if missing:
            raise ValueError("Missing required environment names: " + ", ".join(missing))
        return cls(
            host=environment["WATERGEO_DB_HOST"],
            port=int(environment.get("WATERGEO_DB_PORT", "25060")),
            admin_database=environment.get("WATERGEO_DB_ADMIN_NAME", "defaultdb"),
            admin_user=environment["WATERGEO_DB_ADMIN_USER"],
            admin_password=environment["WATERGEO_DB_ADMIN_PASSWORD"],
            sslrootcert=environment["WATERGEO_DB_SSLROOTCERT"],
        )

    def connect(self, database: str, user: str, password: str) -> Connection[tuple[object, ...]]:
        return psycopg.connect(
            host=self.host,
            port=self.port,
            dbname=database,
            user=user,
            password=password,
            sslmode="verify-full",
            sslrootcert=self.sslrootcert,
            connect_timeout=10,
            options="-c statement_timeout=15000 -c lock_timeout=5000",
        )


def role_passwords(environment: Mapping[str, str]) -> dict[str, str]:
    names = {
        "watergeo_migrator": "WATERGEO_MIGRATION_PASSWORD",
        "watergeo_app": "WATERGEO_DB_PASSWORD",
        "watergeo_ingest": "WATERGEO_INGESTION_PASSWORD",
    }
    missing = [name for name in names.values() if len(environment.get(name, "")) < 16]
    if missing:
        raise ValueError(
            "Missing or short (minimum 16) secret environment names: " + ", ".join(missing)
        )
    return {role: environment[name] for role, name in names.items()}


def provision(environment: Mapping[str, str]) -> None:
    parameters = ConnectionParameters.from_environment(environment)
    passwords = role_passwords(environment)
    with parameters.connect(
        parameters.admin_database, parameters.admin_user, parameters.admin_password
    ) as administrator:
        administrator.autocommit = True
        with administrator.cursor() as cursor:
            for role in ROLES:
                cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,))
                if cursor.fetchone() is None:
                    cursor.execute(
                        sql.SQL(
                            "CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION"
                        ).format(sql.Identifier(role))
                    )
                cursor.execute(
                    sql.SQL("ALTER ROLE {} PASSWORD %s").format(sql.Identifier(role)),
                    (passwords[role],),
                )
            cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", (DATABASE_NAME,))
            if cursor.fetchone() is None:
                cursor.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(DATABASE_NAME)))
            cursor.execute(
                sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(
                    sql.Identifier(DATABASE_NAME)
                )
            )
            for role in ROLES:
                cursor.execute(
                    sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                        sql.Identifier(DATABASE_NAME), sql.Identifier(role)
                    )
                )
            cursor.execute("ALTER ROLE watergeo_app SET default_transaction_read_only = on")

    with (
        parameters.connect(DATABASE_NAME, parameters.admin_user, parameters.admin_password) as db,
        db.cursor() as cursor,
    ):
        cursor.execute("CREATE EXTENSION IF NOT EXISTS postgis WITH SCHEMA public")
        cursor.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
        cursor.execute("CREATE SCHEMA IF NOT EXISTS watergeo AUTHORIZATION watergeo_migrator")
        cursor.execute("ALTER SCHEMA watergeo OWNER TO watergeo_migrator")
        cursor.execute("REVOKE ALL ON SCHEMA watergeo FROM PUBLIC")
        cursor.execute("GRANT USAGE ON SCHEMA watergeo TO watergeo_app, watergeo_ingest")
        cursor.execute(
            """
            ALTER DEFAULT PRIVILEGES FOR ROLE watergeo_migrator IN SCHEMA watergeo
            GRANT SELECT ON TABLES TO watergeo_app
            """
        )


@contextmanager
def _savepoint(connection: Connection[tuple[object, ...]]) -> Iterator[None]:
    with connection.transaction():
        yield


def _must_be_denied(connection: Connection[tuple[object, ...]], statement: str) -> None:
    try:
        with _savepoint(connection), connection.cursor() as cursor:
            cursor.execute(statement)
    except (InsufficientPrivilege, ReadOnlySqlTransaction):
        return
    raise RuntimeError(f"Privilege verification unexpectedly allowed: {statement}")


def verify(environment: Mapping[str, str]) -> None:
    parameters = ConnectionParameters.from_environment(environment)
    passwords = role_passwords(environment)
    with (
        parameters.connect(DATABASE_NAME, parameters.admin_user, parameters.admin_password) as db,
        db.cursor() as cursor,
    ):
        cursor.execute("SELECT public.PostGIS_Version()")
        cursor.fetchone()
        cursor.execute(
            """
            SELECT rolname, rolsuper, rolcreatedb, rolcreaterole, rolreplication
            FROM pg_roles WHERE rolname = ANY(%s) ORDER BY rolname
            """,
            (list(ROLES),),
        )
        rows = cursor.fetchall()
        if len(rows) != len(ROLES) or any(any(row[1:]) for row in rows):
            raise RuntimeError("WaterGeo roles are missing or hold elevated cluster privileges")
        cursor.execute(
            """
            SELECT tablename
            FROM pg_catalog.pg_tables
            WHERE schemaname = 'watergeo' AND tablename <> 'alembic_version'
            ORDER BY tablename
            """
        )
        tables = [str(row[0]) for row in cursor.fetchall()]
        if not tables:
            raise RuntimeError("No migrated WaterGeo tables were found")
        for role, allowed in (
            ("watergeo_app", {"SELECT"}),
            ("watergeo_ingest", {"SELECT", "INSERT"}),
        ):
            for table in tables:
                qualified = f"watergeo.{table}"
                for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE"):
                    cursor.execute(
                        "SELECT has_table_privilege(%s, %s, %s)",
                        (role, qualified, privilege),
                    )
                    actual = cursor.fetchone()
                    if actual != (privilege in allowed,):
                        raise RuntimeError(
                            f"{role} has an unexpected {privilege} result on {qualified}"
                        )
            cursor.execute("SELECT has_schema_privilege(%s, 'watergeo', 'USAGE')", (role,))
            if cursor.fetchone() != (True,):
                raise RuntimeError(f"{role} lacks watergeo schema usage")
            cursor.execute("SELECT has_schema_privilege(%s, 'watergeo', 'CREATE')", (role,))
            if cursor.fetchone() != (False,):
                raise RuntimeError(f"{role} can create in the watergeo schema")
            cursor.execute("SELECT has_database_privilege(%s, 'watergeo', 'TEMP')", (role,))
            if cursor.fetchone() != (False,):
                raise RuntimeError(f"{role} can create temporary database objects")

    for role in ROLES:
        with parameters.connect(DATABASE_NAME, role, passwords[role]) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT current_user")
                if cursor.fetchone() != (role,):
                    raise RuntimeError(f"Could not authenticate as {role}")
            if role == "watergeo_app":
                _must_be_denied(
                    connection, "CREATE TABLE watergeo.__watergeo_privilege_probe(id int)"
                )
                _must_be_denied(
                    connection,
                    "UPDATE watergeo.alembic_version SET version_num = version_num",
                )
            elif role == "watergeo_ingest":
                _must_be_denied(
                    connection, "CREATE TABLE watergeo.__watergeo_privilege_probe(id int)"
                )
                _must_be_denied(
                    connection,
                    "UPDATE watergeo.alembic_version SET version_num = version_num",
                )
                _must_be_denied(connection, "DELETE FROM watergeo.alembic_version WHERE false")
            else:
                with connection.transaction(), connection.cursor() as cursor:
                    cursor.execute("CREATE TABLE watergeo.__watergeo_privilege_probe(id int)")
                    cursor.execute("DROP TABLE watergeo.__watergeo_privilege_probe")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("provision", "verify"))
    arguments = parser.parse_args(argv)
    if arguments.action == "provision":
        provision(os.environ)
    else:
        verify(os.environ)
    print(f"Production database {arguments.action} completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
