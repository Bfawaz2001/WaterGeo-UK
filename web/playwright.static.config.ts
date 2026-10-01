import { defineConfig } from "@playwright/test";

const basePath = process.env.VITE_BASE_PATH || "/WaterGeo-UK/";
const normalizedBase = basePath === "/" ? "/" : `/${basePath.replace(/^\/+|\/+$/gu, "")}/`;
const baseURL = `http://127.0.0.1:4174${normalizedBase}`;

export default defineConfig({
  testDir: "./e2e-static",
  fullyParallel: false,
  retries: 0,
  workers: 1,
  reporter: "line",
  use: {
    baseURL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    ...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH
      ? { launchOptions: { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH } }
      : {}),
  },
  webServer: {
    command:
      "node scripts/static-e2e-assets.mjs prepare && npm run build && " +
      "node scripts/static-e2e-assets.mjs cleanup && npm run preview -- --host 127.0.0.1 --port 4174",
    url: baseURL,
    reuseExistingServer: false,
    env: {
      VITE_WATERGEO_DATA_MODE: "static",
      VITE_BASE_PATH: normalizedBase,
      VITE_WATERGEO_STATIC_DATA_PATH: `${normalizedBase}watergeo-data`,
    },
  },
});
