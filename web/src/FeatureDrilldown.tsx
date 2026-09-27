import { useEffect, useState } from "react";

import { api } from "./api";
import { TrendChart } from "./TrendChart";
import type { HydrologyMeasure, ReservoirReading, SelectedFeature } from "./types";

type Drilldown =
  | { kind: "hydrology"; measures: HydrologyMeasure[] }
  | { kind: "reservoirs"; readings: ReservoirReading[]; truncated: boolean }
  | { kind: "water-quality"; rows: Array<{ id: string; value: string }> };

export function FeatureDrilldown({ selected }: { selected: SelectedFeature }) {
  const [detail, setDetail] = useState<Drilldown | null>(null);
  const [error, setError] = useState(false);
  const [parameter, setParameter] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    void (async () => {
      try {
        let result: Drilldown;
        if (selected.kind === "hydrology") {
          const response = await api.hydrologyDetail(selected.item.station_id, controller.signal, selected.dataset.snapshot_id);
          if (response.dataset.snapshot_id !== selected.dataset.snapshot_id) throw new Error("Snapshot changed");
          result = { kind: "hydrology", measures: response.measures };
        } else if (selected.kind === "water-quality") {
          const response = await api.samplingPointDetail(selected.item.sampling_point_id, selected.dataset.snapshot_id, controller.signal);
          if (response.dataset.snapshot_id !== selected.dataset.snapshot_id) throw new Error("Snapshot changed");
          result = {
            kind: "water-quality",
            rows: Object.entries(response.publisher_metadata).map(([id, value]) => ({
              id,
              value: typeof value === "string" ? value : JSON.stringify(value),
            })),
          };
        } else if (selected.kind === "reservoirs") {
          const response = await api.reservoirReadings(selected.item.reservoir_id, selected.dataset.snapshot_id, controller.signal);
          if (response.dataset.snapshot_id !== selected.dataset.snapshot_id) throw new Error("Snapshot changed");
          result = { kind: "reservoirs", readings: response.items, truncated: response.next_after !== null };
        } else {
          return;
        }
        if (!controller.signal.aborted) { setDetail(result); setError(false); }
      } catch { if (!controller.signal.aborted) setError(true); }
    })();
    return () => controller.abort();
  }, [selected]);
  if (selected.kind === "water-supply" || selected.kind === "water-body" || selected.kind === "thames-discharge") return null;
  if (error) return <p className="state-error" role="alert">Details unavailable or snapshot changed. Reselect a current result to retry.</p>;
  if (!detail) return <p role="status">Loading source details…</p>;

  if (detail.kind === "hydrology") {
    const measures = detail.measures.filter((measure) => !parameter || measure.parameter === parameter);
    return <section aria-label="Source detail drill-down">
      <h3>Latest publisher observations</h3>
      <label>Measurement type at this station <select value={parameter} onChange={(event) => setParameter(event.target.value)}><option value="">All measures</option>{[...new Set(detail.measures.map((row) => row.parameter))].map((label) => <option key={label}>{label}</option>)}</select></label>
      {measures.length === 0 && <p>No accepted observations for this measurement type.</p>}
      <div className="observation-list">{measures.map((measure) => <article key={measure.measure_id}>
        <strong>{measure.parameter}</strong>
        <span className="observation-value">{measure.latest_observation ? `${measure.latest_observation.value ?? "Missing"} ${measure.unit_name}` : "No accepted observation"}</span>
        {measure.latest_observation && <span>Publisher observed <time dateTime={measure.latest_observation.observed_at}>{new Date(measure.latest_observation.observed_at).toLocaleString()}</time></span>}
      </article>)}</div>
      <p className="caveat">Latest values are publisher observations. WaterGeo retrieval time is shown separately under provenance.</p>
    </section>;
  }

  if (detail.kind === "reservoirs") {
    const latestFirst = [...detail.readings].sort((a, b) => b.observed_at.localeCompare(a.observed_at));
    return <section aria-label="Source detail drill-down">
      <h3>Publisher edition trend</h3>
      <TrendChart
        label="Reservoir storage percentage"
        unit="%"
        points={detail.readings.map((reading) => ({ observed_at: reading.observed_at, value: reading.current_percentage }))}
      />
      {detail.truncated && <p className="caveat">The chart is bounded to the first 100 dated values in this edition.</p>}
      <details><summary>View recent chart values</summary><dl>{latestFirst.slice(0, 8).map((reading) => <div key={reading.observed_at}><dt><time dateTime={reading.observed_at}>{new Date(reading.observed_at).toLocaleDateString()}</time></dt><dd>{reading.current_percentage}% · {reading.current_level} {reading.current_level_unit}</dd></div>)}</dl></details>
      <p className="caveat">This chart contains one dated publisher edition. It does not indicate restrictions, safety or supply risk.</p>
    </section>;
  }

  return <section aria-label="Source detail drill-down">
    <h3>Publisher sampling metadata</h3>
    {detail.rows.length === 0 && <p>No accepted metadata fields.</p>}
    <dl>{detail.rows.map((row) => <div key={row.id}><dt>{row.id.replaceAll("_", " ")}</dt><dd>{row.value}</dd></div>)}</dl>
  </section>;
}
