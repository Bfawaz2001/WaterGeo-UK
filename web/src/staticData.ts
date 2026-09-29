import { staticDataPath } from "./config";

const cache = new Map<string, Promise<unknown>>();
const MAX_STATIC_BYTES = 64 * 1024 * 1024;

export class StaticDataError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

async function asset<T>(relative: string, signal?: AbortSignal): Promise<T> {
  const path = `${staticDataPath()}/${relative}`;
  const load = async () => {
    const response = await fetch(path, {
      headers: { Accept: "application/json, application/geo+json" },
      credentials: "same-origin",
      redirect: "error",
      ...(signal ? { signal } : {}),
    });
    if (!response.ok) throw new StaticDataError(response.status, "Static snapshot asset unavailable");
    const declared = Number(response.headers.get("content-length"));
    if (Number.isFinite(declared) && declared > MAX_STATIC_BYTES) {
      throw new StaticDataError(413, "Static snapshot asset exceeded the browser limit");
    }
    const bytes = await response.arrayBuffer();
    if (bytes.byteLength > MAX_STATIC_BYTES) {
      throw new StaticDataError(413, "Static snapshot asset exceeded the browser limit");
    }
    return JSON.parse(new TextDecoder().decode(bytes)) as unknown;
  };
  if (signal) return (await load()) as T;
  const pending = cache.get(path) ?? load();
  cache.set(path, pending);
  return (await pending) as T;
}

interface StaticDataset {
  snapshot_id: string;
  [key: string]: unknown;
}

interface StaticItems {
  dataset: StaticDataset;
  items: Array<Record<string, unknown>>;
}

export interface StaticPublicationMetadata {
  publication_id: string;
  generated_at: string;
  watergeo_commit?: string;
}

export async function staticPublicationMetadata(
  signal?: AbortSignal,
): Promise<StaticPublicationMetadata> {
  return await asset<StaticPublicationMetadata>("manifest.json", signal);
}

function distanceMetres(lon: number, lat: number, itemLon: number, itemLat: number): number {
  const radians = Math.PI / 180;
  const dLat = (itemLat - lat) * radians;
  const dLon = (itemLon - lon) * radians;
  const value =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(lat * radians) * Math.cos(itemLat * radians) * Math.sin(dLon / 2) ** 2;
  return 6_371_000 * 2 * Math.atan2(Math.sqrt(value), Math.sqrt(1 - value));
}

function assertSnapshot(dataset: StaticDataset, expected: string | null): void {
  if (expected && dataset.snapshot_id !== expected) {
    throw new StaticDataError(503, "Static publication snapshot does not match the selection");
  }
}

function boundedPage(
  source: StaticItems,
  url: URL,
  identity: string,
  spatial = false,
): StaticItems & { next_after_id: string | null } {
  assertSnapshot(source.dataset, url.searchParams.get("snapshot_id"));
  const limit = Math.min(100, Math.max(1, Number(url.searchParams.get("limit") ?? 50)));
  const after = url.searchParams.get("after_id");
  let items = source.items.filter((item) => !after || String(item[identity]) > after);
  if (spatial) {
    const lon = Number(url.searchParams.get("lon"));
    const lat = Number(url.searchParams.get("lat"));
    const radius = Number(url.searchParams.get("radius_m"));
    items = items
      .flatMap((item) => {
        if (item.longitude === null || item.latitude === null) return [];
        const itemLon = Number(item.longitude);
        const itemLat = Number(item.latitude);
        const distance = distanceMetres(lon, lat, itemLon, itemLat);
        return Number.isFinite(distance) && distance <= radius ? [{ ...item, distance_m: distance }] : [];
      })
      .sort((left, right) => Number(left.distance_m) - Number(right.distance_m));
  }
  const selected = items.slice(0, limit);
  return {
    dataset: source.dataset,
    items: selected,
    next_after_id: items.length > limit ? String(selected.at(-1)?.[identity]) : null,
  };
}

const LISTS: Record<string, [string, string]> = {
  "/v1/hydrology/stations": ["datasets/hydrology/items.json", "station_id"],
  "/v1/water-quality/sampling-points": [
    "datasets/water-quality/items.json",
    "sampling_point_id",
  ],
  "/v1/severn-trent/reservoir-levels/reservoirs": [
    "datasets/reservoir-levels/items.json",
    "reservoir_id",
  ],
  "/v1/thames-water/discharge-status/sites": [
    "datasets/thames-discharge/items.json",
    "site_id",
  ],
  "/v1/rainfall/stations": ["datasets/rainfall/items.json", "station_id"],
  "/v1/bathing-waters": ["datasets/bathing-waters/items.json", "bathing_water_id"],
  "/v1/catchments/water-bodies": [
    "datasets/catchments/water-bodies.json",
    "water_body_id",
  ],
};

function listRoute(pathname: string): [string, string, boolean] | undefined {
  const normalized = pathname.replace(/\/near$/u, "");
  const entry = LISTS[normalized];
  return entry ? [entry[0], entry[1], pathname.endsWith("/near")] : undefined;
}

export async function staticRequest<T>(path: string, signal?: AbortSignal): Promise<T> {
  const url = new URL(path, "https://watergeo.invalid");
  if (url.pathname === "/v1/sources/status") return await asset<T>("source-status.json", signal);
  if (url.pathname === "/v1/search") {
    const index = await asset<{ items: Array<Record<string, unknown>> }>("search-index.json", signal);
    const term = (url.searchParams.get("q") ?? "").trim().toLocaleLowerCase();
    const limit = Math.min(24, Number(url.searchParams.get("limit") ?? 24));
    const matches = index.items.filter((item) => String(item.label).toLocaleLowerCase().includes(term));
    return {
      query: term,
      items: matches.slice(0, limit),
      truncated: matches.length > limit,
      available_kinds: [...new Set(index.items.map((item) => item.kind))],
      unavailable_kinds: [],
    } as T;
  }
  const list = listRoute(url.pathname);
  if (list) {
    return boundedPage(await asset<StaticItems>(list[0], signal), url, list[1], list[2]) as T;
  }
  const nationalDetail = url.pathname.match(
    /^\/v1\/(rainfall\/stations|bathing-waters)\/([^/]+)$/u,
  );
  if (nationalDetail) {
    const rainfall = nationalDetail[1] === "rainfall/stations";
    const source = await asset<StaticItems>(
      rainfall ? "datasets/rainfall/items.json" : "datasets/bathing-waters/items.json",
      signal,
    );
    assertSnapshot(source.dataset, url.searchParams.get("snapshot_id"));
    const identity = decodeURIComponent(nationalDetail[2]!);
    const field = rainfall ? "station_id" : "bathing_water_id";
    const item = source.items.find((candidate) => candidate[field] === identity);
    if (!item) throw new StaticDataError(404, "Static source entity not found");
    return { dataset: source.dataset, item } as T;
  }
  if (url.pathname === "/v1/catchments/dataset") {
    const source = await asset<StaticItems>("datasets/catchments/water-bodies.json", signal);
    assertSnapshot(source.dataset, url.searchParams.get("snapshot_id"));
    return source.dataset as T;
  }
  if (url.pathname === "/v1/company-performance/companies") {
    const source = await asset<StaticItems>(
      "datasets/company-performance/companies.json",
      signal,
    );
    assertSnapshot(source.dataset, url.searchParams.get("snapshot_id"));
    return { ...source, next_after_id: null } as T;
  }
  const performance = url.pathname.match(
    /^\/v1\/company-performance\/companies\/([^/]+)$/u,
  );
  if (performance) {
    const source = await asset<StaticItems>(
      "datasets/company-performance/companies.json",
      signal,
    );
    assertSnapshot(source.dataset, url.searchParams.get("snapshot_id"));
    const identity = decodeURIComponent(performance[1]!);
    const item = source.items.find((candidate) => candidate.company_id === identity);
    if (!item) throw new StaticDataError(404, "Static company performance not found");
    return { dataset: source.dataset, item } as T;
  }
  if (url.pathname === "/v1/flood-monitoring/areas") {
    const [manifest, areas] = await Promise.all([
      asset<{ sources: Record<string, StaticDataset> }>("manifest.json", signal),
      asset<{ features: Array<Record<string, unknown>> }>(
        "datasets/flood-warnings/areas.geojson",
        signal,
      ),
    ]);
    const dataset = manifest.sources["flood-warnings"];
    if (!dataset) throw new StaticDataError(503, "Flood snapshot missing from publication");
    return {
      dataset,
      items: areas.features.map((feature) => ({
        ...(feature.properties as Record<string, unknown>),
        geometry: feature.geometry,
      })),
      next_after_id: null,
    } as T;
  }
  if (url.pathname === "/v1/water-supply/areas/at-point") {
    throw new StaticDataError(
      501,
      "Point-in-polygon lookup requires API mode; use static search to select an area",
    );
  }
  const supply = url.pathname.match(/^\/v1\/water-supply\/areas\/(\d+)\/geometry$/u);
  if (supply) return await asset<T>(`datasets/water-supply/areas/${supply[1]}.geojson`, signal);
  const waterBodyGeometry = url.pathname.match(
    /^\/v1\/catchments\/water-bodies\/([^/]+)\/geometry$/u,
  );
  if (waterBodyGeometry) {
    const body = decodeURIComponent(waterBodyGeometry[1]!);
    const collection = await asset<{ type: string; features: Array<Record<string, unknown>> }>(
      "datasets/catchments/water-bodies.geojson",
      signal,
    );
    return {
      type: "FeatureCollection",
      water_body_id: body,
      snapshot_id: url.searchParams.get("snapshot_id"),
      features: collection.features.filter(
        (feature) => (feature.properties as Record<string, unknown>).water_body_id === body,
      ),
    } as T;
  }
  const waterBody = url.pathname.match(/^\/v1\/catchments\/water-bodies\/([^/]+)$/u);
  if (waterBody) {
    const body = decodeURIComponent(waterBody[1]!);
    const source = await asset<StaticItems>("datasets/catchments/water-bodies.json", signal);
    assertSnapshot(source.dataset, url.searchParams.get("snapshot_id"));
    const item = source.items.find((candidate) => candidate.water_body_id === body);
    if (!item) throw new StaticDataError(404, "Static Water Body not found");
    return {
      ...item,
      snapshot_id: source.dataset.snapshot_id,
      geometry_url: `/v1/catchments/water-bodies/${encodeURIComponent(body)}/geometry`,
    } as T;
  }
  throw new StaticDataError(501, "This operation requires WaterGeo API mode");
}

export function clearStaticCaches(): void {
  cache.clear();
}
