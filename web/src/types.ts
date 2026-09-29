import type { Geometry } from "geojson";

export type LayerId =
  | "hydrology"
  | "rainfall"
  | "water-quality"
  | "flood-warnings"
  | "bathing-waters"
  | "reservoirs"
  | "thames-discharge"
  | "water-supply";

export interface PointGeometry {
  type: "Point";
  coordinates: [number, number];
}

export interface DatasetProvenance {
  snapshot_id: string;
  publisher: string;
  attribution: string;
  licence: string;
  licence_url?: string;
  retrieval_completed_at: string;
  caveat?: string;
  freshness_caveat?: string;
  edition?: string;
}

export interface HydrologyStation {
  station_id: string;
  source_uri: string;
  labels: string[];
  location_status: "available" | "unavailable";
  latitude: number | null;
  longitude: number | null;
  geometry: PointGeometry | null;
  distance_m: number | null;
}

export interface HydrologyMeasure {
  measure_id: string;
  parameter: string;
  unit_name: string;
  latest_observation: { value: number | null; observed_at: string } | null;
}

export interface HydrologyDetail extends HydrologyStation {
  dataset: DatasetProvenance;
  measures: HydrologyMeasure[];
}

export interface SamplingPoint {
  sampling_point_id: string;
  source_uri: string;
  alt_label: string;
  pref_label: string | null;
  latitude: number | null;
  longitude: number | null;
  geometry: PointGeometry | null;
  location_status: "available" | "unavailable";
  distance_m: number | null;
}

export interface SamplingPointDetail extends SamplingPoint {
  dataset: DatasetProvenance;
  publisher_metadata: Record<string, unknown>;
}

export interface ReservoirReading {
  observed_at: string;
  current_level: number;
  current_level_unit: string;
  current_percentage: number;
}

export interface Reservoir {
  reservoir_id: string;
  name: string;
  latitude: number;
  longitude: number;
  geometry: PointGeometry;
  capacity: number;
  capacity_unit: string;
  distance_m: number | null;
  latest_reading: ReservoirReading | null;
}

export interface ReservoirDetail extends Reservoir {
  dataset: DatasetProvenance;
}

export type ThamesAlertStatus = "Discharging" | "Not discharging" | "Offline";

export interface ThamesDischargeSite {
  site_id: string;
  location_name: string;
  permit_number: string;
  grid_reference: string;
  easting: number;
  northing: number;
  geometry: PointGeometry;
  receiving_watercourse: string;
  alert_status: ThamesAlertStatus;
  status_changed: string;
  alert_past_48_hours: boolean;
  most_recent_discharge_start: string | null;
  most_recent_discharge_stop: string | null;
  distance_m: number | null;
}

export interface ThamesDischargeDetail extends ThamesDischargeSite {
  dataset: DatasetProvenance;
}

export interface RainfallStation {
  station_id: string;
  publisher_uri: string;
  display_name: string | null;
  latitude: number | null;
  longitude: number | null;
  grid_reference: string | null;
  latest_observed_at: string | null;
  latest_value_mm: number | null;
  latest_value: number | null;
  latest_unit: string | null;
  latest_period_seconds: number | null;
  distance_m: number | null;
}

export interface BathingWater {
  bathing_water_id: string;
  publisher_uri: string;
  name: string;
  latitude: number;
  longitude: number;
  classification: string | null;
  assessment_year: number | null;
  latest_sample_uri: string | null;
  latest_risk_prediction: unknown;
  distance_m: number | null;
}

export interface FloodArea {
  area_id: string;
  label: string;
  description: string;
  county: string;
  river_or_sea: string | null;
  geometry: Geometry;
  warning_id: string | null;
  severity: string | null;
  severity_level: number | null;
  message: string | null;
  time_raised: string | null;
  time_message_changed: string | null;
  time_severity_changed: string | null;
}

export type SearchKind = LayerId | "water-body";

export interface SearchResult {
  kind: SearchKind;
  identity: string;
  label: string;
  context: string;
  publisher: string;
  snapshot_id: string;
  longitude: number | null;
  latitude: number | null;
}

export interface SearchResponse {
  query: string;
  items: SearchResult[];
  truncated: boolean;
  available_kinds: SearchKind[];
  unavailable_kinds: SearchKind[];
}

export interface NearbyPage<T> {
  dataset: DatasetProvenance;
  items: T[];
  next_after_id: string | null;
  spatial_exclusion_note?: string | null;
}

export interface NationalDetail<T> {
  dataset: DatasetProvenance;
  item: T;
}

export interface CompanyPerformance {
  company_id: string;
  company_name: string;
  boundary_company_acronym: string | null;
  measures: Array<{
    reporting_period: string;
    measure_code: string;
    measure_name: string;
    value: number | null;
    value_state: "reported" | "missing" | "not_applicable";
    unit: string | null;
    definition: string | null;
    publication: string;
  }>;
}

export interface AreaSummary {
  source_id: number;
  area_served: string | null;
  company: string | null;
  company_acronym: string | null;
  company_type: string | null;
  area_type: string | null;
  warnings: string | null;
  transformed: boolean;
}

export interface AreaPage {
  snapshot_id: string;
  items: AreaSummary[];
  next_after_id: number | null;
}

export interface AreaFeature {
  type: "Feature";
  id: number;
  properties: AreaSummary & {
    snapshot_id: string;
    geometry_url: string;
    licence_statement: string | null;
    source_provenance: string | null;
    disclaimer: string | null;
    premises_disclaimer: string | null;
    coastline_disclaimer: string | null;
  };
  geometry: {
    type: "MultiPolygon";
    coordinates: number[][][][];
  };
  presentation: {
    policy_version: string;
    review_reference: string;
    method: "reprojection" | "post_transform_structure";
  };
}

export interface CatchmentDataset extends DatasetProvenance {
  source_url: string;
  plan_version: "c3-plan";
  relationship_caveat: string;
}

export interface WaterBody {
  water_body_id: string;
  operational_catchment_id: string;
  management_catchment_id: string;
  river_basin_district_id: string;
  name: string;
  water_body_type: string | null;
  publisher_uri: string;
}

export interface WaterBodyPage {
  dataset: CatchmentDataset;
  items: WaterBody[];
  next_after_id: string | null;
}

export interface WaterBodyDetail extends WaterBody {
  snapshot_id: string;
  geometry_url: string;
}

export interface GeoJSONFeatureCollection {
  type: "FeatureCollection";
  water_body_id?: string;
  snapshot_id?: string;
  features: Array<{
    type: "Feature";
    id?: string | number;
    geometry: Geometry;
    properties: Record<string, unknown>;
  }>;
}

export type SourceAvailability = "available" | "unavailable";
export type Freshness = "current" | "stale" | "unknown" | "not_applicable";

export interface SourceStatus {
  source: string;
  semantics: "versioned_release" | "dynamic_snapshot" | "bounded_history" | "versioned_plan";
  availability: SourceAvailability;
  snapshot_id: string | null;
  retrieval_freshness: Freshness;
  observation_freshness: Freshness;
  retrieved_at: string | null;
  observation_newest_at: string | null;
  caveat: string;
}

export interface SourceStatuses {
  checked_at: string;
  sources: SourceStatus[];
}

export type SelectedFeature =
  | { kind: "hydrology"; item: HydrologyStation; dataset: DatasetProvenance }
  | { kind: "water-quality"; item: SamplingPoint; dataset: DatasetProvenance }
  | { kind: "reservoirs"; item: Reservoir; dataset: DatasetProvenance }
  | { kind: "thames-discharge"; item: ThamesDischargeSite; dataset: DatasetProvenance }
  | { kind: "rainfall"; item: RainfallStation; dataset: DatasetProvenance }
  | { kind: "bathing-waters"; item: BathingWater; dataset: DatasetProvenance }
  | { kind: "flood-warnings"; item: FloodArea; dataset: DatasetProvenance }
  | {
      kind: "water-supply";
      item: AreaFeature;
      performance?: NationalDetail<CompanyPerformance> | null;
    }
  | {
      kind: "water-body";
      item: WaterBodyDetail;
      dataset: CatchmentDataset;
      geometry: GeoJSONFeatureCollection;
    };
