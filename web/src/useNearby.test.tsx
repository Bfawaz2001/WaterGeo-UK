import { act, renderHook } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { ApiError, api } from "./api";
import { dataset } from "./test/fixtures";
import type { HydrologyStation, NearbyPage } from "./types";
import { useNearby } from "./useNearby";

afterEach(() => vi.useRealTimers());

it("waits for the actual map viewport before issuing the initial nearby request", async () => {
  vi.useFakeTimers();
  const hydrology = vi.spyOn(api, "hydrologyNear").mockResolvedValue({ dataset, items: [], next_after_id: null });
  const layers = new Set(["hydrology"] as const);
  const { rerender } = renderHook(({ radiusM }) => useNearby({ longitude: -1, latitude: 52, radiusM }, layers, 20), { initialProps: { radiusM: 0 } });
  await act(() => vi.advanceTimersByTimeAsync(100));
  expect(hydrology).not.toHaveBeenCalled();
  rerender({ radiusM: 5000 });
  await act(() => vi.advanceTimersByTimeAsync(20));
  expect(hydrology).toHaveBeenCalledOnce();
});

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

it.each(["water-quality", "reservoirs"] as const)("clears only mismatched %s results and permits a fresh snapshot", async (layer) => {
  vi.useFakeTimers();
  const item = { station_id: "keep" } as HydrologyStation;
  vi.spyOn(api, "hydrologyNear").mockResolvedValue({ dataset, items: [item], next_after_id: null });
  const method = layer === "water-quality" ? "waterQualityNear" : "reservoirsNear";
  const target = vi.spyOn(api, method)
    .mockResolvedValueOnce({ dataset, items: [{}] as never[], next_after_id: null })
    .mockRejectedValueOnce(new ApiError(503, "WaterGeo changed snapshot during this map interaction"))
    .mockResolvedValueOnce({ dataset: { ...dataset, snapshot_id: "B" }, items: [{}] as never[], next_after_id: null });
  const layers = new Set(["hydrology", layer] as const);
  const { result, rerender } = renderHook(({ longitude }) =>
    useNearby({ longitude, latitude: 52, radiusM: 5000 }, layers, 20),
  { initialProps: { longitude: -1 } });
  await act(() => vi.advanceTimersByTimeAsync(20));
  expect(result.current.provenance[layer]?.snapshot_id).toBe(dataset.snapshot_id);
  rerender({ longitude: -2 });
  await act(() => vi.advanceTimersByTimeAsync(20));
  expect(result.current[layer === "water-quality" ? "waterQuality" : "reservoirs"]).toEqual([]);
  expect(result.current.provenance[layer]).toBeUndefined();
  expect(result.current.errors[layer]).toBeTruthy();
  expect(result.current.hydrology).toEqual([item]);
  rerender({ longitude: -3 });
  await act(() => vi.advanceTimersByTimeAsync(20));
  expect(target.mock.calls[2]?.[4]).toBeUndefined();
  expect(result.current.provenance[layer]?.snapshot_id).toBe("B");
  expect(result.current.errors[layer]).toBeUndefined();
});

it("sends Thames status filters to the bounded server query", async () => {
  vi.useFakeTimers();
  const thames = vi.spyOn(api, "thamesDischargeNear").mockResolvedValue({
    dataset,
    items: [{
      site_id: "TWL00001", location_name: "Test", permit_number: "CTCR.0001",
      grid_reference: "SU12345678", easting: 412340, northing: 156780,
      geometry: { type: "Point", coordinates: [-1.82, 51.31] },
      receiving_watercourse: "Test Brook", alert_status: "Discharging",
      status_changed: "2026-09-20T12:30:00", alert_past_48_hours: true,
      most_recent_discharge_start: "2026-09-20T12:00:00",
      most_recent_discharge_stop: null, distance_m: 10,
    }],
    next_after_id: null,
  });
  const layers = new Set(["thames-discharge"] as const);
  const { result } = renderHook(() => useNearby(
    { longitude: -1.82, latitude: 51.31, radiusM: 5000 },
    layers,
    20,
    { status: "Discharging", recent: true },
  ));
  await act(() => vi.advanceTimersByTimeAsync(20));
  expect(thames).toHaveBeenCalledWith(-1.82, 51.31, 5000, expect.any(AbortSignal), undefined, "Discharging", true);
  expect(result.current.thamesDischarge[0]?.site_id).toBe("TWL00001");
});
