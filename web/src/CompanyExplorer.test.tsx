import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";

import { api } from "./api";
import { CompanyExplorer } from "./CompanyExplorer";
import type { AreaFeature, AreaSummary, WaterCompany } from "./types";

const snapshot = "11111111-1111-4111-8111-111111111111";
const company: WaterCompany = {
  company_acronym: "ANH",
  display_name: "Anglian Water",
  publisher_labels: ["Anglian Water"],
  area_count: 2,
};
const areas: AreaSummary[] = [1, 2].map((source_id) => ({
  source_id,
  area_served: `Area ${source_id}`,
  company: "Anglian Water",
  company_acronym: "ANH",
  company_type: "Water and sewerage",
  area_type: "Appointment",
  warnings: null,
  transformed: false,
}));
const features = areas.map((area) => ({
  type: "Feature",
  id: area.source_id,
  properties: {
    ...area,
    snapshot_id: snapshot,
    geometry_url: `/geometry/${area.source_id}`,
    licence_statement: null,
    source_provenance: null,
    disclaimer: null,
    premises_disclaimer: null,
    coastline_disclaimer: null,
  },
  geometry: { type: "MultiPolygon", coordinates: [] },
  presentation: {
    policy_version: "v3",
    review_reference: "ADR 0006",
    method: "reprojection",
  },
})) as AreaFeature[];

afterEach(() => vi.restoreAllMocks());

it("pins every page, verifies completeness, and supports company and area navigation", async () => {
  vi.spyOn(api, "waterSupplyCompanies").mockResolvedValue({ snapshot_id: snapshot, items: [company] });
  vi.spyOn(api, "waterSupplyCompanyAreas")
    .mockResolvedValueOnce({ snapshot_id: snapshot, company, items: [areas[0]!], next_after_id: 1 })
    .mockResolvedValueOnce({ snapshot_id: snapshot, company, items: [areas[1]!], next_after_id: null });
  vi.spyOn(api, "waterSupplyCompanyGeometry").mockResolvedValue({
    type: "FeatureCollection", snapshot_id: snapshot, company, features,
  });
  const performanceDataset = { snapshot_id: "performance", publisher: "Ofwat", attribution: "Ofwat", licence: "OGL", retrieval_completed_at: "2026-01-01T00:00:00Z" };
  vi.spyOn(api, "companyPerformanceCompanies").mockResolvedValue({
    dataset: performanceDataset,
    items: [{ company_id: "anglian", company_name: "Anglian Water", boundary_company_acronym: "ANH" }], next_after_id: null,
  });
  const performance = { dataset: performanceDataset, item: { company_id: "anglian", company_name: "Anglian Water", boundary_company_acronym: "ANH", measures: [] } };
  vi.spyOn(api, "companyPerformance").mockResolvedValue(performance);
  const onShowCompany = vi.fn();
  const onSelectArea = vi.fn();
  const onSelectPerformance = vi.fn();
  render(<CompanyExplorer onShowCompany={onShowCompany} onSelectArea={onSelectArea} onSelectPerformance={onSelectPerformance} />);

  await userEvent.selectOptions(await screen.findByLabelText("Water company"), "ANH");
  expect(await screen.findByText((_, element) => element?.textContent === "2 verified areas")).toBeInTheDocument();
  expect(api.waterSupplyCompanyAreas).toHaveBeenNthCalledWith(
    1, "ANH", snapshot, undefined, expect.any(AbortSignal),
  );
  expect(api.waterSupplyCompanyAreas).toHaveBeenNthCalledWith(
    2, "ANH", snapshot, 1, expect.any(AbortSignal),
  );
  expect(onShowCompany).toHaveBeenCalledWith(expect.objectContaining({ snapshot_id: snapshot }));

  await userEvent.type(screen.getByLabelText("Find an area in this company"), "Area 2");
  expect(screen.getByText("1 of 2 verified areas shown.")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: /Area 2/ }));
  expect(onSelectArea).toHaveBeenCalledWith(features[1]);
  await userEvent.click(screen.getByRole("button", { name: "Show all company areas" }));
  expect(onShowCompany).toHaveBeenCalledTimes(2);
  await userEvent.click(screen.getByRole("button", { name: "View company performance" }));
  expect(api.companyPerformance).toHaveBeenCalledWith("anglian", "performance", expect.any(AbortSignal));
  expect(onSelectPerformance).toHaveBeenCalledWith(performance);
});

it("fails closed when geometry does not match the verified inventory", async () => {
  vi.spyOn(api, "waterSupplyCompanies").mockResolvedValue({ snapshot_id: snapshot, items: [company] });
  vi.spyOn(api, "waterSupplyCompanyAreas").mockResolvedValue({
    snapshot_id: snapshot, company, items: areas, next_after_id: null,
  });
  vi.spyOn(api, "waterSupplyCompanyGeometry").mockResolvedValue({
    type: "FeatureCollection", snapshot_id: snapshot, company, features: [features[0]!],
  });
  const onShowCompany = vi.fn();
  render(<CompanyExplorer onShowCompany={onShowCompany} onSelectArea={vi.fn()} onSelectPerformance={vi.fn()} />);
  await userEvent.selectOptions(await screen.findByLabelText("Water company"), "ANH");
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "complete company-area view could not be verified",
  );
  await waitFor(() => expect(onShowCompany).not.toHaveBeenCalled());
});

it("clears the loading state when an in-flight company selection is cleared", async () => {
  vi.spyOn(api, "waterSupplyCompanies").mockResolvedValue({ snapshot_id: snapshot, items: [company] });
  const pending = (
    _acronym: string,
    _snapshotId: string,
    _cursor?: number,
    signal?: AbortSignal,
  ) => new Promise<never>((_resolve, reject) => {
    if (!signal) throw new Error("Expected an abort signal");
    signal.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")));
  });
  vi.spyOn(api, "waterSupplyCompanyAreas").mockImplementation(pending);
  vi.spyOn(api, "waterSupplyCompanyGeometry").mockImplementation(
    (_acronym, _snapshotId, signal) => new Promise<never>((_resolve, reject) => {
      signal?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")));
    }),
  );
  render(<CompanyExplorer onShowCompany={vi.fn()} onSelectArea={vi.fn()} onSelectPerformance={vi.fn()} />);

  const selector = await screen.findByLabelText("Water company");
  await userEvent.selectOptions(selector, "ANH");
  expect(screen.getByRole("status")).toHaveTextContent("Loading and verifying");
  await userEvent.selectOptions(selector, "");
  expect(screen.queryByText(/Loading and verifying/u)).not.toBeInTheDocument();
});
