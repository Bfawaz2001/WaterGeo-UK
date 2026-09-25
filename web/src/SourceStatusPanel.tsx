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
};

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
          {visible.map((source) => (
            <li key={source.source}>
              <span className={`status-mark status-${source.availability}`} aria-hidden="true" />
              <span>
                <strong>{LABELS[source.source]}</strong>
                <small>
                  {source.availability === "unavailable"
                    ? "Unavailable"
                    : `${source.semantics.replaceAll("_", " ")} · ${source.retrieval_freshness}`}
                </small>
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
