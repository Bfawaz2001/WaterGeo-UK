import type { SourceStatuses } from "./types";

interface Props {
  status: SourceStatuses | null;
  error: string | null;
  loading: boolean;
}

const LABELS: Record<string, string> = {
  ofwat: "Water supply",
  hydrology: "Hydrology",
  catchments: "Catchments",
  "water-quality": "Water Quality",
  "stream-reservoir-levels": "Reservoir levels",
  "thames-discharge-status": "Thames discharge monitors",
};

function display(source: SourceStatuses["sources"][number]): { label: string; kind: string } {
  if (source.availability === "unavailable") return { label: "Not loaded", kind: "not-loaded" };
  if (source.semantics === "versioned_release" || source.semantics === "versioned_plan") {
    return { label: "Static / versioned", kind: "versioned" };
  }
  if (source.retrieval_freshness === "stale") return { label: "Stale", kind: "stale" };
  if (source.retrieval_freshness === "unknown") return { label: "Freshness unknown", kind: "unknown" };
  return { label: "Available", kind: "available" };
}

export function SourceStatusPanel({ status, error, loading }: Props) {
  const visible = status?.sources.filter((source) => source.source in LABELS) ?? [];
  return (
    <section className="panel-section status-section" aria-labelledby="status-heading">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Accepted evidence</p>
          <h2 id="status-heading">Source status</h2>
        </div>
        {status && <time dateTime={status.checked_at}>{new Date(status.checked_at).toLocaleTimeString()}</time>}
      </div>
      {loading && <p role="status">Checking WaterGeo sources…</p>}
      {error && <p className="state-error" role="alert">{error}</p>}
      {visible.length > 0 && (
        <ul className="status-list">
          {visible.map((source) => {
            const state = display(source);
            return <li key={source.source} aria-label={`${LABELS[source.source]}: ${state.label}`}>
              <span className={`status-mark status-${state.kind}`} aria-hidden="true" />
              <span>
                <strong>{LABELS[source.source]}</strong>
                <small>{state.label}</small>
              </span>
            </li>;
          })}
        </ul>
      )}
      {visible.some((source) => source.availability === "unavailable") && (
        <p className="status-guidance">No compatible local snapshot is loaded for sources marked Not loaded.</p>
      )}
    </section>
  );
}
