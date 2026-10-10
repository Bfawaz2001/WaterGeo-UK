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
  "water-quality": "Water Quality metadata",
  "stream-reservoir-levels": "Reservoir levels",
  "thames-discharge-status": "Thames discharge monitors",
  rainfall: "Rainfall",
  "flood-monitoring": "Flood monitoring",
  "bathing-waters": "Bathing waters",
  "company-performance": "Company performance",
};

function compactAge(seconds: number | null | undefined): string | null {
  if (seconds === null || seconds === undefined || seconds < 0) return null;
  if (seconds < 60) return "under 1 min";
  if (seconds < 3600) return `${Math.floor(seconds / 60)} min`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} hr`;
  const days = Math.floor(seconds / 86400);
  return `${days} ${days === 1 ? "day" : "days"}`;
}

function ageAtRender(
  source: SourceStatuses["sources"][number],
  checkedAt: string | undefined,
): number | null {
  const initialAge = source.snapshot_age_seconds;
  if (
    initialAge === null
    || initialAge === undefined
    || !Number.isFinite(initialAge)
    || initialAge < 0
    || !checkedAt
  ) return null;
  const checked = Date.parse(checkedAt);
  const retrieved = source.retrieved_at ? Date.parse(source.retrieved_at) : Number.NaN;
  const elapsed = (Date.now() - checked) / 1000;
  if (
    !Number.isFinite(checked)
    || !Number.isFinite(retrieved)
    || retrieved > checked
    || elapsed < 0
  ) return null;
  return initialAge + elapsed;
}

function display(
  source: SourceStatuses["sources"][number],
  checkedAt?: string,
): { label: string; kind: string } {
  if (source.availability === "unavailable") return { label: "Not loaded", kind: "not-loaded" };
  if (source.semantics === "versioned_release" || source.semantics === "versioned_plan") {
    return {
      label: source.source_version ? `Edition ${source.source_version}` : "Static / versioned",
      kind: "versioned",
    };
  }
  const ageSeconds = ageAtRender(source, checkedAt);
  if (source.retrieval_max_age_seconds !== null && source.retrieval_max_age_seconds !== undefined) {
    if (ageSeconds === null) return { label: "Freshness unavailable", kind: "unknown" };
    return ageSeconds <= source.retrieval_max_age_seconds
      ? { label: "Current by policy", kind: "available" }
      : { label: "Stale by policy", kind: "stale" };
  }
  const age = compactAge(ageSeconds);
  if (age !== null) return { label: `Retrieved ${age} ago`, kind: "unknown" };
  return { label: "Freshness policy not configured", kind: "unknown" };
}

export function SourceStatusPanel({ status, error, loading }: Props) {
  const visible = status?.sources.filter((source) => source.source in LABELS) ?? [];
  const needsAttention = Boolean(error) || visible.some((source) => {
    const state = display(source, status?.checked_at);
    return state.kind === "not-loaded" || state.kind === "stale" || state.kind === "unknown";
  });
  const available = visible.filter((source) => source.availability === "available").length;
  return (
    <details className="panel-section status-section" open={needsAttention}>
      <summary>
        <span><span className="eyebrow">Accepted evidence</span><strong id="status-heading">Source status</strong></span>
        <span className={needsAttention ? "status-summary attention" : "status-summary"}>{loading ? "Checking" : error ? "Unavailable" : `${available}/${visible.length} available`}</span>
      </summary>
      {status && <p className="status-checked">Checked <time dateTime={status.checked_at}>{new Date(status.checked_at).toLocaleString()}</time></p>}
      {loading && <p role="status">Checking WaterGeo sources…</p>}
      {error && <p className="state-error" role="alert">{error}</p>}
      {visible.length > 0 && (
        <ul className="status-list">
          {visible.map((source) => {
            const state = display(source, status?.checked_at);
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
      {visible.some((source) => source.semantics === "dynamic_snapshot" && source.availability === "available") && (
        <p className="status-guidance">Current or stale uses configured WaterGeo retrieval policy. Where only an age is shown, no freshness policy is configured. Retrieved ages are WaterGeo retrieval times, not publisher observation times.</p>
      )}
    </details>
  );
}
