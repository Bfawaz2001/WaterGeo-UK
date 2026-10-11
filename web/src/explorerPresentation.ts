import type { BathingWater, HydrologyMeasure } from "./types";

export const BATHING_CLASSIFICATIONS = ["Excellent", "Good", "Sufficient", "Poor"] as const;
export type BathingClassification = "" | (typeof BATHING_CLASSIFICATIONS)[number] | "unclassified";

export function filterBathingWaters(
  items: BathingWater[],
  classification: BathingClassification,
): BathingWater[] {
  if (!classification) return items;
  if (classification === "unclassified") return items.filter((item) => item.classification === null);
  return items.filter((item) => item.classification === classification);
}

export function periodLabel(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return "Period not supplied";
  if (seconds % 86_400 === 0) {
    const days = seconds / 86_400;
    return `${days} day${days === 1 ? "" : "s"}`;
  }
  if (seconds % 3_600 === 0) {
    const hours = seconds / 3_600;
    return `${hours} hour${hours === 1 ? "" : "s"}`;
  }
  if (seconds % 60 === 0) {
    const minutes = seconds / 60;
    return `${minutes} minute${minutes === 1 ? "" : "s"}`;
  }
  return `${seconds} seconds`;
}

export function hydrologyMeasureLabel(measure: HydrologyMeasure): string {
  const statistic = measure.source_fields?.valueStatistic;
  const identity = typeof statistic === "object" && statistic !== null && "@id" in statistic
    ? statistic["@id"]
    : undefined;
  const term = typeof identity === "string" ? identity.split(/[/#]/u).at(-1) : undefined;
  const statisticLabel = term?.replace(/([a-z])([A-Z])/gu, "$1 $2").toLocaleLowerCase();
  if (statisticLabel && statisticLabel !== "instantaneous") {
    const prefix = measure.period === 86_400 ? "Daily " : "";
    return `${prefix}${statisticLabel} ${measure.parameter}`;
  }
  return `Latest ${measure.parameter.toLocaleLowerCase()} observation`;
}

export function sourceFieldLabel(
  fields: Record<string, unknown> | undefined,
  key: string,
): string | null {
  const value = fields?.[key];
  if (typeof value === "string" || typeof value === "number") return String(value);
  if (typeof value !== "object" || value === null) return null;
  const objectValue = value as Record<string, unknown>;
  for (const label of ["label", "name", "@id"]) {
    const candidate = objectValue[label];
    if (typeof candidate === "string") {
      return label === "@id" ? candidate.split(/[/#]/u).at(-1) ?? candidate : candidate;
    }
  }
  return null;
}
