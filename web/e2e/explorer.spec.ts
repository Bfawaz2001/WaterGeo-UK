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
      await route.fulfill({ json: { checked_at: "2026-09-26T12:01:00Z", sources: [] } });
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
    if (url.pathname === "/v1/search") {
      await route.fulfill({ json: {
        query: url.searchParams.get("q"), truncated: false,
        available_kinds: ["hydrology"], unavailable_kinds: [],
        items: [{
          kind: "hydrology", identity: "station-1", label: "Synthetic station",
          context: "Hydrology station", publisher: "Environment Agency",
          snapshot_id: dataset.snapshot_id, longitude: -2.5, latitude: 54.5,
        }],
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
  await expect(page.getByRole("heading", { name: "Layers", exact: true })).toBeVisible();
  await page.getByText("Browse nearby results without the map").click();
  const station = page.getByRole("button", { name: /Synthetic station/ });
  await expect(station).toBeVisible({ timeout: 10_000 });
  await station.click();
  await expect(page.getByRole("heading", { name: "Synthetic station" })).toBeVisible();
  await expect(page.getByText("Synthetic acceptance data")).toBeVisible();
  await expect(page.locator('time[datetime="2026-09-26T12:00:00Z"]')).toBeVisible();
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
  await expect(page.getByText(/Publisher observed/)).toBeVisible();
  await expect(page.getByText("WaterGeo retrieved")).toBeVisible();
});

test("water-supply lookup and API failure states remain visible", async ({ page }) => {
  const api = await syntheticApi(page);
  await page.goto("/");
  await page.getByRole("checkbox", { name: /Water-supply lookup/i }).check();
  await page.locator(".maplibregl-canvas").click({ position: { x: 300, y: 250 } });
  const area = page.getByRole("button", { name: /Synthetic Water/ });
  await expect(area).toBeVisible();
  await area.click();
  await expect(page.getByRole("heading", { name: "Synthetic Water" })).toBeVisible();

  api.failures = true;
  await page.reload();
  await expect(page.getByText("Source status is currently unavailable.")).toBeVisible();
  await expect(page.getByText("Dataset is currently unavailable.")).toBeVisible();
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
