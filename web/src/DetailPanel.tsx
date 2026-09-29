import { FeatureDrilldown } from "./FeatureDrilldown";
import { Icon, type IconName } from "./Icon";
import type { DatasetProvenance, SelectedFeature } from "./types";

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
  const minutes = Math.floor(Math.max(0, Date.now() - new Date(value).getTime()) / 60_000);
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
    <section className="provenance-block" aria-labelledby="provenance-heading">
      <div className="provenance-heading">
        <span className="source-seal" aria-hidden="true">i</span>
        <span><strong id="provenance-heading">Source and provenance</strong><small>{dataset.publisher}</small></span>
      </div>
      <p className="retrieval-age"><strong>WaterGeo retrieved</strong> · {retrievalAge(dataset.retrieval_completed_at)} · <time dateTime={dataset.retrieval_completed_at}>{new Date(dataset.retrieval_completed_at).toLocaleString()}</time></p>
      <p>{dataset.attribution}</p>
      <details className="technical-disclosure">
        <summary>Snapshot and licence details</summary>
        <dl>
          <div><dt>Snapshot</dt><dd><code>{dataset.snapshot_id}</code></dd></div>
          <div><dt>Licence</dt><dd>{licence ? <a href={licence} target="_blank" rel="noreferrer">{dataset.licence}</a> : dataset.licence}</dd></div>
        </dl>
      </details>
      {(dataset.caveat ?? dataset.freshness_caveat) && <p className="caveat">{dataset.caveat ?? dataset.freshness_caveat}</p>}
    </section>
  );
}

function SummaryGrid({ children }: { children: React.ReactNode }) {
  return <dl className="summary-grid">{children}</dl>;
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <div><dt>{label}</dt><dd>{children}</dd></div>;
}

const ICONS: Record<SelectedFeature["kind"], IconName> = {
  hydrology: "hydrology",
  rainfall: "hydrology",
  "bathing-waters": "water-quality",
  "flood-warnings": "water-quality",
  "water-quality": "water-quality",
  reservoirs: "reservoirs",
  "thames-discharge": "thames-discharge",
  "water-supply": "water-supply",
  "water-body": "catchment",
};

export function DetailPanel({ selected, onClose }: Props) {
  if (!selected) {
    return <section className="detail-panel empty-detail" aria-labelledby="detail-heading"><p className="eyebrow">Selection</p><h2 id="detail-heading">Inspect a mapped feature</h2><p>Select a point, look up a water-supply area, or browse a Water Body.</p></section>;
  }

  let title: string;
  let body: React.ReactNode;
  let dataset: DatasetProvenance | null = null;
  if (selected.kind === "hydrology") {
    title = selected.item.labels[0] ?? selected.item.station_id;
    dataset = selected.dataset;
    body = <SummaryGrid><Field label="Station ID"><code>{selected.item.station_id}</code></Field><Field label="Location">{selected.item.latitude?.toFixed(5)}, {selected.item.longitude?.toFixed(5)}</Field></SummaryGrid>;
  } else if (selected.kind === "rainfall") {
    title = selected.item.display_name ?? `Rainfall station ${selected.item.station_id}`;
    dataset = selected.dataset;
    body = <><div className="metric-hero"><span><strong>{selected.item.latest_value === null ? "No latest value" : `${selected.item.latest_value} ${selected.item.latest_unit ?? "publisher unit not stated"}`}</strong><small>Publisher accumulation{selected.item.latest_period_seconds ? ` over ${selected.item.latest_period_seconds / 60} minutes` : ""}</small></span></div><SummaryGrid><Field label="Station ID"><code>{selected.item.station_id}</code></Field><Field label="Publisher observed">{selected.item.latest_observed_at ? <time dateTime={selected.item.latest_observed_at}>{new Date(selected.item.latest_observed_at).toLocaleString()}</time> : "Not supplied"}</Field><Field label="Published location">{selected.item.latitude === null || selected.item.longitude === null ? "Not published" : `${selected.item.latitude.toFixed(5)}, ${selected.item.longitude.toFixed(5)}`}</Field></SummaryGrid><p className="caveat">The publisher may omit station names and locations, and reduces published positions to a 100 m grid. WaterGeo does not infer a more precise location.</p></>;
  } else if (selected.kind === "bathing-waters") {
    title = selected.item.name;
    dataset = selected.dataset;
    body = <><div className="metric-hero"><span><strong>{selected.item.classification ?? "Classification not published"}</strong><small>{selected.item.assessment_year ? `Publisher classification for ${selected.item.assessment_year}` : "No assessment year supplied"}</small></span></div><SummaryGrid><Field label="Bathing-water ID"><code>{selected.item.bathing_water_id}</code></Field><Field label="Latest sample context">{selected.item.latest_sample_uri ? <a href={selected.item.latest_sample_uri} target="_blank" rel="noreferrer">Publisher record</a> : "Not supplied"}</Field></SummaryGrid><p className="caveat">Classification, individual samples and publisher advice are separate facts. WaterGeo does not make a safe-to-swim judgement.</p></>;
  } else if (selected.kind === "flood-warnings") {
    title = selected.item.label;
    dataset = selected.dataset;
    body = <><div className="status-hero"><span className="status-pill">{selected.item.severity ?? "No warning in this snapshot"}</span></div><p>{selected.item.message ?? selected.item.description}</p>{selected.item.time_message_changed && <SummaryGrid><Field label="Publisher message changed"><time dateTime={selected.item.time_message_changed}>{new Date(selected.item.time_message_changed).toLocaleString()}</time></Field><Field label="Flood area"><code>{selected.item.area_id}</code></Field></SummaryGrid>}<p className="caveat caveat-prominent">WaterGeo is not an emergency warning service. Use the official Environment Agency flood service for safety decisions.</p></>;
  } else if (selected.kind === "water-quality") {
    title = selected.item.pref_label ?? selected.item.alt_label;
    dataset = selected.dataset;
    body = <SummaryGrid><Field label="Sampling-point ID"><code>{selected.item.sampling_point_id}</code></Field><Field label="Location">{selected.item.latitude?.toFixed(5)}, {selected.item.longitude?.toFixed(5)}</Field></SummaryGrid>;
  } else if (selected.kind === "reservoirs") {
    title = selected.item.name;
    dataset = selected.dataset;
    body = <>
      <div className="metric-hero"><span><strong>{selected.item.latest_reading ? `${selected.item.latest_reading.current_percentage}%` : "No reading"}</strong><small>Latest publisher observation</small></span><span className="edition-badge">Dated 2025 edition</span></div>
      <SummaryGrid><Field label="Capacity">{selected.item.capacity} {selected.item.capacity_unit}</Field>{selected.item.latest_reading && <Field label="Publisher observed"><time dateTime={selected.item.latest_reading.observed_at}>{new Date(selected.item.latest_reading.observed_at).toLocaleString()}</time></Field>}</SummaryGrid>
      <p className="caveat">Percentage is publisher data from a dated edition. It is not a restriction, safety, or supply-risk classification.</p>
      <details className="technical-disclosure"><summary>Publisher identifiers</summary><SummaryGrid><Field label="Reservoir ID"><code>{selected.item.reservoir_id}</code></Field></SummaryGrid></details>
    </>;
  } else if (selected.kind === "thames-discharge") {
    title = selected.item.location_name;
    dataset = selected.dataset;
    const moments = [
      selected.item.most_recent_discharge_start && { label: "Most recent indicated discharge started", value: selected.item.most_recent_discharge_start },
      selected.item.most_recent_discharge_stop && { label: "Most recent indicated discharge stopped", value: selected.item.most_recent_discharge_stop },
      { label: `Status changed to ${selected.item.alert_status}`, value: selected.item.status_changed },
    ].filter((moment): moment is { label: string; value: string } => Boolean(moment));
    const statusClass = selected.item.alert_status.toLowerCase().replaceAll(" ", "-");
    body = <>
      <div className="status-hero"><span className={`status-pill status-${statusClass}`}>{selected.item.alert_status}</span><span>{selected.item.alert_past_48_hours ? "Activity indicated in past 48 hours" : "No activity indicated in past 48 hours"}</span></div>
      <SummaryGrid><Field label="Receiving watercourse">{selected.item.receiving_watercourse}</Field><Field label="Permit"><code>{selected.item.permit_number}</code></Field></SummaryGrid>
      <h3>Publisher status timeline</h3>
      <ol className="status-timeline">{moments.map((moment) => <li key={`${moment.label}:${moment.value}`}><strong>{moment.label}</strong><span>{moment.value.replace("T", " ")} (timezone not supplied)</span></li>)}</ol>
      <p className="caveat">EDM status indicates monitor activity. It does not measure discharge volume, water quality or bathing safety.</p>
      <details className="technical-disclosure"><summary>Publisher identifiers</summary><SummaryGrid><Field label="Site ID"><code>{selected.item.site_id}</code></Field></SummaryGrid></details>
    </>;
  } else if (selected.kind === "water-supply") {
    title = selected.item.properties.company ?? `Area ${selected.item.id}`;
    body = <>
      <div className="metric-hero water-supply-hero"><span><strong>{selected.item.properties.area_served ?? "Area served not stated"}</strong><small>Dated analytical boundary</small></span></div>
      <p className="caveat caveat-prominent">{selected.item.properties.disclaimer ?? "This dated analytical boundary does not establish a property's current legal supplier."}</p>
      {selected.item.properties.licence_statement && <p>{selected.item.properties.licence_statement}</p>}
      {selected.item.properties.source_provenance && <p className="secondary-copy">{selected.item.properties.source_provenance}</p>}
      {selected.item.properties.premises_disclaimer && <p className="caveat">{selected.item.properties.premises_disclaimer}</p>}
      {selected.item.properties.coastline_disclaimer && <p className="caveat">{selected.item.properties.coastline_disclaimer}</p>}
      {selected.performance && <section aria-labelledby="company-performance-heading"><h3 id="company-performance-heading">Company performance</h3><p>{selected.performance.item.company_name} · official published measures</p><ul>{selected.performance.item.measures.slice(0, 6).map((measure) => <li key={`${measure.measure_code}:${measure.reporting_period}`}><strong>{measure.measure_name}</strong>: {measure.value_state === "reported" ? `${measure.value ?? ""}${measure.unit ? ` ${measure.unit}` : ""}` : measure.value_state.replace("_", " ")} ({measure.reporting_period})</li>)}</ul><p className="caveat">Regulatory performance facts use their own reporting periods and do not change the dated boundary meaning.</p><Provenance dataset={selected.performance.dataset} /></section>}
      <details className="technical-disclosure"><summary>Geometry and presentation details</summary><SummaryGrid>
        <Field label="Source ID">{selected.item.id}</Field><Field label="Presentation">{selected.item.presentation.method}</Field>
        <Field label="Policy">{selected.item.presentation.policy_version}</Field><Field label="Review">{selected.item.presentation.review_reference}</Field>
        <Field label="Snapshot"><code>{selected.item.properties.snapshot_id}</code></Field>
      </SummaryGrid></details>
    </>;
  } else {
    title = selected.item.name;
    dataset = selected.dataset;
    body = <>
      <div className="metric-hero"><span><strong>{selected.item.water_body_type ?? "Type not stated"}</strong><small>Catchment Data Explorer classification</small></span><span className="edition-badge">{selected.geometry.features.length} geometry feature{selected.geometry.features.length === 1 ? "" : "s"}</span></div>
      <SummaryGrid><Field label="Operational catchment"><code>{selected.item.operational_catchment_id}</code></Field><Field label="Management catchment"><code>{selected.item.management_catchment_id}</code></Field><Field label="River basin district"><code>{selected.item.river_basin_district_id}</code></Field></SummaryGrid>
      <p className="caveat">Publisher geometry features are shown individually. No relationship to stations, sampling points, companies or reservoirs is inferred.</p>
      <details className="technical-disclosure"><summary>Publisher identifiers</summary><SummaryGrid><Field label="Water Body ID"><code>{selected.item.water_body_id}</code></Field></SummaryGrid></details>
    </>;
  }

  return (
    <section className="detail-panel" aria-labelledby="detail-heading">
      <button className="close-button" type="button" onClick={onClose} aria-label="Close selected feature details">×</button>
      <div className={`detail-kind layer-${selected.kind}`}><span className="layer-symbol"><Icon name={ICONS[selected.kind]} /></span><span>Selected {selected.kind.replaceAll("-", " ")}</span></div>
      <h2 id="detail-heading">{title}</h2>
      {body}
      {(selected.kind === "hydrology" || selected.kind === "water-quality" || selected.kind === "reservoirs") && <FeatureDrilldown key={`${selected.kind}:${selected.dataset.snapshot_id}:${selected.kind === "hydrology" ? selected.item.station_id : selected.kind === "water-quality" ? selected.item.sampling_point_id : selected.item.reservoir_id}`} selected={selected} />}
      {dataset && <Provenance dataset={dataset} />}
    </section>
  );
}
