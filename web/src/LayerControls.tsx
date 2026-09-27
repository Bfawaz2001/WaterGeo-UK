import type { LayerId } from "./types";

const LAYERS: Array<{ id: LayerId; label: string; description: string; group: "changing" | "context" }> = [
  { id: "hydrology", label: "Hydrology stations", description: "Latest accepted EA snapshot", group: "changing" },
  {
    id: "water-quality",
    label: "Water Quality sampling points",
    description: "Publisher metadata, not results", group: "changing",
  },
  {
    id: "reservoirs",
    label: "Severn Trent reservoirs",
    description: "Dated 2025 publisher edition", group: "changing",
  },
  {
    id: "thames-discharge",
    label: "Thames Water discharge monitors",
    description: "Near-real-time publisher indications", group: "changing",
  },
  {
    id: "water-supply",
    label: "Water-supply lookup",
    description: "Click map; one reviewed area at a time", group: "context",
  },
];

interface Props {
  active: Set<LayerId>;
  counts: Partial<Record<LayerId, number>>;
  loading: Set<LayerId>;
  errors: Partial<Record<LayerId, string>>;
  onToggle: (layer: LayerId) => void;
}

export function LayerControls({ active, counts, loading, errors, onToggle }: Props) {
  return (
    <section className="panel-section" aria-labelledby="layers-heading">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Map contents</p>
          <h2 id="layers-heading">Layers</h2>
        </div>
        <span className="bounded-badge">Bounded</span>
      </div>
      {(["changing", "context"] as const).map((group) => <div className="layer-group" key={group}>
        <h3>{group === "changing" ? "Operational and observed" : "Geographic context"}</h3>
        <div className="layer-list">
        {LAYERS.filter((layer) => layer.group === group).map((layer) => (
          <label className={`layer-option layer-${layer.id}`} key={layer.id}>
            <input
              type="checkbox"
              checked={active.has(layer.id)}
              onChange={() => onToggle(layer.id)}
            />
            <span className="layer-swatch" aria-hidden="true" />
            <span>
              <strong>{layer.label}</strong>
              <small>{layer.description}</small>
              {active.has(layer.id) && layer.id !== "water-supply" && (
                <small className={errors[layer.id] ? "state-error" : "state-detail"}>
                  {loading.has(layer.id)
                    ? `Updating nearby results… ${counts[layer.id] ?? 0} previous points retained until ready.`
                    : errors[layer.id] ?? `${counts[layer.id] ?? 0} nearest results shown (maximum 100)`}
                </small>
              )}
            </span>
          </label>
        ))}
        </div>
      </div>)}
      <p className="interpretation-note">
        Layers are independent publisher datasets. Spatial overlap does not establish a relationship.
      </p>
    </section>
  );
}
