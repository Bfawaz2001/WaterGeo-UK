import { expect, it } from "vitest";
import { geometryBounds } from "./mapNavigation";
import { filterFloods, FLOOD_STATES } from "./floodFilters";
import type { FloodArea } from "./types";

it("bounds points, lines and multipart geometry without changing coordinates", () => {
  const geometry = { type: "GeometryCollection", geometries: [
    { type: "Point", coordinates: [-1, 52] },
    { type: "LineString", coordinates: [[-2, 51], [0, 54]] },
    { type: "MultiPolygon", coordinates: [[[[0, 52], [1, 52], [1, 53], [0, 52]]]] },
  ] } as const;
  const copy = JSON.parse(JSON.stringify(geometry));
  expect(geometryBounds([copy])).toEqual([[-2, 51], [1, 54]]);
  expect(copy).toEqual(geometry);
  expect(geometryBounds([{ type: "Point", coordinates: [-1, 52] }])).toEqual([[-1, 52], [-1, 52]]);
});

it("does not navigate on missing, nonfinite, out-of-range or antimeridian bounds", () => {
  expect(geometryBounds([null, { type: "Polygon", coordinates: [] }])).toBeNull();
  expect(geometryBounds([{ type: "Point", coordinates: [NaN, 52] }])).toBeNull();
  expect(geometryBounds([{ type: "Point", coordinates: [-1, 91] }])).toBeNull();
  expect(geometryBounds([{ type: "MultiPoint", coordinates: [[-179, 52], [179, 52]] }])).toBeNull();
});

it("filters exact publisher levels, retains unknown warnings in All, and excludes areas without warnings", () => {
  const items = [1, 2, 3, 4, null].map((severity_level, i) => ({
    area_id: String(i), warning_id: `W${i}`, severity_level,
  })) as FloodArea[];
  items.push({ area_id: "no-warning", warning_id: null, severity_level: null } as FloodArea);
  expect(filterFloods(items, "")).toHaveLength(5);
  for (const state of FLOOD_STATES) {
    expect(filterFloods(items, state.value).map((item) => item.severity_level)).toEqual([Number(state.value)]);
  }
  expect(filterFloods([], "4")).toEqual([]);
  expect(items).toHaveLength(6);
});
