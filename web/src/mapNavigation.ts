import type { Geometry } from "geojson";

export type MapBounds = [[number, number], [number, number]];
export interface MapNavigation { id: number; bounds: MapBounds; maxZoom?: number }

/** Only accepted coordinate pairs contribute; never navigate using malformed geometry. */
export function geometryBounds(geometries: Array<Geometry | null>): MapBounds | null {
  const positions: [number, number][] = [];
  const coordinates = (value: unknown): void => {
    if (!Array.isArray(value)) return;
    if (typeof value[0] === "number" && typeof value[1] === "number") {
      const [x, y] = value as [number, number];
      if (Number.isFinite(x) && Number.isFinite(y) && Math.abs(x) <= 180 && Math.abs(y) <= 90) positions.push([x, y]);
      return;
    }
    value.forEach(coordinates);
  };
  const inspect = (geometry: Geometry | null): void => {
    if (!geometry) return;
    if (geometry.type === "GeometryCollection") geometry.geometries.forEach(inspect);
    else coordinates(geometry.coordinates);
  };
  geometries.forEach(inspect);
  if (!positions.length) return null;
  let west = 180, south = 90, east = -180, north = -90;
  for (const [x, y] of positions) {
    west = Math.min(west, x); east = Math.max(east, x);
    south = Math.min(south, y); north = Math.max(north, y);
  }
  // UK products never require an antimeridian-spanning fit.
  return east - west > 180 ? null : [[west, south], [east, north]];
}

/** Orientation extents, not dataset coverage boundaries or distribution estimates. */
export const REGIONS: Array<{ label: string; bounds: MapBounds }> = [
  { label: "Great Britain", bounds: [[-8.5, 49.8], [1.9, 59.4]] },
  { label: "Northern England", bounds: [[-5.2, 53.4], [-0.2, 55.8]] },
  { label: "Midlands", bounds: [[-3.2, 51.7], [0.2, 53.5]] },
  { label: "South East", bounds: [[-2.1, 50.6], [1.8, 52.2]] },
  { label: "South West", bounds: [[-5.8, 49.9], [-1.6, 51.8]] },
  { label: "Wales", bounds: [[-5.4, 51.3], [-2.5, 53.5]] },
  { label: "Scotland", bounds: [[-7.6, 54.6], [-0.7, 59.3]] },
];
