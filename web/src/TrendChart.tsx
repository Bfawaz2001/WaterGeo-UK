import { useState } from "react";
import { MetadataValue } from "./MetadataValue";
import { instant } from "./historicalObservations";

interface Point {
  observed_at: string;
  value: number | null;
  source_fields?: Record<string, unknown>;
}

export function TrendChart({
  points,
  label,
  unit,
  period,
}: {
  points: Point[];
  label: string;
  unit: string;
  period?: number;
}) {
  const [active, setActive] = useState(points.length - 1);
  if (points.length === 0)
    return <p>No accepted values are available for this chart.</p>;
  let times: number[];
  try {
    times = points.map((point) => instant(point.observed_at));
  } catch {
    return <p role="alert">Invalid chart observations.</p>;
  }
  if (
    points.some(
      (point, index) =>
        !Number.isFinite(times[index]) ||
        (index > 0 && times[index]! <= times[index - 1]!) ||
        (point.value !== null && !Number.isFinite(point.value)),
    )
  )
    return <p role="alert">Invalid chart observations.</p>;
  const width = 400;
  const height = 180;
  const padding = 38;
  const values = points.flatMap((point) =>
    point.value === null ? [] : [point.value],
  );
  const minimum = values.length ? Math.min(...values) : 0;
  const maximum = values.length ? Math.max(...values) : 0;
  // Normalize before subtraction to avoid overflowing finite values of opposite signs.
  const magnitude = Math.max(Math.abs(minimum), Math.abs(maximum), 1);
  const low = minimum / magnitude - (maximum === minimum ? 0.05 : 0);
  const range = maximum === minimum ? 0.1 : maximum / magnitude - low;
  const firstTime = times[0]!;
  const span = times.at(-1)! - firstTime || 1;
  const position = (point: Point, index: number) => ({
    x: padding + ((times[index]! - firstTime) / span) * (width - padding * 2),
    y:
      height -
      padding -
      (((point.value ?? minimum) / magnitude - low) / range) *
        (height - padding * 2),
  });
  const path = points
    .map((point, index) => {
      if (point.value === null) return "";
      const connected =
        index > 0 &&
        points[index - 1]!.value !== null &&
        (!period || times[index]! - times[index - 1]! <= period * 1500);
      const { x, y } = position(point, index);
      const command = `${connected ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`;
      return command;
    })
    .join(" ");
  const first = points[0]!;
  const last = points.at(-1)!;
  const activeIndex = Math.max(0, Math.min(active, points.length - 1));
  const activePoint = points[activeIndex]!;
  const rangeDescription = values.length
    ? `range ${minimum.toFixed(1)} to ${maximum.toFixed(1)} ${unit}`
    : "no reported numeric values";
  const description = `${label}: ${points.length} publisher observations from ${first.observed_at} to ${last.observed_at}; ${rangeDescription}; ${points.length - values.length} missing observations.`;
  const dateLabel = (text: string) =>
    new Date(text).toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      ...(span < 3 * 86400_000
        ? { hour: "2-digit", minute: "2-digit" }
        : { year: "numeric" }),
    });
  return (
    <figure className="trend-chart">
      <div className="chart-summary">
        <span>
          <strong>
            {last.value === null
              ? "Missing"
              : `${Number.isInteger(last.value) ? last.value.toFixed(1) : last.value}${unit}`}
          </strong>
          <small>Last observation in series</small>
        </span>
        <span>
          <strong>
            {values.length
              ? `${minimum}–${maximum} ${unit}`
              : "No numeric values"}
          </strong>
          <small>Edition range</small>
        </span>
      </div>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label={description}
        onMouseMove={(event) => {
          if ((event.target as Element).tagName.toLowerCase() === "circle")
            return;
          const rect = event.currentTarget.getBoundingClientRect();
          if (rect.width === 0) return;
          const target =
            firstTime +
            Math.max(
              0,
              Math.min(
                1,
                (((event.clientX - rect.left) / rect.width) * width - padding) /
                  (width - 2 * padding),
              ),
            ) *
              span;
          let left = 0;
          let right = times.length - 1;
          while (left < right) {
            const mid = Math.floor((left + right) / 2);
            if (times[mid]! < target) left = mid + 1;
            else right = mid;
          }
          setActive(
            left > 0 && target - times[left - 1]! < times[left]! - target
              ? left - 1
              : left,
          );
        }}
      >
        <line x1={padding} y1={padding} x2={padding} y2={height - padding} />
        <line
          x1={padding}
          y1={height - padding}
          x2={width - padding}
          y2={height - padding}
        />
        <text x={padding} y={16}>
          {unit}
        </text>
        {values.length > 0 &&
          (maximum === minimum ? (
            <text x={padding - 4} y={height / 2} textAnchor="end">
              {minimum.toPrecision(3)}
            </text>
          ) : (
            <>
              <text x={padding - 4} y={padding} textAnchor="end">
                {maximum.toPrecision(3)}
              </text>
              <text x={padding - 4} y={height - padding} textAnchor="end">
                {minimum.toPrecision(3)}
              </text>
            </>
          ))}
        <path d={path} />
        {points.map((point, index) => {
          if (point.value === null) return null;
          const connectsBefore =
            index > 0 &&
            points[index - 1]!.value !== null &&
            (!period || times[index]! - times[index - 1]! <= period * 1500);
          const connectsAfter =
            index + 1 < points.length &&
            points[index + 1]!.value !== null &&
            (!period || times[index + 1]! - times[index]! <= period * 1500);
          // Single-point segments need a visible marker even in large series.
          if (points.length > 200 && (connectsBefore || connectsAfter))
            return null;
          const { x, y } = position(point, index);
          return (
            <circle
              key={point.observed_at}
              className={index === points.length - 1 ? "chart-latest" : ""}
              cx={x}
              cy={y}
              r="3"
              tabIndex={points.length <= 200 ? 0 : undefined}
              role="graphics-symbol"
              aria-label={`${point.value} ${unit}, ${new Date(point.observed_at).toLocaleString()}`}
              onFocus={() => setActive(index)}
              onMouseEnter={() => setActive(index)}
            >
              <title>
                {point.value} {unit} — {point.observed_at}
              </title>
            </circle>
          );
        })}
        {activePoint.value !== null && (
          <circle
            className="chart-latest"
            cx={position(activePoint, activeIndex).x}
            cy={position(activePoint, activeIndex).y}
            r="4"
          />
        )}
      </svg>
      <figcaption>
        <span>{dateLabel(first.observed_at)}</span>
        <strong aria-live="polite">
          {activePoint.value === null
            ? "Missing"
            : `${Number.isInteger(activePoint.value) ? activePoint.value.toFixed(1) : activePoint.value} ${unit}`}{" "}
          · {new Date(activePoint.observed_at).toLocaleString()}
        </strong>
        <span>{dateLabel(last.observed_at)}</span>
      </figcaption>
      <p className="chart-timezone">
        Chart timestamps: {Intl.DateTimeFormat().resolvedOptions().timeZone}.
      </p>
      <label>
        Inspect reading{" "}
        <input
          type="range"
          min="0"
          max={points.length - 1}
          value={activeIndex}
          onChange={(event) => setActive(Number(event.target.value))}
          aria-valuetext={`${activePoint.value ?? "Missing"} ${unit}, ${activePoint.observed_at}`}
        />
      </label>
      {activePoint.source_fields && (
        <details>
          <summary>Selected reading quality and publisher fields</summary>
          <MetadataValue value={activePoint.source_fields} />
        </details>
      )}
      <p className="visually-hidden">{points.length} dated values</p>
    </figure>
  );
}
