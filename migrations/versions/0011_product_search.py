"""Add bounded product-search indexes.

Revision ID: 0011
Revises: 0010
"""

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE INDEX hydrology_station_search_name
            ON watergeo.hydrology_station
            (snapshot_id, (lower(COALESCE(labels->>0, ''))) text_pattern_ops);
        CREATE INDEX hydrology_station_search_identity
            ON watergeo.hydrology_station
            (snapshot_id, (lower(station_id)) text_pattern_ops);
        CREATE INDEX water_quality_sampling_point_search_name
            ON watergeo.water_quality_sampling_point
            (snapshot_id, (lower(COALESCE(pref_label, alt_label))) text_pattern_ops);
        CREATE INDEX water_quality_sampling_point_search_identity
            ON watergeo.water_quality_sampling_point
            (snapshot_id, (lower(sampling_point_id)) text_pattern_ops);
        CREATE INDEX stream_reservoir_search_name
            ON watergeo.stream_reservoir
            (snapshot_id, (lower(name)) text_pattern_ops);
        CREATE INDEX stream_reservoir_search_identity
            ON watergeo.stream_reservoir
            (snapshot_id, (lower(reservoir_id)) text_pattern_ops);
        CREATE INDEX thames_discharge_search_name
            ON watergeo.thames_discharge_site
            (snapshot_id, (lower(location_name)) text_pattern_ops);
        CREATE INDEX thames_discharge_search_identity
            ON watergeo.thames_discharge_site
            (snapshot_id, (lower(site_id)) text_pattern_ops);
        CREATE INDEX catchment_water_body_search_name
            ON watergeo.catchment_water_body
            (snapshot_id, (lower(name)) text_pattern_ops);
        CREATE INDEX catchment_water_body_search_identity
            ON watergeo.catchment_water_body
            (snapshot_id, (lower(water_body_id)) text_pattern_ops);
        CREATE INDEX water_supply_area_search_company
            ON watergeo.water_supply_area
            (snapshot_id, (lower(COALESCE(source_fields->>'COMPANY', ''))) text_pattern_ops);
        CREATE INDEX water_supply_area_search_served
            ON watergeo.water_supply_area
            (snapshot_id, (lower(COALESCE(source_fields->>'AreaServed', ''))) text_pattern_ops);
        CREATE INDEX water_supply_area_search_identity
            ON watergeo.water_supply_area
            (snapshot_id, ((source_id)::text) text_pattern_ops);
    """)


def downgrade() -> None:
    op.execute("""
        DROP INDEX IF EXISTS watergeo.water_supply_area_search_identity;
        DROP INDEX IF EXISTS watergeo.water_supply_area_search_served;
        DROP INDEX IF EXISTS watergeo.water_supply_area_search_company;
        DROP INDEX IF EXISTS watergeo.catchment_water_body_search_identity;
        DROP INDEX IF EXISTS watergeo.catchment_water_body_search_name;
        DROP INDEX IF EXISTS watergeo.thames_discharge_search_identity;
        DROP INDEX IF EXISTS watergeo.thames_discharge_search_name;
        DROP INDEX IF EXISTS watergeo.stream_reservoir_search_identity;
        DROP INDEX IF EXISTS watergeo.stream_reservoir_search_name;
        DROP INDEX IF EXISTS watergeo.water_quality_sampling_point_search_identity;
        DROP INDEX IF EXISTS watergeo.water_quality_sampling_point_search_name;
        DROP INDEX IF EXISTS watergeo.hydrology_station_search_identity;
        DROP INDEX IF EXISTS watergeo.hydrology_station_search_name;
    """)
