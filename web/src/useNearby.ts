import { useEffect, useRef, useState } from "react";

import { ApiError, api } from "./api";
import type {
  DatasetProvenance,
  BathingWater,
  FloodArea,
  HydrologyStation,
  RainfallStation,
  LayerId,
  Reservoir,
  SamplingPoint,
  ThamesAlertStatus,
  ThamesDischargeSite,
} from "./types";

export interface ViewportQuery {
  longitude: number;
  latitude: number;
  radiusM: number;
}

interface NearbyState {
  hydrology: HydrologyStation[];
  rainfall: RainfallStation[];
  bathingWaters: BathingWater[];
  floodWarnings: FloodArea[];
  waterQuality: SamplingPoint[];
  reservoirs: Reservoir[];
  thamesDischarge: ThamesDischargeSite[];
  provenance: Partial<Record<LayerId, DatasetProvenance>>;
  loading: Set<LayerId>;
  errors: Partial<Record<LayerId, string>>;
}

const EMPTY: NearbyState = {
  hydrology: [],
  rainfall: [],
  bathingWaters: [],
  floodWarnings: [],
  waterQuality: [],
  reservoirs: [],
  thamesDischarge: [],
  provenance: {},
  loading: new Set(),
  errors: {},
};

function message(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 503) return "This dataset is currently unavailable from the WaterGeo service.";
    if (error.status === 422) return "The map request was outside the supported bounds.";
  }
  return "This layer could not be loaded.";
}

export function useNearby(
  query: ViewportQuery,
  layers: Set<LayerId>,
  delayMs = 350,
  thamesFilters: { status?: ThamesAlertStatus; recent?: boolean } = {},
): NearbyState {
  const [state, setState] = useState<NearbyState>(EMPTY);
  const generation = useRef(0);
  const waterQualitySnapshot = useRef<string | undefined>(undefined);
  const reservoirSnapshot = useRef<string | undefined>(undefined);

  useEffect(() => {
    if (query.radiusM <= 0) return;
    const current = ++generation.current;
    const controller = new AbortController();
    const requested = (["hydrology", "rainfall", "water-quality", "flood-warnings", "bathing-waters", "reservoirs", "thames-discharge"] as const).filter((layer) =>
      layers.has(layer),
    );
    const timer = window.setTimeout(() => {
      setState((previous) => ({
        ...previous,
        hydrology: layers.has("hydrology") ? previous.hydrology : [],
        rainfall: layers.has("rainfall") ? previous.rainfall : [],
        bathingWaters: layers.has("bathing-waters") ? previous.bathingWaters : [],
        floodWarnings: layers.has("flood-warnings") ? previous.floodWarnings : [],
        waterQuality: layers.has("water-quality") ? previous.waterQuality : [],
        reservoirs: layers.has("reservoirs") ? previous.reservoirs : [],
        thamesDischarge: layers.has("thames-discharge") ? previous.thamesDischarge : [],
        loading: new Set(requested),
        errors: {},
      }));
      const jobs = requested.map(async (layer) => {
        if (layer === "hydrology") {
          const page = await api.hydrologyNear(
            query.longitude,
            query.latitude,
            Math.min(query.radiusM, 100_000),
            controller.signal,
          );
          return { layer, items: page.items, dataset: page.dataset } as const;
        }
        if (layer === "rainfall") {
          const page = await api.rainfallNear(
            query.longitude,
            query.latitude,
            Math.min(query.radiusM, 100_000),
            controller.signal,
          );
          return { layer, items: page.items, dataset: page.dataset } as const;
        }
        if (layer === "bathing-waters") {
          const page = await api.bathingWatersNear(
            query.longitude,
            query.latitude,
            Math.min(query.radiusM, 200_000),
            controller.signal,
          );
          return { layer, items: page.items, dataset: page.dataset } as const;
        }
        if (layer === "flood-warnings") {
          const page = await api.floodAreas(controller.signal);
          return { layer, items: page.items, dataset: page.dataset } as const;
        }
        if (layer === "water-quality") {
          const page = await api.waterQualityNear(
            query.longitude,
            query.latitude,
            Math.min(query.radiusM, 100_000),
            controller.signal,
            waterQualitySnapshot.current,
          );
          if (!controller.signal.aborted && current === generation.current) waterQualitySnapshot.current ??= page.dataset.snapshot_id;
          return { layer, items: page.items, dataset: page.dataset } as const;
        }
        if (layer === "reservoirs") {
          const page = await api.reservoirsNear(
            query.longitude,
            query.latitude,
            Math.min(query.radiusM, 200_000),
            controller.signal,
            reservoirSnapshot.current,
          );
          if (!controller.signal.aborted && current === generation.current) reservoirSnapshot.current ??= page.dataset.snapshot_id;
          return { layer, items: page.items, dataset: page.dataset } as const;
        }
        const page = await api.thamesDischargeNear(
          query.longitude,
          query.latitude,
          Math.min(query.radiusM, 200_000),
          controller.signal,
          undefined,
          thamesFilters.status,
          thamesFilters.recent,
        );
        return { layer, items: page.items, dataset: page.dataset } as const;
      });

      void Promise.allSettled(jobs).then((results) => {
        if (controller.signal.aborted || current !== generation.current) return;
        setState((previous) => {
          const next: NearbyState = {
            ...previous,
            loading: new Set(),
            errors: {},
            provenance: { ...previous.provenance },
          };
          results.forEach((result, index) => {
            const layer = requested[index];
            if (layer === undefined) return;
            if (result.status === "rejected") {
              if (result.reason instanceof DOMException && result.reason.name === "AbortError") return;
              next.errors[layer] = message(result.reason);
              if (result.reason instanceof ApiError && result.reason.message.includes("snapshot")) {
                if (layer === "water-quality") {
                  waterQualitySnapshot.current = undefined;
                  next.waterQuality = [];
                }
                if (layer === "reservoirs") {
                  reservoirSnapshot.current = undefined;
                  next.reservoirs = [];
                }
                delete next.provenance[layer];
              }
              return;
            }
            next.provenance[layer] = result.value.dataset;
            if (layer === "hydrology") next.hydrology = result.value.items as HydrologyStation[];
            if (layer === "rainfall") next.rainfall = result.value.items as RainfallStation[];
            if (layer === "bathing-waters") {
              next.bathingWaters = result.value.items as BathingWater[];
            }
            if (layer === "flood-warnings") {
              next.floodWarnings = result.value.items as FloodArea[];
            }
            if (layer === "water-quality") {
              next.waterQuality = result.value.items as SamplingPoint[];
            }
            if (layer === "reservoirs") next.reservoirs = result.value.items as Reservoir[];
            if (layer === "thames-discharge") {
              next.thamesDischarge = result.value.items as ThamesDischargeSite[];
            }
          });
          return next;
        });
      });
    }, delayMs);

    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [delayMs, layers, query.latitude, query.longitude, query.radiusM, thamesFilters.recent, thamesFilters.status]);

  return state;
}
