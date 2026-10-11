import { afterEach, expect, it, vi } from "vitest";

import { ApiError, api, clearApiCaches } from "./api";
import { staticPublicationMetadata } from "./staticData";

afterEach(() => {
  clearApiCaches();
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

function response(value: unknown): Response {
  return new Response(JSON.stringify(value), {
    headers: { "content-type": "application/json" },
  });
}

it("selects static mode and loads source status from the publication", async () => {
  vi.stubEnv("VITE_WATERGEO_DATA_MODE", "static");
  const fetcher = vi.fn().mockResolvedValue(
    response({ checked_at: "2026-09-29T00:00:00Z", sources: [] }),
  );
  vi.stubGlobal("fetch", fetcher);
  await expect(api.sourceStatuses()).resolves.toMatchObject({ sources: [] });
  expect(fetcher).toHaveBeenCalledWith(
    "/watergeo-data/source-status.json",
    expect.objectContaining({ credentials: "same-origin", redirect: "error" }),
  );
});

it("loads publication generation time separately from source status check time", async () => {
  const fetcher = vi.fn().mockResolvedValue(
    response({
      publication_id: "publication-a",
      generated_at: "2026-09-29T05:19:00Z",
    }),
  );
  vi.stubGlobal("fetch", fetcher);
  await expect(staticPublicationMetadata()).resolves.toEqual({
    publication_id: "publication-a",
    generated_at: "2026-09-29T05:19:00Z",
  });
  expect(fetcher).toHaveBeenCalledWith(
    "/watergeo-data/manifest.json",
    expect.objectContaining({ credentials: "same-origin", redirect: "error" }),
  );
});

it("uses the static search index and bounded client-side rainfall distance", async () => {
  vi.stubEnv("VITE_WATERGEO_DATA_MODE", "static");
  const dataset = { snapshot_id: "snapshot-a", publisher: "Environment Agency" };
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => {
      if (url.endsWith("search-index.json")) {
        return Promise.resolve(
          response({
            items: [
              {
                kind: "rainfall",
                identity: "RF1",
                label: "Rainfall station RF1",
                context: "rainfall",
                publisher: "Environment Agency",
                snapshot_id: "snapshot-a",
                longitude: -1,
                latitude: 52,
              },
            ],
          }),
        );
      }
      return Promise.resolve(
        response({
          dataset,
          items: [
            { station_id: "RF1", display_name: null, longitude: -1, latitude: 52 },
            { station_id: "RF2", display_name: null, longitude: 1, latitude: 54 },
          ],
        }),
      );
    }),
  );
  await expect(api.search("RF1", new AbortController().signal)).resolves.toMatchObject({
    items: [{ identity: "RF1" }],
  });
  await expect(api.rainfallNear(-1, 52, 5_000, new AbortController().signal)).resolves.toMatchObject({
    dataset,
    items: [{ station_id: "RF1" }],
  });
});

it("explicitly rejects server-only point-in-polygon lookup in static mode", async () => {
  vi.stubEnv("VITE_WATERGEO_DATA_MODE", "static");
  await expect(api.areasAtPoint(-1, 52)).rejects.toMatchObject({
    constructor: ApiError,
    status: 501,
    message: expect.stringContaining("requires API mode"),
  });
});

it("serves the complete snapshot-pinned company inventory and exact collection in static mode", async () => {
  vi.stubEnv("VITE_WATERGEO_DATA_MODE", "static");
  const dataset = { snapshot_id: "snapshot-a" };
  const fetcher = vi.fn((url: string) => {
    if (url.endsWith("companies.json")) {
      return Promise.resolve(response({
        dataset,
        snapshot_id: "snapshot-a",
        items: [{
          company_acronym: "ANH", display_name: "Anglian Water",
          publisher_labels: ["Anglian Water"], area_count: 2,
          areas: [{ source_id: 1 }, { source_id: 2 }],
        }],
      }));
    }
    return Promise.resolve(response({
      type: "FeatureCollection", snapshot_id: "snapshot-a",
      company: { company_acronym: "ANH", display_name: "Anglian Water", publisher_labels: ["Anglian Water"], area_count: 2 },
      features: [{ id: 1 }, { id: 2 }],
    }));
  });
  vi.stubGlobal("fetch", fetcher);

  await expect(api.waterSupplyCompanies(undefined, "snapshot-a")).resolves.toMatchObject({
    snapshot_id: "snapshot-a", items: [{ company_acronym: "ANH", area_count: 2 }],
  });
  await expect(api.waterSupplyCompanyAreas("ANH", "snapshot-a", 1)).resolves.toMatchObject({
    snapshot_id: "snapshot-a", items: [{ source_id: 2 }], next_after_id: null,
  });
  await expect(api.waterSupplyCompanyGeometry("ANH", "snapshot-a")).resolves.toMatchObject({
    snapshot_id: "snapshot-a", features: [{ id: 1 }, { id: 2 }],
  });
  expect(fetcher).toHaveBeenCalledWith(
    "/watergeo-data/datasets/water-supply/companies/ANH.geojson",
    expect.any(Object),
  );
});
