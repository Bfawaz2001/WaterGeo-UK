import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { api } from "./api";
import { catchmentDataset } from "./test/fixtures";
import { WaterBodyBrowser } from "./WaterBodyBrowser";

it("loads a snapshot-pinned Water Body and preserves publisher geometry features", async () => {
  vi.spyOn(api, "waterBodies").mockResolvedValue({
    dataset: catchmentDataset,
    next_after_id: null,
    items: [
      {
        water_body_id: "GB/one",
        operational_catchment_id: "OC1",
        management_catchment_id: "MC1",
        river_basin_district_id: "RBD1",
        name: "Example Beck",
        water_body_type: "River",
        publisher_uri: "https://example.test/water-body",
      },
    ],
  });
  vi.spyOn(api, "waterBody").mockResolvedValue({
    water_body_id: "GB/one",
    operational_catchment_id: "OC1",
    management_catchment_id: "MC1",
    river_basin_district_id: "RBD1",
    name: "Example Beck",
    water_body_type: "River",
    publisher_uri: "https://example.test/water-body",
    snapshot_id: catchmentDataset.snapshot_id,
    geometry_url: "/geometry",
  });
  vi.spyOn(api, "waterBodyGeometry").mockResolvedValue({
    type: "FeatureCollection",
    water_body_id: "GB/one",
    snapshot_id: catchmentDataset.snapshot_id,
    features: [
      {
        type: "Feature",
        id: "GB/one:0",
        geometry: { type: "LineString", coordinates: [[-1, 52], [-1.1, 52.1]] },
        properties: { feature_index: 0 },
      },
      {
        type: "Feature",
        id: "GB/one:1",
        geometry: { type: "LineString", coordinates: [[-1.2, 52.2], [-1.3, 52.3]] },
        properties: { feature_index: 1 },
      },
    ],
  });
  const selected = vi.fn();
  function Harness() {
    const [open, setOpen] = useState(false);
    return (
      <WaterBodyBrowser open={open} onToggle={() => setOpen((value) => !value)} onSelect={selected} />
    );
  }
  render(<Harness />);
  await userEvent.click(screen.getByRole("button", { name: /Water Bodies/ }));
  await userEvent.click(await screen.findByRole("button", { name: /Example Beck/ }));
  await waitFor(() => expect(selected).toHaveBeenCalledOnce());
  expect(selected.mock.calls[0]?.[0].geometry.features).toHaveLength(2);
  expect(api.waterBodyGeometry).toHaveBeenCalledWith("GB/one");
});
import { useState } from "react";
