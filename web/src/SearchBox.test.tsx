import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";

import { api } from "./api";
import { SearchBox } from "./SearchBox";
import type { SearchResult } from "./types";

const result: SearchResult = {
  kind: "hydrology",
  identity: "station-1",
  label: "River Avon — Evesham",
  context: "Hydrology station",
  publisher: "Environment Agency",
  snapshot_id: "11111111-1111-4111-8111-111111111111",
  longitude: -1.94,
  latitude: 52.09,
};

beforeEach(() => vi.useFakeTimers({ shouldAdvanceTime: true }));

it("debounces bounded search, groups results and opens a selection", async () => {
  const search = vi.spyOn(api, "search").mockResolvedValue({ query: "river", items: [result], truncated: false, available_kinds: ["hydrology"], unavailable_kinds: [] });
  const select = vi.fn().mockResolvedValue(undefined);
  render(<SearchBox onSelect={select} />);
  await userEvent.type(screen.getByRole("searchbox"), "river");
  expect(search).not.toHaveBeenCalled();
  await act(() => vi.advanceTimersByTimeAsync(250));
  expect(await screen.findByRole("heading", { name: "Hydrology stations" })).toBeInTheDocument();
  expect(search).toHaveBeenCalledWith("river", expect.any(AbortSignal));
  await userEvent.click(screen.getByRole("button", { name: /River Avon/ }));
  expect(select).toHaveBeenCalledWith(result);
});

it("supports keyboard navigation and selection without moving focus from search", async () => {
  vi.spyOn(api, "search").mockResolvedValue({ query: "river", items: [result], truncated: false, available_kinds: ["hydrology"], unavailable_kinds: [] });
  const select = vi.fn().mockResolvedValue(undefined);
  render(<SearchBox onSelect={select} />);
  const input = screen.getByRole("searchbox");
  await userEvent.type(input, "river");
  await act(() => vi.advanceTimersByTimeAsync(250));
  await screen.findByRole("button", { name: /River Avon/ });
  await userEvent.keyboard("{ArrowDown}");
  expect(input).toHaveAttribute("aria-activedescendant", "watergeo-search-result-0");
  expect(input).toHaveFocus();
  await userEvent.keyboard("{Enter}");
  expect(select).toHaveBeenCalledWith(result);
});

it("clears a keyboard-highlighted result as soon as the query changes", async () => {
  const second = { ...result, identity: "station-2", label: "River Avon — Second" };
  const replacement = { ...result, identity: "station-b", label: "River B" };
  vi.spyOn(api, "search")
    .mockResolvedValueOnce({ query: "alpha", items: [result, second], truncated: false, available_kinds: ["hydrology"], unavailable_kinds: [] })
    .mockResolvedValueOnce({ query: "bravo", items: [replacement], truncated: false, available_kinds: ["hydrology"], unavailable_kinds: [] });
  render(<SearchBox onSelect={vi.fn()} />);
  const input = screen.getByRole("searchbox");
  await userEvent.type(input, "alpha");
  await act(() => vi.advanceTimersByTimeAsync(250));
  await screen.findByRole("button", { name: /River Avon — Second/ });
  await userEvent.keyboard("{ArrowDown}{ArrowDown}");
  expect(input).toHaveAttribute("aria-activedescendant", "watergeo-search-result-1");

  fireEvent.change(input, { target: { value: "bravo" } });
  expect(input).not.toHaveAttribute("aria-activedescendant");
  await act(() => vi.advanceTimersByTimeAsync(250));
  await screen.findByRole("button", { name: /River B/ });
  expect(input).not.toHaveAttribute("aria-activedescendant");
  expect(input).toHaveFocus();
});

it("distinguishes no matches from an unavailable search", async () => {
  vi.spyOn(api, "search").mockResolvedValueOnce({ query: "none", items: [], truncated: false, available_kinds: ["hydrology"], unavailable_kinds: [] });
  render(<SearchBox onSelect={vi.fn()} />);
  await userEvent.type(screen.getByRole("searchbox"), "none");
  await act(() => vi.advanceTimersByTimeAsync(250));
  expect(await screen.findAllByText("No matching WaterGeo features.")).toHaveLength(2);

  vi.mocked(api.search).mockRejectedValueOnce(new Error("offline"));
  await userEvent.clear(screen.getByRole("searchbox"));
  await userEvent.type(screen.getByRole("searchbox"), "river");
  await act(() => vi.advanceTimersByTimeAsync(250));
  expect(await screen.findAllByText("Search is currently unavailable.")).toHaveLength(2);
});

it("reports unavailable sources separately from no matching data", async () => {
  vi.spyOn(api, "search").mockResolvedValue({
    query: "none", items: [], truncated: false,
    available_kinds: ["hydrology"], unavailable_kinds: ["water-quality", "reservoirs"],
  });
  render(<SearchBox onSelect={vi.fn()} />);
  await userEvent.type(screen.getByRole("searchbox"), "none");
  await act(() => vi.advanceTimersByTimeAsync(250));
  expect(await screen.findAllByText("No matches in available datasets. 2 sources are unavailable.")).toHaveLength(2);
});

it("reports a failed feature selection separately from search availability", async () => {
  vi.spyOn(api, "search").mockResolvedValue({
    query: "river", items: [result], truncated: false,
    available_kinds: ["hydrology"], unavailable_kinds: [],
  });
  render(<SearchBox onSelect={vi.fn().mockRejectedValue(new Error("snapshot missing"))} />);
  await userEvent.type(screen.getByRole("searchbox"), "river");
  await act(() => vi.advanceTimersByTimeAsync(250));
  await userEvent.click(await screen.findByRole("button", { name: /River Avon/ }));
  expect(await screen.findAllByText(/feature is unavailable in the selected snapshot/)).toHaveLength(2);
});
