import { useEffect, useState } from "react";
import { overviewPath, parseOverview, type Overview } from "./overview";
import { readBoundedJson } from "./api";

export function OverviewControl({ onChange }: { onChange: (value: Overview | null) => void }) {
  const path = import.meta.env.VITE_WATER_SUPPLY_OVERVIEW as string | undefined;
  const [enabled, setEnabled] = useState(false);
  const [error, setError] = useState(false);
  const [loaded, setLoaded] = useState<Overview | null>(null);
  useEffect(() => {
    if (!enabled || !path) { onChange(null); return; }
    const controller = new AbortController();
    void (async () => {
      try {
        const safePath = overviewPath(path);
        const response = await fetch(safePath, { signal: controller.signal, redirect: "error", credentials: "same-origin" });
        if (!response.ok || response.headers.get("content-type")?.split(";")[0]?.trim() !== "application/json") throw new Error("Unavailable");
        const overview = parseOverview(await readBoundedJson(response, 64_000), safePath);
        if (controller.signal.aborted) return;
        setLoaded(overview);
        onChange(overview);
      } catch {
        if (!controller.signal.aborted) { setError(true); onChange(null); }
      }
    })();
    return () => controller.abort();
  }, [enabled, path, onChange]);
  if (!path) return null;
  return <section className="panel-section" aria-label="National overview">
    <label><input type="checkbox" checked={enabled} onChange={(event) => { setError(false); setLoaded(null); setEnabled(event.target.checked); }} /> Water-supply overview</label>
    <p className="caveat">Simplified dated boundaries for orientation. Enable water-supply lookup for exact reviewed geometry and all boundary matches.</p>
    {enabled && !loaded && !error && <p role="status">Loading overview…</p>}
    {enabled && error && <p role="alert">Overview unavailable. Toggle to retry.</p>}
    {enabled && loaded && <p className="state-detail">Snapshot {loaded.snapshot}<br />{loaded.attribution}</p>}
  </section>;
}
