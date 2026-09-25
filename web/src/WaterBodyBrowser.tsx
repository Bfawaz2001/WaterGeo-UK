import { useRef, useState } from "react";

import { ApiError, api } from "./api";
import type { CatchmentDataset, SelectedFeature, WaterBody } from "./types";

interface Props {
  open: boolean;
  onToggle: () => void;
  onSelect: (selected: Extract<SelectedFeature, { kind: "water-body" }>) => void;
}

export function WaterBodyBrowser({ open, onToggle, onSelect }: Props) {
  const [items, setItems] = useState<WaterBody[]>([]);
  const [dataset, setDataset] = useState<CatchmentDataset>();
  const [next, setNext] = useState<string | null>();
  const [search, setSearch] = useState("");
  const [error, setError] = useState<string>();
  const [loading, setLoading] = useState(false);
  const generation = useRef(0);

  const load = async (after?: string) => {
    const current = ++generation.current;
    setLoading(true);
    setError(undefined);
    try {
      const page = await api.waterBodies(dataset?.snapshot_id, after);
      if (current !== generation.current) return;
      setDataset(page.dataset);
      setItems((existing) => (after ? [...existing, ...page.items] : page.items));
      setNext(page.next_after_id);
    } catch (reason) {
      if (current !== generation.current) return;
      setError(reason instanceof ApiError && reason.status === 503 ? "Catchment data is unavailable." : "Water Bodies could not be loaded.");
    } finally {
      if (current === generation.current) setLoading(false);
    }
  };

  const toggle = () => {
    if (!open && items.length === 0 && !loading) void load();
    onToggle();
  };

  const select = async (item: WaterBody) => {
    const current = ++generation.current;
    setLoading(true);
    setError(undefined);
    try {
      const [detail, geometry] = await Promise.all([
        api.waterBody(item.water_body_id),
        api.waterBodyGeometry(item.water_body_id),
      ]);
      if (current !== generation.current) return;
      if (!dataset || detail.snapshot_id !== dataset.snapshot_id || geometry.snapshot_id !== dataset.snapshot_id) {
        throw new ApiError(503, "Water Body snapshot changed during selection");
      }
      onSelect({ kind: "water-body", item: detail, dataset, geometry });
    } catch {
      if (current === generation.current) setError("This Water Body could not be displayed.");
    } finally {
      if (current === generation.current) setLoading(false);
    }
  };

  const normalized = search.trim().toLocaleLowerCase();
  const filtered = items.filter(
    (item) =>
      normalized === "" ||
      item.name.toLocaleLowerCase().includes(normalized) ||
      item.water_body_id.toLocaleLowerCase().includes(normalized),
  );

  return (
    <section className="panel-section water-body-browser" aria-labelledby="water-body-heading">
      <button className="section-toggle" type="button" onClick={toggle} aria-expanded={open}>
        <span><span className="eyebrow">Catchment Data Explorer</span><strong id="water-body-heading">Water Bodies</strong></span>
        <span aria-hidden="true">{open ? "−" : "+"}</span>
      </button>
      {open && (
        <div className="browser-content">
          <label htmlFor="water-body-search">Find in loaded Water Bodies</label>
          <input id="water-body-search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Name or publisher ID" />
          <p className="state-detail">First 100 are loaded at a time and pinned to one snapshot.</p>
          {error && <p className="state-error" role="alert">{error}</p>}
          <ul className="result-list" aria-label="Water Body results">
            {filtered.slice(0, 50).map((item) => (
              <li key={item.water_body_id}>
                <button type="button" onClick={() => void select(item)}>
                  <strong>{item.name}</strong><small>{item.water_body_id} · {item.water_body_type ?? "type not stated"}</small>
                </button>
              </li>
            ))}
          </ul>
          {!loading && filtered.length === 0 && <p>No loaded Water Bodies match that text.</p>}
          {loading && <p role="status">Loading Water Bodies…</p>}
          {next && !search && <button className="secondary-button" type="button" disabled={loading} onClick={() => void load(next)}>Load next 100</button>}
        </div>
      )}
    </section>
  );
}
