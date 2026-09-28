import type { LayerId } from "./types";
import { Icon, type IconName } from "./Icon";

const LAYERS: Array<{ id: LayerId; icon: IconName; label: string; description: string; group: "changing" | "context" }> = [
  { id: "hydrology", icon: "hydrology", label: "Hydrology stations", description: "Latest EA observations", group: "changing" },
  {
    id: "water-quality",
    icon: "water-quality", label: "Water Quality sampling points",
    description: "Publisher metadata, not results", group: "changing",
  },
  {
    id: "reservoirs",
    icon: "reservoirs", label: "Severn Trent reservoirs",
    description: "Dated 2025 publisher edition", group: "changing",
  },
  {
    id: "thames-discharge",
    icon: "thames-discharge", label: "Thames discharge monitors",
    description: "Near-real-time publisher indications", group: "changing",
  },
  {
    id: "water-supply",
    icon: "water-supply", label: "Water-supply lookup",
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
            <span className="layer-symbol" aria-hidden="true"><Icon name={layer.icon} /></span>
            <span className="layer-copy">
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
            <span className="switch-track" aria-hidden="true"><span /></span>
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
