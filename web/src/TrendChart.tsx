interface Point {
  observed_at: string;
  value: number;
}

export function TrendChart({ points, label, unit }: { points: Point[]; label: string; unit: string }) {
  if (points.length === 0) return <p>No accepted values are available for this chart.</p>;
  const width = 320;
  const height = 116;
  const padding = 12;
  const values = points.map((point) => point.value);
  const minimum = Math.min(...values);
  const maximum = Math.max(...values);
  const range = maximum - minimum || 1;
  const path = points.map((point, index) => {
    const x = padding + (index / Math.max(1, points.length - 1)) * (width - padding * 2);
    const y = height - padding - ((point.value - minimum) / range) * (height - padding * 2);
    return `${index === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
  const first = points[0];
  const last = points.at(-1);
  const description = `${label}: ${points.length} publisher values from ${first?.observed_at ?? "unknown"} to ${last?.observed_at ?? "unknown"}; range ${minimum.toFixed(1)} to ${maximum.toFixed(1)} ${unit}.`;
  return (
    <figure className="trend-chart">
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={description} preserveAspectRatio="none">
        <line x1={padding} y1={padding} x2={padding} y2={height - padding} />
        <line x1={padding} y1={height - padding} x2={width - padding} y2={height - padding} />
        <path d={path} />
        {points.map((point, index) => {
          const x = padding + (index / Math.max(1, points.length - 1)) * (width - padding * 2);
          const y = height - padding - ((point.value - minimum) / range) * (height - padding * 2);
          return <circle key={`${point.observed_at}:${index}`} cx={x} cy={y} r="2.5"><title>{point.value} {unit} — {point.observed_at}</title></circle>;
        })}
      </svg>
      <figcaption>{minimum.toFixed(1)}–{maximum.toFixed(1)} {unit} · {points.length} dated values</figcaption>
    </figure>
  );
}
