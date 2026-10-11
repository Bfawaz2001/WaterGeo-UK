import { describe, expect, it } from "vitest";

import {
  BATHING_CLASSIFICATIONS,
  filterBathingWaters,
  hydrologyMeasureLabel,
  periodLabel,
  sourceFieldLabel,
} from "./explorerPresentation";
import type { BathingWater } from "./types";

const base: Omit<BathingWater, "bathing_water_id" | "classification"> = {
  publisher_uri: "https://environment.data.gov.uk/id/bathing-water/example",
  name: "Example beach",
  latitude: 51,
  longitude: -2,
  assessment_year: 2025,
  latest_sample_uri: null,
  latest_risk_prediction: null,
  distance_m: 100,
};

describe("bathing-water classification presentation", () => {
  const items = [...BATHING_CLASSIFICATIONS, null].map((classification, index) => ({
    ...base,
    bathing_water_id: String(index),
    classification,
  }));

  it.each(BATHING_CLASSIFICATIONS)("filters the exact %s publisher classification", (classification) => {
    expect(filterBathingWaters(items, classification).map((item) => item.classification)).toEqual([classification]);
  });

  it("preserves null as unclassified and All as the complete loaded result", () => {
    expect(filterBathingWaters(items, "unclassified")).toEqual([items.at(-1)]);
    expect(filterBathingWaters(items, "")).toBe(items);
  });
});

it("presents simple publisher quality fields without interpreting them", () => {
  expect(sourceFieldLabel({ quality: "Good" }, "quality")).toBe("Good");
  expect(sourceFieldLabel({ quality: { "@id": "https://example.test/quality/Estimated" } }, "quality")).toBe("Estimated");
  expect(sourceFieldLabel({}, "quality")).toBeNull();
});

it("formats declared periods without assuming every reading is 15 minutes", () => {
  expect(periodLabel(900)).toBe("15 minutes");
  expect(periodLabel(86_400)).toBe("1 day");
  expect(periodLabel(null)).toBe("Period not supplied");
});

it("uses publisher statistic metadata when available and retains a readable fallback", () => {
  const measure = { measure_id: "m", parameter: "flow", unit_name: "m3/s", period: 900, source_fields: {}, latest_observation: null };
  expect(hydrologyMeasureLabel(measure)).toBe("Latest flow observation");
  expect(hydrologyMeasureLabel({ ...measure, period: 86_400, source_fields: { valueStatistic: { "@id": "http://environment.data.gov.uk/reference/def/core/mean" } } })).toBe("Daily mean flow");
  expect(hydrologyMeasureLabel({ ...measure, source_fields: { valueStatistic: { "@id": "http://environment.data.gov.uk/reference/def/core/instantaneous" } } })).toBe("Latest flow observation");
});
