import { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react";

import { ApiError, api } from "./api";
import { DetailPanel } from "./DetailPanel";
import { LayerControls } from "./LayerControls";
import { SourceStatusPanel } from "./SourceStatusPanel";
import type { AreaPage, AreaSummary, LayerId, SelectedFeature, SourceStatuses } from "./types";
import { explorerSearch, parseExplorerState, parseWaterSupplyId } from "./urlState";
import { useNearby, type ViewportQuery } from "./useNearby";
import { WaterBodyBrowser } from "./WaterBodyBrowser";

const MapView = lazy(async () => {
  const module = await import("./MapView");
  return { default: module.MapView };
});

function selectionKey(selected: SelectedFeature | null): string | null {
  if (!selected) return null;
  if (selected.kind === "hydrology") return `hydrology:${selected.item.station_id}`;
  if (selected.kind === "water-quality") return `water-quality:${selected.item.sampling_point_id}`;
  if (selected.kind === "reservoirs") return `reservoirs:${selected.item.reservoir_id}`;
  if (selected.kind === "water-supply") return `water-supply:${selected.item.id}`;
  return `water-body:${selected.item.water_body_id}`;
}

export function App() {
  const initial = useMemo(() => parseExplorerState(window.location.search), []);
  const [layers, setLayers] = useState(initial.layers);
  const [viewport, setViewport] = useState<ViewportQuery & { zoom: number }>({
    longitude: initial.longitude,
    latitude: initial.latitude,
    zoom: initial.zoom,
    radiusM: 100_000,
  });
  const nearby = useNearby(viewport, layers);
  const [sourceStatus, setSourceStatus] = useState<SourceStatuses | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [selected, setSelected] = useState<SelectedFeature | null>(null);
  const [areaMatches, setAreaMatches] = useState<AreaPage | null>(null);
  const [areaError, setAreaError] = useState<string>();
  const [areaLoading, setAreaLoading] = useState(false);
  const [waterBodiesOpen, setWaterBodiesOpen] = useState(false);
  const lookupController = useRef<AbortController | undefined>(undefined);
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

  useEffect(() => () => lookupController.current?.abort(), []);

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
  }, [initial.selected, nearby]);

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

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand-mark" aria-hidden="true">WG</div>
        <div className="brand-copy">
          <span>WaterGeo UK</span>
          <strong>Public water data explorer</strong>
        </div>
        <button className="share-button" type="button" onClick={() => void copyShareUrl()} aria-label="Copy a shareable map URL">Copy view link</button>
      </header>

      <aside className="control-panel" aria-label="Explorer controls">
        <LayerControls
          active={layers}
          counts={{
            hydrology: nearby.hydrology.length,
            "water-quality": nearby.waterQuality.length,
            reservoirs: nearby.reservoirs.length,
          }}
          loading={nearby.loading}
          errors={nearby.errors}
          onToggle={toggleLayer}
        />
        <WaterBodyBrowser
          open={waterBodiesOpen}
          onToggle={() => setWaterBodiesOpen((value) => !value)}
          onSelect={(feature) => setSelected(feature)}
        />
        <SourceStatusPanel status={sourceStatus} error={statusError} loading={!sourceStatus && !statusError} />
      </aside>

      <main className="map-workspace">
        <Suspense fallback={<div className="map-loading" role="status">Loading map renderer…</div>}>
          <MapView
            initial={initial}
            activeLayers={layers}
            hydrology={nearby.hydrology}
            waterQuality={nearby.waterQuality}
            reservoirs={nearby.reservoirs}
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
