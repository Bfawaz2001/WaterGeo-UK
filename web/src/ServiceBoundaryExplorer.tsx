import { verifiedJson } from "./serviceBundleIntegrity";
import { useEffect, useMemo, useState } from "react";

interface Area {
  boundary_id: string; service: string; company_id: string; company_name: string;
  source_id: number; COMPANY: string; Acronym: string; AreaServed: string;
  AreaType: string; CoType: string; WARNINGS: string; source_valid: boolean;
  source_validity: string; geometry_file: string; source_fields_json: string;
}
interface Manifest {
  product_version: string;
  files: Record<string, { bytes: number; sha256: string }>;
  datasets: Record<string, { dataset: string; sha256: string; attribution: string; validation: { record_count: number } }>;
}
interface Preview { id: string; geometry: { type: string; coordinates: number[][][] | number[][][][] } }
interface Index { areas: Area[]; services: { service: string; area_count: number }[] }


async function verifiedAsset<T>(base: string, path: string, manifest: Manifest, signal: AbortSignal): Promise<T> {
  const evidence = manifest.files[path];
  if (!evidence || evidence.bytes > 10 * 1024 * 1024 || /(^\/|\.\.|\\)/u.test(path)) throw new Error("Invalid asset");
  return verifiedJson<T>(await fetch(`${base}/${path}`, { signal, redirect: "error" }), evidence);
}

function outlines(features: Preview[]) {
  const rings = features.flatMap((feature) => feature.geometry.type === "Polygon"
    ? feature.geometry.coordinates as number[][][]
    : (feature.geometry.coordinates as number[][][][]).flat());
  const points = rings.flat();
  if (!points.length) return null;
  const xs = points.map((point) => point[0]!); const ys = points.map((point) => -point[1]!);
  const minX = xs.reduce((a, b) => Math.min(a, b)); const minY = ys.reduce((a, b) => Math.min(a, b));
  const width = Math.max(0.005, xs.reduce((a, b) => Math.max(a, b)) - minX);
  const height = Math.max(0.005, ys.reduce((a, b) => Math.max(a, b)) - minY);
  return { viewBox: `${minX - width * .05} ${minY - height * .05} ${width * 1.1} ${height * 1.1}`,
    paths: rings.map((ring) => ring.map((p, i) => `${i ? "L" : "M"}${p[0]},${-p[1]!}`).join(" ") + "Z") };
}

export function ServiceBoundaryExplorer({ base, manifestHash }: { base: string; manifestHash: string }) {
  const [manifest, setManifest] = useState<Manifest>(); const [index, setIndex] = useState<Index>();
  const [service, setService] = useState("water-supply"); const [company, setCompany] = useState("");
  const [preview, setPreview] = useState<Preview[]>([]); const [selected, setSelected] = useState<Area>();
  const [error, setError] = useState(""); const [verified, setVerified] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    void (async () => {
      if (!base.startsWith("/") || /[?#\\]/u.test(base) || base.startsWith("//") || base.includes("..")) throw new Error("Invalid bundle path");
      const response = await fetch(`${base}/manifest.json`, { signal: controller.signal, redirect: "error" });
      if (!response.ok) throw new Error("Bundle unavailable");
      const metadata = await verifiedJson<Manifest>(response, { sha256: manifestHash });
      if (metadata.product_version !== "watergeo-ofwat-services-v1") throw new Error("Unsupported bundle");
      const inventory = await verifiedAsset<Index>(base, "index.json", metadata, controller.signal);
      if (inventory.services.length !== 2 || new Set(inventory.services.map((s) => s.service)).size !== 2) throw new Error("Missing services");
      for (const edition of inventory.services) {
        const areas = inventory.areas.filter((area) => area.service === edition.service);
        if (areas.length !== edition.area_count || new Set(areas.map((a) => a.boundary_id)).size !== areas.length ||
          areas.length !== metadata.datasets[edition.service]?.validation.record_count ||
          areas.some((a) => !a.company_id || a.boundary_id !== `${metadata.datasets[edition.service]!.dataset}:${metadata.datasets[edition.service]!.sha256}:${a.source_id}`)) throw new Error("Incomplete inventory");
      }
      if (!controller.signal.aborted) { setManifest(metadata); setIndex(inventory); }
    })().catch(() => { if (!controller.signal.aborted) setError("The service bundle could not be verified."); });
    return () => controller.abort();
  }, [base, manifestHash]);
  useEffect(() => {
    if (!manifest) return;
    const controller = new AbortController();
    void verifiedAsset<{ features: Preview[] }>(base, `${service}-overview.geojson`, manifest, controller.signal)
      .then((layer) => { if (!controller.signal.aborted) setPreview(layer.features); })
      .catch(() => { if (!controller.signal.aborted) setError("The service overview could not be verified."); });
    return () => controller.abort();
  }, [base, manifest, service]);
  const companies = useMemo(() => [...new Map(index?.areas.filter((a) => a.service === service).map((a) => [a.company_id, a.company_name])).entries()].sort((a, b) => a[1].localeCompare(b[1])), [index, service]);
  const areas = index?.areas.filter((a) => a.service === service && a.company_id === company) ?? [];
  const ids = new Set(areas.map((area) => area.boundary_id));
  const drawing = outlines(preview.filter((feature) => ids.has(feature.id)));
  useEffect(() => {
    if (!selected || !manifest) return;
    const controller = new AbortController();
    void verifiedAsset<{ id: string }>(base, selected.geometry_file, manifest, controller.signal).then((feature) => {
      if (feature.id !== selected.boundary_id) throw new Error("Feature identity changed");
      if (!controller.signal.aborted) setVerified(feature.id);
    }).catch(() => { if (!controller.signal.aborted) setError("The individual area could not be verified."); });
    return () => controller.abort();
  }, [base, manifest, selected]);
  return <section className="panel-section" aria-label="Water and sewerage service boundaries">
    <h2>Explore service boundaries</h2>
    <p>April 2024 publisher areas, with individual NAVs retained. These dated analytical boundaries are not legal supplier records.</p>
    <label>Service<select aria-label="Service" value={service} onChange={(event) => { setPreview([]); setVerified(""); setService(event.target.value); setCompany(""); setSelected(undefined); setError(""); }}>
      <option value="water-supply">Water supply</option><option value="sewerage">Sewerage</option>
    </select></label>
    <label>Undertaker<select aria-label="Undertaker" value={company} onChange={(event) => { setCompany(event.target.value); setSelected(undefined); }}>
      <option value="">Choose an undertaker</option>{companies.map(([id, name]) => <option key={id} value={id}>{name}</option>)}
    </select></label>
    {error && <p role="alert">{error}</p>}
    {company && <><p>{areas.length} verified associated areas · {areas.filter((a) => !a.source_valid).length} quarantined from coverage analysis</p>
      {drawing && <svg viewBox={drawing.viewBox} role="img" aria-label="All company areas, simplified overview" style={{ width: "100%", height: 260 }}>
        {drawing.paths.map((path, i) => <path key={i} d={path} fill="none" stroke="#167d6b" strokeWidth="1" vectorEffect="non-scaling-stroke" />)}
      </svg>}
      <p className="caveat">Simplified outlines are for display only. Invalid publisher features remain visible as outlines and require geometry review before coverage analysis.</p>
      <ul className="result-list company-area-list">{areas.map((area) => <li key={area.boundary_id}><button type="button" onClick={() => { setVerified(""); setSelected(area); }}>
        <strong>{area.AreaServed || `Area ${area.source_id}`}</strong><small>{area.AreaType} · {area.Acronym} · ID {area.source_id}{!area.source_valid && " · Invalid source geometry"}</small>
      </button></li>)}</ul></>}
    {selected && <details open><summary>{selected.AreaServed} — source attributes</summary>
      <p>{selected.source_validity}</p>{selected.WARNINGS && <p>{selected.WARNINGS}</p>}
      <pre style={{ whiteSpace: "pre-wrap" }}>{JSON.stringify(JSON.parse(selected.source_fields_json), null, 2)}</pre>
      {verified === selected.boundary_id && <a href={`${base}/${selected.geometry_file}`} download>Download verified area GeoJSON</a>}
    </details>}
    {manifest && <p className="caveat">{manifest.datasets[service]?.attribution}</p>}
  </section>;
}
