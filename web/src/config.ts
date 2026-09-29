import type { StyleSpecification } from "maplibre-gl";

export const OPENFREEMAP_STYLE = "https://tiles.openfreemap.org/styles/liberty";

export const FALLBACK_STYLE: StyleSpecification = {
  version: 8,
  name: "WaterGeo context-free fallback",
  sources: {},
  layers: [
    {
      id: "background",
      type: "background",
      paint: { "background-color": "#e9f0ed" },
    },
  ],
};

export type DataMode = "api" | "static";

function sameOriginPath(value: string, variable: string): string {
  if (!value.startsWith("/") || value.startsWith("//") || /[:?#\\]/u.test(value)) {
    throw new Error(`${variable} must be a same-origin absolute path`);
  }
  const normalized = value.replace(/\/{2,}/gu, "/").replace(/\/$/u, "");
  return normalized || "/";
}

export function deploymentBasePath(value = import.meta.env.BASE_URL): string {
  const path = sameOriginPath(value || "/", "Vite BASE_URL");
  return path === "/" ? "/" : `${path}/`;
}

export function dataMode(value = import.meta.env.VITE_WATERGEO_DATA_MODE): DataMode {
  if (value === undefined || value === "" || value === "api") return "api";
  if (value === "static") return "static";
  throw new Error("VITE_WATERGEO_DATA_MODE must be api or static");
}

export function staticDataPath(
  value = import.meta.env.VITE_WATERGEO_STATIC_DATA_PATH,
  base = import.meta.env.BASE_URL,
): string {
  if (value) return sameOriginPath(value, "VITE_WATERGEO_STATIC_DATA_PATH");
  return `${deploymentBasePath(base)}watergeo-data`.replace(/\/$/u, "");
}

export function apiBasePath(value = import.meta.env.VITE_API_BASE_PATH): string {
  if (value === undefined || value === "") return "";
  if (!value.startsWith("/") || value.startsWith("//") || value.includes("://") || /[?#\\]/u.test(value)) {
    throw new Error("VITE_API_BASE_PATH must be a same-origin absolute path");
  }
  return value.replace(/\/$/, "");
}

export function basemapStyle(
  value = import.meta.env.VITE_BASEMAP_STYLE_URL,
): string | StyleSpecification {
  if (value === "") return FALLBACK_STYLE;
  return value ?? OPENFREEMAP_STYLE;
}
