import { expect, it } from "vitest";

import { explorerSearch, parseExplorerState, parseWaterSupplyId } from "./urlState";

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


it.each(["0", "-1", "1.5", "1e3", " 3", "abc", "9007199254740992", "9999999999999999999"])("rejects unsafe shared source ID %s", (identity) => {
  expect(parseWaterSupplyId(identity)).toBeNull();
  expect(parseExplorerState("?selected=" + encodeURIComponent("water-supply:" + identity)).selected).toBeNull();
});

it.each(["3", "1141", "9007199254740991"])("preserves safe shared source ID %s", (identity) => {
  expect(parseWaterSupplyId(identity)).toBe(Number(identity));
  expect(parseExplorerState("?selected=water-supply:" + identity).selected).toBe("water-supply:" + identity);
});
