import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";

import { DetailPanel } from "./DetailPanel";
import { LayerControls } from "./LayerControls";
import { SourceStatusPanel } from "./SourceStatusPanel";
import { dataset, sourceStatuses } from "./test/fixtures";
import { Onboarding } from "./Onboarding";
import type { SourceStatus } from "./types";

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

it("renders accessible layer toggles and reports bounded results", async () => {
  const toggle = vi.fn();
  render(
    <LayerControls
      active={new Set(["hydrology"])}
      counts={{ hydrology: 12 }}
      loading={new Set()}
      errors={{}}
      onToggle={toggle}
    />,
  );
  await userEvent.click(screen.getByRole("checkbox", { name: /Hydrology stations/i }));
  expect(toggle).toHaveBeenCalledWith("hydrology");
  expect(screen.getByText(/12 loaded nearby results/)).toBeInTheDocument();
  expect(screen.getByText("Latest accepted EA data")).toBeInTheDocument();
  expect(screen.getByText(/Spatial overlap does not establish/)).toBeInTheDocument();
});

it("distinguishes available and not-loaded source states outside the map", () => {
  vi.useFakeTimers();
  vi.setSystemTime("2026-09-24T12:01:00Z");
  render(<SourceStatusPanel status={sourceStatuses} error={null} loading={false} />);
  expect(screen.getByText("Hydrology")).toBeInTheDocument();
  expect(screen.getByText("Water Quality metadata")).toBeInTheDocument();
  expect(screen.getByText("Current by policy")).toBeInTheDocument();
  expect(screen.getByText("Not loaded")).toBeInTheDocument();
  expect(screen.getByText(/No compatible local snapshot/)).toBeInTheDocument();
});

it("renders a source-status request failure as an error", () => {
  render(<SourceStatusPanel status={null} error="Source status is currently unavailable." loading={false} />);
  expect(screen.getByRole("alert")).toHaveTextContent("Source status is currently unavailable.");
  expect(screen.queryByText("Not loaded")).not.toBeInTheDocument();
});

it("summarises healthy source status and keeps precise unavailable detail", () => {
  const available = { ...sourceStatuses, sources: sourceStatuses.sources.map((source) => ({ ...source, availability: "available" as const })) };
  render(<SourceStatusPanel status={available} error={null} loading={false} />);
  expect(screen.getByText(`${available.sources.length}/${available.sources.length} available`)).toBeInTheDocument();
  expect(screen.getByText("Hydrology")).toBeInTheDocument();
});

it("summarises the ten primary products with truthful retrieval and edition semantics", () => {
  vi.useFakeTimers();
  vi.setSystemTime("2026-09-24T12:01:00Z");
  const primary = [
    ["hydrology", "dynamic_snapshot"],
    ["water-quality", "dynamic_snapshot"],
    ["thames-discharge-status", "dynamic_snapshot"],
    ["rainfall", "dynamic_snapshot"],
    ["flood-monitoring", "dynamic_snapshot"],
    ["bathing-waters", "dynamic_snapshot"],
    ["ofwat", "versioned_release"],
    ["catchments", "versioned_plan"],
    ["stream-reservoir-levels", "versioned_release"],
    ["company-performance", "versioned_release"],
  ] as const;
  const sources: SourceStatus[] = primary.map(([source, semantics]) => ({
    source,
    semantics,
    availability: "available",
    snapshot_id: dataset.snapshot_id,
    source_version: semantics === "dynamic_snapshot" ? null : "reviewed-2026",
    snapshot_age_seconds: semantics === "dynamic_snapshot" ? 8 * 60 : 86400,
    retrieval_freshness: semantics === "dynamic_snapshot" ? "unknown" : "not_applicable",
    observation_freshness: "not_applicable",
    retrieved_at: dataset.retrieval_completed_at,
    observation_newest_at: null,
    caveat: "Synthetic status.",
  }));
  sources.push(
    { ...sources[0]!, source: "hydrology-history", semantics: "bounded_history" },
    { ...sources[1]!, source: "water-quality-observations", semantics: "bounded_history" },
  );

  render(
    <SourceStatusPanel
      status={{ checked_at: "2026-09-24T12:01:00Z", sources }}
      error={null}
      loading={false}
    />,
  );

  expect(screen.getByText("10/10 available")).toBeInTheDocument();
  expect(screen.getByText("Company performance")).toBeInTheDocument();
  expect(screen.getAllByText("Retrieved 8 min ago")).toHaveLength(6);
  expect(screen.getAllByText("Edition reviewed-2026")).toHaveLength(4);
  expect(screen.getByText(/no freshness policy is configured/)).toBeInTheDocument();
  expect(screen.getByText(/not publisher observation times/)).toBeInTheDocument();
  expect(screen.queryByText("hydrology-history")).not.toBeInTheDocument();
  expect(screen.queryByText("water-quality-observations")).not.toBeInTheDocument();
});

it("recomputes configured freshness as static wall-clock time advances", () => {
  vi.useFakeTimers();
  vi.setSystemTime("2026-09-24T12:01:00Z");
  const hydrology: SourceStatus = {
    ...sourceStatuses.sources[0]!,
    snapshot_age_seconds: 60,
    retrieval_max_age_seconds: 120,
  };
  const view = render(
    <SourceStatusPanel
      status={{ checked_at: "2026-09-24T12:01:00Z", sources: [hydrology] }}
      error={null}
      loading={false}
    />,
  );
  expect(screen.getByText("Current by policy")).toBeInTheDocument();

  vi.setSystemTime("2026-09-24T12:02:01Z");
  view.rerender(
    <SourceStatusPanel
      status={{ checked_at: "2026-09-24T12:01:00Z", sources: [hydrology] }}
      error={null}
      loading={false}
    />,
  );
  expect(screen.getByText("Stale by policy")).toBeInTheDocument();
});

it.each([
  ["future", "2026-09-24T12:02:00Z"],
  ["invalid", "not-a-timestamp"],
])("shows neutral freshness for a configured policy with %s retrieval time", (_case, retrievedAt) => {
  vi.useFakeTimers();
  vi.setSystemTime("2026-09-24T12:01:00Z");
  const hydrology: SourceStatus = {
    ...sourceStatuses.sources[0]!,
    snapshot_age_seconds: 60,
    retrieval_max_age_seconds: 120,
    retrieved_at: retrievedAt,
  };
  render(
    <SourceStatusPanel
      status={{ checked_at: "2026-09-24T12:01:00Z", sources: [hydrology] }}
      error={null}
      loading={false}
    />,
  );
  expect(screen.getByText("Freshness unavailable")).toBeInTheDocument();
  expect(screen.queryByText(/by policy/)).not.toBeInTheDocument();
});

it("shows dismissible first-use guidance and remembers dismissal", async () => {
  window.localStorage.clear();
  const first = render(<Onboarding />);
  expect(screen.getByRole("heading", { name: "Explore public water data in context" })).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Start exploring" }));
  expect(screen.queryByRole("heading", { name: "Explore public water data in context" })).not.toBeInTheDocument();
  first.unmount();
  render(<Onboarding />);
  expect(screen.queryByRole("heading", { name: "Explore public water data in context" })).not.toBeInTheDocument();
});

it("shows onboarding when local storage cannot be read", () => {
  vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new DOMException("blocked"); });
  render(<Onboarding />);
  expect(screen.getByRole("heading", { name: "Explore public water data in context" })).toBeInTheDocument();
});

it("dismisses onboarding for the page when local storage cannot be written", async () => {
  window.localStorage.clear();
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new DOMException("blocked"); });
  render(<Onboarding />);
  await userEvent.click(screen.getByRole("button", { name: "Start exploring" }));
  expect(screen.queryByRole("heading", { name: "Explore public water data in context" })).not.toBeInTheDocument();
});

it("shows source provenance and reservoir interpretation caveats", () => {
  render(
    <DetailPanel
      onClose={vi.fn()}
      selected={{
        kind: "reservoirs",
        dataset,
        item: {
          reservoir_id: "10014",
          name: "Draycote",
          latitude: 52.3,
          longitude: -1.3,
          geometry: { type: "Point", coordinates: [-1.3, 52.3] },
          capacity: 22000,
          capacity_unit: "ML",
          distance_m: 100,
          latest_reading: {
            observed_at: "2025-05-01T00:00:00Z",
            current_level: 100,
            current_level_unit: "ML",
            current_percentage: 80,
          },
        },
      }}
    />,
  );
  expect(screen.getByRole("heading", { name: "Draycote" })).toBeInTheDocument();
  expect(screen.getByText(/not a restriction, safety, or supply-risk/)).toBeInTheDocument();
  expect(screen.getByText(dataset.attribution)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: dataset.licence })).toHaveAttribute("href", dataset.licence_url);
});

it("shows Thames monitor semantics and an offset-free status timeline", () => {
  render(<DetailPanel onClose={vi.fn()} selected={{
    kind: "thames-discharge",
    dataset: { ...dataset, publisher: "Thames Water Utilities Limited" },
    item: {
      site_id: "TWL00001", location_name: "Test overflow", permit_number: "CTCR.0001",
      grid_reference: "SU12345678", easting: 412340, northing: 156780,
      geometry: { type: "Point", coordinates: [-1.82, 51.31] },
      receiving_watercourse: "Test Brook", alert_status: "Discharging",
      status_changed: "2026-09-20T12:30:00", alert_past_48_hours: true,
      most_recent_discharge_start: "2026-09-20T12:00:00",
      most_recent_discharge_stop: null, distance_m: 10,
    },
  }} />);
  expect(screen.getByRole("heading", { name: "Test overflow" })).toBeInTheDocument();
  expect(screen.getAllByText(/timezone not supplied/)).toHaveLength(2);
  expect(screen.getByText(/does not measure discharge volume/)).toBeInTheDocument();
});

it("distinguishes a missing rainfall observation from numeric zero and preserves identity", () => {
  const rainfall = {
    station_id: "585122_", publisher_uri: "https://example.test/rainfall/585122_",
    display_name: null, latitude: 54.42, longitude: -2.98, grid_reference: "SD123456",
    latest_observed_at: null, latest_value_mm: null, latest_value: null,
    latest_unit: null, latest_period_seconds: null, distance_m: 10,
  };
  const view = render(<DetailPanel onClose={vi.fn()} selected={{ kind: "rainfall", dataset, item: rainfall }} />);
  expect(screen.getByRole("heading", { name: "Rainfall gauge 585122_" })).toBeInTheDocument();
  expect(screen.getByText("No accepted latest rainfall reading available")).toBeInTheDocument();
  expect(screen.getByText("Missing is distinct from zero rainfall")).toBeInTheDocument();
  expect(screen.getByText("585122_")).toBeInTheDocument();

  view.rerender(<DetailPanel onClose={vi.fn()} selected={{ kind: "rainfall", dataset, item: {
    ...rainfall, latest_observed_at: "2026-09-24T11:45:00Z", latest_value_mm: 0,
    latest_value: 0, latest_unit: "mm", latest_period_seconds: 900,
  } }} />);
  expect(screen.getByText("0 mm")).toBeInTheDocument();
  expect(screen.getAllByText(/15 minutes/)).toHaveLength(2);
});

it("describes bathing classifications and Water Quality locations without safety claims", () => {
  const view = render(<DetailPanel onClose={vi.fn()} selected={{ kind: "bathing-waters", dataset, item: {
    bathing_water_id: "uk123", publisher_uri: "https://example.test/bathing/uk123",
    name: "Clevedon Beach", latitude: 51.44, longitude: -2.86, classification: "Good",
    assessment_year: 2025, latest_sample_uri: null, latest_risk_prediction: null, distance_m: 20,
  } }} />);
  expect(screen.getByText("Good")).toBeInTheDocument();
  expect(screen.getByText(/Annual publisher classification · 2025/)).toBeInTheDocument();
  expect(screen.getByText(/not a daily swimming-safety rating/)).toBeInTheDocument();

  view.rerender(<DetailPanel onClose={vi.fn()} selected={{ kind: "water-quality", dataset, item: {
    sampling_point_id: "GB/POINT 1", source_uri: "https://example.test/quality/GB%2FPOINT%201",
    alt_label: "Point one", pref_label: null, latitude: 51, longitude: -2,
    geometry: { type: "Point", coordinates: [-2, 51] }, location_status: "available", distance_m: 5,
  } }} />);
  expect(screen.getByText("Sampling location")).toBeInTheDocument();
  expect(screen.getByText(/Observation series are separate bounded retrievals/)).toBeInTheDocument();
  expect(screen.getByText("GB/POINT 1")).toBeInTheDocument();
});
