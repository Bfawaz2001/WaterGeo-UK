"""Append-only Thames Water discharge-status snapshots."""

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE watergeo.thames_discharge_snapshot (
            id uuid PRIMARY KEY,
            api_version text NOT NULL,
            retrieval_started_at timestamptz NOT NULL,
            retrieval_completed_at timestamptz NOT NULL
                CHECK (retrieval_completed_at >= retrieval_started_at),
            content_sha256 text NOT NULL CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
            normalized_sha256 text NOT NULL CHECK (normalized_sha256 ~ '^[0-9a-f]{64}$'),
            normalization_version text NOT NULL,
            site_count integer NOT NULL CHECK (site_count BETWEEN 1 AND 1000),
            discharging_count integer NOT NULL CHECK (discharging_count BETWEEN 0 AND site_count),
            offline_count integer NOT NULL CHECK (offline_count BETWEEN 0 AND site_count),
            manifest jsonb NOT NULL CHECK (
                jsonb_typeof(manifest)='object' AND octet_length(manifest::text) <= 524288
            ),
            UNIQUE (content_sha256, normalization_version)
        );

        CREATE TABLE watergeo.thames_discharge_site (
            snapshot_id uuid NOT NULL REFERENCES watergeo.thames_discharge_snapshot(id),
            site_id text COLLATE "C" NOT NULL CHECK (site_id ~ '^TWL[0-9]{5}$'),
            location_name text NOT NULL CHECK (length(location_name) BETWEEN 1 AND 256),
            permit_number text NOT NULL CHECK (length(permit_number) BETWEEN 1 AND 64),
            grid_reference text NOT NULL CHECK (length(grid_reference) BETWEEN 1 AND 32),
            easting double precision NOT NULL CHECK (easting BETWEEN 0 AND 700000),
            northing double precision NOT NULL CHECK (northing BETWEEN 0 AND 1300000),
            geom public.geometry(Point,4326) NOT NULL CHECK (
                NOT public.ST_IsEmpty(geom) AND public.ST_IsValid(geom)
            ),
            receiving_watercourse text NOT NULL
                CHECK (length(receiving_watercourse) BETWEEN 1 AND 256),
            alert_status text NOT NULL CHECK (
                alert_status IN ('Discharging','Not discharging','Offline')
            ),
            status_changed timestamp without time zone NOT NULL,
            alert_past_48_hours boolean NOT NULL,
            most_recent_discharge_start timestamp without time zone,
            most_recent_discharge_stop timestamp without time zone,
            source_fields jsonb NOT NULL CHECK (
                jsonb_typeof(source_fields)='object'
                AND octet_length(source_fields::text) <= 65536
            ),
            PRIMARY KEY (snapshot_id, site_id),
            CHECK (most_recent_discharge_stop IS NULL OR (
                most_recent_discharge_start IS NOT NULL
                AND most_recent_discharge_stop >= most_recent_discharge_start
            ))
        );
        CREATE INDEX thames_discharge_site_geography
            ON watergeo.thames_discharge_site USING gist ((geom::public.geography));
        GRANT SELECT ON watergeo.thames_discharge_snapshot,
            watergeo.thames_discharge_site TO watergeo_app;
        GRANT SELECT, INSERT ON watergeo.thames_discharge_snapshot,
            watergeo.thames_discharge_site TO watergeo_ingest;
    """)


def downgrade() -> None:
    op.execute("""
        DROP TABLE watergeo.thames_discharge_site;
        DROP TABLE watergeo.thames_discharge_snapshot;
    """)
