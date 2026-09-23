"""Immutable scoped Water Quality observations with determinand/unit evidence."""

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE watergeo.water_quality_observation_retrieval (
            id uuid PRIMARY KEY,
            sampling_point_snapshot_id uuid NOT NULL,
            sampling_point_id text NOT NULL,
            determinand_notation text NOT NULL
                CHECK (determinand_notation ~ '^[A-Za-z0-9_.-]{1,64}$'),
            date_from date NOT NULL,
            date_to date NOT NULL CHECK (date_to > date_from AND date_to - date_from <= 31),
            retrieval_started_at timestamptz NOT NULL,
            retrieval_completed_at timestamptz NOT NULL
                CHECK (retrieval_completed_at >= retrieval_started_at),
            content_sha256 text NOT NULL CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
            normalized_sha256 text NOT NULL CHECK (normalized_sha256 ~ '^[0-9a-f]{64}$'),
            normalization_version text NOT NULL,
            record_count integer NOT NULL CHECK (record_count BETWEEN 0 AND 5000),
            determinand jsonb NOT NULL CHECK (jsonb_typeof(determinand)='object'
                AND determinand->>'notation'=determinand_notation),
            manifest jsonb NOT NULL CHECK (jsonb_typeof(manifest)='object'
                AND octet_length(manifest::text) <= 2097152),
            FOREIGN KEY (sampling_point_snapshot_id, sampling_point_id)
                REFERENCES watergeo.water_quality_sampling_point(snapshot_id, sampling_point_id),
            UNIQUE (content_sha256, normalization_version),
            UNIQUE (id, sampling_point_id, determinand_notation)
        );
        CREATE INDEX water_quality_observation_retrieval_point
            ON watergeo.water_quality_observation_retrieval
            (sampling_point_id, retrieval_completed_at DESC, id DESC);
        CREATE INDEX water_quality_sampling_point_keyset
            ON watergeo.water_quality_sampling_point(snapshot_id, sampling_point_id COLLATE "C");

        CREATE TABLE watergeo.water_quality_observation_unit (
            retrieval_id uuid NOT NULL REFERENCES watergeo.water_quality_observation_retrieval(id),
            notation text NOT NULL CHECK (notation ~ '^[A-Za-z0-9_.-]{1,64}$'),
            source_fields jsonb NOT NULL CHECK (jsonb_typeof(source_fields)='object'
                AND source_fields->>'notation'=notation),
            PRIMARY KEY (retrieval_id, notation)
        );

        CREATE TABLE watergeo.water_quality_observation (
            retrieval_id uuid NOT NULL,
            observation_id text COLLATE "C" NOT NULL CHECK (length(observation_id) <= 2048),
            sampling_point_id text NOT NULL,
            determinand_notation text NOT NULL,
            sample_id text NOT NULL CHECK (length(sample_id) <= 2048),
            sampling_id text NOT NULL CHECK (length(sampling_id) <= 2048),
            observed_at_text text NOT NULL CHECK (length(observed_at_text) <= 64),
            unit_notation text NOT NULL,
            result_text text CHECK (length(result_text) <= 256),
            numeric_value double precision
                CHECK (numeric_value > '-Infinity'::float8 AND numeric_value < 'Infinity'::float8),
            upper_bound double precision
                CHECK (upper_bound > '-Infinity'::float8 AND upper_bound < 'Infinity'::float8),
            lower_bound double precision
                CHECK (lower_bound > '-Infinity'::float8 AND lower_bound < 'Infinity'::float8),
            source_fields jsonb NOT NULL CHECK (jsonb_typeof(source_fields)='object'
                AND octet_length(source_fields::text) <= 262144),
            CHECK (num_nonnulls(numeric_value, upper_bound, lower_bound) <= 1),
            PRIMARY KEY (retrieval_id, observation_id),
            FOREIGN KEY (retrieval_id, sampling_point_id, determinand_notation)
                REFERENCES watergeo.water_quality_observation_retrieval
                (id, sampling_point_id, determinand_notation),
            FOREIGN KEY (retrieval_id, unit_notation)
                REFERENCES watergeo.water_quality_observation_unit(retrieval_id, notation)
        );
        GRANT SELECT ON watergeo.water_quality_observation_retrieval,
            watergeo.water_quality_observation_unit, watergeo.water_quality_observation
            TO watergeo_app;
        GRANT SELECT, INSERT ON watergeo.water_quality_observation_retrieval,
            watergeo.water_quality_observation_unit, watergeo.water_quality_observation
            TO watergeo_ingest;
    """)


def downgrade() -> None:
    op.execute("""
        DROP INDEX watergeo.water_quality_sampling_point_keyset;
        DROP TABLE watergeo.water_quality_observation;
        DROP TABLE watergeo.water_quality_observation_unit;
        DROP TABLE watergeo.water_quality_observation_retrieval;
    """)
