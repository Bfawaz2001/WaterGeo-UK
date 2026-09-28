import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { api } from "./api";
import { FeatureDrilldown } from "./FeatureDrilldown";
import { dataset } from "./test/fixtures";
import type { SelectedFeature } from "./types";

const selected: SelectedFeature = { kind: "hydrology", dataset, item: { station_id: "s1", source_uri: "https://example.test", labels: ["Station"], geometry: null, location_status: "unavailable", latitude: null, longitude: null, distance_m: null } };

it("shows loading then source observations, with a station-scoped measurement filter", async () => {
  vi.spyOn(api, "hydrologyDetail").mockResolvedValue({ ...selected.item, dataset, measures: [
    { measure_id: "m1", parameter: "level", unit_name: "m", latest_observation: { value: 1.2, observed_at: "2026-01-01T00:00:00Z" } },
    { measure_id: "m2", parameter: "flow", unit_name: "m3/s", latest_observation: null },
  ] });
  render(<FeatureDrilldown selected={selected} />);
  expect(screen.getByRole("status")).toHaveTextContent("Loading");
  expect(await screen.findByText(/1.2 m/)).toBeInTheDocument();
  expect(screen.getAllByTitle("Publisher measure identifier")[0]).toHaveTextContent("m1");
  expect(screen.getByText(/Publisher observed/).querySelector("time")).toHaveAttribute("datetime", "2026-01-01T00:00:00Z");
  await userEvent.selectOptions(screen.getByRole("combobox"), "level");
  expect(screen.queryByText("No accepted observation")).not.toBeInTheDocument();
});

it("rejects mismatched detail snapshots and aborts pending work on unmount", async () => {
  const detail = vi.spyOn(api, "hydrologyDetail").mockResolvedValue({ ...selected.item, dataset: { ...dataset, snapshot_id: "wrong" }, measures: [] });
  const { unmount } = render(<FeatureDrilldown selected={selected} />);
  expect(await screen.findByRole("alert")).toHaveTextContent("snapshot changed");
  const signal = detail.mock.calls[0]?.[1];
  unmount();
  expect(signal?.aborted).toBe(true);
});

it("renders an accessible reservoir trend from consistent percentage readings", async () => {
  vi.spyOn(api, "reservoirReadings").mockResolvedValue({
    dataset,
    next_after: null,
    items: [
      { observed_at: "2025-01-01T00:00:00Z", current_percentage: 70, current_level: 70, current_level_unit: "ML" },
      { observed_at: "2025-02-01T00:00:00Z", current_percentage: 82, current_level: 82, current_level_unit: "ML" },
    ],
  });
  render(<FeatureDrilldown selected={{
    kind: "reservoirs", dataset,
    item: { reservoir_id: "r1", name: "Reservoir", latitude: 52, longitude: -1,
      geometry: { type: "Point", coordinates: [-1, 52] }, capacity: 100,
      capacity_unit: "ML", distance_m: null, latest_reading: null },
  }} />);
  expect(await screen.findByRole("img", { name: /Reservoir storage percentage/ })).toHaveAccessibleName(/range 70.0 to 82.0 %/);
  expect(screen.getByText(/2 dated values/)).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /70 %,/ })).not.toBeInTheDocument();
  const firstPoint = screen.getByRole("graphics-symbol", { name: /70 %,/ });
  fireEvent.focus(firstPoint);
  expect(screen.getByText(/70.0 %/)).toBeInTheDocument();
  await userEvent.hover(screen.getByRole("graphics-symbol", { name: /82 %,/ }));
  expect(screen.getByText(/82.0 %/)).toBeInTheDocument();
});

it("renders publisher classifications as labels with secondary notation", async () => {
  const waterQuality: SelectedFeature = {
    kind: "water-quality",
    dataset,
    item: {
      sampling_point_id: "AN-1", source_uri: "https://example.test/AN-1",
      alt_label: "A long sampling point name", pref_label: null,
      latitude: 52, longitude: -1, geometry: { type: "Point", coordinates: [-1, 52] },
      location_status: "available", distance_m: null,
    },
  };
  vi.spyOn(api, "samplingPointDetail").mockResolvedValue({
    ...waterQuality.item,
    dataset,
    publisher_metadata: {
      region: { notation: "MD", pref_label: "Midlands" },
      sampling_point_type: { notation: "TZ", pref_label: "TRADE DISCHARGES - UNSPECIFIED" },
      active: true,
      aliases: ["Upper Trent", "Tame"],
    },
  });
  render(<FeatureDrilldown selected={waterQuality} />);
  expect(await screen.findByText("Midlands")).toBeInTheDocument();
  expect(screen.getByText("MD")).toBeInTheDocument();
  expect(screen.getByText("TRADE DISCHARGES - UNSPECIFIED")).toBeInTheDocument();
  expect(screen.getByText("TZ")).toBeInTheDocument();
  expect(screen.getByText("Yes")).toBeInTheDocument();
  expect(screen.getByText("Upper Trent")).toBeInTheDocument();
  expect(screen.queryByText(/\{"notation"/)).not.toBeInTheDocument();
});
