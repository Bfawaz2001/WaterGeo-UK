import { describe, expect, it } from "vitest";

import {
  FALLBACK_STYLE,
  OPENFREEMAP_STYLE,
  apiBasePath,
  basemapStyle,
  dataMode,
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

  it("validates API and static data modes and same-origin static paths", () => {
    expect(dataMode(undefined)).toBe("api");
    expect(dataMode("static")).toBe("static");
    expect(() => dataMode("hybrid")).toThrow("api or static");
    expect(staticDataPath(undefined)).toBe("/watergeo-data");
    expect(staticDataPath("/snapshot/")).toBe("/snapshot");
    expect(() => staticDataPath("https://example.test/data")).toThrow("same-origin");
  });
});
