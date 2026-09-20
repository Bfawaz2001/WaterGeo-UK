"""Environment Agency Catchment Data Explorer Cycle 3 hierarchy snapshot."""

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE watergeo.catchment_snapshot (
            id uuid PRIMARY KEY,

            plan_version text NOT NULL
                CHECK (
                    plan_version ~ '^[A-Za-z0-9_.-]+$'
                    AND length(plan_version) <= 64
                ),

            retrieval_started_at timestamptz NOT NULL,
            retrieval_completed_at timestamptz NOT NULL,

            content_sha256 text NOT NULL
                CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),

            normalized_sha256 text NOT NULL
                CHECK (normalized_sha256 ~ '^[0-9a-f]{64}$'),

            normalization_version text NOT NULL,

            river_basin_district_count integer NOT NULL
                CHECK (river_basin_district_count >= 0),

            management_catchment_count integer NOT NULL
                CHECK (management_catchment_count >= 0),

            operational_catchment_count integer NOT NULL
                CHECK (operational_catchment_count >= 0),

            water_body_count integer NOT NULL
                CHECK (water_body_count >= 0),

            geometry_feature_count integer NOT NULL
                CHECK (geometry_feature_count >= 0),

            manifest jsonb NOT NULL
                CHECK (jsonb_typeof(manifest) = 'object'),

            CHECK (retrieval_completed_at >= retrieval_started_at),

            UNIQUE (content_sha256, normalization_version)
        );

        CREATE INDEX catchment_snapshot_latest
            ON watergeo.catchment_snapshot (
                plan_version,
                retrieval_completed_at DESC,
                id DESC
            );

        CREATE TABLE watergeo.catchment_river_basin_district (
            snapshot_id uuid NOT NULL
                REFERENCES watergeo.catchment_snapshot (id),

            river_basin_district_id text NOT NULL
                CHECK (
                    river_basin_district_id ~ '^[A-Za-z0-9_.-]+$'
                    AND length(river_basin_district_id) <= 128
                ),

            name text NOT NULL
                CHECK (
                    btrim(name) <> ''
                    AND length(name) <= 512
                ),

            publisher_uri text NOT NULL
                CHECK (
                    publisher_uri ~ '^https?://'
                    AND length(publisher_uri) <= 2048
                ),

            source_fields jsonb NOT NULL
                CHECK (jsonb_typeof(source_fields) = 'object'),

            PRIMARY KEY (snapshot_id, river_basin_district_id)
        );

        CREATE TABLE watergeo.catchment_management (
            snapshot_id uuid NOT NULL
                REFERENCES watergeo.catchment_snapshot (id),

            management_catchment_id text NOT NULL
                CHECK (
                    management_catchment_id ~ '^[A-Za-z0-9_.-]+$'
                    AND length(management_catchment_id) <= 128
                ),

            river_basin_district_id text NOT NULL,

            name text NOT NULL
                CHECK (
                    btrim(name) <> ''
                    AND length(name) <= 512
                ),

            publisher_uri text NOT NULL
                CHECK (
                    publisher_uri ~ '^https?://'
                    AND length(publisher_uri) <= 2048
                ),

            source_fields jsonb NOT NULL
                CHECK (jsonb_typeof(source_fields) = 'object'),

            PRIMARY KEY (snapshot_id, management_catchment_id),

            FOREIGN KEY (snapshot_id, river_basin_district_id)
                REFERENCES watergeo.catchment_river_basin_district (
                    snapshot_id,
                    river_basin_district_id
                ),

            UNIQUE (
                snapshot_id,
                management_catchment_id,
                river_basin_district_id
            )
        );

        CREATE INDEX catchment_management_by_rbd
            ON watergeo.catchment_management (
                snapshot_id,
                river_basin_district_id,
                management_catchment_id
            );

        CREATE TABLE watergeo.catchment_operational (
            snapshot_id uuid NOT NULL
                REFERENCES watergeo.catchment_snapshot (id),

            operational_catchment_id text NOT NULL
                CHECK (
                    operational_catchment_id ~ '^[A-Za-z0-9_.-]+$'
                    AND length(operational_catchment_id) <= 128
                ),

            management_catchment_id text NOT NULL,
            river_basin_district_id text NOT NULL,

            name text NOT NULL
                CHECK (
                    btrim(name) <> ''
                    AND length(name) <= 512
                ),

            publisher_uri text NOT NULL
                CHECK (
                    publisher_uri ~ '^https?://'
                    AND length(publisher_uri) <= 2048
                ),

            source_fields jsonb NOT NULL
                CHECK (jsonb_typeof(source_fields) = 'object'),

            PRIMARY KEY (snapshot_id, operational_catchment_id),

            FOREIGN KEY (
                snapshot_id,
                management_catchment_id,
                river_basin_district_id
            )
                REFERENCES watergeo.catchment_management (
                    snapshot_id,
                    management_catchment_id,
                    river_basin_district_id
                ),

            UNIQUE (
                snapshot_id,
                operational_catchment_id,
                management_catchment_id,
                river_basin_district_id
            )
        );

        CREATE INDEX catchment_operational_by_management
            ON watergeo.catchment_operational (
                snapshot_id,
                management_catchment_id,
                operational_catchment_id
            );

        CREATE TABLE watergeo.catchment_water_body (
            snapshot_id uuid NOT NULL
                REFERENCES watergeo.catchment_snapshot (id),

            water_body_id text NOT NULL
                CHECK (
                    water_body_id ~ '^[A-Za-z0-9_.-]+$'
                    AND length(water_body_id) <= 128
                ),

            operational_catchment_id text NOT NULL,
            management_catchment_id text NOT NULL,
            river_basin_district_id text NOT NULL,

            name text NOT NULL
                CHECK (
                    btrim(name) <> ''
                    AND length(name) <= 512
                ),

            water_body_type text
                CHECK (
                    water_body_type IS NULL
                    OR (
                        btrim(water_body_type) <> ''
                        AND length(water_body_type) <= 128
                    )
                ),
            publisher_uri text NOT NULL
                CHECK (
                    publisher_uri ~ '^https?://'
                    AND length(publisher_uri) <= 2048
                ),

            source_fields jsonb NOT NULL
                CHECK (jsonb_typeof(source_fields) = 'object'),

            PRIMARY KEY (snapshot_id, water_body_id),

            FOREIGN KEY (
                snapshot_id,
                operational_catchment_id,
                management_catchment_id,
                river_basin_district_id
            )
                REFERENCES watergeo.catchment_operational (
                    snapshot_id,
                    operational_catchment_id,
                    management_catchment_id,
                    river_basin_district_id
                )
        );

        CREATE INDEX catchment_water_body_by_operational
            ON watergeo.catchment_water_body (
                snapshot_id,
                operational_catchment_id,
                water_body_id
            );

        CREATE TABLE watergeo.catchment_water_body_geometry (
            snapshot_id uuid NOT NULL,
            water_body_id text NOT NULL,
            feature_index integer NOT NULL
                CHECK (feature_index >= 0),

            geometry_type_uri text NOT NULL
                CHECK (
                    geometry_type_uri ~ '^https?://'
                    AND length(geometry_type_uri) <= 2048
                ),

            geometry_kind text NOT NULL
                CHECK (
                    btrim(geometry_kind) <> ''
                    AND length(geometry_kind) <= 128
                ),

            geom geometry(Geometry, 4326) NOT NULL
                CHECK (NOT ST_IsEmpty(geom)),

            source_fields jsonb NOT NULL
                CHECK (jsonb_typeof(source_fields) = 'object'),

            PRIMARY KEY (
                snapshot_id,
                water_body_id,
                feature_index
            ),

            FOREIGN KEY (snapshot_id, water_body_id)
                REFERENCES watergeo.catchment_water_body (
                    snapshot_id,
                    water_body_id
                )
        );

        CREATE INDEX catchment_water_body_geometry_gix
            ON watergeo.catchment_water_body_geometry
            USING gist (geom);

        GRANT SELECT
            ON watergeo.catchment_snapshot,
               watergeo.catchment_river_basin_district,
               watergeo.catchment_management,
               watergeo.catchment_operational,
               watergeo.catchment_water_body,
               watergeo.catchment_water_body_geometry
            TO watergeo_app;

        GRANT SELECT, INSERT
            ON watergeo.catchment_snapshot,
               watergeo.catchment_river_basin_district,
               watergeo.catchment_management,
               watergeo.catchment_operational,
               watergeo.catchment_water_body,
               watergeo.catchment_water_body_geometry
            TO watergeo_ingest;
    """)


def downgrade() -> None:
    op.execute("""
        DROP TABLE watergeo.catchment_water_body_geometry;
        DROP TABLE watergeo.catchment_water_body;
        DROP TABLE watergeo.catchment_operational;
        DROP TABLE watergeo.catchment_management;
        DROP TABLE watergeo.catchment_river_basin_district;
        DROP TABLE watergeo.catchment_snapshot;
    """)
