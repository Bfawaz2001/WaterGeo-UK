import { act, renderHook } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { api } from "./api";
import { dataset } from "./test/fixtures";
import type { HydrologyStation, NearbyPage } from "./types";
import { useNearby } from "./useNearby";

afterEach(() => vi.useRealTimers());

it("debounces movement, aborts stale requests, and ignores late results", async () => {
  vi.useFakeTimers();
  const resolvers: Array<(value: NearbyPage<HydrologyStation>) => void> = [];
  const hydrology = vi.spyOn(api, "hydrologyNear").mockImplementation(
    () => new Promise((resolve) => resolvers.push(resolve)),
  );
  const layers = new Set(["hydrology"] as const);
  const { result, rerender } = renderHook(
    ({ longitude }) =>
      useNearby({ longitude, latitude: 52, radiusM: 5000 }, layers, 20),
    { initialProps: { longitude: -1 } },
  );
  await act(() => vi.advanceTimersByTime(20));
  expect(hydrology).toHaveBeenCalledTimes(1);
  const firstSignal = hydrology.mock.calls[0]?.[3];
  rerender({ longitude: -2 });
  expect(firstSignal?.aborted).toBe(true);
  await act(() => vi.advanceTimersByTime(20));
  expect(hydrology).toHaveBeenCalledTimes(2);
  await act(async () => {
    resolvers[1]?.({
      dataset,
      items: [{
        station_id: "new",
        source_uri: "https://example.test/new",
        labels: ["New"],
        location_status: "available",
        latitude: 52,
        longitude: -2,
        geometry: { type: "Point", coordinates: [-2, 52] },
        distance_m: 1,
      }],
      next_after_id: null,
    });
    await Promise.resolve();
  });
  await act(async () => {
    resolvers[0]?.({
      dataset,
      items: [{
        station_id: "old",
        source_uri: "https://example.test/old",
        labels: ["Old"],
        location_status: "available",
        latitude: 52,
        longitude: -1,
        geometry: { type: "Point", coordinates: [-1, 52] },
        distance_m: 1,
      }],
      next_after_id: null,
    });
    await Promise.resolve();
  });
  expect(result.current.hydrology[0]?.station_id).toBe("new");
});
