import type { DatasetProvenance, SelectedFeature } from "./types";
import { FeatureDrilldown } from "./FeatureDrilldown";

interface Props {
  selected: SelectedFeature | null;
  onClose: () => void;
}

function safePublisherUrl(value: string | undefined): string | null {
  if (!value) return null;
  try {
    const url = new URL(value);
    return url.protocol === "https:" ? url.toString() : null;
  } catch {
    return null;
  }
}

function Provenance({ dataset }: { dataset: DatasetProvenance }) {
  const licence = safePublisherUrl(dataset.licence_url);
  return (
    <div className="provenance-block">
      <h3>Source and provenance</h3>
      <dl>
        <div><dt>Publisher</dt><dd>{dataset.publisher}</dd></div>
        <div><dt>Snapshot</dt><dd><code>{dataset.snapshot_id}</code></dd></div>
        <div><dt>Retrieved</dt><dd>{new Date(dataset.retrieval_completed_at).toLocaleString()}</dd></div>
        <div>
          <dt>Licence</dt>
          <dd>{licence ? <a href={licence} target="_blank" rel="noreferrer">{dataset.licence}</a> : dataset.licence}</dd>
        </div>
      </dl>
      <p>{dataset.attribution}</p>
      {(dataset.caveat ?? dataset.freshness_caveat) && (
        <p className="caveat">{dataset.caveat ?? dataset.freshness_caveat}</p>
      )}
    </div>
  );
}

export function DetailPanel({ selected, onClose }: Props) {
  if (!selected) {
    return (
      <section className="detail-panel empty-detail" aria-labelledby="detail-heading">
        <p className="eyebrow">Selection</p>
        <h2 id="detail-heading">Inspect a mapped feature</h2>
        <p>Select a point, look up a water-supply area, or browse a Water Body.</p>
      </section>
    );
  }

  let title: string;
  let body: React.ReactNode;
  let dataset: DatasetProvenance | null = null;
  if (selected.kind === "hydrology") {
    title = selected.item.labels[0] ?? selected.item.station_id;
    dataset = selected.dataset;
    body = <dl><div><dt>Station ID</dt><dd>{selected.item.station_id}</dd></div><div><dt>Location</dt><dd>{selected.item.latitude?.toFixed(5)}, {selected.item.longitude?.toFixed(5)}</dd></div></dl>;
  } else if (selected.kind === "water-quality") {
    title = selected.item.pref_label ?? selected.item.alt_label;
    dataset = selected.dataset;
    body = <dl><div><dt>Sampling-point ID</dt><dd>{selected.item.sampling_point_id}</dd></div><div><dt>Location</dt><dd>{selected.item.latitude?.toFixed(5)}, {selected.item.longitude?.toFixed(5)}</dd></div></dl>;
  } else if (selected.kind === "reservoirs") {
    title = selected.item.name;
    dataset = selected.dataset;
    body = (
      <>
        <dl>
          <div><dt>Reservoir ID</dt><dd>{selected.item.reservoir_id}</dd></div>
          <div><dt>Publisher capacity</dt><dd>{selected.item.capacity} {selected.item.capacity_unit}</dd></div>
          <div><dt>Dated level</dt><dd>{selected.item.latest_reading ? `${selected.item.latest_reading.current_percentage}% at ${new Date(selected.item.latest_reading.observed_at).toLocaleString()}` : "No reading in this edition"}</dd></div>
        </dl>
        <p className="caveat">Percentage is publisher data from a dated edition. It is not a restriction, safety, or supply-risk classification.</p>
      </>
    );
  } else if (selected.kind === "water-supply") {
    title = selected.item.properties.company ?? `Area ${selected.item.id}`;
    body = (
      <>
        <dl>
          <div><dt>Source ID</dt><dd>{selected.item.id}</dd></div>
          <div><dt>Area served</dt><dd>{selected.item.properties.area_served ?? "Not stated"}</dd></div>
          <div><dt>Presentation</dt><dd>{selected.item.presentation.method}</dd></div>
          <div><dt>Presentation policy</dt><dd>{selected.item.presentation.policy_version}</dd></div>
          <div><dt>Review</dt><dd>{selected.item.presentation.review_reference}</dd></div>
          <div><dt>Snapshot</dt><dd><code>{selected.item.properties.snapshot_id}</code></dd></div>
        </dl>
        <p className="caveat">{selected.item.properties.disclaimer ?? "This dated analytical boundary does not establish a property's current legal supplier."}</p>
        {selected.item.properties.licence_statement && <p>{selected.item.properties.licence_statement}</p>}
        {selected.item.properties.source_provenance && <p>{selected.item.properties.source_provenance}</p>}
        {selected.item.properties.premises_disclaimer && <p className="caveat">{selected.item.properties.premises_disclaimer}</p>}
        {selected.item.properties.coastline_disclaimer && <p className="caveat">{selected.item.properties.coastline_disclaimer}</p>}
      </>
    );
  } else {
    title = selected.item.name;
    dataset = selected.dataset;
    body = (
      <>
        <dl>
          <div><dt>Water Body ID</dt><dd>{selected.item.water_body_id}</dd></div>
          <div><dt>Type</dt><dd>{selected.item.water_body_type ?? "Not stated"}</dd></div>
          <div><dt>Operational catchment</dt><dd>{selected.item.operational_catchment_id}</dd></div>
          <div><dt>Management catchment</dt><dd>{selected.item.management_catchment_id}</dd></div>
          <div><dt>River basin district</dt><dd>{selected.item.river_basin_district_id}</dd></div>
          <div><dt>Geometry features</dt><dd>{selected.geometry.features.length}</dd></div>
        </dl>
        <p className="caveat">Publisher geometry features are shown individually. No relationship to stations, sampling points, companies or reservoirs is inferred.</p>
      </>
    );
  }

  return (
    <section className="detail-panel" aria-labelledby="detail-heading">
      <button className="close-button" type="button" onClick={onClose} aria-label="Close selected feature details">×</button>
      <p className="eyebrow">Selected {selected.kind.replaceAll("-", " ")}</p>
      <h2 id="detail-heading">{title}</h2>
      {body}
      {selected.kind !== "water-supply" && selected.kind !== "water-body" && (
        <FeatureDrilldown key={`${selected.kind}:${selected.dataset.snapshot_id}:${selected.kind === "hydrology" ? selected.item.station_id : selected.kind === "water-quality" ? selected.item.sampling_point_id : selected.item.reservoir_id}`} selected={selected} />
      )}
      {dataset && <Provenance dataset={dataset} />}
    </section>
  );
}
