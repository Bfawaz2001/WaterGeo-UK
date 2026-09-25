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

it("renders available and unavailable source states outside the map", () => {
  render(<SourceStatusPanel status={sourceStatuses} error={null} loading={false} />);
  expect(screen.getByText("Hydrology")).toBeInTheDocument();
  expect(screen.getByText("Water Quality")).toBeInTheDocument();
  expect(screen.getByText("Unavailable")).toBeInTheDocument();
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
