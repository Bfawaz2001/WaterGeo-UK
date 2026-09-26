import { apiBasePath } from "./config";

export interface Overview { url: string; snapshot: string; attribution: string }

export function overviewPath(value: string): string {
  const path = apiBasePath(value);
  if (!/^\/[A-Za-z0-9_/-]+\/manifest\.json$/u.test(path)) throw new Error("Invalid overview path");
  return path;
}

export function parseOverview(value: unknown, manifestPath: string): Overview {
  if (typeof value !== "object" || value === null) throw new Error("Invalid overview");
  const manifest = value as Record<string, unknown>;
  const dataset = manifest.dataset as Record<string, unknown> | undefined;
  const tiles = manifest.tiles as Record<string, unknown> | undefined;
  const files = manifest.files as Record<string, unknown> | undefined;
  if (manifest.export_version !== "watergeo-export-v1" || manifest.entity !== "water-supply" ||
      tiles?.layer !== "water_supply" || !files?.["water-supply.pmtiles"] ||
      typeof dataset?.snapshot_id !== "string" || !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/u.test(dataset.snapshot_id) ||
      typeof dataset.attribution !== "string") throw new Error("Invalid overview manifest");
  const path = overviewPath(manifestPath);
  return { url: path.replace(/manifest\.json$/u, "water-supply.pmtiles"), snapshot: dataset.snapshot_id, attribution: dataset.attribution };
}
