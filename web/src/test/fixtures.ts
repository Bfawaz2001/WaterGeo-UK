import type { CatchmentDataset, DatasetProvenance, SourceStatuses } from "../types";

export const dataset: DatasetProvenance = {
  snapshot_id: "11111111-1111-4111-8111-111111111111",
  publisher: "Environment Agency",
  attribution: "Contains Environment Agency information.",
  licence: "Open Government Licence v3",
  licence_url: "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
  retrieval_completed_at: "2026-09-24T12:00:00Z",
  freshness_caveat: "Retrieval time is not observation time.",
};

export const catchmentDataset: CatchmentDataset = {
  ...dataset,
  licence: "Open Government Licence",
  source_url: "https://environment.data.gov.uk/catchment-planning/",
  plan_version: "c3-plan",
  relationship_caveat: "No station-to-catchment relationship is asserted.",
};

export const sourceStatuses: SourceStatuses = {
  checked_at: "2026-09-24T12:01:00Z",
  sources: [
    {
      source: "hydrology",
      semantics: "dynamic_snapshot",
      availability: "available",
      snapshot_id: dataset.snapshot_id,
      retrieval_freshness: "current",
      observation_freshness: "unknown",
      retrieved_at: "2026-09-24T12:00:00Z",
      observation_newest_at: null,
      caveat: "Latest values may be old.",
    },
    {
      source: "water-quality",
      semantics: "dynamic_snapshot",
      availability: "unavailable",
      snapshot_id: null,
      retrieval_freshness: "unknown",
      observation_freshness: "not_applicable",
      retrieved_at: null,
      observation_newest_at: null,
      caveat: "Unavailable.",
    },
  ],
};
