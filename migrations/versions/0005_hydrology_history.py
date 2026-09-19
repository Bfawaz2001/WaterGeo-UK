"""Append-only bounded Environment Agency hydrology history."""

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE watergeo.hydrology_history_retrieval (
            id uuid PRIMARY KEY,

            measure_id text NOT NULL
                CHECK (
                    measure_id ~ '^[A-Za-z0-9_.-]+$'
                    AND length(measure_id) <= 256
                ),

            requested_from timestamptz NOT NULL,
            requested_to timestamptz NOT NULL,

            retrieval_started_at timestamptz NOT NULL,
            retrieval_completed_at timestamptz NOT NULL,

            content_sha256 text NOT NULL
                CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),

            normalized_sha256 text NOT NULL
                CHECK (normalized_sha256 ~ '^[0-9a-f]{64}$'),

            normalization_version text NOT NULL,

            record_count integer NOT NULL
                CHECK (record_count >= 0),

            manifest jsonb NOT NULL
                CHECK (jsonb_typeof(manifest) = 'object'),

            CHECK (requested_to >= requested_from),
            CHECK (
                requested_to <= requested_from + interval '31 days'
            ),
            CHECK (
                retrieval_completed_at >= retrieval_started_at
            ),

            UNIQUE (content_sha256, normalization_version),
            UNIQUE (id, measure_id)
        );

        CREATE INDEX hydrology_history_retrieval_measure_latest
            ON watergeo.hydrology_history_retrieval (
                measure_id,
                retrieval_completed_at DESC,
                id DESC
            );

        CREATE TABLE watergeo.hydrology_historical_observation (
            retrieval_id uuid NOT NULL,
            measure_id text NOT NULL
                CHECK (
                    measure_id ~ '^[A-Za-z0-9_.-]+$'
                    AND length(measure_id) <= 256
                ),

            observed_at timestamptz NOT NULL,

            value double precision
                CHECK (
                    value > '-Infinity'::float8
                    AND value < 'Infinity'::float8
                ),

            source_fields jsonb NOT NULL
                CHECK (jsonb_typeof(source_fields) = 'object'),

            PRIMARY KEY (retrieval_id, observed_at),

            FOREIGN KEY (retrieval_id, measure_id)
                REFERENCES watergeo.hydrology_history_retrieval (
                    id,
                    measure_id
                )
        );

        GRANT SELECT
            ON watergeo.hydrology_history_retrieval,
               watergeo.hydrology_historical_observation
            TO watergeo_app;

        GRANT SELECT, INSERT
            ON watergeo.hydrology_history_retrieval,
               watergeo.hydrology_historical_observation
            TO watergeo_ingest;
    """)


def downgrade() -> None:
    op.execute("""
        DROP TABLE watergeo.hydrology_historical_observation;
        DROP TABLE watergeo.hydrology_history_retrieval;
    """)
