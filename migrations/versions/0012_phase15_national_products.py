"""Phase 15 national rainfall, flood, bathing-water and performance products."""

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE watergeo.national_source_snapshot (
            id uuid PRIMARY KEY,
            source_key text NOT NULL CHECK (source_key IN (
                'rainfall','flood-monitoring','bathing-waters','company-performance'
            )),
            retrieval_started_at timestamptz NOT NULL,
            retrieval_completed_at timestamptz NOT NULL
                CHECK (retrieval_completed_at >= retrieval_started_at),
            content_sha256 text NOT NULL CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
            normalized_sha256 text NOT NULL CHECK (normalized_sha256 ~ '^[0-9a-f]{64}$'),
            normalization_version text NOT NULL,
            entity_count integer NOT NULL CHECK (
                entity_count >= 0 AND (source_key='flood-monitoring' OR entity_count > 0)
            ),
            secondary_count integer NOT NULL CHECK (secondary_count >= 0),
            skipped_count integer NOT NULL CHECK (skipped_count >= 0),
            manifest jsonb NOT NULL CHECK (jsonb_typeof(manifest)='object'),
            UNIQUE (source_key, content_sha256, normalization_version)
        );
        CREATE INDEX national_source_snapshot_current
            ON watergeo.national_source_snapshot (source_key, retrieval_completed_at DESC, id DESC);

        CREATE TABLE watergeo.rainfall_station (
            snapshot_id uuid NOT NULL REFERENCES watergeo.national_source_snapshot(id),
            station_id text COLLATE "C" NOT NULL,
            publisher_uri text NOT NULL,
            display_name text,
            geom public.geometry(Point,4326) CHECK (geom IS NULL OR public.ST_IsValid(geom)),
            grid_reference text,
            latest_observed_at timestamptz,
            latest_value_mm double precision CHECK (latest_value_mm >= 0),
            latest_value double precision CHECK (latest_value >= 0),
            latest_unit text,
            latest_period_seconds integer CHECK (latest_period_seconds > 0),
            source_fields jsonb NOT NULL,
            PRIMARY KEY (snapshot_id, station_id)
        );
        CREATE INDEX rainfall_station_geography
            ON watergeo.rainfall_station USING gist ((geom::public.geography))
            WHERE geom IS NOT NULL;

        CREATE TABLE watergeo.flood_area (
            snapshot_id uuid NOT NULL REFERENCES watergeo.national_source_snapshot(id),
            area_id text COLLATE "C" NOT NULL,
            publisher_uri text NOT NULL,
            label text NOT NULL,
            description text NOT NULL,
            county text NOT NULL,
            river_or_sea text,
            centroid public.geometry(Point,4326) NOT NULL,
            geom public.geometry(Geometry,4326) NOT NULL CHECK (
                public.GeometryType(geom) IN ('POLYGON','MULTIPOLYGON')
                AND public.ST_IsValid(geom) AND NOT public.ST_IsEmpty(geom)
            ),
            geometry_policy jsonb NOT NULL CHECK (jsonb_typeof(geometry_policy)='object'),
            source_fields jsonb NOT NULL,
            PRIMARY KEY (snapshot_id, area_id)
        );
        CREATE INDEX flood_area_geography ON watergeo.flood_area USING gist (geom);

        CREATE TABLE watergeo.flood_warning (
            snapshot_id uuid NOT NULL REFERENCES watergeo.national_source_snapshot(id),
            warning_id text COLLATE "C" NOT NULL,
            area_id text COLLATE "C" NOT NULL,
            description text NOT NULL,
            severity text NOT NULL,
            severity_level integer NOT NULL CHECK (severity_level BETWEEN 1 AND 4),
            message text,
            is_tidal boolean,
            time_raised timestamptz NOT NULL,
            time_message_changed timestamptz NOT NULL,
            time_severity_changed timestamptz NOT NULL,
            source_fields jsonb NOT NULL,
            PRIMARY KEY (snapshot_id, warning_id),
            FOREIGN KEY (snapshot_id, area_id)
                REFERENCES watergeo.flood_area(snapshot_id, area_id)
        );

        CREATE TABLE watergeo.bathing_water (
            snapshot_id uuid NOT NULL REFERENCES watergeo.national_source_snapshot(id),
            bathing_water_id text COLLATE "C" NOT NULL,
            publisher_uri text NOT NULL,
            name text NOT NULL,
            geom public.geometry(Point,4326) NOT NULL CHECK (public.ST_IsValid(geom)),
            classification text,
            assessment_year integer CHECK (assessment_year BETWEEN 1988 AND 2200),
            latest_sample_uri text,
            latest_risk_prediction jsonb,
            source_fields jsonb NOT NULL,
            PRIMARY KEY (snapshot_id, bathing_water_id)
        );
        CREATE INDEX bathing_water_geography
            ON watergeo.bathing_water USING gist ((geom::public.geography));

        CREATE TABLE watergeo.company_performance_company (
            snapshot_id uuid NOT NULL REFERENCES watergeo.national_source_snapshot(id),
            company_id text COLLATE "C" NOT NULL,
            company_name text NOT NULL,
            boundary_company_acronym text,
            PRIMARY KEY (snapshot_id, company_id)
        );
        CREATE TABLE watergeo.company_performance_measure (
            snapshot_id uuid NOT NULL REFERENCES watergeo.national_source_snapshot(id),
            company_id text COLLATE "C" NOT NULL,
            reporting_period text COLLATE "C" NOT NULL,
            measure_code text COLLATE "C" NOT NULL,
            measure_name text NOT NULL,
            value double precision,
            value_state text NOT NULL CHECK (
                value_state IN ('reported','missing','not_applicable')
            ),
            unit text,
            definition text,
            publication text NOT NULL,
            source_fields jsonb NOT NULL,
            PRIMARY KEY (snapshot_id, company_id, reporting_period, measure_code),
            FOREIGN KEY (snapshot_id, company_id)
                REFERENCES watergeo.company_performance_company(snapshot_id, company_id),
            CHECK ((value_state='reported') = (value IS NOT NULL))
        );

        GRANT SELECT ON watergeo.national_source_snapshot, watergeo.rainfall_station,
            watergeo.flood_area, watergeo.flood_warning, watergeo.bathing_water,
            watergeo.company_performance_company, watergeo.company_performance_measure
            TO watergeo_app;
        GRANT SELECT, INSERT ON watergeo.national_source_snapshot, watergeo.rainfall_station,
            watergeo.flood_area, watergeo.flood_warning, watergeo.bathing_water,
            watergeo.company_performance_company, watergeo.company_performance_measure
            TO watergeo_ingest;
    """)


def downgrade() -> None:
    op.execute("""
        DROP TABLE watergeo.company_performance_measure;
        DROP TABLE watergeo.company_performance_company;
        DROP TABLE watergeo.bathing_water;
        DROP TABLE watergeo.flood_warning;
        DROP TABLE watergeo.flood_area;
        DROP TABLE watergeo.rainfall_station;
        DROP TABLE watergeo.national_source_snapshot;
    """)
