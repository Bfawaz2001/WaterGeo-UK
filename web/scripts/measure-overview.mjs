// Reproducible local I/O measurements, not network or GPU render benchmarks.
import { open, readFile } from "node:fs/promises";
import { performance } from "node:perf_hooks";
import { PMTiles } from "pmtiles";

const directory = process.argv[2];
if (!directory) throw new Error("Usage: node scripts/measure-overview.mjs EXPORT_DIRECTORY");
const file = await open(`${directory}/water-supply.pmtiles`, "r");
let bytes = 0;
let requests = 0;
const source = {
  getKey: () => "local-watergeo-overview",
  async getBytes(offset, length) {
    const buffer = Buffer.alloc(length);
    const read = await file.read(buffer, 0, length, offset);
    bytes += read.bytesRead;
    requests++;
    return { data: buffer.buffer.slice(buffer.byteOffset, buffer.byteOffset + read.bytesRead) };
  },
};
try {
  const start = performance.now();
  const archive = new PMTiles(source);
  const header = await archive.getHeader();
  const metadata = await archive.getMetadata();
  // Six tiles covering a representative UK viewport at zoom five.
  const tiles = [];
  for (const x of [15, 16]) for (const y of [9, 10, 11]) {
    tiles.push(await archive.getZxy(5, x, y));
  }
  const tileMs = performance.now() - start;
  const text = await readFile(`${directory}/water-supply.geojson`, "utf8");
  const parseStart = performance.now();
  const collection = JSON.parse(text);
  console.log(JSON.stringify({
    pmtiles: { bytesRead: bytes, reads: requests, localReadAndDecodeMs: tileMs,
      presentTiles: tiles.filter(Boolean).length, minZoom: header.minZoom, maxZoom: header.maxZoom, layers: metadata.vector_layers },
    geojson: { bytes: Buffer.byteLength(text), parseMs: performance.now() - parseStart, features: collection.features.length },
  }, null, 2));
} finally { await file.close(); }
