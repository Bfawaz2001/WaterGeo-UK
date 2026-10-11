import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { ApiError, api } from "./api";
import type {
  AreaFeature,
  AreaSummary,
  CompanyPerformance,
  NationalDetail,
  WaterCompany,
  WaterCompanyFeatureCollection,
} from "./types";

interface Props {
  initialCompany?: string | null;
  selectedAreaId?: number | null;
  onShowCompany: (collection: WaterCompanyFeatureCollection) => void;
  onSelectArea: (feature: AreaFeature) => void;
  onSelectPerformance: (performance: NationalDetail<CompanyPerformance>) => void;
}

async function completeInventory(
  company: WaterCompany,
  snapshotId: string,
  signal: AbortSignal,
): Promise<AreaSummary[]> {
  const items: AreaSummary[] = [];
  let afterId: number | undefined;
  for (let pageNumber = 0; pageNumber < 20; pageNumber += 1) {
    const page = await api.waterSupplyCompanyAreas(
      company.company_acronym,
      snapshotId,
      afterId,
      signal,
    );
    if (
      page.snapshot_id !== snapshotId ||
      page.company.company_acronym !== company.company_acronym ||
      page.company.area_count !== company.area_count
    ) {
      throw new ApiError(503, "Water-supply company snapshot changed");
    }
    items.push(...page.items);
    if (page.next_after_id === null) break;
    if (page.next_after_id === afterId) {
      throw new ApiError(503, "Water-supply company pagination did not advance");
    }
    afterId = page.next_after_id;
  }
  if (
    items.length !== company.area_count ||
    new Set(items.map((item) => item.source_id)).size !== items.length
  ) {
    throw new ApiError(503, "Water-supply company inventory is incomplete");
  }
  return items;
}

async function companyPerformance(
  acronym: string,
  signal: AbortSignal,
): Promise<NationalDetail<CompanyPerformance> | null> {
  const companies = await api.companyPerformanceCompanies(signal);
  const match = companies.items.find(
    (candidate) => candidate.boundary_company_acronym === acronym,
  );
  return match
    ? await api.companyPerformance(match.company_id, companies.dataset.snapshot_id, signal)
    : null;
}

export function CompanyExplorer({
  initialCompany,
  selectedAreaId,
  onShowCompany,
  onSelectArea,
  onSelectPerformance,
}: Props) {
  const [companies, setCompanies] = useState<WaterCompany[]>([]);
  const [snapshotId, setSnapshotId] = useState<string>();
  const [selectedAcronym, setSelectedAcronym] = useState("");
  const [inventory, setInventory] = useState<AreaSummary[]>([]);
  const [collection, setCollection] = useState<WaterCompanyFeatureCollection>();
  const [performance, setPerformance] = useState<NationalDetail<CompanyPerformance> | null>();
  const [filter, setFilter] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>();
  const request = useRef<AbortController | undefined>(undefined);
  const initialApplied = useRef(false);

  useEffect(() => {
    const controller = new AbortController();
    void api.waterSupplyCompanies(controller.signal).then((page) => {
      setCompanies(page.items);
      setSnapshotId(page.snapshot_id);
    }).catch((reason: unknown) => {
      if (!(reason instanceof DOMException && reason.name === "AbortError")) {
        setError("The verified water-company index is currently unavailable.");
      }
    });
    return () => controller.abort();
  }, []);

  const selectCompany = useCallback(async (acronym: string) => {
    request.current?.abort();
    setSelectedAcronym(acronym);
    setInventory([]);
    setCollection(undefined);
    setPerformance(undefined);
    setFilter("");
    setError(undefined);
    setLoading(false);
    if (!acronym) return;
    const company = companies.find((candidate) => candidate.company_acronym === acronym);
    if (!company || !snapshotId) {
      setError("The selected company is not in this accepted boundary snapshot.");
      return;
    }
    const controller = new AbortController();
    request.current = controller;
    setLoading(true);
    try {
      const [areas, geometry] = await Promise.all([
        completeInventory(company, snapshotId, controller.signal),
        api.waterSupplyCompanyGeometry(acronym, snapshotId, controller.signal),
      ]);
      const areaIds = areas.map((area) => area.source_id);
      const geometryIds = geometry.features.map((feature) => feature.id);
      if (
        geometry.snapshot_id !== snapshotId ||
        geometry.company.company_acronym !== acronym ||
        geometry.company.area_count !== areas.length ||
        areaIds.some((identifier, index) => identifier !== geometryIds[index])
      ) {
        throw new ApiError(503, "Water-supply company geometry is incomplete");
      }
      if (!controller.signal.aborted) {
        setInventory(areas);
        setCollection(geometry);
        onShowCompany(geometry);
      }
      try {
        const result = await companyPerformance(acronym, controller.signal);
        if (!controller.signal.aborted) setPerformance(result);
      } catch (reason) {
        if (reason instanceof DOMException && reason.name === "AbortError") throw reason;
        if (!controller.signal.aborted) setPerformance(null);
      }
    } catch (reason) {
      if (!(reason instanceof DOMException && reason.name === "AbortError")) {
        setError("The complete company-area view could not be verified and was not shown.");
      }
    } finally {
      if (!controller.signal.aborted) setLoading(false);
    }
  }, [companies, onShowCompany, snapshotId]);

  useEffect(() => {
    if (initialApplied.current || !initialCompany || !companies.length || !snapshotId) return;
    initialApplied.current = true;
    void selectCompany(initialCompany);
  }, [companies, initialCompany, selectCompany, snapshotId]);

  useEffect(() => () => request.current?.abort(), []);

  const matchingAreas = useMemo(() => {
    const term = filter.trim().toLocaleLowerCase();
    return term
      ? inventory.filter((area) =>
          `${area.area_served ?? ""} ${area.source_id}`.toLocaleLowerCase().includes(term),
        )
      : inventory;
  }, [filter, inventory]);

  const featureById = useMemo(
    () => new Map(collection?.features.map((feature) => [feature.id, feature]) ?? []),
    [collection],
  );
  const selectedCompany = companies.find(
    (company) => company.company_acronym === selectedAcronym,
  );

  return (
    <section className="panel-section company-explorer" aria-labelledby="company-explorer-heading">
      <p className="eyebrow">Reviewed boundary edition</p>
      <h2 id="company-explorer-heading">Explore water companies</h2>
      <p>Choose a publisher acronym group to browse every associated area in the accepted April 2024 edition.</p>
      <label>
        Water company
        <select
          value={selectedAcronym}
          onChange={(event) => void selectCompany(event.target.value)}
        >
          <option value="">Choose a company</option>
          {companies.map((company) => (
            <option key={company.company_acronym} value={company.company_acronym}>
              {company.display_name} ({company.company_acronym})
            </option>
          ))}
        </select>
      </label>
      {loading && <p role="status">Loading and verifying the complete company inventory…</p>}
      {error && <p className="state-error" role="alert">{error}</p>}
      {collection && selectedCompany && (
        <>
          <p className="company-total" role="status"><strong>{inventory.length}</strong> verified area{inventory.length === 1 ? "" : "s"}</p>
          <button className="secondary-button" type="button" onClick={() => onShowCompany(collection)}>
            Show all company areas
          </button>
          <p className="caveat">Multiple exact publisher features are shown together. They are not dissolved into a legal or current company boundary.</p>
          <details><summary>Boundary snapshot identity</summary><code>{collection.snapshot_id}</code></details>
          {selectedCompany.publisher_labels.length > 1 && (
            <details><summary>Publisher name variants</summary><ul>{selectedCompany.publisher_labels.map((label) => <li key={label}>{label}</li>)}</ul></details>
          )}
          <label>
            Find an area in this company
            <input value={filter} onChange={(event) => setFilter(event.target.value)} placeholder="Area name or source ID" />
          </label>
          <p>{matchingAreas.length} of {inventory.length} verified areas shown.</p>
          <ul className="result-list company-area-list">
            {matchingAreas.map((area) => (
              <li key={area.source_id}>
                <button
                  type="button"
                  aria-current={selectedAreaId === area.source_id ? "true" : undefined}
                  onClick={() => {
                    const feature = featureById.get(area.source_id);
                    if (feature) onSelectArea(feature);
                  }}
                >
                  <strong>{area.area_served ?? `Area ${area.source_id}`}</strong>
                  <small>Publisher source ID {area.source_id}</small>
                </button>
              </li>
            ))}
          </ul>
          <section className="company-performance-summary" aria-labelledby="company-performance-summary-heading">
            <h3 id="company-performance-summary-heading">Company performance</h3>
            {performance === undefined && <p>Loading the separate company-level publication…</p>}
            {performance === null && <p>No reviewed company-performance crosswalk is available for this acronym.</p>}
            {performance && <>
              <p><strong>{performance.item.company_name}</strong> · {performance.item.measures.length} published measure rows</p>
              <button className="secondary-button" type="button" onClick={() => onSelectPerformance(performance)}>View company performance</button>
              <p className="caveat">These company-wide measures use their own publication and reporting periods. They do not describe an individual area polygon.</p>
            </>}
          </section>
        </>
      )}
    </section>
  );
}
