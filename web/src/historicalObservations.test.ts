import { expect, it, vi } from "vitest";
import { api } from "./api";
import {
  collectHistory,
  historyCsv,
  instant,
  validateDiscovery,
} from "./historicalObservations";
import {
  historyEdition as edition,
  historyRows as rows,
  historyPage as page,
  historyMeasure as measure,
} from "./test/historyFixtures";

it("collects a complete retrieval, preserving zero, missing and negative observations", async () => {
  const request = vi
    .spyOn(api, "hydrologyHistory")
    .mockResolvedValueOnce(page(rows.slice(0, 2), rows[1]!.observed_at))
    .mockResolvedValueOnce(page(rows.slice(2)));
  expect(await collectHistory(edition, new AbortController().signal)).toEqual(
    rows,
  );
  expect(request.mock.calls[1]?.[2]).toBe(rows[1]!.observed_at);
});
it.each([
  ["incomplete", page(rows.slice(0, 1))],
  ["duplicate", page([rows[0]!, rows[0]!, rows[2]!])],
  ["measure mismatch", { ...page(), measure_id: "wrong" }],
  ["hash mismatch", { ...page(), content_sha256: "c".repeat(64) }],
  ["window mismatch", { ...page(), requested_to: "2026-10-02T01:00:00Z" }],
  [
    "invalid number",
    page([{ ...rows[0]!, value: Infinity }, ...rows.slice(1)]),
  ],
  [
    "invalid date",
    page([{ ...rows[0]!, observed_at: "bad" }, ...rows.slice(1)]),
  ],
  [
    "outside window",
    page([
      { ...rows[0]!, observed_at: "2026-09-30T00:00:00Z" },
      ...rows.slice(1),
    ]),
  ],
  [
    "missing contradiction",
    page([{ ...rows[0]!, value: null }, ...rows.slice(1)]),
  ],
  [
    "publisher mismatch",
    page([
      {
        ...rows[0]!,
        source_fields: {
          quality: "Unchecked",
          measure: { "@id": "http://example.test/level-1" },
        },
      },
      ...rows.slice(1),
    ]),
  ],
  ["cursor inconsistency", page(rows.slice(0, 2), rows[0]!.observed_at)],
  ["empty continuing page", page([], rows[0]!.observed_at)],
])(
  "rejects %s before a partial result can be exported",
  async (_name, response) => {
    vi.spyOn(api, "hydrologyHistory").mockResolvedValue(response);
    await expect(
      collectHistory(edition, new AbortController().signal),
    ).rejects.toThrow();
  },
);
it("rejects repeated cursors and overlong pagination", async () => {
  vi.spyOn(api, "hydrologyHistory").mockResolvedValue(
    page(rows.slice(0, 1), rows[0]!.observed_at),
  );
  await expect(
    collectHistory(edition, new AbortController().signal),
  ).rejects.toThrow(/duplicate/);
});
it("does not fetch incompatible or oversized retrievals", async () => {
  const request = vi.spyOn(api, "hydrologyHistory");
  await expect(
    collectHistory(
      { ...edition, record_count: 10001 },
      new AbortController().signal,
    ),
  ).rejects.toThrow(/limit/);
  await expect(
    collectHistory(
      { ...edition, normalization_version: "future" },
      new AbortController().signal,
    ),
  ).rejects.toThrow(/incompatible/);
  expect(request).not.toHaveBeenCalled();
});
it("honours cancellation even if transport resolves after abort", async () => {
  const controller = new AbortController();
  vi.spyOn(api, "hydrologyHistory").mockImplementation(() => {
    controller.abort();
    return Promise.resolve(page());
  });
  await expect(collectHistory(edition, controller.signal)).rejects.toThrow();
});
it("validates deterministic exact-measure discovery and repeated editions", () => {
  const response = {
    measure_id: edition.measure_id,
    items: [edition],
    next_after_id: null,
  };
  expect(() =>
    validateDiscovery(response, edition.measure_id, []),
  ).not.toThrow();
  const tiedOlder = {
    ...edition,
    retrieval_id: "00000000-0000-4000-8000-000000000001",
  };
  expect(() =>
    validateDiscovery(
      { ...response, items: [edition, tiedOlder] },
      edition.measure_id,
      [],
    ),
  ).not.toThrow();
  expect(() =>
    validateDiscovery(
      { ...response, items: [tiedOlder, edition] },
      edition.measure_id,
      [],
    ),
  ).toThrow(/ordering/);
  expect(() => validateDiscovery(response, "flow", [])).toThrow();
  expect(() =>
    validateDiscovery(response, edition.measure_id, [edition]),
  ).toThrow();
  expect(() =>
    validateDiscovery(
      { ...response, next_after_id: "wrong" },
      edition.measure_id,
      [],
    ),
  ).toThrow();
  expect(() =>
    validateDiscovery(
      { ...response, items: [{ ...edition, normalized_sha256: "wrong" }] },
      edition.measure_id,
      [],
    ),
  ).toThrow();
});
it("exports stable UTF-8 CSV with provenance, safe text, quality JSON and original numbers", () => {
  const csv = historyCsv(
    edition,
    { ...measure, unit_name: '=HYPERLINK("bad")' },
    rows,
  );
  expect(
    csv.startsWith(
      "\uFEFFretrieval_id,measure_id,observed_at,value,value_state,unit,",
    ),
  ).toBe(true);
  expect(csv).toContain(',0,"reported"');
  expect(csv).toContain(',-2,"reported"');
  expect(csv).toContain(',"","missing"');
  expect(csv).toContain('"\'=HYPERLINK(""bad"")"');
  expect(csv).toContain('""quality"":""Missing""');
  expect(csv).toContain(edition.normalized_sha256);
  expect(csv.split("\r\n")).toHaveLength(5);
});
it.each([
  "bad",
  "2026-10-01",
  "2026-10-01T00:00:00",
  "2026-02-30T00:00:00Z",
  "2026-10-01T24:00:00Z",
])("rejects invalid or timezone-free timestamp %s", (date) =>
  expect(() => instant(date)).toThrow(),
);

it("accepts a valid empty retrieval and bounds unfinished pagination to ten pages", async () => {
  const request = vi
    .spyOn(api, "hydrologyHistory")
    .mockResolvedValueOnce({ ...page([]), record_count: 0 });
  expect(
    await collectHistory(
      { ...edition, record_count: 0 },
      new AbortController().signal,
    ),
  ).toEqual([]);
  request.mockReset();
  for (let index = 0; index < 10; index++) {
    const row = {
      ...rows[0]!,
      observed_at: new Date(
        Date.parse(edition.requested_from) + index * 900_000,
      ).toISOString(),
    };
    request.mockResolvedValueOnce({
      ...page([row], row.observed_at),
      record_count: 100,
    });
  }
  await expect(
    collectHistory(
      { ...edition, record_count: 100 },
      new AbortController().signal,
    ),
  ).rejects.toThrow(/Incomplete historical pagination/);
  expect(request).toHaveBeenCalledTimes(10);
});
