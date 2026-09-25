import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";

import { App } from "./App";
import type { AreaFeature, CatchmentDataset, GeoJSONFeatureCollection, WaterBodyDetail } from "./types";
import { dataset, sourceStatuses } from "./test/fixtures";

const mocks = vi.hoisted(() => ({
  sourceStatuses: vi.fn(),
  areasAtPoint: vi.fn(),
  areaGeometry: vi.fn(),
  catchmentDataset: vi.fn(),
  waterBody: vi.fn(),
  waterBodyGeometry: vi.fn(),
}));

vi.mock("./api", () => ({
  ApiError: class ApiError extends Error {
    status = 503;
  },
  api: {
    sourceStatuses: mocks.sourceStatuses,
    areasAtPoint: mocks.areasAtPoint,
    areaGeometry: mocks.areaGeometry,
    catchmentDataset: mocks.catchmentDataset,
    waterBody: mocks.waterBody,
    waterBodyGeometry: mocks.waterBodyGeometry,
  },
}));

vi.mock("./useNearby", () => ({
  useNearby: () => ({
    hydrology: [
      {
        station_id: "station-1",
        source_uri: "https://example.test/station",
        labels: ["River Station"],
        location_status: "available",
        latitude: 52,
        longitude: -1,
        geometry: { type: "Point", coordinates: [-1, 52] },
        distance_m: 10,
      },
    ],
    waterQuality: [],
    reservoirs: [],
    provenance: { hydrology: dataset },
    loading: new Set(),
    errors: {},
  }),
}));

vi.mock("./MapView", () => ({
  MapView: ({ onMapClick, onSelectPoint }: { onMapClick: (lon: number, lat: number) => void; onSelectPoint: (kind: string, id: string) => void }) => (
    <div aria-label="Mock map">
      <button type="button" onClick={() => onMapClick(-1, 52)}>Click map</button>
      <button type="button" onClick={() => onSelectPoint("hydrology", "station-1")}>Select station</button>
    </div>
  ),
}));

vi.mock("./WaterBodyBrowser", () => ({
  WaterBodyBrowser: () => <section aria-label="Water Bodies" />,
}));

const areaFeature: AreaFeature = {
  type: "Feature",
  id: 3,
  properties: {
    source_id: 3,
    area_served: "Example area",
    company: "Example Water",
    company_acronym: "EW",
    company_type: "Water only",
    area_type: "Appointment",
    warnings: null,
    transformed: false,
    snapshot_id: "33333333-3333-4333-8333-333333333333",
    geometry_url: "/geometry",
    licence_statement: "Open Government Licence",
    source_provenance: "Public source",
    disclaimer: "A match does not establish the current supplier.",
    premises_disclaimer: null,
    coastline_disclaimer: null,
  },
  geometry: { type: "MultiPolygon", coordinates: [] },
  presentation: {
    policy_version: "v1",
    review_reference: "ADR 0006",
    method: "reprojection",
  },
};

const catchmentDataset: CatchmentDataset = {
  ...dataset,
  source_url: "https://example.test/catchments",
  plan_version: "c3-plan",
  relationship_caveat: "Relationships are publisher hierarchy only.",
};

const waterBody: WaterBodyDetail = {
  water_body_id: "GB/one two",
  operational_catchment_id: "OC1",
  management_catchment_id: "MC1",
  river_basin_district_id: "RBD1",
  name: "Example Water Body",
  water_body_type: "River",
  publisher_uri: "https://example.test/water-body",
  snapshot_id: dataset.snapshot_id,
  geometry_url: "/geometry",
};

const waterBodyGeometry: GeoJSONFeatureCollection = {
  type: "FeatureCollection",
  water_body_id: waterBody.water_body_id,
  snapshot_id: dataset.snapshot_id,
  features: [],
};

beforeEach(() => {
  window.history.replaceState(null, "", "/");
  mocks.sourceStatuses.mockResolvedValue(sourceStatuses);
  mocks.areasAtPoint.mockResolvedValue({
    snapshot_id: areaFeature.properties.snapshot_id,
    next_after_id: null,
    items: [
      { ...areaFeature.properties, source_id: 3 },
      { ...areaFeature.properties, source_id: 4, company: "Second Water" },
    ],
  });
  mocks.areaGeometry.mockResolvedValue(areaFeature);
  mocks.catchmentDataset.mockResolvedValue(catchmentDataset);
  mocks.waterBody.mockResolvedValue(waterBody);
  mocks.waterBodyGeometry.mockResolvedValue(waterBodyGeometry);
});

it("restores a shared Water Body selection with matching snapshot provenance", async () => {
  window.history.replaceState(null, "", "/?selected=water-body%3AGB%2Fone%20two");
  render(<App />);
  expect(await screen.findByRole("heading", { name: "Example Water Body" })).toBeInTheDocument();
  expect(mocks.waterBody).toHaveBeenCalledWith("GB/one two", expect.any(AbortSignal));
  expect(screen.getByText(dataset.attribution)).toBeInTheDocument();
});

it("selects a point and presents its provenance outside the map", async () => {
  render(<App />);
  await userEvent.click(await screen.findByRole("button", { name: "Select station" }));
  expect(screen.getByRole("heading", { name: "River Station" })).toBeInTheDocument();
  expect(screen.getByText(dataset.attribution)).toBeInTheDocument();
});

it("retains overlapping water-supply matches and loads only the chosen geometry", async () => {
  render(<App />);
  await userEvent.click(screen.getByRole("checkbox", { name: /Water-supply lookup/i }));
  await userEvent.click(await screen.findByRole("button", { name: "Click map" }));
  expect(await screen.findByText(/2 matching areas/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /Example Water/ })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /Second Water/ })).toBeInTheDocument();
  expect(mocks.areaGeometry).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole("button", { name: /Example Water/ }));
  await waitFor(() => expect(mocks.areaGeometry).toHaveBeenCalledWith(3, expect.any(AbortSignal)));
  expect(await screen.findByRole("heading", { name: "Example Water" })).toBeInTheDocument();
  expect(screen.getByText(/does not establish the current supplier/)).toBeInTheDocument();
});


it.each(["0", "9007199254740993", "-1", "abc"])("does not request invalid shared area %s", async (identity) => {
  window.history.replaceState(null, "", "/?selected=water-supply:" + identity);
  render(<App />);
  await screen.findByRole("button", { name: "Select station" });
  expect(mocks.areaGeometry).not.toHaveBeenCalled();
});
