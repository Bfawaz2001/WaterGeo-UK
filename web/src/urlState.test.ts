import { expect, it } from "vitest";

import { explorerSearch, parseExplorerState } from "./urlState";

it("accepts bounded camera, known layers, and a short stable selection", () => {
  const state = parseExplorerState(
    "?lon=-1.25&lat=52.4&z=9&layers=hydrology,reservoirs&selected=reservoirs:10014",
  );
  expect(state).toMatchObject({ longitude: -1.25, latitude: 52.4, zoom: 9, selected: "reservoirs:10014" });
  expect([...state.layers]).toEqual(["hydrology", "reservoirs"]);
  expect(explorerSearch(state)).toContain("selected=reservoirs%3A10014");
});

it("rejects invalid URL coordinates, layers, and oversized selections", () => {
  const state = parseExplorerState(`?lon=Infinity&lat=200&z=99&layers=unknown&selected=water-body:${"x".repeat(200)}`);
  expect(state.longitude).toBe(-2.5);
  expect(state.latitude).toBe(54.5);
  expect(state.zoom).toBe(5.2);
  expect([...state.layers]).toEqual(["hydrology"]);
  expect(state.selected).toBeNull();
});
