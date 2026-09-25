import { afterEach, describe, expect, it, vi } from "vitest";

import { api, clearApiCaches } from "./api";

afterEach(() => {
  clearApiCaches();
  vi.unstubAllGlobals();
});

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

it("encodes opaque Water Body path identifiers and stays same-origin", async () => {
  const fetcher = vi.fn().mockResolvedValue(
    json({
      water_body_id: "GB/one two",
      operational_catchment_id: "1",
      management_catchment_id: "2",
      river_basin_district_id: "3",
      name: "Test body",
      water_body_type: "River",
      publisher_uri: "https://example.test/body",
      snapshot_id: "11111111-1111-4111-8111-111111111111",
      geometry_url: "/geometry",
    }),
  );
  vi.stubGlobal("fetch", fetcher);
  await api.waterBody("GB/one two");
  expect(fetcher).toHaveBeenCalledWith(
    "/v1/catchments/water-bodies/GB%2Fone%20two",
    expect.objectContaining({ redirect: "error", credentials: "same-origin" }),
  );
});

it("rejects a snapshot change instead of silently combining results", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      json({
        dataset: { snapshot_id: "22222222-2222-4222-8222-222222222222" },
        items: [],
        next_after_id: null,
      }),
    ),
  );
  await expect(
    api.waterQualityNear(
      -1,
      52,
      1000,
      new AbortController().signal,
      "11111111-1111-4111-8111-111111111111",
    ),
  ).rejects.toThrow("changed snapshot");
});

it("preserves cancellation as AbortError", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn((_url: string, options: RequestInit) =>
      new Promise<Response>((_resolve, reject) => {
        options.signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
      }),
    ),
  );
  const controller = new AbortController();
  const request = api.sourceStatuses(controller.signal);
  controller.abort();
  await expect(request).rejects.toMatchObject({ name: "AbortError" });
});

describe.each([404, 422, 503])("HTTP %s", (status) => {
  it("returns a typed sanitized API error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json({ detail: "Safe public detail" }, status)));
    await expect(api.sourceStatuses()).rejects.toEqual(
      expect.objectContaining({ status, message: "Safe public detail" }),
    );
  });
});

it("deduplicates identical metadata requests", async () => {
  let resolve!: (value: Response) => void;
  const fetcher = vi.fn().mockReturnValue(new Promise<Response>((done) => { resolve = done; }));
  vi.stubGlobal("fetch", fetcher);
  const first = api.sourceStatuses();
  const second = api.sourceStatuses();
  resolve(json({ checked_at: "2026-09-24T00:00:00Z", sources: [] }));
  await Promise.all([first, second]);
  expect(fetcher).toHaveBeenCalledTimes(1);
});
