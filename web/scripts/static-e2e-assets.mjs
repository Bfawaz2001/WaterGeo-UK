import { access, cp, mkdir, rm, writeFile } from "node:fs/promises";

const command = process.argv[2];
const fixture = new URL("../e2e-static/fixture/watergeo-data/", import.meta.url);
const publicDirectory = new URL("../public/watergeo-data/", import.meta.url);
const publicManifest = new URL("manifest.json", publicDirectory);
const marker = new URL("../public/.watergeo-static-e2e-fixture", import.meta.url);

async function exists(path) {
  try {
    await access(path);
    return true;
  } catch {
    return false;
  }
}

if (command === "prepare") {
  if (!(await exists(publicManifest))) {
    if (await exists(publicDirectory)) {
      throw new Error("Refusing to replace an incomplete public/watergeo-data directory");
    }
    await mkdir(publicDirectory, { recursive: true });
    await cp(fixture, publicDirectory, { recursive: true });
    await writeFile(marker, "temporary deterministic static E2E fixture\n");
  }
} else if (command === "cleanup") {
  if (await exists(marker)) {
    await rm(publicDirectory, { recursive: true, force: true });
    await rm(marker);
  }
} else {
  throw new Error("Usage: node scripts/static-e2e-assets.mjs prepare|cleanup");
}
