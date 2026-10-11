import { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react";

import { ApiError, api } from "./api";
import { dataMode } from "./config";
import { staticPublicationMetadata } from "./staticData";
import { DetailPanel } from "./DetailPanel";
import { LayerControls } from "./LayerControls";
import { SourceStatusPanel } from "./SourceStatusPanel";
import { SearchBox } from "./SearchBox";
import type { AreaFeature, AreaPage, AreaSummary, LayerId, SearchResult, SelectedFeature, SourceStatuses, ThamesAlertStatus, WaterCompanyFeatureCollection } from "./types";
import { explorerSearch, parseExplorerState, parseWaterSupplyId } from "./urlState";
import { useNearby, type ViewportQuery } from "./useNearby";
import { WaterBodyBrowser } from "./WaterBodyBrowser";
import { OverviewControl } from "./OverviewControl";
import type { Overview } from "./overview";
import { Icon } from "./Icon";
import { geometryBounds, REGIONS, type MapNavigation } from "./mapNavigation";
import { filterFloods, FLOOD_STATES, type FloodFilter } from "./floodFilters";
import { Onboarding } from "./Onboarding";
import { BATHING_CLASSIFICATIONS, filterBathingWaters, type BathingClassification } from "./explorerPresentation";
import { CompanyExplorer } from "./CompanyExplorer";

const MapView = lazy(async () => {
  const module = await import("./MapView");
  return { default: module.MapView };
});

function selectionKey(selected: SelectedFeature | null): string | null {
  if (!selected) return null;
  if (selected.kind === "hydrology") return `hydrology:${selected.item.station_id}`;
  if (selected.kind === "rainfall") return `rainfall:${selected.item.station_id}`;
  if (selected.kind === "bathing-waters") return `bathing-waters:${selected.item.bathing_water_id}`;
  if (selected.kind === "flood-warnings") return `flood-warnings:${selected.item.area_id}`;
  if (selected.kind === "water-quality") return `water-quality:${selected.item.sampling_point_id}`;
  if (selected.kind === "reservoirs") return `reservoirs:${selected.item.reservoir_id}`;
  if (selected.kind === "thames-discharge") return `thames-discharge:${selected.item.site_id}`;
  if (selected.kind === "water-supply") return `water-supply:${selected.item.id}`;
  if (selected.kind === "company-performance") return null;
  return `water-body:${selected.item.water_body_id}`;
}

export function App() {
  const mode = dataMode();
  const initial = useMemo(() => parseExplorerState(window.location.search), []);
  const [layers, setLayers] = useState(initial.layers);
  const [panelOpen, setPanelOpen] = useState(() => window.innerWidth > 740);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [thamesStatus, setThamesStatus] = useState<ThamesAlertStatus | "">("");
  const [floodSeverity, setFloodSeverity] = useState<FloodFilter>(initial.floodSeverity);
  const [bathingClassification, setBathingClassification] = useState<BathingClassification>(initial.bathingClassification);
  const [navigation, setNavigation] = useState<MapNavigation | null>(null);
  const navigationId = useRef(0);
  const navigate = (bounds: MapNavigation["bounds"] | null, maxZoom = 12) => {
    if (bounds) setNavigation({ id: ++navigationId.current, bounds, maxZoom });
  };
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
  const rainfall = nearby.rainfall ?? [];
  const loadedBathingWaters = useMemo(
    () => nearby.bathingWaters ?? [],
    [nearby.bathingWaters],
  );
  const bathingWaters = useMemo(
    () => filterBathingWaters(loadedBathingWaters, bathingClassification),
    [loadedBathingWaters, bathingClassification],
  );
  const floodWarnings = useMemo(
    () => filterFloods(nearby.floodWarnings ?? [], floodSeverity),
    [nearby.floodWarnings, floodSeverity],
  );
  const [sourceStatus, setSourceStatus] = useState<SourceStatuses | null>(null);
  const [staticPublication, setStaticPublication] = useState<Awaited<ReturnType<typeof staticPublicationMetadata>> | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [selected, setSelected] = useState<SelectedFeature | null>(null);
  const [mapFocus, setMapFocus] = useState<{ key: string; longitude?: number; latitude?: number } | null>(null);
  const [areaMatches, setAreaMatches] = useState<AreaPage | null>(null);
  const [areaError, setAreaError] = useState<string>();
  const [areaLoading, setAreaLoading] = useState(false);
  const [mapNotice, setMapNotice] = useState<string>();
  const [shareFeedback, setShareFeedback] = useState<{ kind: "success" | "error"; message: string; url?: string }>();
  const [waterBodiesOpen, setWaterBodiesOpen] = useState(false);
  const [companyAreas, setCompanyAreas] = useState<WaterCompanyFeatureCollection | null>(null);
  const [companyAcronym, setCompanyAcronym] = useState<string | null>(initial.company);
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

  useEffect(() => {
    if (mode !== "static") return;
    const controller = new AbortController();
    void staticPublicationMetadata(controller.signal)
      .then(setStaticPublication)
      .catch((error: unknown) => {
        if (!(error instanceof DOMException && error.name === "AbortError")) {
          setStatusError("Static publication metadata is currently unavailable.");
        }
      });
    return () => controller.abort();
  }, [mode]);

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
      company: companyAcronym,
      floodSeverity,
      bathingClassification,
    });
    window.history.replaceState(null, "", `${window.location.pathname}${next}`);
    queueMicrotask(() => setShareFeedback(undefined));
  }, [bathingClassification, companyAcronym, floodSeverity, layers, selected, viewport.latitude, viewport.longitude, viewport.zoom]);

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
        setMapFocus(null);
        const bounds = geometryBounds(geometry.features.map((feature) => feature.geometry));
        if (bounds) {
          setMapNotice(undefined);
          navigate(bounds);
        } else {
          setMapNotice("The selected Water Body has no usable accepted geometry to show on the map.");
        }
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
      if (layers.has("water-supply")) {
        setCompanyAreas(null);
      }
    }
  };

  const selectPoint = (layer: LayerId, identity: string) => {
    setMapNotice(undefined);
    if (layer === "hydrology") {
      const item = nearby.hydrology.find((candidate) => candidate.station_id === identity);
      const dataset = nearby.provenance.hydrology;
      if (item && dataset) {
        setSelected({ kind: layer, item, dataset });
        if (item.longitude !== null && item.latitude !== null) setMapFocus({ key: `${layer}:${identity}`, longitude: item.longitude, latitude: item.latitude });
      }
    } else if (layer === "rainfall") {
      const item = rainfall.find((candidate) => candidate.station_id === identity);
      const dataset = nearby.provenance.rainfall;
      if (item && dataset) {
        setSelected({ kind: layer, item, dataset });
        setMapFocus({
          key: `${layer}:${identity}`,
          ...(item.longitude === null ? {} : { longitude: item.longitude }),
          ...(item.latitude === null ? {} : { latitude: item.latitude }),
        });
      }
    } else if (layer === "bathing-waters") {
      const item = bathingWaters.find((candidate) => candidate.bathing_water_id === identity);
      const dataset = nearby.provenance["bathing-waters"];
      if (item && dataset) {
        setSelected({ kind: layer, item, dataset });
        setMapFocus({ key: `${layer}:${identity}`, longitude: item.longitude, latitude: item.latitude });
      }
    } else if (layer === "flood-warnings") {
      const item = floodWarnings.find((candidate) => candidate.area_id === identity);
      const dataset = nearby.provenance["flood-warnings"];
      if (item && dataset) {
        setSelected({ kind: layer, item, dataset });
        setMapFocus({ key: `${layer}:${identity}` });
        navigate(geometryBounds([item.geometry]));
      }
    } else if (layer === "water-quality") {
      const item = nearby.waterQuality.find((candidate) => candidate.sampling_point_id === identity);
      const dataset = nearby.provenance["water-quality"];
      if (item && dataset) {
        setSelected({ kind: layer, item, dataset });
        if (item.longitude !== null && item.latitude !== null) setMapFocus({ key: `${layer}:${identity}`, longitude: item.longitude, latitude: item.latitude });
      }
    } else if (layer === "reservoirs") {
      const item = nearby.reservoirs.find((candidate) => candidate.reservoir_id === identity);
      const dataset = nearby.provenance.reservoirs;
      if (item && dataset) {
        setSelected({ kind: layer, item, dataset });
        setMapFocus({ key: `${layer}:${identity}`, longitude: item.longitude, latitude: item.latitude });
      }
    } else if (layer === "thames-discharge") {
      const item = thamesDischarge.find((candidate) => candidate.site_id === identity);
      const dataset = nearby.provenance["thames-discharge"];
      if (item && dataset) {
        setSelected({ kind: layer, item, dataset });
        setMapFocus({ key: `${layer}:${identity}`, longitude: item.geometry.coordinates[0], latitude: item.geometry.coordinates[1] });
      }
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

  const selectSupplyArea = (item: AreaFeature, signal: AbortSignal) => {
    if (!signal.aborted) {
      setSelected({ kind: "water-supply", item });
      setMapFocus({ key: `water-supply:${item.id}` });
    }
  };

  const chooseArea = (area: AreaSummary) => {
    lookupController.current?.abort();
    const controller = new AbortController();
    lookupController.current = controller;
    setAreaLoading(true);
    setAreaError(undefined);
    setMapNotice(undefined);
    void api
      .areaGeometry(area.source_id, controller.signal)
      .then((item) => selectSupplyArea(item, controller.signal))
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
    const url = window.location.href;
    setShareFeedback(undefined);
    try {
      await navigator.clipboard.writeText(url);
      const local = ["localhost", "127.0.0.1", "::1"].includes(window.location.hostname);
      setShareFeedback({
        kind: "success",
        message: local
          ? "Link copied. This local address works only on this computer."
          : "Link copied.",
      });
    } catch {
      setShareFeedback({
        kind: "error",
        message: "Copy was blocked. Select and copy this URL manually.",
        url,
      });
    }
  };

  const openSearchResult = async (result: SearchResult) => {
    searchSelectionController.current?.abort();
    const controller = new AbortController();
    searchSelectionController.current = controller;
    setAreaMatches(null);
    setAreaError(undefined);
    setMapNotice(undefined);
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
    } else if (result.kind === "rainfall") {
      const detail = await api.rainfallDetail(result.identity, result.snapshot_id, controller.signal);
      if (detail.dataset.snapshot_id !== result.snapshot_id) throw new ApiError(503, "Search snapshot changed");
      enable("rainfall");
      setSelected({ kind: "rainfall", item: detail.item, dataset: detail.dataset });
      focusPoint(detail.item.longitude, detail.item.latitude);
    } else if (result.kind === "bathing-waters") {
      const detail = await api.bathingWaterDetail(result.identity, result.snapshot_id, controller.signal);
      if (detail.dataset.snapshot_id !== result.snapshot_id) throw new ApiError(503, "Search snapshot changed");
      enable("bathing-waters");
      setSelected({ kind: "bathing-waters", item: detail.item, dataset: detail.dataset });
      focusPoint(detail.item.longitude, detail.item.latitude);
    } else if (result.kind === "flood-warnings") {
      const page = await api.floodAreas(controller.signal, false);
      const item = page.items.find((candidate) => candidate.area_id === result.identity);
      if (page.dataset.snapshot_id !== result.snapshot_id || !item) throw new ApiError(503, "Search snapshot changed");
      enable("flood-warnings");
      setSelected({ kind: "flood-warnings", item, dataset: page.dataset });
      focusPoint(null, null);
      navigate(geometryBounds([item.geometry]));
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
      setMapFocus(null);
      const bounds = geometryBounds(geometry.features.map((feature) => feature.geometry));
      if (bounds) {
        setMapNotice(undefined);
        navigate(bounds);
      } else {
        setMapNotice("The selected Water Body has no usable accepted geometry to show on the map.");
      }
    } else {
      const sourceId = parseWaterSupplyId(result.identity);
      if (sourceId === null) throw new ApiError(422, "Invalid water-supply identity");
      const item = await api.areaGeometry(sourceId, controller.signal);
      if (item.properties.snapshot_id !== result.snapshot_id) throw new ApiError(503, "Search snapshot changed");
      enable("water-supply");
      selectSupplyArea(item, controller.signal);
    }
  };

  return (
    <div className={`app-shell ${panelOpen ? "" : "controls-collapsed"}`}>
      <header className="topbar">
        <button className="share-button panel-toggle" aria-label="Layers & filters" aria-expanded={panelOpen} aria-controls="explorer-controls" onClick={() => setPanelOpen((open) => !open)}><Icon name="layers" /> <span>Layers & filters</span></button>
        <div className="brand-mark" aria-hidden="true"><span>W</span></div>
        <div className="brand-copy">
          <span>WaterGeo UK</span>
          <strong>Explore public UK water data</strong>
        </div>
        <SearchBox onSelect={openSearchResult} />
        <div className="share-control">
          <button className="share-button" type="button" onClick={() => void copyShareUrl()} aria-label="Copy a shareable map URL"><Icon name="copy" /> <span>Copy view</span></button>
          {shareFeedback && <div className={`share-feedback ${shareFeedback.kind === "error" ? "state-error" : ""}`} role="status" aria-live="polite">
            <span>{shareFeedback.message}</span>
            {shareFeedback.url && <input aria-label="Share URL for manual copying" readOnly value={shareFeedback.url} onFocus={(event) => event.currentTarget.select()} />}
          </div>}
        </div>
      </header>
      {mode === "static" && (
        <div className="static-snapshot-banner" role="status">
          <span><strong>Public beta</strong> · independent open-source project using accepted public publisher data
          {staticPublication && (
            <> · published <time dateTime={staticPublication.generated_at}>{new Date(staticPublication.generated_at).toLocaleString()}</time></>
          )}</span>
          <details>
            <summary>Publication details</summary>
            <span>Not affiliated with or endorsed by Ofwat, the Environment Agency, or any water company. Review <a href="#source-status">source provenance and status</a>.</span>
            {staticPublication && <code>Publication {staticPublication.publication_id}</code>}
          </details>
        </div>
      )}

      <aside id="explorer-controls" className="control-panel" aria-label="Explorer controls" hidden={!panelOpen}>
        <section className="panel-section orientation" aria-labelledby="orientation-heading">
          <p className="eyebrow">National to local</p>
          <h2 id="orientation-heading">Explore a region</h2>
          <p>Choose a region, then zoom into clusters or search by name. Points show bounded local results, not national totals.</p>
          <div className="region-grid">{REGIONS.map((region) => <button className="secondary-button" key={region.label} onClick={() => navigate(region.bounds, 8)}>{region.label}</button>)}</div>
          <details><summary>Coverage and overview</summary>
            <p>EA layers cover England; water-supply and company-performance products cover England and Wales. Thames and Severn Trent are company-specific. No nationwide point distribution layer is loaded.</p>
            <OverviewControl onChange={setOverview} />
          </details>
        </section>
        <LayerControls
          active={layers}
          counts={{
            hydrology: nearby.hydrology.length,
            rainfall: rainfall.length,
            "bathing-waters": bathingWaters.length,
            "flood-warnings": floodWarnings.length,
            "water-quality": nearby.waterQuality.length,
            reservoirs: nearby.reservoirs.length,
            "thames-discharge": thamesDischarge.length,
          }}
          loading={nearby.loading}
          errors={nearby.errors}
          onToggle={toggleLayer}
        />
        <CompanyExplorer
          initialCompany={initial.company}
          boundariesEnabled={layers.has("water-supply")}
          selectedAreaId={selected?.kind === "water-supply" ? selected.item.id : null}
          onCompanyChange={(acronym) => {
            setCompanyAreas(null);
            setCompanyAcronym(acronym);
            setAreaMatches(null);
            setAreaError(undefined);
            setSelected((current) =>
              current?.kind === "water-supply" || current?.kind === "company-performance"
                ? null
                : current,
            );
            setMapFocus(null);
            setMapNotice(undefined);
          }}
          onShowCompany={(collection) => {
            setCompanyAreas(collection);
            setSelected((current) => current?.kind === "water-supply" ? null : current);
            setMapFocus(null);
            setMapNotice(undefined);
            navigate(geometryBounds(collection.features.map((feature) => feature.geometry)));
          }}
          onSelectArea={(item) => {
            setSelected({ kind: "water-supply", item });
            setMapFocus({ key: `water-supply:${item.id}` });
            setMapNotice(undefined);
          }}
          onSelectPerformance={(performance) => {
            setSelected({
              kind: "company-performance",
              item: performance.item,
              dataset: performance.dataset,
            });
            setMapFocus(null);
          }}
        />
        {layers.has("flood-warnings") && (
          <section className="panel-section" aria-labelledby="flood-filter-heading">
            <p className="eyebrow">Active filters</p>
            <h2 id="flood-filter-heading">Flood warning state</h2>
            <label>Publisher severity <select value={floodSeverity} onChange={(event) => {
              const value = event.target.value as FloodFilter;
              setFloodSeverity(value);
              if (!nearby.loading.has("flood-warnings") && !nearby.errors["flood-warnings"]) {
                navigate(geometryBounds(filterFloods(nearby.floodWarnings ?? [], value).map((item) => item.geometry)));
              }
            }}>
              <option value="">All accepted warning states</option>
              {FLOOD_STATES.map((state) => <option key={state.value} value={state.value}>{state.label}</option>)}
            </select></label>
            <p role="status">{floodWarnings.length} matching areas in the loaded accepted warning snapshot.</p>
            {!floodWarnings.length && !nearby.loading.has("flood-warnings") && !nearby.errors["flood-warnings"] && <p>No matching warnings in this snapshot. The map position is unchanged.</p>}
            <button className="secondary-button" disabled={!floodWarnings.length || nearby.loading.has("flood-warnings") || Boolean(nearby.errors["flood-warnings"])} onClick={() => navigate(geometryBounds(floodWarnings.map((item) => item.geometry)))}>Show matching warning areas</button>
            <p className="caveat">All includes warnings no longer in force. Unknown states remain in All. A selected detail retains its original snapshot even when filtered out.</p>
            <a href="https://check-for-flooding.service.gov.uk/" target="_blank" rel="noreferrer">Official EA flood guidance</a>
          </section>
        )}
        {layers.has("bathing-waters") && (
          <section className="panel-section" aria-labelledby="bathing-filter-heading">
            <p className="eyebrow">Loaded-result filter</p>
            <h2 id="bathing-filter-heading">Bathing-water classification</h2>
            <label>Annual publisher classification <select value={bathingClassification} onChange={(event) => {
              const value = event.target.value as BathingClassification;
              setBathingClassification(value);
              if (!nearby.loading.has("bathing-waters") && !nearby.errors["bathing-waters"]) {
                const matches = filterBathingWaters(loadedBathingWaters, value);
                navigate(geometryBounds(matches.map((item) => ({ type: "Point", coordinates: [item.longitude, item.latitude] }))));
              }
            }}>
              <option value="">All classifications</option>
              {BATHING_CLASSIFICATIONS.map((classification) => <option key={classification}>{classification}</option>)}
              <option value="unclassified">Unclassified / no published classification</option>
            </select></label>
            <p role="status">{bathingWaters.length} match{bathingWaters.length === 1 ? "" : "es"} within {loadedBathingWaters.length} loaded nearby result{loadedBathingWaters.length === 1 ? "" : "s"}.</p>
            {!bathingWaters.length && !nearby.loading.has("bathing-waters") && !nearby.errors["bathing-waters"] && <p>No loaded bathing waters match this classification. The map position is unchanged.</p>}
            <button
              className="secondary-button"
              disabled={!bathingWaters.length || nearby.loading.has("bathing-waters") || Boolean(nearby.errors["bathing-waters"])}
              onClick={() => navigate(geometryBounds(bathingWaters.map((item) => ({ type: "Point", coordinates: [item.longitude, item.latitude] }))))}
            >Show loaded classification matches</button>
            <p className="caveat">Filtering applies after the bounded nearest-100 query in both static and API modes. Counts are not national totals. Annual classification is not daily swimming-safety advice.</p>
          </section>
        )}
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
            <button className="secondary-button" disabled={!thamesDischarge.length || nearby.loading.has("thames-discharge") || Boolean(nearby.errors["thames-discharge"])} onClick={() => navigate(geometryBounds(thamesDischarge.map((item) => item.geometry)))}>Show loaded monitor matches</button>
            <p className="caveat">Fits only the loaded nearby matches, not every matching monitor nationwide. Apply a filter and wait for the updated results before navigating.</p>
            <p className="caveat">
              Near-real-time means the latest accepted WaterGeo retrieval for each map request, not instantaneous publisher state.
              {nearby.provenance["thames-discharge"] && (
                <> Latest WaterGeo retrieval: <time dateTime={nearby.provenance["thames-discharge"].retrieval_completed_at}>{new Date(nearby.provenance["thames-discharge"].retrieval_completed_at).toLocaleString()}</time>.</>
              )}
            </p>
          </section>
        )}
        <details className="panel-section"><summary>Browse nearby results without the map</summary>
          <p>Point layers: nearest 100 within a bounded radius. Flood areas: loaded accepted warning snapshot. Cluster counts describe these loaded features only.</p>
          <ul className="result-list nearby-list">
            {layers.has("hydrology") && nearby.hydrology.map((item) => <li key={`h:${item.station_id}`}><button onClick={() => selectPoint("hydrology", item.station_id)}>Station: {item.labels[0] ?? item.station_id}</button></li>)}
            {layers.has("rainfall") && rainfall.map((item) => <li key={`rf:${item.station_id}`}><button onClick={() => selectPoint("rainfall", item.station_id)}>Rainfall: {item.display_name ?? item.station_id}</button></li>)}
            {layers.has("bathing-waters") && bathingWaters.map((item) => <li key={`b:${item.bathing_water_id}`}><button onClick={() => selectPoint("bathing-waters", item.bathing_water_id)}>Bathing water: {item.name}</button></li>)}
            {layers.has("flood-warnings") && floodWarnings.map((item) => <li key={`f:${item.area_id}`}><button onClick={() => selectPoint("flood-warnings", item.area_id)}>Flood area: {item.label} · {item.severity}</button></li>)}
            {layers.has("water-quality") && nearby.waterQuality.map((item) => <li key={`q:${item.sampling_point_id}`}><button onClick={() => selectPoint("water-quality", item.sampling_point_id)}>Sampling point: {item.pref_label ?? item.alt_label}</button></li>)}
            {layers.has("reservoirs") && nearby.reservoirs.map((item) => <li key={`r:${item.reservoir_id}`}><button onClick={() => selectPoint("reservoirs", item.reservoir_id)}>Reservoir: {item.name}</button></li>)}
            {layers.has("thames-discharge") && thamesDischarge.map((item) => <li key={`t:${item.site_id}`}><button onClick={() => selectPoint("thames-discharge", item.site_id)}>Thames monitor: {item.location_name} · {item.alert_status}</button></li>)}
          </ul>
        </details>
        <WaterBodyBrowser
          open={waterBodiesOpen}
          onToggle={() => setWaterBodiesOpen((value) => !value)}
          onSelect={(feature) => {
            setSelected(feature);
            setMapFocus(null);
            const bounds = geometryBounds(feature.geometry.features.map((item) => item.geometry));
            if (bounds) {
              setMapNotice(undefined);
              navigate(bounds);
            } else {
              setMapNotice("The selected Water Body has no usable accepted geometry to show on the map.");
            }
          }}
        />
        <div id="source-status"><SourceStatusPanel status={sourceStatus} error={statusError} loading={!sourceStatus && !statusError} /></div>
      </aside>

      <main className="map-workspace">
        <Onboarding />
        {viewport.radiusM === 0 && <p className="map-message" role="status">Preparing map viewport…</p>}
        {mapNotice && <p className="map-message state-error" role="alert">{mapNotice}</p>}
        <Suspense fallback={<div className="map-loading" role="status">Loading map renderer…</div>}>
          <MapView
            navigation={navigation}
            overview={overview}
            focus={mapFocus}
            initial={initial}
            activeLayers={layers}
            hydrology={nearby.hydrology}
            rainfall={rainfall}
            bathingWaters={bathingWaters}
            floodWarnings={floodWarnings}
            waterQuality={nearby.waterQuality}
            reservoirs={nearby.reservoirs}
            thamesDischarge={thamesDischarge}
            area={selected?.kind === "water-supply" ? selected.item : null}
            companyAreas={companyAreas}
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
        <DetailPanel selected={selected} onClose={() => { setSelected(null); setMapFocus(null); setMapNotice(undefined); }} />
      </aside>
    </div>
  );
}
