import { expect, test, type Page, type Route } from "@playwright/test";

const snapshot = "11111111-1111-4111-8111-111111111111";
const generatedAt = "2026-09-29T09:19:00Z";
const dataset = {
  snapshot_id: snapshot,
  publisher: "Environment Agency",
  attribution: "Synthetic static acceptance data",
  licence: "Open Government Licence",
  licence_url: "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
  retrieval_completed_at: "2026-09-29T08:00:00Z",
};

async function json(route: Route, value: unknown): Promise<void> {
  await route.fulfill({ contentType: "application/json", body: JSON.stringify(value) });
}

async function staticPublication(page: Page): Promise<void> {
  await page.route("**/watergeo-data/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/source-status.json")) {
      await json(route, {
        checked_at: "2026-09-29T08:05:00Z",
        sources: [],
      });
    } else if (path.endsWith("/manifest.json")) {
      await json(route, {
        publication_id: "static-publication-a",
        generated_at: generatedAt,
        sources: { "flood-warnings": dataset },
      });
    } else if (path.endsWith("/search-index.json")) {
      await json(route, {
        items: [
          {
            kind: "water-supply",
            identity: "3",
            label: "Synthetic Water",
            context: "Synthetic area",
            publisher: "Ofwat",
            snapshot_id: snapshot,
            longitude: null,
            latitude: null,
          },
        ],
      });
    } else if (path.endsWith("/datasets/hydrology/items.json")) {
      await json(route, {
        dataset,
        items: [
          {
            station_id: "H1",
            source_uri: "https://example.test/h1",
            labels: ["Static hydrology"],
            location_status: "available",
            latitude: 54.5,
            longitude: -2.5,
            geometry: { type: "Point", coordinates: [-2.5, 54.5] },
          },
        ],
      });
    } else if (path.endsWith("/datasets/rainfall/items.json")) {
      await json(route, {
        dataset,
        items: [
          {
            station_id: "RF1",
            display_name: null,
            publisher_uri: "https://example.test/rf1",
            latitude: 54.5,
            longitude: -2.5,
            latest_value_mm: 1.2,
            latest_observed_at: "2026-09-29T07:45:00Z",
          },
        ],
      });
    } else if (path.endsWith("/datasets/bathing-waters/items.json")) {
      await json(route, {
        dataset,
        items: [
          {
            bathing_water_id: "BW1",
            publisher_uri: "https://example.test/bw1",
            name: "Static beach",
            latitude: 54.5,
            longitude: -2.5,
            classification: "Good",
            assessment_year: 2025,
            latest_sample_uri: "https://example.test/sample",
          },
        ],
      });
    } else if (path.endsWith("/datasets/flood-warnings/areas.geojson")) {
      await json(route, {
        type: "FeatureCollection",
        features: [
          {
            type: "Feature",
            id: "F1",
            geometry: {
              type: "Polygon",
              coordinates: [[[-2.6, 54.4], [-2.4, 54.4], [-2.5, 54.6], [-2.6, 54.4]]],
            },
            properties: {
              area_id: "F1",
              label: "Static flood area",
              county: "Testshire",
              description: "Publisher description",
              severity: "Flood Alert",
              severity_level: 3,
              message: "Publisher warning",
              time_message_changed: "2026-09-29T07:50:00Z",
            },
          },
        ],
      });
    } else if (path.endsWith("/datasets/water-supply/areas/3.geojson")) {
      await json(route, {
        type: "Feature",
        id: 3,
        properties: {
          source_id: 3,
          area_served: "Synthetic area",
          company: "Synthetic Water",
          company_acronym: "SYN",
          snapshot_id: snapshot,
          disclaimer: "Dated boundary.",
        },
        geometry: { type: "MultiPolygon", coordinates: [] },
        presentation: {
          policy_version: "test",
          review_reference: "test",
          method: "reprojection",
        },
      });
    } else if (path.endsWith("/datasets/company-performance/companies.json")) {
      await json(route, {
        dataset: { ...dataset, publisher: "Ofwat" },
        items: [
          {
            company_id: "SYN1",
            company_name: "Synthetic Water",
            boundary_company_acronym: "SYN",
            measures: [
              {
                reporting_period: "2024-25",
                measure_code: "M1",
                measure_name: "Published measure",
                value: 4,
                value_state: "reported",
                unit: "count",
                definition: "Publisher definition",
                publication: "Synthetic edition",
              },
            ],
          },
        ],
      });
    } else {
      await route.fulfill({ status: 404, contentType: "application/json", body: "{}" });
    }
  });
}

test("static production mode shows national layers, caveats and company facts", async ({ page }) => {
  await staticPublication(page);
  await page.goto("/");
  await expect(page.getByText("Static accepted snapshot")).toBeVisible();
  await expect(page.locator(`time[datetime="${generatedAt}"]`)).toBeVisible();
  await page.getByRole("button", { name: "Start exploring" }).click();
  await page.getByRole("checkbox", { name: /Hydrology stations/ }).check();
  await page.getByRole("checkbox", { name: /Rainfall gauges/ }).check();
  await page.getByRole("checkbox", { name: /Flood warnings/ }).check();
  await page.getByRole("checkbox", { name: /Bathing waters/ }).check();
  await page.getByText("Browse nearby results without the map").click();
  await page.getByRole("button", { name: /Station: Static hydrology/ }).click();
  await expect(page.getByRole("note")).toContainText(
    "Detailed observations are available in API mode",
  );
  await expect(page.getByRole("button", { name: /Rainfall: RF1/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /Bathing water: Static beach/ })).toBeVisible();
  await page.getByRole("button", { name: /Flood area: Static flood area/ }).click();
  await expect(page.getByText(/not an emergency warning service/i)).toBeVisible();

  const search = page.getByRole("searchbox", { name: "Search WaterGeo" });
  await search.fill("Synthetic Water");
  await page.getByRole("button", { name: /Synthetic Water.*Synthetic area/ }).click();
  await expect(page.getByRole("heading", { name: "Company performance" })).toBeVisible();
  await expect(page.getByText(/Published measure/)).toBeVisible();
});
