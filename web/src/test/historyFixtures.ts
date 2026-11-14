import type {
  HistoryEdition,
  HistoryObservation,
  HistoryPage,
} from "../historicalObservations";
import type { HydrologyMeasure } from "../types";
export const historyMeasure: HydrologyMeasure = {
  measure_id: "level-1",
  parameter: "level",
  unit_name: "m",
  period: 900,
  source_fields: {},
  latest_observation: null,
};
export const historyEdition: HistoryEdition = {
  retrieval_id: "11111111-1111-4111-8111-111111111111",
  measure_id: "level-1",
  requested_from: "2026-10-01T00:00:00Z",
  requested_to: "2026-10-02T00:00:00Z",
  retrieval_started_at: "2026-10-03T00:00:00Z",
  retrieval_completed_at: "2026-10-03T00:01:00Z",
  record_count: 3,
  content_sha256: "a".repeat(64),
  normalized_sha256: "b".repeat(64),
  normalization_version: "ea-hydrology-history-v1",
  licence: "Open Government Licence v3",
};
export function observation(
  time: string,
  value: number | null,
): HistoryObservation {
  return {
    observed_at: time,
    value,
    source_fields: {
      measure: {
        "@id": "http://environment.data.gov.uk/hydrology/id/measures/level-1",
      },
      quality: value === null ? "Missing" : "Unchecked",
      completeness: "Complete",
    },
  };
}
export const historyRows = [
  observation("2026-10-01T00:00:00Z", 0),
  observation("2026-10-01T00:15:00Z", null),
  observation("2026-10-01T01:00:00Z", -2),
];
export function historyPage(
  rows = historyRows,
  next: string | null = null,
): HistoryPage {
  return { ...historyEdition, observations: rows, next_after: next };
}
