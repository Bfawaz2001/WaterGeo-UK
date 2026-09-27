import type { ReactNode } from "react";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function scalar(value: unknown): string | null {
  if (value === null) return "Not supplied";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "string" || typeof value === "number") return String(value);
  return null;
}

export function MetadataValue({ value, depth = 0 }: { value: unknown; depth?: number }): ReactNode {
  const simple = scalar(value);
  if (simple !== null) return simple;
  if (Array.isArray(value)) {
    const items = value as unknown[];
    if (items.length === 0) return "None supplied";
    return <ul className="metadata-values">{items.map((item, index) => (
      <li key={index}><MetadataValue value={item} depth={depth + 1} /></li>
    ))}</ul>;
  }
  if (isRecord(value)) {
    const label = scalar(value.pref_label);
    const notation = scalar(value.notation);
    if (label && label !== "Not supplied") return <span className="metadata-classification">
      <span>{label}</span>
      {notation && notation !== "Not supplied" && notation !== label && <small>{notation}</small>}
    </span>;
    const entries = Object.entries(value);
    if (entries.length === 0) return "No fields supplied";
    if (depth >= 2) return entries.map(([key, item]) => `${key}: ${scalar(item) ?? "structured value"}`).join("; ");
    return <dl className="metadata-nested">{entries.map(([key, item]) => <div key={key}>
      <dt>{key.replaceAll("_", " ")}</dt><dd><MetadataValue value={item} depth={depth + 1} /></dd>
    </div>)}</dl>;
  }
  return String(value);
}
