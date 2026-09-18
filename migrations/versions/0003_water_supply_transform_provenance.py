"""Record provenance for reviewed water-supply transformations."""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE watergeo.water_supply_area_transformation (
            snapshot_id uuid NOT NULL,
            source_id bigint NOT NULL,

            transformation_id text NOT NULL
                CHECK (btrim(transformation_id) <> ''),

            method text NOT NULL
                CHECK (btrim(method) <> ''),

            keep_collapsed boolean NOT NULL,

            shapely_version text NOT NULL
                CHECK (btrim(shapely_version) <> ''),

            geos_version text NOT NULL
                CHECK (btrim(geos_version) <> ''),

            invalid_reason text NOT NULL
                CHECK (btrim(invalid_reason) <> ''),

            source_decoded_wkb_sha256 text NOT NULL
                CHECK (
                    source_decoded_wkb_sha256
                    ~ '^[0-9a-f]{64}$'
                ),

            canonical_wkb_sha256 text NOT NULL
                CHECK (
                    canonical_wkb_sha256
                    ~ '^[0-9a-f]{64}$'
                ),

            review_status text NOT NULL
                CHECK (btrim(review_status) <> ''),

            review_reason text NOT NULL
                CHECK (btrim(review_reason) <> ''),

            review_reference text NOT NULL
                CHECK (btrim(review_reference) <> ''),

            details jsonb NOT NULL
                CHECK (jsonb_typeof(details) = 'object'),

            transformed_at timestamptz NOT NULL
                DEFAULT transaction_timestamp(),

            PRIMARY KEY (snapshot_id, source_id),

            FOREIGN KEY (snapshot_id, source_id)
                REFERENCES watergeo.water_supply_area(
                    snapshot_id,
                    source_id
                )
        )
    """)

    op.execute("""
        GRANT SELECT
        ON watergeo.water_supply_area_transformation
        TO watergeo_app
    """)

    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_roles
                WHERE rolname = 'watergeo_ingest'
            ) THEN
                RAISE EXCEPTION
                    'watergeo_ingest role is missing; '
                    'bootstrap database roles before running migration 0003';
            END IF;
        END
        $$
    """)

    op.execute("""
        GRANT SELECT, INSERT
        ON watergeo.water_supply_snapshot,
           watergeo.water_supply_area,
           watergeo.water_supply_area_transformation
        TO watergeo_ingest
    """)


def downgrade() -> None:
    op.execute("DROP TABLE watergeo.water_supply_area_transformation")
