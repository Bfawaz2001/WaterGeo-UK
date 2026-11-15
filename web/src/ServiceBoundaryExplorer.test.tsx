/// <reference types="node" />
import { webcrypto } from "node:crypto";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import { ServiceBoundaryExplorer } from "./ServiceBoundaryExplorer";
import { verifiedJson } from "./serviceBundleIntegrity";

const encoder = new TextEncoder();
async function checksum(text: string) {
  return Array.from(new Uint8Array(await webcrypto.subtle.digest("SHA-256", encoder.encode(text))), (n) => n.toString(16).padStart(2, "0")).join("");
}
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

it("verifies both service inventories and retains quarantined insets", async () => {
  vi.stubGlobal("crypto", webcrypto);
  const services = ["water-supply", "sewerage"];
  const areas = services.map((service) => ({
    boundary_id: `${service}:snapshot:7`, service, source_id: 7,
    company_id: "fixture", company_name: "Fixture Water", COMPANY: "Publisher Fixture",
    Acronym: "FIX", AreaServed: `${service} inset`, AreaType: "inset", CoType: "NAV",
    WARNINGS: "Publisher caveat", source_valid: service === "water-supply",
    source_validity: service === "water-supply" ? "Valid Geometry" : "Holes are nested",
    geometry_file: `areas/${service}/7.geojson`, source_fields_json: '{"Licence":"OGL"}',
  }));
  const inventory = { areas, services: services.map((service) => ({ service, area_count: 1 })) };
  const assets: Record<string, string> = { "index.json": JSON.stringify(inventory) };
  for (const area of areas) {
    assets[`${area.service}-overview.geojson`] = JSON.stringify({ features: [{ id: area.boundary_id,
      geometry: { type: "Polygon", coordinates: [[[0, 50], [1, 50], [1, 51], [0, 50]]] } }] });
    assets[area.geometry_file] = JSON.stringify({ id: area.boundary_id });
  }
  const files = Object.fromEntries(await Promise.all(Object.entries(assets).map(async ([name, text]) => [name, { bytes: encoder.encode(text).length, sha256: await checksum(text) }])));
  const manifest = JSON.stringify({ product_version: "watergeo-ofwat-services-v1", files,
    datasets: Object.fromEntries(services.map((service) => [service, { dataset: service, sha256: "snapshot", attribution: "Ofwat fixture", validation: { record_count: 1 } }])) });
  assets["manifest.json"] = manifest;
  vi.stubGlobal("fetch", vi.fn((url: string) => Promise.resolve(new Response(assets[url.replace("/bundle/", "")], { status: 200 }))));
  render(<ServiceBoundaryExplorer base="/bundle" manifestHash={await checksum(manifest)} />);
  await waitFor(() => expect(screen.getByRole("option", { name: "Fixture Water" })).toBeInTheDocument());
  await userEvent.selectOptions(screen.getByLabelText("Undertaker"), "fixture");
  expect(screen.getByText(/1 verified associated areas · 0 quarantined/)).toBeInTheDocument();
  await userEvent.selectOptions(screen.getByLabelText("Service"), "sewerage");
  await userEvent.selectOptions(screen.getByLabelText("Undertaker"), "fixture");
  expect(screen.getByText(/1 verified associated areas · 1 quarantined/)).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: /sewerage inset/ }));
  expect(await screen.findByRole("link", { name: "Download verified area GeoJSON" })).toHaveAttribute("href", "/bundle/areas/sewerage/7.geojson");
  expect(screen.getByText("Holes are nested")).toBeInTheDocument();
});

it("rejects corruption and oversized assets", async () => {
  vi.stubGlobal("crypto", webcrypto);
  await expect(verifiedJson(new Response('{"tampered":true}'), { sha256: "0".repeat(64) })).rejects.toThrow("checksum mismatch");
  await expect(verifiedJson(new Response("{}", { headers: { "content-length": "10485761" } }), { sha256: "0".repeat(64) })).rejects.toThrow("Asset unavailable");
});

it("fails closed when a pinned manifest changes", async () => {
  vi.stubGlobal("crypto", webcrypto);
  vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response("{}"))));
  render(<ServiceBoundaryExplorer base="/bundle" manifestHash={"0".repeat(64)} />);
  expect(await screen.findByRole("alert")).toHaveTextContent("could not be verified");
  expect(screen.queryByRole("img")).not.toBeInTheDocument();
});
