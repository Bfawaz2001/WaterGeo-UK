import { expect, test, type Page } from "@playwright/test";

const dataset = {
  snapshot_id: "11111111-1111-4111-8111-111111111111",
  publisher: "Environment Agency",
  attribution: "Synthetic acceptance data",
  licence: "Open Government Licence",
  licence_url: "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
  retrieval_completed_at: "2026-09-26T12:00:00Z",
};

async function syntheticApi(page: Page) {
  const state = { failures: false };
  await page.route("**/v1/**", async (route) => {
    const url = new URL(route.request().url());
    if (state.failures) {
      await route.fulfill({ status: 503, contentType: "application/json", body: '{"detail":"unavailable"}' });
      return;
    }
    if (url.pathname === "/v1/sources/status") {
      const sources = [
        { source: "hydrology", semantics: "dynamic_snapshot", source_version: null },
        { source: "water-quality", semantics: "dynamic_snapshot", source_version: null },
        { source: "thames-discharge-status", semantics: "dynamic_snapshot", source_version: null },
        { source: "rainfall", semantics: "dynamic_snapshot", source_version: null },
        { source: "flood-monitoring", semantics: "dynamic_snapshot", source_version: null },
        { source: "bathing-waters", semantics: "dynamic_snapshot", source_version: null },
        { source: "ofwat", semantics: "versioned_release", source_version: "2024-04 / v1_5" },
        { source: "catchments", semantics: "versioned_plan", source_version: "c3-plan" },
        { source: "stream-reservoir-levels", semantics: "versioned_release", source_version: "2025 edition" },
        { source: "company-performance", semantics: "versioned_release", source_version: "WCPR 2024-25 / PR24 V6.0" },
      ];
      await route.fulfill({ json: {
        checked_at: "2026-09-26T12:01:00Z",
        sources: sources.map((item) => {
          const dynamic = item.semantics === "dynamic_snapshot";
          return {
            ...item,
            availability: "available",
            snapshot_id: dataset.snapshot_id,
            snapshot_age_seconds: 60,
            retrieval_max_age_seconds: dynamic ? 3600 : null,
            retrieval_freshness: dynamic ? "current" : "not_applicable",
            observation_freshness: item.source === "hydrology" ? "unknown" : "not_applicable",
            retrieved_at: dataset.retrieval_completed_at,
            observation_newest_at: item.source === "hydrology" ? dataset.retrieval_completed_at : null,
            caveat: "Synthetic status",
          };
        }),
      } });
      return;
    }
    if (url.pathname === "/v1/hydrology/stations/near") {
      await route.fulfill({ json: {
        dataset,
        items: [{
          station_id: "station-1", source_uri: "https://example.test/station",
          labels: ["Synthetic station"], location_status: "available",
          latitude: 54.5, longitude: -2.5,
          geometry: { type: "Point", coordinates: [-2.5, 54.5] }, distance_m: 10,
        }],
        next_after_id: null,
      } });
      return;
    }
    if (url.pathname === "/v1/flood-monitoring/areas") {
      await route.fulfill({ json: { dataset, items: [
        "Severe Flood Warning", "Flood Warning", "Flood Alert", "Warning no longer in force",
      ].map((severity, index) => ({
        area_id: `F${index + 1}`, warning_id: `W${index + 1}`,
        label: `Warning area ${index + 1}`, severity_level: index + 1, severity,
        message: `Publisher message ${index + 1}`, description: "Synthetic area",
        time_message_changed: "2026-09-26T11:45:00Z",
        geometry: { type: "Polygon", coordinates: [[[-2.6, 54.4], [-2.4, 54.4], [-2.5, 54.6], [-2.6, 54.4]]] },
      })), next_after_id: null } });
      return;
    }
    if (url.pathname === "/v1/search") {
      const term = url.searchParams.get("q") ?? "";
      const found = term.includes("quality")
        ? { kind: "water-quality", identity: "quality-1", label: "Synthetic sampling point", context: "Water Quality sampling point", publisher: "Environment Agency", longitude: -2.4, latitude: 54.4 }
        : term.includes("reservoir")
          ? { kind: "reservoirs", identity: "reservoir-1", label: "Synthetic Reservoir", context: "Reservoir", publisher: "Severn Trent", longitude: -2.3, latitude: 54.3 }
          : term.includes("thames")
            ? { kind: "thames-discharge", identity: "thames-1", label: "Synthetic overflow", context: "Discharge monitor", publisher: "Thames Water", longitude: -1.8, latitude: 51.3 }
            : term.includes("body")
              ? { kind: "water-body", identity: "GB-WB-1", label: "Synthetic Water Body", context: "River Water Body", publisher: "Environment Agency", longitude: null, latitude: null }
              : { kind: "hydrology", identity: "station-1", label: "Synthetic station", context: "Hydrology station", publisher: "Environment Agency", longitude: -2.5, latitude: 54.5 };
      await route.fulfill({ json: {
        query: url.searchParams.get("q"), truncated: false,
        available_kinds: [found.kind], unavailable_kinds: [], items: [{ ...found, snapshot_id: dataset.snapshot_id }],
      } });
      return;
    }
    if (url.pathname === "/v1/hydrology/stations/station-1") {
      await route.fulfill({ json: {
        station_id: "station-1", source_uri: "https://example.test/station",
        labels: ["Synthetic station"], location_status: "available",
        latitude: 54.5, longitude: -2.5,
        geometry: { type: "Point", coordinates: [-2.5, 54.5] }, distance_m: null,
        dataset,
        measures: [{ measure_id: "level-1", parameter: "level", unit_name: "m", latest_observation: {
          value: 0.82, observed_at: "2026-09-26T11:45:00Z",
        } }],
      } });
      return;
    }
    if (url.pathname === "/v1/water-quality/sampling-points/quality-1") {
      await route.fulfill({ json: { sampling_point_id: "quality-1", source_uri: "https://example.test/quality", alt_label: "Synthetic sampling point", pref_label: "Synthetic sampling point", latitude: 54.4, longitude: -2.4, geometry: { type: "Point", coordinates: [-2.4, 54.4] }, location_status: "available", distance_m: null, dataset, publisher_metadata: { region: { notation: "NW", pref_label: "North West" }, sampling_point_type: { notation: "R", pref_label: "River monitoring point" } } } });
      return;
    }
    if (url.pathname === "/v1/severn-trent/reservoir-levels/reservoirs/reservoir-1") {
      await route.fulfill({ json: { reservoir_id: "reservoir-1", name: "Synthetic Reservoir", latitude: 54.3, longitude: -2.3, geometry: { type: "Point", coordinates: [-2.3, 54.3] }, capacity: 25000, capacity_unit: "ML", distance_m: null, latest_reading: { observed_at: "2025-05-01T00:00:00Z", current_level: 20000, current_level_unit: "ML", current_percentage: 80 }, dataset } });
      return;
    }
    if (url.pathname === "/v1/severn-trent/reservoir-levels/reservoirs/reservoir-1/readings") {
      await route.fulfill({ json: { dataset, next_after: null, items: [
        { observed_at: "2025-03-01T00:00:00Z", current_percentage: 72, current_level: 18000, current_level_unit: "ML" },
        { observed_at: "2025-04-01T00:00:00Z", current_percentage: 76, current_level: 19000, current_level_unit: "ML" },
        { observed_at: "2025-05-01T00:00:00Z", current_percentage: 80, current_level: 20000, current_level_unit: "ML" },
      ] } });
      return;
    }
    if (url.pathname === "/v1/thames-water/discharge-status/sites/thames-1") {
      await route.fulfill({ json: { site_id: "thames-1", location_name: "Synthetic overflow", permit_number: "PERMIT-1", grid_reference: "SU123456", easting: 412300, northing: 156700, geometry: { type: "Point", coordinates: [-1.8, 51.3] }, receiving_watercourse: "Synthetic Brook", alert_status: "Discharging", status_changed: "2026-09-26T11:30:00", alert_past_48_hours: true, most_recent_discharge_start: "2026-09-26T11:00:00", most_recent_discharge_stop: null, distance_m: null, dataset } });
      return;
    }
    if (url.pathname === "/v1/catchments/dataset") {
      await route.fulfill({ json: { ...dataset, source_url: "https://example.test/catchments", plan_version: "c3-plan", relationship_caveat: "Publisher hierarchy only" } });
      return;
    }
    if (url.pathname === "/v1/catchments/water-bodies") {
      await route.fulfill({ json: { dataset: { ...dataset, source_url: "https://example.test/catchments", plan_version: "c3-plan", relationship_caveat: "Publisher hierarchy only" }, next_after_id: null, items: [{ water_body_id: "GB-WB-1", operational_catchment_id: "OC-1", management_catchment_id: "MC-1", river_basin_district_id: "RBD-1", name: "Synthetic Water Body", water_body_type: "River", publisher_uri: "https://example.test/body" }] } });
      return;
    }
    if (url.pathname === "/v1/catchments/water-bodies/GB-WB-1") {
      await route.fulfill({ json: { water_body_id: "GB-WB-1", operational_catchment_id: "OC-1", management_catchment_id: "MC-1", river_basin_district_id: "RBD-1", name: "Synthetic Water Body", water_body_type: "River", publisher_uri: "https://example.test/body", snapshot_id: dataset.snapshot_id, geometry_url: "/geometry" } });
      return;
    }
    if (url.pathname === "/v1/catchments/water-bodies/GB-WB-1/geometry") {
      await route.fulfill({ contentType: "application/geo+json", json: { type: "FeatureCollection", water_body_id: "GB-WB-1", snapshot_id: dataset.snapshot_id, features: [{ type: "Feature", id: "GB-WB-1:0", geometry: { type: "LineString", coordinates: [[-2.5, 54.4], [-2.4, 54.5]] }, properties: { feature_index: 0 } }] } });
      return;
    }
    if (url.pathname === "/v1/water-supply/areas/at-point") {
      await route.fulfill({ json: { snapshot_id: dataset.snapshot_id, next_after_id: null, items: [{
        source_id: 3, area_served: "Synthetic area", company: "Synthetic Water",
        company_acronym: "SW", company_type: "Water only", area_type: "Appointment",
        warnings: null, transformed: false,
      }] } });
      return;
    }
    if (url.pathname === "/v1/water-supply/areas/3/geometry") {
      await route.fulfill({ contentType: "application/geo+json", json: {
        type: "Feature", id: 3,
        properties: {
          source_id: 3, area_served: "Synthetic area", company: "Synthetic Water",
          company_acronym: "SW", company_type: "Water only", area_type: "Appointment",
          warnings: null, transformed: false, snapshot_id: dataset.snapshot_id,
          geometry_url: "/geometry", licence_statement: "Synthetic licence",
          source_provenance: "Synthetic acceptance data", disclaimer: "Synthetic boundary.",
          premises_disclaimer: null, coastline_disclaimer: null,
        },
        geometry: { type: "MultiPolygon", coordinates: [] },
        presentation: { policy_version: "test", review_reference: "test", method: "reprojection" },
      } });
      return;
    }
    await route.fulfill({ status: 404, contentType: "application/json", body: '{"detail":"not found"}' });
  });
  return state;
}

test("explorer loads bounded data and shows selected provenance", async ({ page }) => {
  await syntheticApi(page);
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Explore public water data in context" })).toBeVisible();
  await page.getByRole("button", { name: "Start exploring" }).click();
  await expect(page.getByRole("heading", { name: "Layers", exact: true })).toBeVisible();
  await page.getByRole("checkbox", { name: /Water Quality sampling points/ }).check();
  await expect(page.getByRole("checkbox", { name: /Water Quality sampling points/ })).toBeChecked();
  await page.getByText("Browse nearby results without the map").click();
  const station = page.getByRole("button", { name: /Synthetic station/ });
  await expect(station).toBeVisible({ timeout: 10_000 });
  const canvas = page.getByTestId("map-canvas");
  const box = await canvas.boundingBox();
  expect(box).not.toBeNull();
  await canvas.click({ position: { x: box!.width / 2, y: box!.height / 2 } });
  await expect(page.getByRole("heading", { name: "Synthetic station" })).toBeVisible();
  await expect(page.getByText("Synthetic acceptance data")).toBeVisible();
  await expect(page.getByRole("complementary", { name: "Selected feature information" }).locator('time[datetime="2026-09-26T12:00:00Z"]')).toBeVisible();
});

test("unified search opens a snapshot-consistent feature with observation timing", async ({ page }) => {
  await syntheticApi(page);
  await page.goto("/");
  const search = page.getByRole("searchbox", { name: "Search WaterGeo" });
  await search.fill("synthetic");
  const result = page.getByRole("button", { name: /Synthetic station.*Hydrology station/ });
  await expect(result).toBeVisible();
  await result.click();
  await expect(page.getByRole("heading", { name: "Synthetic station" })).toBeVisible();
  await expect(page.getByText("0.82 m")).toBeVisible();
  await expect(page.getByRole("complementary", { name: "Selected feature information" }).getByText("Observed:")).toBeVisible();
  await expect(page.getByText("WaterGeo retrieved")).toBeVisible();
});

test("water-supply lookup and API failure states remain visible", async ({ page }) => {
  const api = await syntheticApi(page);
  await page.goto("/");
  await page.getByRole("button", { name: "Dismiss explorer introduction" }).click();
  await page.getByRole("checkbox", { name: /Water-supply lookup/i }).check();
  await page.locator(".maplibregl-canvas").click({ position: { x: 300, y: 250 } });
  const area = page.getByRole("button", { name: /Synthetic Water/ });
  await expect(area).toBeVisible();
  await area.click();
  await expect(page.getByRole("heading", { name: "Synthetic Water" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Selected supply area" })).toBeVisible();

  api.failures = true;
  await page.reload();
  await expect(page.getByText("Source status is currently unavailable.")).toBeVisible();
  await expect(page.getByText("This dataset is currently unavailable from the WaterGeo service.")).toBeVisible();
});

test("mobile viewport exposes the collapsed controls", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await syntheticApi(page);
  await page.goto("/");
  const toggle = page.getByRole("button", { name: "Layers & filters" });
  await expect(toggle).toHaveAttribute("aria-expanded", "false");
  await toggle.click();
  await expect(page.getByRole("complementary", { name: "Explorer controls" })).toBeVisible();
  await expect(page.getByRole("searchbox", { name: "Search WaterGeo" })).toBeVisible();
  await page.getByRole("searchbox", { name: "Search WaterGeo" }).fill("synthetic");
  await expect(page.getByRole("button", { name: /Synthetic station.*Hydrology station/ })).toBeVisible();
});

test("redesigned details preserve Water Quality, reservoir and Thames semantics", async ({ page }) => {
  await syntheticApi(page);
  await page.goto("/");
  await page.getByRole("button", { name: "Dismiss explorer introduction" }).click();
  const search = page.getByRole("searchbox", { name: "Search WaterGeo" });

  await search.fill("quality");
  await page.getByRole("button", { name: /Synthetic sampling point.*Water Quality/ }).click();
  await expect(page.getByRole("heading", { name: "Synthetic sampling point" })).toBeVisible();
  await expect(page.getByText("River monitoring point")).toBeVisible();
  await expect(page.getByText("North West")).toBeVisible();

  await search.fill("reservoir");
  await page.getByRole("button", { name: /Synthetic Reservoir.*Reservoir/ }).click();
  await expect(page.getByRole("heading", { name: "Synthetic Reservoir" })).toBeVisible();
  await expect(page.getByText("Dated 2025 edition")).toBeVisible();
  await expect(page.getByRole("img", { name: /Reservoir storage percentage/ })).toBeVisible();
  await expect(page.getByText("80.0%", { exact: true })).toBeVisible();

  await search.fill("thames");
  await page.getByRole("button", { name: /Synthetic overflow.*Discharge monitor/ }).click();
  await expect(page.getByRole("heading", { name: "Synthetic overflow" })).toBeVisible();
  await expect(page.getByRole("complementary", { name: "Selected feature information" }).getByText("Discharging", { exact: true })).toBeVisible();
  await expect(page.getByText(/does not measure discharge volume/)).toBeVisible();
});

test("Water Body browser explains loaded scope and selection hierarchy", async ({ page }) => {
  await syntheticApi(page);
  await page.goto("/");
  await page.getByRole("button", { name: "Dismiss explorer introduction" }).click();
  await page.getByRole("button", { name: /Rivers & Catchments/ }).click();
  await expect(page.getByText(/filter applies only to records loaded below/)).toBeVisible();
  await page.getByRole("button", { name: /Synthetic Water Body/ }).click();
  await expect(page.getByRole("heading", { name: "Synthetic Water Body" })).toBeVisible();
  await expect(page.getByText("Catchment Data Explorer classification")).toBeVisible();
});

test("searched Water Body navigation and shared filter state remain visible", async ({ page, context }) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await syntheticApi(page);
  await page.goto("/");
  await page.getByRole("button", { name: "Dismiss explorer introduction" }).click();
  const search = page.getByRole("searchbox", { name: "Search WaterGeo" });
  await search.fill("body");
  await page.getByRole("button", { name: /Synthetic Water Body.*River Water Body/ }).click();
  await expect(page.getByRole("heading", { name: "Synthetic Water Body" })).toBeVisible();

  await page.getByRole("checkbox", { name: /Flood warnings/ }).check();
  await page.getByLabel("Publisher severity").selectOption("3");
  await page.getByRole("checkbox", { name: /Bathing waters/ }).check();
  await page.getByLabel("Annual publisher classification").selectOption("Good");
  await page.getByRole("button", { name: "Copy a shareable map URL" }).click();
  await expect(page.getByText(/Link copied/)).toBeVisible();
  await expect(page).toHaveURL(/flood=3/);
  await expect(page).toHaveURL(/bathing=Good/);
  await expect(page).toHaveURL(/selected=water-body/);
});

test("source health expands from a compact product summary", async ({ page }) => {
  await page.clock.setFixedTime(new Date("2026-09-26T12:01:00Z"));
  await syntheticApi(page);
  await page.goto("/");
  await expect(page.getByText("10/10 available")).toBeVisible();
  await page.getByText("Source status", { exact: true }).click();
  await expect(page.getByLabel("Hydrology: Current by policy")).toBeVisible();
  await expect(page.getByLabel("Bathing waters: Current by policy")).toBeVisible();
  await expect(
    page.getByLabel("Company performance: Edition WCPR 2024-25 / PR24 V6.0"),
  ).toBeVisible();
});


test("regional navigation and exact flood-state filters preserve selected provenance", async ({ page }) => {
  await syntheticApi(page);
  await page.goto("/");
  await page.getByRole("button", { name: "Start exploring" }).click();
  await page.getByRole("button", { name: "Midlands", exact: true }).click();
  await expect(page).not.toHaveURL(/lon=-2.50000/);
  await page.getByRole("checkbox", { name: /Flood warnings/ }).check();
  await page.getByText("Browse nearby results without the map").click();
  const warnings = page.getByRole("button", { name: /Flood area: Warning area/ });
  await expect(warnings).toHaveCount(4);
  const severity = page.getByLabel("Publisher severity");
  for (const level of ["1", "2", "3", "4"]) {
    await severity.selectOption(level);
    await expect(warnings).toHaveCount(1);
    await expect(warnings).toHaveText(`Flood area: Warning area ${level} · ${["Severe Flood Warning", "Flood Warning", "Flood Alert", "Warning no longer in force"][Number(level) - 1]}`);
  }
  await warnings.click();
  await expect(page.getByRole("heading", { name: "Warning area 4" })).toBeVisible();
  await expect(page.getByText("Warning no longer in force", { exact: true }).last()).toBeVisible();
  await severity.selectOption("1");
  await expect(page.getByRole("heading", { name: "Warning area 4" })).toBeVisible();
  await expect(page.getByText("Synthetic acceptance data")).toBeVisible();
  await severity.selectOption("");
  await expect(warnings).toHaveCount(4);
});
