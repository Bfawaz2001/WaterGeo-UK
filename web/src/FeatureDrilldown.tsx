import { useEffect, useState } from "react";
import { api } from "./api";
import type { SelectedFeature } from "./types";

export function FeatureDrilldown({ selected }: { selected: SelectedFeature }) {
  const [rows, setRows] = useState<Array<{ id: string; label: string; value: string }> | null>(null);
  const [error, setError] = useState(false);
  const [parameter, setParameter] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    void (async () => {
      try {
        let result: Array<{ id: string; label: string; value: string }> = [];
        if (selected.kind === "hydrology") {
          const detail = await api.hydrologyDetail(selected.item.station_id, controller.signal);
          if (detail.dataset.snapshot_id !== selected.dataset.snapshot_id) throw new Error("Snapshot changed");
          result = detail.measures.map((measure) => ({ id: measure.measure_id, label: measure.parameter, value: measure.latest_observation ? `${measure.latest_observation.value ?? "Missing"} ${measure.unit_name} · ${measure.latest_observation.observed_at}` : "No accepted observation" }));
        } else if (selected.kind === "water-quality") {
          const detail = await api.samplingPointDetail(selected.item.sampling_point_id, selected.dataset.snapshot_id, controller.signal);
          if (detail.dataset.snapshot_id !== selected.dataset.snapshot_id) throw new Error("Snapshot changed");
          result = Object.entries(detail.publisher_metadata).map(([key, value]) => ({ id: key, label: key, value: typeof value === "string" ? value : JSON.stringify(value) }));
        } else if (selected.kind === "reservoirs") {
          const page = await api.reservoirReadings(selected.item.reservoir_id, selected.dataset.snapshot_id, controller.signal);
          if (page.dataset.snapshot_id !== selected.dataset.snapshot_id) throw new Error("Snapshot changed");
          result = page.items.map((reading) => ({ id: reading.observed_at, label: reading.observed_at, value: `${reading.current_percentage}% · ${reading.current_level} ${reading.current_level_unit}` }));
        }
        if (!controller.signal.aborted) { setRows(result); setError(false); }
      } catch { if (!controller.signal.aborted) setError(true); }
    })();
    return () => controller.abort();
  }, [selected]);
  if (selected.kind === "water-supply" || selected.kind === "water-body") return null;
  if (error) return <p role="alert">Details unavailable or snapshot changed. Reselect a current result to retry.</p>;
  if (!rows) return <p role="status">Loading source details…</p>;
  return <section aria-label="Source detail drill-down">
    <h3>{selected.kind === "hydrology" ? "Measures and latest accepted observations" : selected.kind === "reservoirs" ? "First 20 dated readings in this edition" : "Publisher sampling metadata"}</h3>
    {selected.kind === "hydrology" && <label>Measurement type at this station <select value={parameter} onChange={(event) => setParameter(event.target.value)}><option value="">All measures</option>{[...new Set(rows.map((row) => row.label))].map((label) => <option key={label}>{label}</option>)}</select></label>}
    {rows.length === 0 && <p>No accepted detail records.</p>}
    <dl>{rows.filter((row) => !parameter || row.label === parameter).map((row) => <div key={row.id}><dt>{row.label}</dt><dd>{row.value}</dd></div>)}</dl>
  </section>;
}
