import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import { OverviewControl } from "./OverviewControl";
import { parseOverview } from "./overview";

const manifest = { export_version: "watergeo-export-v1", entity: "water-supply", dataset: { snapshot_id: "11111111-1111-4111-8111-111111111111", attribution: "Reviewed source attribution" }, tiles: { layer: "water_supply" }, files: { "water-supply.pmtiles": {} } };
afterEach(() => { vi.unstubAllEnvs(); vi.unstubAllGlobals(); });

it("loads overview provenance only when enabled and removes it when disabled", async () => {
  vi.stubEnv("VITE_WATER_SUPPLY_OVERVIEW", "/exports/snapshot/manifest.json");
  const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify(manifest), { headers: { "content-type": "application/json" } }));
  vi.stubGlobal("fetch", fetcher);
  const onChange = vi.fn();
  render(<OverviewControl onChange={onChange} />);
  expect(fetcher).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole("checkbox"));
  expect(await screen.findByText(/Reviewed source attribution/)).toBeInTheDocument();
  expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ url: "/exports/snapshot/water-supply.pmtiles", snapshot: manifest.dataset.snapshot_id }));
  await userEvent.click(screen.getByRole("checkbox"));
  expect(onChange).toHaveBeenLastCalledWith(null);
});

it("rejects foreign manifests and external or unsafe paths", () => {
  expect(() => parseOverview({ ...manifest, entity: "other" }, "/manifest.json")).toThrow();
  for (const path of ["https://other.test/manifest.json", "//other.test/manifest.json", "/x/../manifest.json", "/x?bad/manifest.json"]) expect(() => parseOverview(manifest, path)).toThrow();
});
