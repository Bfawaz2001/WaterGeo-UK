"""Append-only Severn Trent Water reservoir-level snapshots from Stream."""

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE watergeo.stream_reservoir_snapshot (
            id uuid PRIMARY KEY,
            source_item_id text NOT NULL,
            edition text NOT NULL,
            source_item_created_at timestamptz NOT NULL,
            source_item_modified_at timestamptz NOT NULL
                CHECK (source_item_modified_at >= source_item_created_at),
            retrieval_started_at timestamptz NOT NULL,
            retrieval_completed_at timestamptz NOT NULL
                CHECK (retrieval_completed_at >= retrieval_started_at),
            content_sha256 text NOT NULL CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
            normalized_sha256 text NOT NULL CHECK (normalized_sha256 ~ '^[0-9a-f]{64}$'),
            normalization_version text NOT NULL,
            reservoir_count integer NOT NULL CHECK (reservoir_count BETWEEN 1 AND 256),
            reading_count integer NOT NULL CHECK (reading_count BETWEEN 1 AND 2000),
            manifest jsonb NOT NULL CHECK (
                jsonb_typeof(manifest)='object' AND octet_length(manifest::text) <= 2097152
            ),
            UNIQUE (content_sha256, normalization_version)
        );

        CREATE TABLE watergeo.stream_reservoir (
            snapshot_id uuid NOT NULL REFERENCES watergeo.stream_reservoir_snapshot(id),
            reservoir_id text COLLATE "C" NOT NULL
                CHECK (reservoir_id ~ '^[A-Za-z0-9_.-]{1,64}$'),
            name text NOT NULL CHECK (length(name) BETWEEN 1 AND 256),
            latitude double precision NOT NULL CHECK (
                latitude >= -90 AND latitude <= 90
                AND latitude > '-Infinity'::float8 AND latitude < 'Infinity'::float8
            ),
            longitude double precision NOT NULL CHECK (
                longitude >= -180 AND longitude <= 180
                AND longitude > '-Infinity'::float8 AND longitude < 'Infinity'::float8
            ),
            geom public.geometry(Point,4326) NOT NULL CHECK (
                NOT public.ST_IsEmpty(geom) AND public.ST_IsValid(geom)
                AND public.ST_X(geom)=longitude AND public.ST_Y(geom)=latitude
            ),
            capacity double precision NOT NULL CHECK (
                capacity > 0 AND capacity < 'Infinity'::float8
            ),
            capacity_unit text NOT NULL CHECK (capacity_unit='ML'),
            PRIMARY KEY (snapshot_id, reservoir_id)
        );
        CREATE INDEX stream_reservoir_geography
            ON watergeo.stream_reservoir USING gist ((geom::public.geography));

        CREATE TABLE watergeo.stream_reservoir_level (
            snapshot_id uuid NOT NULL,
            reservoir_id text COLLATE "C" NOT NULL,
            observed_at timestamptz NOT NULL,
            current_level double precision NOT NULL CHECK (
                current_level >= 0 AND current_level < 'Infinity'::float8
            ),
            current_level_unit text NOT NULL CHECK (current_level_unit='ML'),
            current_percentage double precision NOT NULL CHECK (
                current_percentage >= 0 AND current_percentage <= 100
                AND current_percentage > '-Infinity'::float8
                AND current_percentage < 'Infinity'::float8
            ),
            publisher_object_id integer NOT NULL CHECK (publisher_object_id > 0),
            source_fields jsonb NOT NULL CHECK (
                jsonb_typeof(source_fields)='object'
                AND octet_length(source_fields::text) <= 65536
            ),
            PRIMARY KEY (snapshot_id, reservoir_id, observed_at),
            UNIQUE (snapshot_id, publisher_object_id),
            FOREIGN KEY (snapshot_id, reservoir_id)
                REFERENCES watergeo.stream_reservoir(snapshot_id, reservoir_id)
        );

        GRANT SELECT ON watergeo.stream_reservoir_snapshot,
            watergeo.stream_reservoir, watergeo.stream_reservoir_level TO watergeo_app;
        GRANT SELECT, INSERT ON watergeo.stream_reservoir_snapshot,
            watergeo.stream_reservoir, watergeo.stream_reservoir_level TO watergeo_ingest;
    """)


def downgrade() -> None:
    op.execute("""
        DROP TABLE watergeo.stream_reservoir_level;
        DROP TABLE watergeo.stream_reservoir;
        DROP TABLE watergeo.stream_reservoir_snapshot;
    """)
