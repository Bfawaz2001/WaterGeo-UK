"""Create water-supply snapshots and validated source areas.

No source data is loaded. Geometry constraints deliberately use an unconstrained
PostGIS geometry column: a typmod would silently assign SRID 27700 to SRID 0 input.
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE watergeo.water_supply_snapshot (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            source_sha256 text NOT NULL CHECK (source_sha256 ~ '^[0-9a-f]{64}$'),
            source_url text NOT NULL CHECK (btrim(source_url) <> ''),
            source_bytes bigint NOT NULL CHECK (source_bytes > 0),
            retrieved_at timestamptz NOT NULL,
            publisher text NOT NULL CHECK (btrim(publisher) <> ''),
            distributor text NOT NULL CHECK (btrim(distributor) <> ''),
            licence_name text NOT NULL CHECK (btrim(licence_name) <> ''),
            licence_version text CHECK (btrim(licence_version) <> ''),
            licence_url text NOT NULL CHECK (btrim(licence_url) <> ''),
            attribution text NOT NULL CHECK (btrim(attribution) <> ''),
            transformation_version text NOT NULL CHECK (btrim(transformation_version) <> ''),
            ingested_at timestamptz NOT NULL DEFAULT transaction_timestamp(),
            CONSTRAINT water_supply_snapshot_content_transform_key
                UNIQUE (source_sha256, transformation_version)
        )
    """)
    op.execute("""
        CREATE TABLE watergeo.water_supply_area (
            snapshot_id uuid NOT NULL REFERENCES watergeo.water_supply_snapshot(id),
            source_id bigint NOT NULL,
            source_fields jsonb NOT NULL,
            geom public.geometry NOT NULL,
            PRIMARY KEY (snapshot_id, source_id),
            CONSTRAINT water_supply_area_fields_object
                CHECK (jsonb_typeof(source_fields) = 'object'),
            CONSTRAINT water_supply_area_geometry_type
                CHECK (public.GeometryType(geom) = 'MULTIPOLYGON'),
            CONSTRAINT water_supply_area_geometry_srid
                CHECK (public.ST_SRID(geom) = 27700),
            CONSTRAINT water_supply_area_geometry_dimensions
                CHECK (public.ST_NDims(geom) = 2),
            CONSTRAINT water_supply_area_geometry_not_empty
                CHECK (NOT public.ST_IsEmpty(geom)),
            CONSTRAINT water_supply_area_geometry_valid
                CHECK (public.ST_IsValid(geom, 0))
        )
    """)
    op.execute("""
        CREATE INDEX water_supply_area_geom_idx
        ON watergeo.water_supply_area USING gist (geom)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE watergeo.water_supply_area")
    op.execute("DROP TABLE watergeo.water_supply_snapshot")
