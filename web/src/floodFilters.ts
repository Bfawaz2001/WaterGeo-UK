import type { FloodArea } from "./types";

export const FLOOD_STATES = [
  { value: "1", label: "Severe Flood Warning", color: "#902039" },
  { value: "2", label: "Flood Warning", color: "#d14b29" },
  { value: "3", label: "Flood Alert", color: "#ad7500" },
  { value: "4", label: "Warning no longer in force", color: "#697b83" },
] as const;
export type FloodFilter = "" | "1" | "2" | "3" | "4";
export function filterFloods(items: FloodArea[], severity: FloodFilter): FloodArea[] {
  // A polygon without a warning is not an accepted warning state.
  return items.filter((item) => typeof item.warning_id === "string" &&
    (!severity || String(item.severity_level) === severity));
}
