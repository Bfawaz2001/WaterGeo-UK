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

function retrievalAge(value: string): string {
  const elapsed = Math.max(0, Date.now() - new Date(value).getTime());
  const minutes = Math.floor(elapsed / 60_000);
  if (minutes < 1) return "Retrieved less than a minute ago";
  if (minutes < 60) return `Retrieved ${minutes} minute${minutes === 1 ? "" : "s"} ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 48) return `Retrieved ${hours} hour${hours === 1 ? "" : "s"} ago`;
  const days = Math.floor(hours / 24);
  return `Retrieved ${days} day${days === 1 ? "" : "s"} ago`;
}

function Provenance({ dataset }: { dataset: DatasetProvenance }) {
  const licence = safePublisherUrl(dataset.licence_url);
  return (
    <div className="provenance-block">
      <h3>Source and provenance</h3>
      <dl>
        <div><dt>Publisher</dt><dd>{dataset.publisher}</dd></div>
        <div><dt>Snapshot</dt><dd><code>{dataset.snapshot_id}</code></dd></div>
        <div><dt>WaterGeo retrieved</dt><dd><time dateTime={dataset.retrieval_completed_at}>{new Date(dataset.retrieval_completed_at).toLocaleString()}</time><small>{retrievalAge(dataset.retrieval_completed_at)}</small></dd></div>
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
          <div><dt>Latest publisher observation</dt><dd>{selected.item.latest_reading ? `${selected.item.latest_reading.current_percentage}%` : "No reading in this edition"}</dd></div>
          {selected.item.latest_reading && <div><dt>Publisher observed</dt><dd><time dateTime={selected.item.latest_reading.observed_at}>{new Date(selected.item.latest_reading.observed_at).toLocaleString()}</time></dd></div>}
        </dl>
        <p className="caveat">Percentage is publisher data from a dated edition. It is not a restriction, safety, or supply-risk classification.</p>
      </>
    );
  } else if (selected.kind === "thames-discharge") {
    title = selected.item.location_name;
    dataset = selected.dataset;
    const moments = [
      selected.item.most_recent_discharge_start && {
        label: "Most recent indicated discharge started",
        value: selected.item.most_recent_discharge_start,
      },
      selected.item.most_recent_discharge_stop && {
        label: "Most recent indicated discharge stopped",
        value: selected.item.most_recent_discharge_stop,
      },
      { label: `Status changed to ${selected.item.alert_status}`, value: selected.item.status_changed },
    ].filter((moment): moment is { label: string; value: string } => Boolean(moment));
    body = (
      <>
        <dl>
          <div><dt>Site ID</dt><dd>{selected.item.site_id}</dd></div>
          <div><dt>Permit</dt><dd>{selected.item.permit_number}</dd></div>
          <div><dt>Receiving watercourse</dt><dd>{selected.item.receiving_watercourse}</dd></div>
          <div><dt>Monitor status</dt><dd><strong>{selected.item.alert_status}</strong></dd></div>
          <div><dt>Activity in past 48 hours</dt><dd>{selected.item.alert_past_48_hours ? "Publisher says yes" : "Publisher says no"}</dd></div>
        </dl>
        <h3>Publisher status timeline</h3>
        <ol className="status-timeline">{moments.map((moment) => <li key={`${moment.label}:${moment.value}`}><strong>{moment.label}</strong><span>{moment.value.replace("T", " ")} (timezone not supplied)</span></li>)}</ol>
        <p className="caveat">EDM status indicates monitor activity. It does not measure discharge volume, water quality or bathing safety.</p>
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
      {selected.kind !== "water-supply" && selected.kind !== "water-body" && selected.kind !== "thames-discharge" && (
        <FeatureDrilldown key={`${selected.kind}:${selected.dataset.snapshot_id}:${selected.kind === "hydrology" ? selected.item.station_id : selected.kind === "water-quality" ? selected.item.sampling_point_id : selected.item.reservoir_id}`} selected={selected} />
      )}
      {dataset && <Provenance dataset={dataset} />}
    </section>
  );
}
