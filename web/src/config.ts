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

export function apiBasePath(value = import.meta.env.VITE_API_BASE_PATH): string {
  if (value === undefined || value === "") return "";
  if (!value.startsWith("/") || value.startsWith("//") || value.includes("://")) {
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
