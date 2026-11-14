import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";
import { hydrologyMeasureLabel, periodLabel } from "./explorerPresentation";
import {
  collectHistory,
  historyCsv,
  instant,
  validateDiscovery,
  HISTORY_VERSION,
} from "./historicalObservations";
import type {
  HistoryEdition,
  HistoryObservation,
} from "./historicalObservations";
import type { HydrologyMeasure } from "./types";
import { MetadataValue } from "./MetadataValue";
import { TrendChart } from "./TrendChart";

export function HydrologyHistory({
  measures,
  station,
  metadataSnapshot,
}: {
  measures: HydrologyMeasure[];
  station: string;
  metadataSnapshot?: string;
}) {
  const [measureId, setMeasureId] = useState(measures[0]?.measure_id ?? "");
  const measure = measures.find((row) => row.measure_id === measureId);
  return (
    <div className="hydrology-history">
      <label>
        Historical measurement{" "}
        <select
          value={measureId}
          onChange={(event) => setMeasureId(event.target.value)}
        >
          {measures.map((row, index) => (
            <option value={row.measure_id} key={row.measure_id}>
              {hydrologyMeasureLabel(row, "history")} · {row.unit_name} ·{" "}
              {periodLabel(row.period)} · series {index + 1}
            </option>
          ))}
        </select>
      </label>
      {measure ? (
        <MeasureHistory
          key={measureId}
          measure={measure}
          station={station}
          metadataSnapshot={metadataSnapshot}
        />
      ) : (
        <p>No published measurement series at this station.</p>
      )}
    </div>
  );
}
function MeasureHistory({
  measure,
  station,
  metadataSnapshot,
}: {
  measure: HydrologyMeasure;
  station: string;
  metadataSnapshot: string | undefined;
}) {
  const [editions, setEditions] = useState<HistoryEdition[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [selection, setSelection] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(true);
  const request = useRef<AbortController | null>(null);
  const mounted = useRef(false);
  const load = useCallback(
    async (after?: string, previous: HistoryEdition[] = []) => {
      request.current?.abort();
      const controller = new AbortController();
      request.current = controller;
      try {
        const page = await api.hydrologyRetrievals(
          measure.measure_id,
          controller.signal,
          after,
        );
        if (controller.signal.aborted || !mounted.current) return;
        validateDiscovery(page, measure.measure_id, previous);
        const combined = [...previous, ...page.items];
        setEditions(combined);
        setCursor(page.next_after_id);
        if (!after) setSelection(combined[0]?.retrieval_id ?? "");
      } catch (failure) {
        if (!controller.signal.aborted && mounted.current)
          setError(
            failure instanceof Error
              ? failure.message
              : "Historical discovery failed",
          );
      } finally {
        if (!controller.signal.aborted && mounted.current) setBusy(false);
      }
    },
    [measure.measure_id],
  );
  useEffect(() => {
    mounted.current = true;
    let disposed = false;
    // Schedule discovery after mount; cleanup also prevents a queued obsolete request.
    queueMicrotask(() => {
      if (!disposed) void load();
    });
    return () => {
      disposed = true;
      mounted.current = false;
      request.current?.abort();
    };
  }, [load]);
  const edition = editions.find((row) => row.retrieval_id === selection);
  return (
    <>
      {busy && <p role="status">Discovering stored historical retrievals…</p>}
      {error && (
        <p role="alert">
          Historical observations unavailable: {error}{" "}
          <button
            className="secondary-button"
            onClick={() => {
              setBusy(true);
              setError("");
              void load(cursor ?? undefined, cursor ? editions : []);
            }}
          >
            Retry discovery
          </button>
        </p>
      )}
      {!busy && !error && editions.length === 0 && (
        <p role="status">
          No stored historical data for this published measurement. An operator
          can accept a bounded retrieval; the browser does not download
          publisher readings.
        </p>
      )}
      {editions.length > 0 && (
        <label>
          Available retrieval{" "}
          <select
            value={selection}
            onChange={(event) => setSelection(event.target.value)}
          >
            {editions.map((row, index) => (
              <option key={row.retrieval_id} value={row.retrieval_id}>
                {new Date(row.requested_from).toLocaleString()} –{" "}
                {new Date(row.requested_to).toLocaleString()} · retrieved{" "}
                {new Date(row.retrieval_completed_at).toLocaleString()} ·{" "}
                {row.record_count} records · edition {index + 1}
              </option>
            ))}
          </select>
        </label>
      )}
      {cursor && (
        <p>
          {editions.length >= 200 ? (
            "Discovery is bounded to 200 retrievals for this measure."
          ) : (
            <button
              className="secondary-button"
              disabled={busy}
              onClick={() => {
                setBusy(true);
                setError("");
                void load(cursor, editions);
              }}
            >
              Load older retrievals
            </button>
          )}{" "}
          More stored editions exist.
        </p>
      )}
      {edition && (
        <RetrievalHistory
          key={edition.retrieval_id}
          edition={edition}
          measure={measure}
          station={station}
          metadataSnapshot={metadataSnapshot}
        />
      )}
    </>
  );
}
function RetrievalHistory({
  edition,
  measure,
  station,
  metadataSnapshot,
}: {
  edition: HistoryEdition;
  measure: HydrologyMeasure;
  station: string;
  metadataSnapshot: string | undefined;
}) {
  const [rows, setRows] = useState<HistoryObservation[] | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [days, setDays] = useState(0);
  const [tablePage, setTablePage] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    void collectHistory(edition, controller.signal).then(
      (result) => {
        if (!controller.signal.aborted) {
          setRows(result);
          setError("");
        }
      },
      (failure: unknown) => {
        if (!controller.signal.aborted)
          setError(
            failure instanceof Error
              ? failure.message
              : "Historical observations unavailable",
          );
      },
    );
    return () => controller.abort();
  }, [edition, attempt]);
  const end = instant(edition.requested_to);
  const start = days ? end - days * 86400_000 : instant(edition.requested_from);
  const displayed =
    rows?.filter((row) => instant(row.observed_at) >= start) ?? [];
  const reported = displayed.flatMap((row) =>
    row.value === null ? [] : [row.value],
  );
  const missing = displayed.length - reported.length;
  const gapCount =
    measure.period > 0
      ? displayed.filter(
          (row, index) =>
            index > 0 &&
            instant(row.observed_at) -
              instant(displayed[index - 1]!.observed_at) >
              measure.period * 1500,
        ).length
      : 0;
  const download = () => {
    const blob = new Blob(
      [historyCsv(edition, measure, displayed, metadataSnapshot)],
      { type: "text/csv;charset=utf-8" },
    );
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `hydrology-${edition.retrieval_id}${days ? `-${days}days` : ""}.csv`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  return (
    <section aria-label="Verified historical series">
      <p>
        {station} · {hydrologyMeasureLabel(measure, "history")} ·{" "}
        {measure.unit_name} · source period {periodLabel(measure.period)}
      </p>
      <p className="caveat">
        One historical retrieval edition, independently dated from the station
        metadata snapshot. Overlapping editions are never combined.
      </p>
      <details className="technical-disclosure">
        <summary>Historical retrieval provenance</summary>
        <dl>
          <dt>Unit and period metadata snapshot (separate from history)</dt>
          <dd>{metadataSnapshot ?? "Unspecified"}</dd>
          <dt>Exact publisher measure</dt>
          <dd>
            <code>{edition.measure_id}</code>
          </dd>
          <dt>Retrieval identity</dt>
          <dd>
            <code>{edition.retrieval_id}</code>
          </dd>
          <dt>Requested observation window (UTC)</dt>
          <dd>
            {edition.requested_from} – {edition.requested_to}
          </dd>
          <dt>WaterGeo retrieval completed</dt>
          <dd>{edition.retrieval_completed_at}</dd>
          <dt>Evidence SHA-256</dt>
          <dd>
            <code>{edition.content_sha256}</code>
          </dd>
          <dt>Normalized SHA-256</dt>
          <dd>
            <code>{edition.normalized_sha256}</code>
          </dd>
          <dt>Normalization</dt>
          <dd>{edition.normalization_version}</dd>
          <dt>Publisher and licence</dt>
          <dd>
            Environment Agency · {edition.licence} · © Environment Agency
            copyright and/or database right 2015. All rights reserved.
          </dd>
        </dl>
      </details>
      {error ? (
        <p role="alert">
          {error}{" "}
          {edition.normalization_version === HISTORY_VERSION && (
            <button
              className="secondary-button"
              onClick={() => {
                setError("");
                setAttempt(attempt + 1);
              }}
            >
              Retry observations
            </button>
          )}
        </p>
      ) : rows === null ? (
        <p role="status">Loading and verifying bounded observations…</p>
      ) : (
        <>
          <label>
            Observation window{" "}
            <select
              value={days}
              onChange={(event) => {
                setDays(Number(event.target.value));
                setTablePage(0);
              }}
            >
              <option value="0">Available recorded period</option>
              {[1, 7, 30].map((count) => (
                <option
                  key={count}
                  value={count}
                  disabled={
                    end - instant(edition.requested_from) < count * 86400_000
                  }
                >
                  {count === 1 ? "24 hours" : `${count} days`}
                  {end - instant(edition.requested_from) < count * 86400_000
                    ? " — unsupported by this retrieval"
                    : ""}
                </option>
              ))}
            </select>
          </label>
          <p role="status">
            Complete retrieval verified: {rows.length} stored records. Showing{" "}
            {displayed.length} accepted observations; {reported.length} reported
            numeric values and {missing} explicit missing observations.
          </p>
          <p>
            Windows end at the retrieval's requested end, rather than today.
            Requested coverage does not prove continuous measurements.
          </p>
          {displayed.length > 0 ? (
            <>
              <p>
                First observed: {displayed[0]!.observed_at}
                <br />
                Last observed: {displayed.at(-1)!.observed_at}
                {reported.length > 0 && (
                  <>
                    <br />
                    Minimum {Math.min(...reported)} · maximum{" "}
                    {Math.max(...reported)} {measure.unit_name}
                  </>
                )}
              </p>
              {(missing > 0 ||
                gapCount > 0 ||
                instant(displayed[0]!.observed_at) > start ||
                instant(displayed.at(-1)!.observed_at) < end) && (
                <p className="caveat">
                  Partial observation coverage: {missing} explicit missing
                  readings; {gapCount} intervals exceed 1.5 times the declared
                  period. Unreported readings are not invented; lines break at
                  missing readings and these gaps.
                </p>
              )}
              <TrendChart
                key={days}
                points={displayed}
                label={`${station} historical ${measure.parameter}`}
                unit={measure.unit_name}
                period={measure.period}
              />
              <button className="primary-button" onClick={download}>
                Download observations CSV
              </button>
              <p>
                CSV contains every accepted observation in the selected window,
                with quality and retrieval details.
              </p>
              <details>
                <summary>Observation table</summary>
                <div className="history-table">
                  <table>
                    <caption>
                      Accepted readings (UTC), page {tablePage + 1}
                    </caption>
                    <thead>
                      <tr>
                        <th>Observed</th>
                        <th>Value ({measure.unit_name})</th>
                        <th>Quality</th>
                        <th>Completeness</th>
                      </tr>
                    </thead>
                    <tbody>
                      {displayed
                        .slice(tablePage * 50, tablePage * 50 + 50)
                        .map((row) => (
                          <tr key={row.observed_at}>
                            <td>{row.observed_at}</td>
                            <td>{row.value ?? "Missing"}</td>
                            <td>
                              <MetadataValue
                                value={
                                  row.source_fields.quality ?? "Unspecified"
                                }
                              />
                            </td>
                            <td>
                              <MetadataValue
                                value={
                                  row.source_fields.completeness ??
                                  "Unspecified"
                                }
                              />
                            </td>
                          </tr>
                        ))}
                    </tbody>
                  </table>
                </div>
                <button
                  className="secondary-button"
                  disabled={tablePage === 0}
                  onClick={() => setTablePage(tablePage - 1)}
                >
                  Previous readings
                </button>
                <button
                  className="secondary-button"
                  disabled={(tablePage + 1) * 50 >= displayed.length}
                  onClick={() => setTablePage(tablePage + 1)}
                >
                  Next readings
                </button>
              </details>
            </>
          ) : (
            <p>
              No stored observations in this window. No values have been
              invented.
            </p>
          )}
          <p className="caveat">
            Historical values do not establish trends, flood risk or safety
            conditions.
          </p>
        </>
      )}
    </section>
  );
}
