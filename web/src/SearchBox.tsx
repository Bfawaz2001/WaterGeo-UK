import { useEffect, useId, useMemo, useRef, useState } from "react";

import { api } from "./api";
import type { SearchKind, SearchResult } from "./types";

const KIND_LABELS: Record<SearchKind, string> = {
  hydrology: "Hydrology stations",
  "water-quality": "Water Quality sampling points",
  reservoirs: "Reservoirs",
  "thames-discharge": "Thames discharge monitors",
  "water-body": "Water Bodies",
  "water-supply": "Water-supply areas",
};

interface Props {
  onSelect: (result: SearchResult) => Promise<void>;
}

export function SearchBox({ onSelect }: Props) {
  const statusId = useId();
  const [term, setTerm] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [truncated, setTruncated] = useState(false);
  const [unavailableKinds, setUnavailableKinds] = useState<SearchKind[]>([]);
  const [state, setState] = useState<"idle" | "loading" | "ready" | "error" | "selecting" | "selection-error">("idle");
  const [open, setOpen] = useState(false);
  const selectionGeneration = useRef(0);

  useEffect(() => {
    const query = term.trim();
    if (query.length < 2) return;
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      setState("loading");
      setOpen(true);
      void api.search(query, controller.signal).then((response) => {
        if (controller.signal.aborted) return;
        setResults(response.items);
        setTruncated(response.truncated);
        setUnavailableKinds(response.unavailable_kinds);
        setState("ready");
      }).catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setResults([]);
        setState("error");
      });
    }, 250);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [term]);

  const groups = useMemo(() => {
    const grouped = new Map<SearchKind, SearchResult[]>();
    for (const result of results) {
      const values = grouped.get(result.kind) ?? [];
      values.push(result);
      grouped.set(result.kind, values);
    }
    return grouped;
  }, [results]);

  const choose = async (result: SearchResult) => {
    const generation = ++selectionGeneration.current;
    setState("selecting");
    try {
      await onSelect(result);
      if (selectionGeneration.current === generation) {
        setOpen(false);
        setState("ready");
      }
    } catch {
      if (selectionGeneration.current === generation) setState("selection-error");
    }
  };

  const status = state === "loading"
    ? "Searching WaterGeo…"
    : state === "selecting"
      ? "Opening selected feature…"
      : state === "error"
        ? "Search is currently unavailable."
        : state === "selection-error"
          ? "That feature is unavailable in the selected snapshot. Search again to use current data."
        : state === "ready" && results.length === 0
          ? unavailableKinds.length > 0
            ? `No matches in available datasets. ${unavailableKinds.length} source${unavailableKinds.length === 1 ? " is" : "s are"} unavailable.`
            : "No matching WaterGeo features."
          : state === "ready"
            ? `${results.length} result${results.length === 1 ? "" : "s"}${truncated ? "; refine your search to see more" : ""}.`
            : "Enter at least two characters.";

  return (
    <div className="product-search" role="search">
      <label htmlFor="watergeo-search">Search WaterGeo</label>
      <div className="search-input-wrap">
        <span aria-hidden="true">⌕</span>
        <input
          id="watergeo-search"
          type="search"
          value={term}
          placeholder="Station, Water Body, reservoir or company"
          autoComplete="off"
          aria-describedby={statusId}
          aria-expanded={open}
          aria-controls="watergeo-search-results"
          onChange={(event) => {
            const value = event.target.value;
            setTerm(value);
            if (value.trim().length < 2) {
              setResults([]);
              setTruncated(false);
              setUnavailableKinds([]);
              setState("idle");
              setOpen(false);
            }
          }}
          onFocus={() => { if (term.trim().length >= 2) setOpen(true); }}
          onKeyDown={(event) => { if (event.key === "Escape") setOpen(false); }}
        />
      </div>
      <span id={statusId} className="visually-hidden" role="status">{status}</span>
      {open && (
        <div id="watergeo-search-results" className="search-results" aria-label="WaterGeo search results">
          <p className={state === "error" || state === "selection-error" ? "state-error" : "search-status"}>{status}</p>
          {Array.from(groups, ([kind, items]) => (
            <section key={kind} aria-labelledby={`search-group-${kind}`}>
              <h2 id={`search-group-${kind}`}>{KIND_LABELS[kind]}</h2>
              <ul>
                {items.map((result) => (
                  <li key={`${result.kind}:${result.identity}`}>
                    <button type="button" onClick={() => void choose(result)} disabled={state === "selecting"}>
                      <strong>{result.label}</strong>
                      <span>{result.context} · {result.publisher}</span>
                    </button>
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      )}
    </div>
  );
}
