import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { TrendChart } from "./TrendChart";
import { historyRows } from "./test/historyFixtures";
it("uses elapsed time and preserves gaps, zero and keyboard reading inspection", () => {
  const points = [
    historyRows[0]!,
    { ...historyRows[0]!, observed_at: "2026-10-01T00:05:00Z", value: 2 },
    ...historyRows.slice(1),
  ];
  const { container } = render(
    <TrendChart
      points={points}
      label="Historical level"
      unit="m"
      period={900}
    />,
  );
  const circles = screen.getAllByRole("graphics-symbol");
  const positions = circles.map((point) => Number(point.getAttribute("cx")));
  expect(
    (positions[1]! - positions[0]!) / (positions[2]! - positions[0]!),
  ).toBeCloseTo(1 / 12);
  expect(
    container.querySelector("path")?.getAttribute("d")?.match(/M/gu),
  ).toHaveLength(2);
  fireEvent.change(screen.getByRole("slider"), { target: { value: "2" } });
  expect(screen.getByRole("slider")).toHaveAttribute(
    "aria-valuetext",
    expect.stringContaining("Missing"),
  );
  expect(screen.getByText(/Missing ·/)).toBeInTheDocument();
});
it("breaks lines at undeclared sample gaps and handles all missing values", () => {
  const { rerender, container } = render(
    <TrendChart
      points={[historyRows[0]!, historyRows[2]!]}
      label="Level"
      unit="m"
      period={900}
    />,
  );
  expect(
    container.querySelector("path")?.getAttribute("d")?.match(/M/gu),
  ).toHaveLength(2);
  rerender(<TrendChart points={[historyRows[1]!]} label="Level" unit="m" />);
  expect(screen.getByText("No numeric values")).toBeInTheDocument();
  expect(screen.getByRole("img")).toHaveAccessibleName(
    /no reported numeric values/,
  );
  expect(container.querySelector("path")).toHaveAttribute("d", "");
});
it("fails closed on invalid geometry inputs", () => {
  render(
    <TrendChart
      points={[{ observed_at: "bad", value: NaN }]}
      label="Level"
      unit="m"
    />,
  );
  expect(screen.getByRole("alert")).toHaveTextContent("Invalid chart");
});

it("keeps isolated extrema visible in large series without thousands of focus stops", () => {
  const points = Array.from({ length: 201 }, (_, index) => ({
    observed_at: new Date(
      Date.parse(historyRows[0]!.observed_at) + index * 900_000,
    ).toISOString(),
    value: index === 100 ? 0 : null,
  }));
  render(
    <TrendChart points={points} label="Sparse level" unit="m" period={900} />,
  );
  expect(screen.getByRole("graphics-symbol")).toHaveAttribute(
    "aria-label",
    expect.stringContaining("0 m"),
  );
  expect(screen.getByRole("graphics-symbol")).not.toHaveAttribute("tabindex");
  fireEvent.change(screen.getByRole("slider"), { target: { value: "100" } });
  expect(screen.getByRole("slider")).toHaveAttribute(
    "aria-valuetext",
    expect.stringContaining("0 m"),
  );
});
