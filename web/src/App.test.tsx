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
  search: vi.fn(),
  hydrologyDetail: vi.fn(),
  waterSupplyCompanies: vi.fn(),
  waterSupplyCompanyAreas: vi.fn(),
  waterSupplyCompanyGeometry: vi.fn(),
  companyPerformanceCompanies: vi.fn(),
  companyPerformance: vi.fn(),
  writeText: vi.fn(),
  browserSelection: vi.fn(),
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
    search: mocks.search,
    hydrologyDetail: mocks.hydrologyDetail,
    waterSupplyCompanies: mocks.waterSupplyCompanies,
    waterSupplyCompanyAreas: mocks.waterSupplyCompanyAreas,
    waterSupplyCompanyGeometry: mocks.waterSupplyCompanyGeometry,
    companyPerformanceCompanies: mocks.companyPerformanceCompanies,
    companyPerformance: mocks.companyPerformance,
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
    bathingWaters: [
      { bathing_water_id: "excellent", publisher_uri: "https://example.test/excellent", name: "Excellent Bay", latitude: 51, longitude: -2, classification: "Excellent", assessment_year: 2025, latest_sample_uri: null, latest_risk_prediction: null, distance_m: 1 },
      { bathing_water_id: "none", publisher_uri: "https://example.test/none", name: "Unclassified Bay", latitude: 52, longitude: -3, classification: null, assessment_year: null, latest_sample_uri: null, latest_risk_prediction: null, distance_m: 2 },
    ],
    reservoirs: [],
    thamesDischarge: [{
      site_id: "TWL00001", location_name: "Test overflow", permit_number: "CTCR.0001",
      grid_reference: "SU12345678", easting: 412340, northing: 156780,
      geometry: { type: "Point", coordinates: [-1.82, 51.31] },
      receiving_watercourse: "Test Brook", alert_status: "Discharging",
      status_changed: "2026-09-20T12:30:00", alert_past_48_hours: true,
      most_recent_discharge_start: "2026-09-20T12:00:00",
      most_recent_discharge_stop: null, distance_m: 10,
    }],
    provenance: { hydrology: dataset, "thames-discharge": dataset, "bathing-waters": dataset },
    loading: new Set(),
    errors: {},
  }),
}));

vi.mock("./MapView", () => ({
  MapView: ({ onMapClick, onSelectPoint, bathingWaters, navigation, focus, waterBody: selectedWaterBody, companyAreas }: { onMapClick: (lon: number, lat: number) => void; onSelectPoint: (kind: string, id: string) => void; bathingWaters: Array<{ bathing_water_id: string }>; navigation?: unknown; focus?: unknown; waterBody?: unknown; companyAreas?: unknown }) => (
    <div aria-label="Mock map">
      <button type="button" onClick={() => onMapClick(-1, 52)}>Click map</button>
      <button type="button" onClick={() => onSelectPoint("hydrology", "station-1")}>Select station</button>
      <span data-testid="mapped-bathing-waters">{bathingWaters.map((item) => item.bathing_water_id).join(",")}</span>
      <span data-testid="map-navigation">{JSON.stringify(navigation)}</span>
      <span data-testid="map-focus">{JSON.stringify(focus)}</span>
      <span data-testid="mapped-water-body">{JSON.stringify(selectedWaterBody)}</span>
      <span data-testid="mapped-company-areas">{JSON.stringify(companyAreas)}</span>
    </div>
  ),
}));

vi.mock("./WaterBodyBrowser", () => ({
  WaterBodyBrowser: ({ onSelect }: { onSelect: (value: unknown) => void }) => <section aria-label="Water Bodies"><button type="button" onClick={() => onSelect(mocks.browserSelection())}>Select Water Body from browser</button></section>,
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
  features: [{ type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: [[-2, 51], [-1, 52]] } }],
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
  const company = { company_acronym: "EW", display_name: "Example Water", publisher_labels: ["Example Water"], area_count: 1 };
  mocks.waterSupplyCompanies.mockResolvedValue({ snapshot_id: areaFeature.properties.snapshot_id, items: [company] });
  mocks.waterSupplyCompanyAreas.mockResolvedValue({ snapshot_id: areaFeature.properties.snapshot_id, company, items: [areaFeature.properties], next_after_id: null });
  mocks.waterSupplyCompanyGeometry.mockResolvedValue({ type: "FeatureCollection", snapshot_id: areaFeature.properties.snapshot_id, company, features: [areaFeature] });
  mocks.companyPerformanceCompanies.mockResolvedValue({ dataset, items: [{ company_id: "example", company_name: "Example Water", boundary_company_acronym: "EW" }], next_after_id: null });
  mocks.companyPerformance.mockResolvedValue({ dataset, item: { company_id: "example", company_name: "Example Water", boundary_company_acronym: "EW", measures: [{ reporting_period: "2024-25", measure_code: "M1", measure_name: "Leakage", value: 1, value_state: "reported", unit: "Ml/d", definition: "Fixture", publication: "Fixture" }] } });
  mocks.catchmentDataset.mockResolvedValue(catchmentDataset);
  mocks.waterBody.mockResolvedValue(waterBody);
  mocks.waterBodyGeometry.mockResolvedValue(waterBodyGeometry);
  mocks.search.mockResolvedValue({
    query: "river", truncated: false, available_kinds: ["hydrology"], unavailable_kinds: [], items: [{
      kind: "hydrology", identity: "station-1", label: "River Station",
      context: "Hydrology station", publisher: "Environment Agency",
      snapshot_id: dataset.snapshot_id, longitude: -1, latitude: 52,
    }],
  });
  mocks.hydrologyDetail.mockResolvedValue({
    station_id: "station-1", source_uri: "https://example.test/station",
    labels: ["River Station"], location_status: "available", latitude: 52, longitude: -1,
    geometry: { type: "Point", coordinates: [-1, 52] }, distance_m: null,
    dataset, measures: [],
  });
  mocks.browserSelection.mockReturnValue({ kind: "water-body", item: waterBody, dataset: catchmentDataset, geometry: waterBodyGeometry });
  mocks.writeText.mockReset();
  mocks.writeText.mockResolvedValue(undefined);
  Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText: mocks.writeText } });
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

it("supersedes point focus and navigates once to selected Water Body geometry", async () => {
  render(<App />);
  await userEvent.click(await screen.findByRole("button", { name: "Select station" }));
  expect(screen.getByTestId("map-focus")).toHaveTextContent("station-1");
  await userEvent.click(screen.getByRole("button", { name: "Select Water Body from browser" }));
  expect(screen.getByRole("heading", { name: "Example Water Body" })).toBeInTheDocument();
  expect(screen.getByTestId("map-focus")).toHaveTextContent("null");
  expect(screen.getByTestId("map-navigation")).toHaveTextContent('"bounds":[[-2,51],[-1,52]]');
  expect(screen.getByTestId("mapped-water-body")).toHaveTextContent('"LineString"');
});

it("navigates a searched Water Body and keeps its accepted snapshot geometry selected", async () => {
  mocks.search.mockResolvedValueOnce({
    query: "till", truncated: false, available_kinds: ["water-body"], unavailable_kinds: [], items: [{
      kind: "water-body", identity: waterBody.water_body_id, label: waterBody.name,
      context: "Water Body", publisher: "Environment Agency",
      snapshot_id: dataset.snapshot_id, longitude: null, latitude: null,
    }],
  });
  render(<App />);
  await userEvent.type(screen.getByRole("searchbox"), "till");
  await userEvent.click(await screen.findByRole("button", { name: /Example Water Body/ }));
  await waitFor(() => expect(mocks.waterBodyGeometry).toHaveBeenCalledWith(
    waterBody.water_body_id, expect.any(AbortSignal), dataset.snapshot_id,
  ));
  expect(screen.getByTestId("map-navigation")).toHaveTextContent('"bounds":[[-2,51],[-1,52]]');
  expect(screen.getByTestId("mapped-water-body")).toHaveTextContent('"LineString"');
});

it("keeps the current view and reports an accepted Water Body without usable geometry", async () => {
  mocks.browserSelection.mockReturnValueOnce({
    kind: "water-body", item: waterBody, dataset: catchmentDataset,
    geometry: { ...waterBodyGeometry, features: [] },
  });
  render(<App />);
  await userEvent.click(screen.getByRole("button", { name: "Select Water Body from browser" }));
  expect(screen.getByRole("alert")).toHaveTextContent(/no usable accepted geometry/);
  expect(screen.getByTestId("map-navigation")).toHaveTextContent("null");
  await userEvent.click(screen.getByRole("button", { name: "Select station" }));
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

it("shows accessible copy success and a manual fallback without using boundary errors", async () => {
  render(<App />);
  await userEvent.click(screen.getByRole("button", { name: "Copy a shareable map URL" }));
  expect(await screen.findByText("Link copied. This local address works only on this computer.")).toBeInTheDocument();
  expect(mocks.writeText).toHaveBeenCalledWith(window.location.href);

  await userEvent.click(screen.getByRole("button", { name: "Select station" }));
  await waitFor(() => expect(screen.queryByText(/Link copied/)).not.toBeInTheDocument());

  mocks.writeText.mockRejectedValueOnce(new Error("blocked"));
  await userEvent.click(screen.getByRole("button", { name: "Copy a shareable map URL" }));
  expect(await screen.findByText(/Copy was blocked/)).toBeInTheDocument();
  expect(screen.getByRole("textbox", { name: "Share URL for manual copying" })).toHaveValue(window.location.href);
  expect(screen.queryByText(/boundary lookup could not/)).not.toBeInTheDocument();
});

it("restores supported flood and bathing filters from a shared URL", () => {
  window.history.replaceState(null, "", "/?layers=flood-warnings,bathing-waters&flood=3&bathing=Good");
  render(<App />);
  expect(screen.getByRole("combobox", { name: "Publisher severity" })).toHaveValue("3");
  expect(screen.getByRole("combobox", { name: "Annual publisher classification" })).toHaveValue("Good");
});

it("searches current indexed entities and opens a snapshot-pinned map feature", async () => {
  render(<App />);
  await userEvent.type(screen.getByRole("searchbox"), "river");
  const result = await screen.findByRole("button", { name: /River Station/ });
  await userEvent.click(result);
  await waitFor(() => expect(mocks.hydrologyDetail).toHaveBeenCalledWith(
    "station-1", expect.any(AbortSignal), dataset.snapshot_id,
  ));
  expect(screen.getByRole("heading", { name: "River Station" })).toBeInTheDocument();
  expect(screen.getByRole("checkbox", { name: /Hydrology stations/ })).toBeChecked();
});

it("labels Thames map status with the latest WaterGeo retrieval time", () => {
  window.history.replaceState(null, "", "/?layers=thames-discharge");
  render(<App />);
  expect(screen.getByText(/Near-real-time means the latest accepted WaterGeo retrieval/)).toBeInTheDocument();
  expect(screen.getByText(/Latest WaterGeo retrieval:/)).toBeInTheDocument();
  expect(screen.getByText(/Latest WaterGeo retrieval:/).querySelector("time")).toHaveAttribute(
    "datetime",
    dataset.retrieval_completed_at,
  );
});

it("collapses and restores the layer panel using an accessible control", async () => {
  render(<App />);
  const toggle = screen.getByRole("button", { name: "Layers & filters" });
  expect(toggle).toHaveAttribute("aria-expanded", "true");
  await userEvent.click(toggle);
  expect(toggle).toHaveAttribute("aria-expanded", "false");
  expect(screen.queryByRole("complementary", { name: "Explorer controls" })).not.toBeInTheDocument();
  await userEvent.click(toggle);
  expect(screen.getByRole("complementary", { name: "Explorer controls" })).toBeVisible();
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

it("selects a complete company view and keeps performance as a separate provenance-bearing selection", async () => {
  render(<App />);
  await userEvent.click(screen.getByRole("checkbox", { name: /Water-supply lookup/i }));
  await userEvent.selectOptions(await screen.findByLabelText("Water company"), "EW");
  expect(await screen.findByText((_, element) => element?.textContent === "1 verified area")).toBeInTheDocument();
  expect(mocks.waterSupplyCompanyAreas).toHaveBeenCalledWith(
    "EW", areaFeature.properties.snapshot_id, undefined, expect.any(AbortSignal),
  );
  expect(screen.getByTestId("mapped-company-areas")).toHaveTextContent("FeatureCollection");
  await userEvent.click(screen.getByRole("button", { name: "View company performance" }));
  expect(await screen.findByRole("heading", { name: "Example Water" })).toBeInTheDocument();
  expect(screen.getByText("Company-wide performance")).toBeInTheDocument();
  expect(screen.getByText(dataset.attribution)).toBeInTheDocument();
  expect(screen.getByText(/analytically separate from the dated supply-area polygons/)).toBeInTheDocument();
});

it("clears stale company state before a switched company geometry request fails", async () => {
  const secondCompany = { company_acronym: "SW", display_name: "Second Water", publisher_labels: ["Second Water"], area_count: 1 };
  const secondArea = {
    ...areaFeature,
    id: 4,
    properties: { ...areaFeature.properties, source_id: 4, company: "Second Water", company_acronym: "SW" },
  };
  mocks.waterSupplyCompanies.mockResolvedValue({
    snapshot_id: areaFeature.properties.snapshot_id,
    items: [
      { company_acronym: "EW", display_name: "Example Water", publisher_labels: ["Example Water"], area_count: 1 },
      secondCompany,
    ],
  });
  mocks.waterSupplyCompanyAreas.mockImplementation((acronym: string) => Promise.resolve({
    snapshot_id: areaFeature.properties.snapshot_id,
    company: acronym === "EW"
      ? { company_acronym: "EW", display_name: "Example Water", publisher_labels: ["Example Water"], area_count: 1 }
      : secondCompany,
    items: [acronym === "EW" ? areaFeature.properties : secondArea.properties],
    next_after_id: null,
  }));
  mocks.waterSupplyCompanyGeometry.mockImplementation((acronym: string) =>
    acronym === "EW"
      ? Promise.resolve({
          type: "FeatureCollection",
          snapshot_id: areaFeature.properties.snapshot_id,
          company: { company_acronym: "EW", display_name: "Example Water", publisher_labels: ["Example Water"], area_count: 1 },
          features: [areaFeature],
        })
      : Promise.reject(new Error("geometry unavailable")),
  );
  render(<App />);
  await userEvent.click(screen.getByRole("checkbox", { name: /Water-supply lookup/i }));
  const selector = await screen.findByLabelText("Water company");
  await userEvent.selectOptions(selector, "EW");
  await userEvent.click(await screen.findByRole("button", { name: /Example area/ }));
  expect(screen.getByRole("heading", { name: "Selected supply area" })).toBeInTheDocument();
  expect(screen.getByTestId("mapped-company-areas")).toHaveTextContent("FeatureCollection");

  await userEvent.selectOptions(selector, "SW");
  expect(screen.queryByRole("heading", { name: "Selected supply area" })).not.toBeInTheDocument();
  expect(screen.getByTestId("mapped-company-areas")).toHaveTextContent("null");
  expect(await screen.findByText(/complete company-area view could not be verified/u)).toBeInTheDocument();
  expect(window.location.search).toContain("company=SW");

  await userEvent.selectOptions(selector, "");
  expect(screen.getByTestId("mapped-company-areas")).toHaveTextContent("null");
  expect(window.location.search).not.toContain("company=");
});

it("opens company performance without enabling boundary geometry", async () => {
  render(<App />);
  await userEvent.selectOptions(await screen.findByLabelText("Water company"), "EW");
  await userEvent.click(await screen.findByRole("button", { name: "View company performance" }));
  expect(screen.getByText("Company-wide performance")).toBeInTheDocument();
  expect(screen.getByText(dataset.attribution)).toBeInTheDocument();
  expect(mocks.waterSupplyCompanyAreas).not.toHaveBeenCalled();
  expect(mocks.waterSupplyCompanyGeometry).not.toHaveBeenCalled();
});

it("filters exact bathing classifications within the explicitly bounded loaded results", async () => {
  render(<App />);
  await userEvent.click(screen.getByRole("checkbox", { name: /Bathing waters/i }));
  expect(screen.getByText(/2 matches within 2 loaded nearby results/)).toBeInTheDocument();
  await userEvent.selectOptions(screen.getByRole("combobox", { name: "Annual publisher classification" }), "Excellent");
  expect(screen.getByText(/1 match within 2 loaded nearby results/)).toBeInTheDocument();
  expect(screen.getByTestId("mapped-bathing-waters")).toHaveTextContent("excellent");
  expect(screen.getByText(/Counts are not national totals/)).toBeInTheDocument();
});


it.each(["0", "9007199254740993", "-1", "abc"])("does not request invalid shared area %s", async (identity) => {
  window.history.replaceState(null, "", "/?selected=water-supply:" + identity);
  render(<App />);
  await screen.findByRole("button", { name: "Select station" });
  expect(mocks.areaGeometry).not.toHaveBeenCalled();
});
