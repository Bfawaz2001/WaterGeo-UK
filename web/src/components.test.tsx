import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { DetailPanel } from "./DetailPanel";
import { LayerControls } from "./LayerControls";
import { SourceStatusPanel } from "./SourceStatusPanel";
import { dataset, sourceStatuses } from "./test/fixtures";

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
  expect(screen.getByText(/12 nearest results shown/)).toBeInTheDocument();
  expect(screen.getByText(/Spatial overlap does not establish/)).toBeInTheDocument();
});

it("distinguishes available and not-loaded source states outside the map", () => {
  render(<SourceStatusPanel status={sourceStatuses} error={null} loading={false} />);
  expect(screen.getByText("Hydrology")).toBeInTheDocument();
  expect(screen.getByText("Water Quality")).toBeInTheDocument();
  expect(screen.getByText("Available")).toBeInTheDocument();
  expect(screen.getByText("Not loaded")).toBeInTheDocument();
  expect(screen.getByText(/No compatible local snapshot/)).toBeInTheDocument();
});

it("renders a source-status request failure as an error", () => {
  render(<SourceStatusPanel status={null} error="Source status is currently unavailable." loading={false} />);
  expect(screen.getByRole("alert")).toHaveTextContent("Source status is currently unavailable.");
  expect(screen.queryByText("Not loaded")).not.toBeInTheDocument();
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
