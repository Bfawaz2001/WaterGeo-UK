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
