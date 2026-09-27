import { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react";

import { ApiError, api } from "./api";
import { DetailPanel } from "./DetailPanel";
import { LayerControls } from "./LayerControls";
import { SourceStatusPanel } from "./SourceStatusPanel";
import { SearchBox } from "./SearchBox";
import type { AreaPage, AreaSummary, LayerId, SearchResult, SelectedFeature, SourceStatuses, ThamesAlertStatus } from "./types";
import { explorerSearch, parseExplorerState, parseWaterSupplyId } from "./urlState";
import { useNearby, type ViewportQuery } from "./useNearby";
import { WaterBodyBrowser } from "./WaterBodyBrowser";
import { OverviewControl } from "./OverviewControl";
import type { Overview } from "./overview";

const MapView = lazy(async () => {
  const module = await import("./MapView");
  return { default: module.MapView };
});

function selectionKey(selected: SelectedFeature | null): string | null {
  if (!selected) return null;
  if (selected.kind === "hydrology") return `hydrology:${selected.item.station_id}`;
  if (selected.kind === "water-quality") return `water-quality:${selected.item.sampling_point_id}`;
  if (selected.kind === "reservoirs") return `reservoirs:${selected.item.reservoir_id}`;
  if (selected.kind === "thames-discharge") return `thames-discharge:${selected.item.site_id}`;
  if (selected.kind === "water-supply") return `water-supply:${selected.item.id}`;
  return `water-body:${selected.item.water_body_id}`;
}

export function App() {
  const initial = useMemo(() => parseExplorerState(window.location.search), []);
  const [layers, setLayers] = useState(initial.layers);
  const [panelOpen, setPanelOpen] = useState(() => window.innerWidth > 740);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [thamesStatus, setThamesStatus] = useState<ThamesAlertStatus | "">("");
  const [thamesRecent, setThamesRecent] = useState(false);
  const [viewport, setViewport] = useState<ViewportQuery & { zoom: number }>({
    longitude: initial.longitude,
    latitude: initial.latitude,
    zoom: initial.zoom,
    radiusM: 0,
  });
  const nearby = useNearby(viewport, layers, 350, {
    ...(thamesStatus ? { status: thamesStatus } : {}),
    ...(thamesRecent ? { recent: true } : {}),
  });
  const thamesDischarge = useMemo(
    () => nearby.thamesDischarge ?? [],
    [nearby.thamesDischarge],
  );
  const [sourceStatus, setSourceStatus] = useState<SourceStatuses | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [selected, setSelected] = useState<SelectedFeature | null>(null);
  const [mapFocus, setMapFocus] = useState<{ key: string; longitude?: number; latitude?: number } | null>(null);
  const [areaMatches, setAreaMatches] = useState<AreaPage | null>(null);
  const [areaError, setAreaError] = useState<string>();
  const [areaLoading, setAreaLoading] = useState(false);
  const [waterBodiesOpen, setWaterBodiesOpen] = useState(false);
  const lookupController = useRef<AbortController | undefined>(undefined);
  const searchSelectionController = useRef<AbortController | undefined>(undefined);
  const initialSelectionApplied = useRef(false);

  useEffect(() => {
    const controller = new AbortController();
    void api
      .sourceStatuses(controller.signal)
      .then(setSourceStatus)
      .catch((error: unknown) => {
        if (!(error instanceof DOMException && error.name === "AbortError")) {
          setStatusError("Source status is currently unavailable.");
        }
      });
    return () => controller.abort();
  }, []);

  useEffect(() => () => {
    lookupController.current?.abort();
    searchSelectionController.current?.abort();
  }, []);

  useEffect(() => {
    const next = explorerSearch({
      longitude: viewport.longitude,
      latitude: viewport.latitude,
      zoom: viewport.zoom,
      layers,
      selected: selectionKey(selected),
    });
    window.history.replaceState(null, "", `${window.location.pathname}${next}`);
  }, [layers, selected, viewport.latitude, viewport.longitude, viewport.zoom]);

  useEffect(() => {
    if (initialSelectionApplied.current || initial.selected === null) return;
    const [kind, ...identityParts] = initial.selected.split(":");
    const identity = identityParts.join(":");
    if (kind === "hydrology") {
      const item = nearby.hydrology.find((candidate) => candidate.station_id === identity);
      const dataset = nearby.provenance.hydrology;
      if (item && dataset) {
        initialSelectionApplied.current = true;
        queueMicrotask(() => setSelected({ kind, item, dataset }));
      }
    } else if (kind === "water-quality") {
      const item = nearby.waterQuality.find((candidate) => candidate.sampling_point_id === identity);
      const dataset = nearby.provenance["water-quality"];
      if (item && dataset) {
        initialSelectionApplied.current = true;
        queueMicrotask(() => setSelected({ kind, item, dataset }));
      }
    } else if (kind === "reservoirs") {
      const item = nearby.reservoirs.find((candidate) => candidate.reservoir_id === identity);
      const dataset = nearby.provenance.reservoirs;
      if (item && dataset) {
        initialSelectionApplied.current = true;
        queueMicrotask(() => setSelected({ kind, item, dataset }));
      }
    } else if (kind === "thames-discharge") {
      const item = thamesDischarge.find((candidate) => candidate.site_id === identity);
      const dataset = nearby.provenance["thames-discharge"];
      if (item && dataset) {
        initialSelectionApplied.current = true;
        queueMicrotask(() => setSelected({ kind, item, dataset }));
      }
    } else if (kind === "water-supply") {
      initialSelectionApplied.current = true;
      const sourceId = parseWaterSupplyId(identity);
      if (sourceId === null) return;
      void api.areaGeometry(sourceId).then((item) => setSelected({ kind, item })).catch(() => setAreaError("The shared water-supply area is unavailable."));
    } else if (kind === "water-body") {
      initialSelectionApplied.current = true;
      const controller = new AbortController();
      void Promise.all([
        api.catchmentDataset(controller.signal),
        api.waterBody(identity, controller.signal),
        api.waterBodyGeometry(identity, controller.signal),
      ]).then(([dataset, item, geometry]) => {
        if (item.snapshot_id !== dataset.snapshot_id || geometry.snapshot_id !== dataset.snapshot_id) {
          throw new ApiError(503, "Water Body snapshot changed during shared selection");
        }
        setSelected({ kind, item, dataset, geometry });
        setWaterBodiesOpen(true);
      }).catch((error: unknown) => {
        if (!(error instanceof DOMException && error.name === "AbortError")) {
          setAreaError("The shared Water Body is unavailable.");
        }
      });
      return () => controller.abort();
    } else {
      initialSelectionApplied.current = true;
    }
  }, [initial.selected, nearby, thamesDischarge]);

  const toggleLayer = (layer: LayerId) => {
    setLayers((current) => {
      const next = new Set(current);
      if (next.has(layer)) next.delete(layer);
      else next.add(layer);
      return next;
    });
    if (layer === "water-supply") {
      setAreaMatches(null);
      setAreaError(undefined);
      if (layers.has("water-supply") && selected?.kind === "water-supply") setSelected(null);
    }
  };

  const selectPoint = (layer: LayerId, identity: string) => {
    if (layer === "hydrology") {
      const item = nearby.hydrology.find((candidate) => candidate.station_id === identity);
      const dataset = nearby.provenance.hydrology;
      if (item && dataset) setSelected({ kind: layer, item, dataset });
    } else if (layer === "water-quality") {
      const item = nearby.waterQuality.find((candidate) => candidate.sampling_point_id === identity);
      const dataset = nearby.provenance["water-quality"];
      if (item && dataset) setSelected({ kind: layer, item, dataset });
    } else if (layer === "reservoirs") {
      const item = nearby.reservoirs.find((candidate) => candidate.reservoir_id === identity);
      const dataset = nearby.provenance.reservoirs;
      if (item && dataset) setSelected({ kind: layer, item, dataset });
    } else if (layer === "thames-discharge") {
      const item = thamesDischarge.find((candidate) => candidate.site_id === identity);
      const dataset = nearby.provenance["thames-discharge"];
      if (item && dataset) setSelected({ kind: layer, item, dataset });
    }
  };

  const lookupArea = (longitude: number, latitude: number) => {
    lookupController.current?.abort();
    const controller = new AbortController();
    lookupController.current = controller;
    setAreaLoading(true);
    setAreaError(undefined);
    setAreaMatches(null);
    void api
      .areasAtPoint(longitude, latitude, controller.signal)
      .then(setAreaMatches)
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setAreaError(
          error instanceof ApiError && error.status === 503
            ? "Water-supply boundaries are currently unavailable."
            : "The boundary lookup could not be completed.",
        );
      })
      .finally(() => {
        if (!controller.signal.aborted) setAreaLoading(false);
      });
  };

  const chooseArea = (area: AreaSummary) => {
    lookupController.current?.abort();
    const controller = new AbortController();
    lookupController.current = controller;
    setAreaLoading(true);
    setAreaError(undefined);
    void api
      .areaGeometry(area.source_id, controller.signal)
      .then((item) => setSelected({ kind: "water-supply", item }))
      .catch((error: unknown) => {
        if (!(error instanceof DOMException && error.name === "AbortError")) {
          setAreaError("The selected reviewed geometry could not be displayed.");
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setAreaLoading(false);
      });
  };

  const copyShareUrl = async () => {
    try {
      await navigator.clipboard.writeText(window.location.href);
    } catch {
      setAreaError("Copy was blocked by the browser. Copy the address bar URL instead.");
    }
  };

  const openSearchResult = async (result: SearchResult) => {
    searchSelectionController.current?.abort();
    const controller = new AbortController();
    searchSelectionController.current = controller;
    const enable = (layer: LayerId) => setLayers((current) => new Set(current).add(layer));
    const focusPoint = (longitude: number | null, latitude: number | null) => {
      setMapFocus({
        key: `${result.kind}:${result.identity}:${result.snapshot_id}`,
        ...(longitude === null ? {} : { longitude }),
        ...(latitude === null ? {} : { latitude }),
      });
    };
    if (result.kind === "hydrology") {
      const detail = await api.hydrologyDetail(result.identity, controller.signal, result.snapshot_id);
      if (detail.dataset.snapshot_id !== result.snapshot_id) throw new ApiError(503, "Search snapshot changed");
      enable("hydrology");
      setSelected({ kind: "hydrology", item: detail, dataset: detail.dataset });
      focusPoint(detail.longitude, detail.latitude);
    } else if (result.kind === "water-quality") {
      const detail = await api.samplingPointDetail(result.identity, result.snapshot_id, controller.signal);
      if (detail.dataset.snapshot_id !== result.snapshot_id) throw new ApiError(503, "Search snapshot changed");
      enable("water-quality");
      setSelected({ kind: "water-quality", item: detail, dataset: detail.dataset });
      focusPoint(detail.longitude, detail.latitude);
    } else if (result.kind === "reservoirs") {
      const detail = await api.reservoirDetail(result.identity, result.snapshot_id, controller.signal);
      if (detail.dataset.snapshot_id !== result.snapshot_id) throw new ApiError(503, "Search snapshot changed");
      enable("reservoirs");
      setSelected({ kind: "reservoirs", item: detail, dataset: detail.dataset });
      focusPoint(detail.longitude, detail.latitude);
    } else if (result.kind === "thames-discharge") {
      const detail = await api.thamesDischargeDetail(result.identity, result.snapshot_id, controller.signal);
      if (detail.dataset.snapshot_id !== result.snapshot_id) throw new ApiError(503, "Search snapshot changed");
      enable("thames-discharge");
      setSelected({ kind: "thames-discharge", item: detail, dataset: detail.dataset });
      focusPoint(result.longitude, result.latitude);
    } else if (result.kind === "water-body") {
      const [dataset, item, geometry] = await Promise.all([
        api.catchmentDataset(controller.signal, result.snapshot_id),
        api.waterBody(result.identity, controller.signal, result.snapshot_id),
        api.waterBodyGeometry(result.identity, controller.signal, result.snapshot_id),
      ]);
      if (dataset.snapshot_id !== result.snapshot_id || item.snapshot_id !== result.snapshot_id || geometry.snapshot_id !== result.snapshot_id) {
        throw new ApiError(503, "Search snapshot changed");
      }
      setSelected({ kind: "water-body", item, dataset, geometry });
      setWaterBodiesOpen(true);
      focusPoint(null, null);
    } else {
      const sourceId = parseWaterSupplyId(result.identity);
      if (sourceId === null) throw new ApiError(422, "Invalid water-supply identity");
      const item = await api.areaGeometry(sourceId, controller.signal);
      if (item.properties.snapshot_id !== result.snapshot_id) throw new ApiError(503, "Search snapshot changed");
      enable("water-supply");
      setSelected({ kind: "water-supply", item });
      focusPoint(null, null);
    }
  };

  return (
    <div className={`app-shell ${panelOpen ? "" : "controls-collapsed"}`}>
      <header className="topbar">
        <button className="share-button panel-toggle" aria-expanded={panelOpen} aria-controls="explorer-controls" onClick={() => setPanelOpen((open) => !open)}>Layers & filters</button>
        <div className="brand-mark" aria-hidden="true">WG</div>
        <div className="brand-copy">
          <span>WaterGeo UK</span>
          <strong>Public water data explorer</strong>
        </div>
        <SearchBox onSelect={openSearchResult} />
        <button className="share-button" type="button" onClick={() => void copyShareUrl()} aria-label="Copy a shareable map URL">Copy view link</button>
      </header>

      <aside id="explorer-controls" className="control-panel" aria-label="Explorer controls" hidden={!panelOpen}>
        <OverviewControl onChange={setOverview} />
        <LayerControls
          active={layers}
          counts={{
            hydrology: nearby.hydrology.length,
            "water-quality": nearby.waterQuality.length,
            reservoirs: nearby.reservoirs.length,
            "thames-discharge": thamesDischarge.length,
          }}
          loading={nearby.loading}
          errors={nearby.errors}
          onToggle={toggleLayer}
        />
        {layers.has("thames-discharge") && (
          <section className="panel-section" aria-labelledby="thames-filter-heading">
            <p className="eyebrow">Server-side filters</p>
            <h2 id="thames-filter-heading">Thames monitor status</h2>
            <label>Status <select value={thamesStatus} onChange={(event) => setThamesStatus(event.target.value as ThamesAlertStatus | "")}>
              <option value="">All statuses</option>
              <option>Discharging</option><option>Not discharging</option><option>Offline</option>
            </select></label>
            <label><input type="checkbox" checked={thamesRecent} onChange={(event) => setThamesRecent(event.target.checked)} /> Publisher marks activity in past 48 hours</label>
            <p className="caveat">Filters run on the full selected snapshot before the nearest 100 results are returned.</p>
            <p className="caveat">
              Near-real-time means the latest accepted WaterGeo retrieval for each map request, not instantaneous publisher state.
              {nearby.provenance["thames-discharge"] && (
                <> Latest WaterGeo retrieval: <time dateTime={nearby.provenance["thames-discharge"].retrieval_completed_at}>{new Date(nearby.provenance["thames-discharge"].retrieval_completed_at).toLocaleString()}</time>.</>
              )}
            </p>
          </section>
        )}
        <details className="panel-section"><summary>Browse nearby results without the map</summary>
          <p>Current bounded results only; maximum 100 per source.</p>
          <ul className="result-list nearby-list">
            {layers.has("hydrology") && nearby.hydrology.map((item) => <li key={`h:${item.station_id}`}><button onClick={() => selectPoint("hydrology", item.station_id)}>Station: {item.labels[0] ?? item.station_id}</button></li>)}
            {layers.has("water-quality") && nearby.waterQuality.map((item) => <li key={`q:${item.sampling_point_id}`}><button onClick={() => selectPoint("water-quality", item.sampling_point_id)}>Sampling point: {item.pref_label ?? item.alt_label}</button></li>)}
            {layers.has("reservoirs") && nearby.reservoirs.map((item) => <li key={`r:${item.reservoir_id}`}><button onClick={() => selectPoint("reservoirs", item.reservoir_id)}>Reservoir: {item.name}</button></li>)}
            {layers.has("thames-discharge") && thamesDischarge.map((item) => <li key={`t:${item.site_id}`}><button onClick={() => selectPoint("thames-discharge", item.site_id)}>Thames monitor: {item.location_name} · {item.alert_status}</button></li>)}
          </ul>
        </details>
        <WaterBodyBrowser
          open={waterBodiesOpen}
          onToggle={() => setWaterBodiesOpen((value) => !value)}
          onSelect={(feature) => setSelected(feature)}
        />
        <SourceStatusPanel status={sourceStatus} error={statusError} loading={!sourceStatus && !statusError} />
      </aside>

      <main className="map-workspace">
        {viewport.radiusM === 0 && <p className="map-message" role="status">Preparing map viewport…</p>}
        <Suspense fallback={<div className="map-loading" role="status">Loading map renderer…</div>}>
          <MapView
            overview={overview}
            focus={mapFocus}
            initial={initial}
            activeLayers={layers}
            hydrology={nearby.hydrology}
            waterQuality={nearby.waterQuality}
            reservoirs={nearby.reservoirs}
            thamesDischarge={thamesDischarge}
            area={selected?.kind === "water-supply" ? selected.item : null}
            waterBody={selected?.kind === "water-body" ? selected.geometry : null}
            onViewport={setViewport}
            onMapClick={lookupArea}
            onSelectPoint={selectPoint}
          />
        </Suspense>
        {(areaLoading || areaError || areaMatches) && layers.has("water-supply") && (
          <section className="area-results" aria-label="Water-supply boundary matches">
            <div className="area-results-heading"><strong>Boundary matches</strong><button type="button" onClick={() => { setAreaMatches(null); setAreaError(undefined); }}>Close</button></div>
            {areaLoading && <p role="status">Checking reviewed boundaries…</p>}
            {areaError && <p className="state-error" role="alert">{areaError}</p>}
            {areaMatches?.items.length === 0 && <p>No reviewed area covers that point.</p>}
            {areaMatches && areaMatches.items.length > 0 && (
              <>
                <p>{areaMatches.items.length} matching area{areaMatches.items.length === 1 ? "" : "s"}. Boundary and overlap matches are all retained.</p>
                <ul className="result-list">
                  {areaMatches.items.map((area) => (
                    <li key={area.source_id}><button type="button" onClick={() => chooseArea(area)}><strong>{area.company ?? `Area ${area.source_id}`}</strong><small>{area.area_served ?? "Area served not stated"}</small></button></li>
                  ))}
                </ul>
              </>
            )}
            <p className="caveat">The April 2024 analytical snapshot is not a guaranteed current property-supplier lookup.</p>
          </section>
        )}
      </main>

      <aside className="selection-region" aria-label="Selected feature information">
        <DetailPanel selected={selected} onClose={() => setSelected(null)} />
      </aside>
    </div>
  );
}
