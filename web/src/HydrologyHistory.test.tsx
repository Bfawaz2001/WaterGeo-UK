import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { api } from "./api";
import { HydrologyHistory } from "./HydrologyHistory";
import { FeatureDrilldown } from "./FeatureDrilldown";
import { dataset } from "./test/fixtures";
import {
  historyEdition as edition,
  historyMeasure as measure,
  historyPage as page,
} from "./test/historyFixtures";
import type { HistoryDiscovery } from "./historicalObservations";
import type { SelectedFeature } from "./types";

function setup() {
  vi.spyOn(api, "hydrologyRetrievals").mockResolvedValue({
    measure_id: measure.measure_id,
    items: [edition],
    next_after_id: null,
  });
  return vi.spyOn(api, "hydrologyHistory").mockResolvedValue(page());
}
it("selects verified history, limits presets to accepted windows and inspects readings", async () => {
  const request = setup();
  render(<HydrologyHistory station="Station" measures={[measure]} />);
  expect(
    await screen.findByRole("button", { name: "Download observations CSV" }),
  ).toBeInTheDocument();
  expect(screen.getByText(/Complete retrieval verified/)).toHaveTextContent(
    "3 stored records",
  );
  expect(screen.getByText(/7 days/)).toBeDisabled();
  expect(screen.getByText(/30 days/)).toBeDisabled();
  expect(screen.getByText(/Partial observation coverage/)).toBeInTheDocument();
  fireEvent.change(screen.getByRole("slider"), { target: { value: "1" } });
  expect(screen.getByRole("slider")).toHaveAttribute(
    "aria-valuetext",
    expect.stringContaining("Missing"),
  );
  await userEvent.selectOptions(
    screen.getByLabelText("Observation window"),
    "1",
  );
  expect(request).toHaveBeenCalledTimes(1);
  await userEvent.click(screen.getByText("Observation table"));
  expect(screen.getByRole("table")).toHaveTextContent("Missing");
});
it("reports failed and incomplete pagination without download", async () => {
  setup().mockResolvedValue({ ...page(), record_count: 4 });
  render(<HydrologyHistory station="Station" measures={[measure]} />);
  expect(await screen.findByRole("alert")).toHaveTextContent(
    /identity or provenance/,
  );
  expect(
    screen.queryByRole("button", { name: "Download observations CSV" }),
  ).not.toBeInTheDocument();
});
it("treats absent history as a normal empty state", async () => {
  vi.spyOn(api, "hydrologyRetrievals").mockResolvedValue({
    measure_id: measure.measure_id,
    items: [],
    next_after_id: null,
  });
  const request = vi.spyOn(api, "hydrologyHistory");
  render(<HydrologyHistory station="Station" measures={[measure]} />);
  expect(
    await screen.findByText(/No stored historical data/),
  ).toBeInTheDocument();
  expect(request).not.toHaveBeenCalled();
});
it("aborts measure discovery and rejects obsolete results on measurement change", async () => {
  let resolve!: (page: HistoryDiscovery) => void;
  const request = vi
    .spyOn(api, "hydrologyRetrievals")
    .mockImplementationOnce(
      () =>
        new Promise((done) => {
          resolve = done;
        }),
    )
    .mockResolvedValue({
      measure_id: "flow-1",
      items: [],
      next_after_id: null,
    });
  render(
    <HydrologyHistory
      station="Station"
      measures={[
        measure,
        {
          ...measure,
          measure_id: "flow-1",
          parameter: "flow",
          unit_name: "m3/s",
        },
      ]}
    />,
  );
  await userEvent.selectOptions(
    screen.getByLabelText("Historical measurement"),
    "flow-1",
  );
  expect(request.mock.calls[0]?.[1].aborted).toBe(true);
  await act(async () => {
    resolve({
      measure_id: measure.measure_id,
      items: [edition],
      next_after_id: null,
    });
    await Promise.resolve();
  });
  expect(
    await screen.findByText(/No stored historical data/),
  ).toBeInTheDocument();
  expect(screen.queryByText("Available retrieval")).not.toBeInTheDocument();
});
it("aborts observations on retrieval change and only renders the new edition", async () => {
  const second = {
    ...edition,
    retrieval_id: "22222222-2222-4222-8222-222222222222",
    retrieval_completed_at: "2026-10-02T00:01:00Z",
    retrieval_started_at: "2026-10-02T00:00:00Z",
  };
  vi.spyOn(api, "hydrologyRetrievals").mockResolvedValue({
    measure_id: measure.measure_id,
    items: [edition, second],
    next_after_id: null,
  });
  let resolve!: (result: ReturnType<typeof page>) => void;
  const request = vi
    .spyOn(api, "hydrologyHistory")
    .mockImplementationOnce(
      () =>
        new Promise((done) => {
          resolve = done;
        }),
    )
    .mockResolvedValue({ ...page(), ...second });
  render(<HydrologyHistory station="Station" measures={[measure]} />);
  await screen.findByLabelText("Available retrieval");
  await waitFor(() => expect(request).toHaveBeenCalledTimes(1));
  await userEvent.selectOptions(
    screen.getByLabelText("Available retrieval"),
    second.retrieval_id,
  );
  expect(request.mock.calls[0]?.[1].aborted).toBe(true);
  await act(async () => {
    resolve(page());
    await Promise.resolve();
  });
  expect(
    await screen.findByRole("button", { name: "Download observations CSV" }),
  ).toBeInTheDocument();
  expect(screen.getByText(second.retrieval_id)).toBeInTheDocument();
});
it("aborts station history and clears old measure detail when station switches", async () => {
  const selected: SelectedFeature = {
    kind: "hydrology",
    dataset,
    item: {
      station_id: "one",
      labels: ["One"],
      source_uri: "https://example.test/one",
      location_status: "unavailable",
      latitude: null,
      longitude: null,
      geometry: null,
      distance_m: null,
    },
  };
  vi.spyOn(api, "hydrologyDetail").mockResolvedValue({
    ...selected.item,
    dataset,
    measures: [measure],
  });
  const request = vi
    .spyOn(api, "hydrologyRetrievals")
    .mockImplementation(() => new Promise(() => {}));
  const { rerender } = render(<FeatureDrilldown selected={selected} />);
  await screen.findByText("Latest measurements");
  await userEvent.click(screen.getByText("Historical observations"));
  await waitFor(() => expect(request).toHaveBeenCalledTimes(1));
  rerender(
    <FeatureDrilldown
      selected={{
        ...selected,
        item: { ...selected.item, station_id: "two", labels: ["Two"] },
      }}
    />,
  );
  expect(request.mock.calls[0]?.[1].aborted).toBe(true);
  expect(screen.queryByText(/Discovering/)).not.toBeInTheDocument();
});
it("explains static history absence without calling either history route", () => {
  vi.stubEnv("VITE_WATERGEO_DATA_MODE", "static");
  const discovery = vi.spyOn(api, "hydrologyRetrievals");
  const observations = vi.spyOn(api, "hydrologyHistory");
  render(
    <FeatureDrilldown
      selected={{
        kind: "hydrology",
        dataset,
        item: {
          station_id: "one",
          labels: ["One"],
          source_uri: "https://example.test/one",
          location_status: "unavailable",
          latitude: null,
          longitude: null,
          geometry: null,
          distance_m: null,
        },
      }}
    />,
  );
  expect(
    screen.getByText(/does not include stored Hydrology history/),
  ).toBeInTheDocument();
  expect(discovery).not.toHaveBeenCalled();
  expect(observations).not.toHaveBeenCalled();
  vi.unstubAllEnvs();
});

it("reports backend failure and supports an explicit successful discovery retry", async () => {
  vi.spyOn(api, "hydrologyRetrievals")
    .mockRejectedValueOnce(new Error("Hydrology history unavailable"))
    .mockResolvedValueOnce({
      measure_id: measure.measure_id,
      items: [],
      next_after_id: null,
    });
  render(<HydrologyHistory station="Station" measures={[measure]} />);
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Hydrology history unavailable",
  );
  await userEvent.click(
    screen.getByRole("button", { name: "Retry discovery" }),
  );
  expect(
    await screen.findByText(/No stored historical data/),
  ).toBeInTheDocument();
});
