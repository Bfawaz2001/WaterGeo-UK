import { apiBasePath } from "./config";
import type {
  AreaFeature,
  AreaPage,
  CatchmentDataset,
  GeoJSONFeatureCollection,
  HydrologyStation,
  NearbyPage,
  Reservoir,
  SamplingPoint,
  SourceStatuses,
  WaterBodyDetail,
  WaterBodyPage,
} from "./types";

const MAX_JSON_BYTES = 10 * 1024 * 1024;
const immutableCache = new Map<string, unknown>();
const pending = new Map<string, Promise<unknown>>();

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

function pathFor(path: string): string {
  if (!path.startsWith("/v1/") && path !== "/health" && path !== "/ready") {
    throw new Error("API path is outside the WaterGeo same-origin contract");
  }
  return `${apiBasePath()}${path}`;
}

async function readBoundedJson(response: Response): Promise<unknown> {
  const declared = Number(response.headers.get("content-length"));
  if (Number.isFinite(declared) && declared > MAX_JSON_BYTES) {
    throw new ApiError(response.status, "Response exceeded the explorer size limit");
  }
  if (!response.body) return await response.json();
  const reader = response.body.getReader();
  const chunks: Uint8Array[] = [];
  let size = 0;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    size += value.byteLength;
    if (size > MAX_JSON_BYTES) {
      await reader.cancel();
      throw new ApiError(response.status, "Response exceeded the explorer size limit");
    }
    chunks.push(value);
  }
  const bytes = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return JSON.parse(new TextDecoder().decode(bytes)) as unknown;
}

async function request<T>(
  path: string,
  options: { signal?: AbortSignal | undefined; immutable?: boolean | undefined } = {},
): Promise<T> {
  const url = pathFor(path);
  if (options.immutable && immutableCache.has(url)) return immutableCache.get(url) as T;
  if (!options.signal && pending.has(url)) return pending.get(url) as Promise<T>;

  const execute = async (): Promise<T> => {
    let response: Response;
    try {
      response = await fetch(url, {
        method: "GET",
        headers: { Accept: "application/json, application/geo+json" },
        redirect: "error",
        credentials: "same-origin",
        ...(options.signal ? { signal: options.signal } : {}),
      });
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") throw error;
      throw new ApiError(0, "WaterGeo could not be reached");
    }
    const body = await readBoundedJson(response);
    if (!response.ok) {
      const detail =
        typeof body === "object" && body !== null && "detail" in body && typeof body.detail === "string"
          ? body.detail
          : `WaterGeo returned HTTP ${response.status}`;
      throw new ApiError(response.status, detail);
    }
    if (typeof body !== "object" || body === null) {
      throw new ApiError(response.status, "WaterGeo returned an invalid response");
    }
    if (options.immutable) immutableCache.set(url, body);
    return body as T;
  };

  const promise = execute();
  if (!options.signal) {
    pending.set(url, promise);
    void promise.then(
      () => pending.delete(url),
      () => pending.delete(url),
    );
  }
  return await promise;
}

function query(values: Record<string, string | number | undefined>): string {
  const params = new URLSearchParams();
  for (const [name, value] of Object.entries(values)) {
    if (value !== undefined) params.set(name, String(value));
  }
  return params.toString();
}

function pinned<T extends { dataset: { snapshot_id: string } }>(
  page: T,
  expectedSnapshot?: string,
): T {
  if (expectedSnapshot !== undefined && page.dataset.snapshot_id !== expectedSnapshot) {
    throw new ApiError(503, "WaterGeo changed snapshot during this map interaction");
  }
  return page;
}

export const api = {
  sourceStatuses: (signal?: AbortSignal) =>
    request<SourceStatuses>("/v1/sources/status", { signal }),

  hydrologyNear: async (lon: number, lat: number, radius: number, signal: AbortSignal) =>
    await request<NearbyPage<HydrologyStation>>(
      `/v1/hydrology/stations/near?${query({ lon, lat, radius_m: radius, limit: 100 })}`,
      { signal },
    ),

  waterQualityNear: async (
    lon: number,
    lat: number,
    radius: number,
    signal: AbortSignal,
    snapshotId?: string,
  ) =>
    pinned(
      await request<NearbyPage<SamplingPoint>>(
        `/v1/water-quality/sampling-points/near?${query({ lon, lat, radius_m: radius, limit: 100, snapshot_id: snapshotId })}`,
        { signal },
      ),
      snapshotId,
    ),

  reservoirsNear: async (
    lon: number,
    lat: number,
    radius: number,
    signal: AbortSignal,
    snapshotId?: string,
  ) =>
    pinned(
      await request<NearbyPage<Reservoir>>(
        `/v1/severn-trent/reservoir-levels/reservoirs/near?${query({ lon, lat, radius_m: radius, limit: 100, snapshot_id: snapshotId })}`,
        { signal },
      ),
      snapshotId,
    ),

  areasAtPoint: (lon: number, lat: number, signal?: AbortSignal) =>
    request<AreaPage>(
      `/v1/water-supply/areas/at-point?${query({ lon, lat, limit: 100 })}`,
      { signal },
    ),

  areaGeometry: (sourceId: number, signal?: AbortSignal) =>
    request<AreaFeature>(`/v1/water-supply/areas/${sourceId}/geometry`, {
      signal,
      immutable: true,
    }),

  catchmentDataset: (signal?: AbortSignal) =>
    request<CatchmentDataset>("/v1/catchments/dataset", { signal, immutable: true }),

  waterBodies: (snapshotId?: string, afterId?: string, signal?: AbortSignal) =>
    request<WaterBodyPage>(
      `/v1/catchments/water-bodies?${query({ limit: 100, snapshot_id: snapshotId, after_id: afterId })}`,
      { signal },
    ).then((page) => pinned(page, snapshotId)),

  waterBody: (identity: string, signal?: AbortSignal) =>
    request<WaterBodyDetail>(`/v1/catchments/water-bodies/${encodeURIComponent(identity)}`, {
      signal,
      immutable: true,
    }),

  waterBodyGeometry: (identity: string, signal?: AbortSignal) =>
    request<GeoJSONFeatureCollection>(
      `/v1/catchments/water-bodies/${encodeURIComponent(identity)}/geometry`,
      { signal, immutable: true },
    ),
};

export function clearApiCaches(): void {
  immutableCache.clear();
  pending.clear();
}
