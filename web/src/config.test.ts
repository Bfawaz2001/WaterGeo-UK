import { describe, expect, it } from "vitest";

import {
  FALLBACK_STYLE,
  OPENFREEMAP_STYLE,
  apiBasePath,
  basemapStyle,
  dataMode,
  deploymentBasePath,
  staticDataPath,
} from "./config";

describe("explorer configuration", () => {
  it("accepts only relative same-origin API prefixes", () => {
    expect(apiBasePath(undefined)).toBe("");
    expect(apiBasePath("/watergeo/")).toBe("/watergeo");
    for (const value of ["watergeo", "//other.example", "https://other.example", "/watergeo?x=1", "/watergeo#x", "/\\other"]) {
      expect(() => apiBasePath(value)).toThrow("same-origin absolute path");
    }
  });

  it("uses a key-free default and supports an explicit context-free fallback", () => {
    expect(basemapStyle(undefined)).toBe(OPENFREEMAP_STYLE);
    expect(basemapStyle("")).toBe(FALLBACK_STYLE);
  });

  it("derives root and repository static paths from the deployment base", () => {
    expect(dataMode(undefined)).toBe("api");
    expect(dataMode("static")).toBe("static");
    expect(() => dataMode("hybrid")).toThrow("api or static");
    expect(deploymentBasePath("/")).toBe("/");
    expect(deploymentBasePath("/WaterGeo-UK/")).toBe("/WaterGeo-UK/");
    expect(deploymentBasePath("/WaterGeo-UK")).toBe("/WaterGeo-UK/");
    expect(staticDataPath(undefined, "/")).toBe("/watergeo-data");
    expect(staticDataPath(undefined, "/WaterGeo-UK/")).toBe("/WaterGeo-UK/watergeo-data");
    expect(staticDataPath("/snapshot/", "/WaterGeo-UK/")).toBe("/snapshot");
  });

  it("rejects external and cross-origin static paths", () => {
    for (const value of ["data", "//example.test/data", "https://example.test/data", "/data?x=1", "/data#x", "/\\host/data"]) {
      expect(() => staticDataPath(value, "/")).toThrow("same-origin absolute path");
    }
    expect(() => deploymentBasePath("https://example.test/WaterGeo-UK/")).toThrow(
      "same-origin absolute path",
    );
  });
});
