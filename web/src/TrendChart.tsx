import { useState } from "react";

interface Point {
  observed_at: string;
  value: number;
}

export function TrendChart({ points, label, unit }: { points: Point[]; label: string; unit: string }) {
  const [active, setActive] = useState(points.length - 1);
  if (points.length === 0) return <p>No accepted values are available for this chart.</p>;
  const width = 320;
  const height = 148;
  const padding = 18;
  const values = points.map((point) => point.value);
  const minimum = Math.min(...values);
  const maximum = Math.max(...values);
  const range = maximum - minimum || 1;
  const position = (point: Point, index: number) => ({
    x: padding + (index / Math.max(1, points.length - 1)) * (width - padding * 2),
    y: height - padding - ((point.value - minimum) / range) * (height - padding * 2),
  });
  const path = points.map((point, index) => {
    const { x, y } = position(point, index);
    return `${index === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
  const first = points[0];
  const last = points.at(-1);
  const activePoint = points[Math.min(active, points.length - 1)] ?? last ?? first;
  const description = `${label}: ${points.length} publisher values from ${first?.observed_at ?? "unknown"} to ${last?.observed_at ?? "unknown"}; range ${minimum.toFixed(1)} to ${maximum.toFixed(1)} ${unit}.`;
  return (
    <figure className="trend-chart">
      <div className="chart-summary">
        <span><strong>{last?.value.toFixed(1)}{unit}</strong><small>Latest publisher value</small></span>
        <span><strong>{minimum.toFixed(1)}–{maximum.toFixed(1)}{unit}</strong><small>Edition range</small></span>
      </div>
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={description} preserveAspectRatio="none">
        <line x1={padding} y1={padding} x2={padding} y2={height - padding} />
        <line x1={padding} y1={height - padding} x2={width - padding} y2={height - padding} />
        <path d={path} />
        {points.map((point, index) => {
          const { x, y } = position(point, index);
          return <circle key={`${point.observed_at}:${index}`} className={index === points.length - 1 ? "chart-latest" : ""} cx={x} cy={y} r={index === points.length - 1 ? "4" : "3"} tabIndex={0} role="graphics-symbol" aria-label={`${point.value} ${unit}, ${new Date(point.observed_at).toLocaleDateString()}`} onFocus={() => setActive(index)} onMouseEnter={() => setActive(index)}><title>{point.value} {unit} — {point.observed_at}</title></circle>;
        })}
      </svg>
      <figcaption><span>{new Date(first?.observed_at ?? "").toLocaleDateString()}</span><strong>{activePoint?.value.toFixed(1)} {unit} · {new Date(activePoint?.observed_at ?? "").toLocaleDateString()}</strong><span>{new Date(last?.observed_at ?? "").toLocaleDateString()}</span></figcaption>
      <p className="visually-hidden">{points.length} dated values</p>
    </figure>
  );
}
