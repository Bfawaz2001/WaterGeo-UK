"""Append-only Environment Agency hydrology retrieval snapshots."""

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE watergeo.hydrology_snapshot (
            id uuid PRIMARY KEY,
            content_sha256 text NOT NULL CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
            normalized_sha256 text NOT NULL CHECK (normalized_sha256 ~ '^[0-9a-f]{64}$'),
            normalization_version text NOT NULL,
            retrieval_started_at timestamptz NOT NULL,
            retrieval_completed_at timestamptz NOT NULL,
            manifest jsonb NOT NULL CHECK (jsonb_typeof(manifest) = 'object'),
            station_count integer NOT NULL CHECK (station_count > 0),
            station_with_location_count integer NOT NULL CHECK (station_with_location_count >= 0),
            station_without_location_count integer NOT NULL CHECK
            (station_without_location_count >= 0),
            measure_count integer NOT NULL CHECK (measure_count > 0),
            latest_observation_count integer NOT NULL CHECK (latest_observation_count >= 0),
            CHECK (station_count = station_with_location_count + station_without_location_count),
            CHECK (latest_observation_count <= measure_count),
            CHECK (retrieval_completed_at >= retrieval_started_at),
            UNIQUE (content_sha256, normalization_version)
        );
        CREATE INDEX hydrology_snapshot_latest ON watergeo.hydrology_snapshot
            (normalization_version, retrieval_completed_at DESC, id DESC);
        CREATE TABLE watergeo.hydrology_station (
            snapshot_id uuid NOT NULL REFERENCES watergeo.hydrology_snapshot(id),
            station_id text NOT NULL
                CHECK (station_id ~ '^[A-Za-z0-9_.-]+$' AND length(station_id) <= 256),
            source_uri text NOT NULL,
            labels jsonb NOT NULL CHECK (jsonb_typeof(labels) = 'array'),
            latitude double precision,
            longitude double precision,
            geom public.geometry(Point,4326),
            source_fields jsonb NOT NULL CHECK (jsonb_typeof(source_fields) = 'object'),
            PRIMARY KEY (snapshot_id, station_id),
            UNIQUE (snapshot_id, source_uri),
            CHECK (
                (latitude IS NULL AND longitude IS NULL AND geom IS NULL)
                OR (latitude IS NOT NULL AND longitude IS NOT NULL AND geom IS NOT NULL
                    AND latitude BETWEEN -90 AND 90 AND longitude BETWEEN -180 AND 180
                    AND NOT public.ST_IsEmpty(geom) AND public.ST_IsValid(geom)
                    AND public.ST_X(geom) = longitude AND public.ST_Y(geom) = latitude)
            )
        );
        CREATE INDEX hydrology_station_geography ON watergeo.hydrology_station
            USING gist ((geom::public.geography)) WHERE geom IS NOT NULL;
        CREATE TABLE watergeo.hydrology_measure (
            snapshot_id uuid NOT NULL,
            measure_id text NOT NULL
                CHECK (measure_id ~ '^[A-Za-z0-9_.-]+$' AND length(measure_id) <= 256),
            station_id text NOT NULL,
            source_uri text NOT NULL,
            parameter text NOT NULL CHECK (parameter IN ('level','flow')),
            unit_name text NOT NULL CHECK (length(unit_name) > 0),
            period integer NOT NULL CHECK (period BETWEEN 1 AND 86400),
            source_fields jsonb NOT NULL CHECK (jsonb_typeof(source_fields) = 'object'),
            PRIMARY KEY (snapshot_id, measure_id),
            UNIQUE (snapshot_id, source_uri),
            FOREIGN KEY (snapshot_id, station_id)
                REFERENCES watergeo.hydrology_station(snapshot_id, station_id)
        );
        CREATE INDEX hydrology_measure_station ON watergeo.hydrology_measure(snapshot_id,
        station_id);
        CREATE TABLE watergeo.hydrology_latest_observation (
            snapshot_id uuid NOT NULL,
            measure_id text NOT NULL,
            observed_at timestamptz NOT NULL,
            value double precision CHECK (value > '-Infinity'::float8 AND value <
            'Infinity'::float8),
            source_fields jsonb NOT NULL CHECK (jsonb_typeof(source_fields) = 'object'),
            PRIMARY KEY (snapshot_id, measure_id),
            FOREIGN KEY (snapshot_id, measure_id)
                REFERENCES watergeo.hydrology_measure(snapshot_id, measure_id)
        );
        GRANT SELECT ON watergeo.hydrology_snapshot, watergeo.hydrology_station,
            watergeo.hydrology_measure, watergeo.hydrology_latest_observation TO watergeo_app;
        GRANT SELECT, INSERT ON watergeo.hydrology_snapshot, watergeo.hydrology_station,
            watergeo.hydrology_measure, watergeo.hydrology_latest_observation TO watergeo_ingest;
    """)


def downgrade() -> None:
    op.execute("""
        DROP TABLE watergeo.hydrology_latest_observation;
        DROP TABLE watergeo.hydrology_measure;
        DROP TABLE watergeo.hydrology_station;
        DROP TABLE watergeo.hydrology_snapshot;
    """)
