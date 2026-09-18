-- Runs as the administrator on FIRST initialisation of an empty volume only.
-- psql quoted variables safely handle punctuation in generated passwords.
\getenv app_password WATERGEO_DB_PASSWORD
\getenv migration_password WATERGEO_MIGRATION_PASSWORD
\getenv ingestion_password WATERGEO_INGESTION_PASSWORD

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE ROLE watergeo_migrator LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
    PASSWORD :'migration_password';
CREATE ROLE watergeo_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
    PASSWORD :'app_password';
CREATE ROLE watergeo_ingest LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
    PASSWORD :'ingestion_password';

REVOKE ALL ON DATABASE watergeo FROM PUBLIC;
GRANT CONNECT ON DATABASE watergeo TO watergeo_migrator, watergeo_app, watergeo_ingest;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
CREATE SCHEMA watergeo AUTHORIZATION watergeo_migrator;
GRANT USAGE ON SCHEMA watergeo TO watergeo_app, watergeo_ingest;
ALTER DEFAULT PRIVILEGES FOR ROLE watergeo_migrator IN SCHEMA watergeo
    GRANT SELECT ON TABLES TO watergeo_app;
ALTER ROLE watergeo_app SET default_transaction_read_only = on;
