import { api } from "./api";
import type { HydrologyMeasure } from "./types";

export interface HistoryMetadata {
  retrieval_id: string;
  measure_id: string;
  requested_from: string;
  requested_to: string;
  retrieval_started_at: string;
  retrieval_completed_at: string;
  record_count: number;
  content_sha256: string;
  normalization_version: string;
  licence: string;
}
export interface HistoryEdition extends HistoryMetadata {
  normalized_sha256: string;
}
export interface HistoryObservation {
  observed_at: string;
  value: number | null;
  source_fields: Record<string, unknown>;
}
export interface HistoryPage extends HistoryMetadata {
  observations: HistoryObservation[];
  next_after: string | null;
}
export interface HistoryDiscovery {
  measure_id: string;
  items: HistoryEdition[];
  next_after_id: string | null;
}
export const HISTORY_LIMIT = 10_000;
export const HISTORY_VERSION = "ea-hydrology-history-v1";
const uuid = /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/iu;
const hash = /^[0-9a-f]{64}$/u;
export function instant(value: string): number {
  if (
    typeof value !== "string" ||
    !/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,6})?(?:Z|[+-]\d\d:\d\d)$/u.test(
      value,
    ) ||
    !Number.isFinite(Date.parse(value))
  ) {
    throw new Error("Invalid observation timestamp");
  }
  if (
    new Date(`${value.slice(0, 10)}T00:00:00Z`).toISOString().slice(0, 10) !==
      value.slice(0, 10) ||
    Number(value.slice(11, 13)) > 23 ||
    Number(value.slice(14, 16)) > 59 ||
    Number(value.slice(17, 19)) > 59
  )
    throw new Error("Invalid observation timestamp");
  return Date.parse(value);
}
export function validateMetadata(row: HistoryMetadata, measure: string): void {
  if (
    !row ||
    !uuid.test(row.retrieval_id) ||
    row.measure_id !== measure ||
    !hash.test(row.content_sha256) ||
    typeof row.normalization_version !== "string" ||
    row.licence !== "Open Government Licence v3" ||
    !Number.isSafeInteger(row.record_count) ||
    row.record_count < 0
  ) {
    throw new Error("Incompatible historical retrieval identity or provenance");
  }
  const span = instant(row.requested_to) - instant(row.requested_from);
  if (
    span < 0 ||
    span > 31 * 86400_000 ||
    instant(row.retrieval_completed_at) < instant(row.retrieval_started_at)
  )
    throw new Error("Invalid retrieval window");
}
export function validateDiscovery(
  page: HistoryDiscovery,
  measure: string,
  seen: HistoryEdition[],
): void {
  if (
    !page ||
    page.measure_id !== measure ||
    !Array.isArray(page.items) ||
    page.items.length > 50 ||
    (page.next_after_id !== null &&
      (!uuid.test(page.next_after_id) ||
        page.next_after_id !== page.items.at(-1)?.retrieval_id))
  )
    throw new Error("Invalid retrieval discovery pagination");
  let previous = seen.at(-1);
  const ids = new Set(seen.map((row) => row.retrieval_id));
  for (const row of page.items) {
    validateMetadata(row, measure);
    if (!hash.test(row.normalized_sha256) || ids.has(row.retrieval_id))
      throw new Error("Repeated or incompatible retrieval");
    if (
      previous &&
      (instant(row.retrieval_completed_at) >
        instant(previous.retrieval_completed_at) ||
        (instant(row.retrieval_completed_at) ===
          instant(previous.retrieval_completed_at) &&
          row.retrieval_id >= previous.retrieval_id))
    )
      throw new Error("Inconsistent retrieval ordering");
    ids.add(row.retrieval_id);
    previous = row;
  }
}
export async function collectHistory(
  edition: HistoryEdition,
  signal: AbortSignal,
): Promise<HistoryObservation[]> {
  if (edition.record_count > HISTORY_LIMIT)
    throw new Error(
      "This retrieval exceeds the 10,000-observation browser limit. No partial series is displayed or exported.",
    );
  if (edition.normalization_version !== HISTORY_VERSION)
    throw new Error(
      "This historical retrieval uses an incompatible normalization version.",
    );
  const rows: HistoryObservation[] = [];
  let cursor: string | undefined;
  let bytes = 0;
  for (let pageNumber = 0; pageNumber < 10; pageNumber++) {
    signal.throwIfAborted();
    const page = await api.hydrologyHistory(
      edition.retrieval_id,
      signal,
      cursor,
    );
    signal.throwIfAborted();
    validateMetadata(page, edition.measure_id);
    for (const key of Object.keys(edition) as (keyof HistoryEdition)[]) {
      if (key !== "normalized_sha256" && page[key] !== edition[key])
        throw new Error(
          "Historical retrieval changed identity or provenance during pagination",
        );
    }
    if (!Array.isArray(page.observations) || page.observations.length > 1000)
      throw new Error("Invalid history page");
    bytes += new TextEncoder().encode(JSON.stringify(page)).byteLength;
    if (bytes > 20 * 1024 * 1024)
      throw new Error(
        "Historical observations exceeded the browser memory budget",
      );
    for (const row of page.observations) {
      const time = instant(row.observed_at);
      const fields = row.source_fields;
      const reference = fields?.measure as { "@id"?: string } | undefined;
      if (
        time < instant(edition.requested_from) ||
        time > instant(edition.requested_to) ||
        (rows.length > 0 && time <= instant(rows.at(-1)!.observed_at)) ||
        !fields ||
        typeof fields !== "object" ||
        Array.isArray(fields) ||
        reference?.["@id"] !==
          `http://environment.data.gov.uk/hydrology/id/measures/${edition.measure_id}` ||
        typeof fields.quality !== "string" ||
        (row.value === null
          ? fields.quality !== "Missing"
          : typeof row.value !== "number" ||
            !Number.isFinite(row.value) ||
            fields.quality === "Missing")
      )
        throw new Error(
          "Inconsistent, duplicate or invalid accepted observation",
        );
      rows.push(row);
    }
    if (rows.length > edition.record_count || rows.length > HISTORY_LIMIT)
      throw new Error("Historical record count exceeded");
    if (page.next_after === null) {
      if (rows.length !== edition.record_count)
        throw new Error(
          "Incomplete historical series. No partial series is displayed or exported.",
        );
      return rows;
    }
    if (
      typeof page.next_after !== "string" ||
      page.observations.length === 0 ||
      instant(page.next_after) !== instant(rows.at(-1)!.observed_at) ||
      (cursor && instant(page.next_after) <= instant(cursor))
    )
      throw new Error("Historical pagination failed to progress");
    cursor = page.next_after;
  }
  throw new Error(
    "Incomplete historical pagination. No partial series is displayed or exported.",
  );
}
function csvCell(value: unknown): string {
  const text =
    typeof value === "string"
      ? value
      : typeof value === "number" || typeof value === "boolean"
        ? String(value)
        : value === null || value === undefined
          ? ""
          : JSON.stringify(value);
  const safe = /^[\s\uFEFF]*[=+@-]/u.test(text) ? `'${text}` : text;
  return `"${safe.replaceAll('"', '""')}"`;
}
export function historyCsv(
  edition: HistoryEdition,
  measure: HydrologyMeasure,
  rows: HistoryObservation[],
  metadataSnapshot = "",
): string {
  const columns = [
    "retrieval_id",
    "measure_id",
    "observed_at",
    "value",
    "value_state",
    "unit",
    "period_seconds",
    "quality",
    "completeness",
    "source_fields_json",
    "requested_from",
    "requested_to",
    "retrieval_completed_at",
    "content_sha256",
    "normalized_sha256",
    "normalization_version",
    "publisher",
    "licence",
    "attribution",
    "metadata_snapshot_id",
  ];
  return (
    "\uFEFF" +
    columns.join(",") +
    "\r\n" +
    rows
      .map((row) =>
        [
          edition.retrieval_id,
          edition.measure_id,
          row.observed_at,
          // Numeric values are trusted finite numbers, including negative readings.
          row.value === null ? "" : row.value,
          row.value === null ? "missing" : "reported",
          measure.unit_name,
          measure.period,
          row.source_fields.quality,
          row.source_fields.completeness,
          JSON.stringify(row.source_fields),
          edition.requested_from,
          edition.requested_to,
          edition.retrieval_completed_at,
          edition.content_sha256,
          edition.normalized_sha256,
          edition.normalization_version,
          "Environment Agency",
          edition.licence,
          "© Environment Agency copyright and/or database right 2015. All rights reserved.",
          metadataSnapshot,
        ]
          .map((value, index) =>
            index === 3 && typeof value === "number"
              ? String(value)
              : csvCell(value),
          )
          .join(","),
      )
      .join("\r\n") +
    "\r\n"
  );
}
