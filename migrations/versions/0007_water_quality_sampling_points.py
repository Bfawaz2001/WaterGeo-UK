"""Append-only Environment Agency Water Quality sampling-point snapshots."""

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE watergeo.water_quality_snapshot (
            id uuid PRIMARY KEY,

            content_sha256 text NOT NULL
                CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),

            normalized_sha256 text NOT NULL
                CHECK (normalized_sha256 ~ '^[0-9a-f]{64}$'),

            normalization_version text NOT NULL,

            retrieval_started_at timestamptz NOT NULL,
            retrieval_completed_at timestamptz NOT NULL,

            manifest jsonb NOT NULL
                CHECK (jsonb_typeof(manifest) = 'object'),

            sampling_point_count integer NOT NULL
                CHECK (sampling_point_count > 0),

            sampling_point_with_location_count integer NOT NULL
                CHECK (sampling_point_with_location_count >= 0),

            sampling_point_without_location_count integer NOT NULL
                CHECK (sampling_point_without_location_count >= 0),

            CHECK (
                sampling_point_count =
                sampling_point_with_location_count +
                sampling_point_without_location_count
            ),

            CHECK (retrieval_completed_at >= retrieval_started_at),

            UNIQUE (content_sha256, normalization_version)
        );

        CREATE INDEX water_quality_snapshot_latest
            ON watergeo.water_quality_snapshot (
                normalization_version,
                retrieval_completed_at DESC,
                id DESC
            );

        CREATE TABLE watergeo.water_quality_sampling_point (
            snapshot_id uuid NOT NULL
                REFERENCES watergeo.water_quality_snapshot (id),

            sampling_point_id text NOT NULL
                CHECK (
                    sampling_point_id ~ '^[A-Za-z0-9_.:/ -]+$'
                    AND length(sampling_point_id) <= 256
                ),

            source_uri text NOT NULL
                CHECK (
                    source_uri ~ '^https://environment[.]data[.]gov[.]uk/water-quality/sampling-point/'
                    AND length(source_uri) <= 2048
                ),

            alt_label text NOT NULL
                CHECK (
                    btrim(alt_label) <> ''
                    AND length(alt_label) <= 2048
                ),

            pref_label text
                CHECK (
                    pref_label IS NULL
                    OR (
                        btrim(pref_label) <> ''
                        AND length(pref_label) <= 2048
                    )
                ),

            latitude double precision,
            longitude double precision,

            geom public.geometry(Point, 4326),

            status jsonb
                CHECK (
                    status IS NULL
                    OR jsonb_typeof(status) = 'object'
                ),

            sampling_point_type jsonb
                CHECK (
                    sampling_point_type IS NULL
                    OR jsonb_typeof(sampling_point_type) = 'object'
                ),

            region jsonb
                CHECK (
                    region IS NULL
                    OR jsonb_typeof(region) = 'object'
                ),

            area jsonb
                CHECK (
                    area IS NULL
                    OR jsonb_typeof(area) = 'object'
                ),

            sub_area jsonb
                CHECK (
                    sub_area IS NULL
                    OR jsonb_typeof(sub_area) = 'object'
                ),

            source_fields jsonb NOT NULL
                CHECK (jsonb_typeof(source_fields) = 'object'),

            PRIMARY KEY (
                snapshot_id,
                sampling_point_id
            ),

            UNIQUE (
                snapshot_id,
                source_uri
            ),

            CHECK (
                (
                    latitude IS NULL
                    AND longitude IS NULL
                    AND geom IS NULL
                )
                OR (
                    latitude IS NOT NULL
                    AND longitude IS NOT NULL
                    AND geom IS NOT NULL
                    AND latitude BETWEEN -90 AND 90
                    AND longitude BETWEEN -180 AND 180
                    AND NOT public.ST_IsEmpty(geom)
                    AND public.ST_IsValid(geom)
                    AND public.ST_X(geom) = longitude
                    AND public.ST_Y(geom) = latitude
                )
            )
        );

        CREATE INDEX water_quality_sampling_point_geography
            ON watergeo.water_quality_sampling_point
            USING gist ((geom::public.geography))
            WHERE geom IS NOT NULL;

        CREATE INDEX water_quality_sampling_point_status
            ON watergeo.water_quality_sampling_point (
                snapshot_id,
                ((status ->> 'notation'))
            );

        CREATE INDEX water_quality_sampling_point_type
            ON watergeo.water_quality_sampling_point (
                snapshot_id,
                ((sampling_point_type ->> 'notation'))
            );

        GRANT SELECT
            ON watergeo.water_quality_snapshot,
               watergeo.water_quality_sampling_point
            TO watergeo_app;

        GRANT SELECT, INSERT
            ON watergeo.water_quality_snapshot,
               watergeo.water_quality_sampling_point
            TO watergeo_ingest;
    """)


def downgrade() -> None:
    op.execute("""
        DROP TABLE watergeo.water_quality_sampling_point;
        DROP TABLE watergeo.water_quality_snapshot;
    """)
