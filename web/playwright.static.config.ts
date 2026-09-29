import { defineConfig } from "@playwright/test";

const basePath = process.env.VITE_BASE_PATH || "/";
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
    command: "npm run build && npm run preview -- --host 127.0.0.1 --port 4174",
    url: baseURL,
    reuseExistingServer: false,
    env: {
      VITE_BASEMAP_STYLE_URL: "",
      VITE_WATERGEO_DATA_MODE: "static",
      VITE_BASE_PATH: normalizedBase,
    },
  },
});
