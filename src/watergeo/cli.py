"""Read-only command line interface for a configured WaterGeo HTTP server."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable, Iterable
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from watergeo.client import (
    WaterGeoAPIError,
    WaterGeoClient,
    WaterGeoConfigurationError,
    WaterGeoResponseError,
    WaterGeoTransportError,
)

EXIT_TRANSPORT = 3
EXIT_API = 4
EXIT_RESPONSE = 5

Action = Callable[[WaterGeoClient, argparse.Namespace], object]


def _uuid(value: str | None) -> UUID | None:
    return UUID(value) if value else None


def _datetime(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _jsonable(value: object) -> object:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, Iterable) and not isinstance(value, (str, bytes, dict)):
        return [_jsonable(item) for item in value]
    return value


def _emit(value: object, *, pretty: bool) -> None:
    separators = None if pretty else (",", ":")
    print(
        json.dumps(
            _jsonable(value),
            ensure_ascii=False,
            indent=2 if pretty else None,
            separators=separators,
            sort_keys=True,
        )
    )


def _set_action(parser: argparse.ArgumentParser, action: Action) -> None:
    parser.set_defaults(action=action)


def _pagination(parser: argparse.ArgumentParser, *, all_mode: bool = True) -> None:
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--after-id")
    parser.add_argument("--snapshot-id")
    if all_mode:
        parser.add_argument("--all", action="store_true", dest="all_pages")
        parser.add_argument("--max-pages", type=int, default=1000)
        parser.add_argument("--max-records", type=int, default=100000)


def _near(parser: argparse.ArgumentParser, default_radius: float) -> None:
    parser.add_argument("--lon", type=float, required=True)
    parser.add_argument("--lat", type=float, required=True)
    parser.add_argument("--radius-m", type=float, default=default_radius)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--snapshot-id")


def _detail(parser: argparse.ArgumentParser, identity: str) -> None:
    parser.add_argument(identity)
    parser.add_argument("--snapshot-id")


def _collection_action(page: Callable[..., object], iterator: Callable[..., object]) -> Action:
    def action(client: WaterGeoClient, args: argparse.Namespace) -> object:
        if args.all_pages:
            return iterator(
                client,
                page_size=args.limit,
                max_pages=args.max_pages,
                max_records=args.max_records,
            )
        return page(
            client,
            limit=args.limit,
            after_id=args.after_id,
            snapshot_id=_uuid(args.snapshot_id),
        )

    return action


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="watergeo", description="Query a WaterGeo UK HTTP API")
    parser.add_argument(
        "--base-url",
        default=os.environ.get("WATERGEO_BASE_URL"),
        help="WaterGeo server URL (or set WATERGEO_BASE_URL)",
    )
    parser.add_argument("--pretty", action="store_true", help="indent JSON output")
    domains = parser.add_subparsers(dest="domain", required=True)

    health = domains.add_parser("health", help="check process liveness")
    _set_action(health, lambda client, _: client.health())
    ready = domains.add_parser("ready", help="check database readiness")
    _set_action(ready, lambda client, _: client.readiness())

    sources = domains.add_parser("sources", help="source availability and freshness")
    sources_commands = sources.add_subparsers(dest="command", required=True)
    status = sources_commands.add_parser("status")
    _set_action(status, lambda client, _: client.source_status())

    water_supply = domains.add_parser("water-supply", help="Ofwat water-supply areas")
    ws = water_supply.add_subparsers(dest="command", required=True)
    dataset = ws.add_parser("dataset")
    _set_action(dataset, lambda client, _: client.water_supply_dataset())
    areas = ws.add_parser("areas")
    areas.add_argument("--limit", type=int, default=50)
    areas.add_argument("--after-id", type=int, default=0)
    areas.add_argument("--all", action="store_true", dest="all_pages")
    areas.add_argument("--max-pages", type=int, default=1000)
    areas.add_argument("--max-records", type=int, default=100000)
    _set_action(
        areas,
        lambda client, args: (
            client.iter_water_supply_areas(
                page_size=args.limit, max_pages=args.max_pages, max_records=args.max_records
            )
            if args.all_pages
            else client.water_supply_areas(limit=args.limit, after_id=args.after_id)
        ),
    )
    at_point = ws.add_parser("at-point")
    at_point.add_argument("--lon", type=float, required=True)
    at_point.add_argument("--lat", type=float, required=True)
    at_point.add_argument("--limit", type=int, default=50)
    at_point.add_argument("--after-id", type=int, default=0)
    _set_action(
        at_point,
        lambda client, args: client.water_supply_areas_at_point(
            args.lon, args.lat, limit=args.limit, after_id=args.after_id
        ),
    )
    area = ws.add_parser("area")
    area.add_argument("source_id", type=int)
    _set_action(area, lambda client, args: client.water_supply_area(args.source_id))
    geometry = ws.add_parser("geometry")
    geometry.add_argument("source_id", type=int)
    _set_action(geometry, lambda client, args: client.water_supply_geometry(args.source_id))

    hydrology = domains.add_parser("hydrology", help="EA Hydrology")
    hy = hydrology.add_subparsers(dest="command", required=True)
    dataset = hy.add_parser("dataset")
    _set_action(dataset, lambda client, _: client.hydrology_dataset())
    stations = hy.add_parser("stations")
    _pagination(stations)
    _set_action(
        stations,
        _collection_action(
            lambda client, **kw: client.hydrology_stations(**kw),
            lambda client, **kw: client.iter_hydrology_stations(**kw),
        ),
    )
    near = hy.add_parser("near")
    _near(near, 10_000)
    _set_action(
        near,
        lambda client, args: client.hydrology_stations_near(
            args.lon, args.lat, radius_m=args.radius_m, limit=args.limit
        ),
    )
    station = hy.add_parser("station")
    station.add_argument("station_id")
    _set_action(station, lambda client, args: client.hydrology_station(args.station_id))
    history = hy.add_parser("history")
    history.add_argument("retrieval_id")
    history.add_argument("--limit", type=int, default=100)
    history.add_argument("--after")
    history.add_argument("--all", action="store_true", dest="all_pages")
    history.add_argument("--max-pages", type=int, default=1000)
    history.add_argument("--max-records", type=int, default=100000)
    _set_action(
        history,
        lambda client, args: (
            client.iter_hydrology_history(
                args.retrieval_id,
                page_size=args.limit,
                max_pages=args.max_pages,
                max_records=args.max_records,
            )
            if args.all_pages
            else client.hydrology_history(
                args.retrieval_id, limit=args.limit, after=_datetime(args.after)
            )
        ),
    )

    catchments = domains.add_parser("catchments", help="EA Catchment Data Explorer")
    ca = catchments.add_subparsers(dest="command", required=True)
    dataset = ca.add_parser("dataset")
    _set_action(dataset, lambda client, _: client.catchment_dataset())
    resources = {
        "river-basin-districts": (
            WaterGeoClient.river_basin_districts,
            WaterGeoClient.iter_river_basin_districts,
            WaterGeoClient.river_basin_district,
        ),
        "management-catchments": (
            WaterGeoClient.management_catchments,
            WaterGeoClient.iter_management_catchments,
            WaterGeoClient.management_catchment,
        ),
        "operational-catchments": (
            WaterGeoClient.operational_catchments,
            WaterGeoClient.iter_operational_catchments,
            WaterGeoClient.operational_catchment,
        ),
        "water-bodies": (
            WaterGeoClient.water_bodies,
            WaterGeoClient.iter_water_bodies,
            WaterGeoClient.water_body,
        ),
    }
    for name, (page_method, iterator_method, detail_method) in resources.items():
        command = ca.add_parser(name)
        _pagination(command)
        command.add_argument("--id", dest="entity_id")

        def catchment_action(
            client: WaterGeoClient,
            args: argparse.Namespace,
            *,
            page_method: Callable[..., object] = page_method,
            iterator_method: Callable[..., object] = iterator_method,
            detail_method: Callable[..., object] = detail_method,
        ) -> object:
            if args.entity_id:
                return detail_method(client, args.entity_id)
            if args.all_pages:
                return iterator_method(
                    client,
                    page_size=args.limit,
                    max_pages=args.max_pages,
                    max_records=args.max_records,
                )
            return page_method(
                client,
                limit=args.limit,
                after_id=args.after_id,
                snapshot_id=_uuid(args.snapshot_id),
            )

        _set_action(command, catchment_action)
    body_geometry = ca.add_parser("water-body-geometry")
    body_geometry.add_argument("entity_id")
    _set_action(body_geometry, lambda client, args: client.water_body_geometry(args.entity_id))

    quality = domains.add_parser("water-quality", help="EA Water Quality Explorer")
    wq = quality.add_subparsers(dest="command", required=True)
    dataset = wq.add_parser("dataset")
    dataset.add_argument("--snapshot-id")
    _set_action(
        dataset,
        lambda client, args: client.water_quality_dataset(snapshot_id=_uuid(args.snapshot_id)),
    )
    points = wq.add_parser("sampling-points")
    _pagination(points)
    _set_action(
        points,
        _collection_action(
            lambda client, **kw: client.water_quality_sampling_points(**kw),
            lambda client, **kw: client.iter_water_quality_sampling_points(**kw),
        ),
    )
    near = wq.add_parser("near")
    _near(near, 10_000)
    _set_action(
        near,
        lambda client, args: client.water_quality_sampling_points_near(
            args.lon,
            args.lat,
            radius_m=args.radius_m,
            limit=args.limit,
            snapshot_id=_uuid(args.snapshot_id),
        ),
    )
    point = wq.add_parser("sampling-point")
    _detail(point, "sampling_point_id")
    _set_action(
        point,
        lambda client, args: client.water_quality_sampling_point(
            args.sampling_point_id, snapshot_id=_uuid(args.snapshot_id)
        ),
    )
    observations = wq.add_parser("observations")
    observations.add_argument("retrieval_id")
    observations.add_argument("--limit", type=int, default=100)
    observations.add_argument("--after-id")
    observations.add_argument("--all", action="store_true", dest="all_pages")
    observations.add_argument("--max-pages", type=int, default=1000)
    observations.add_argument("--max-records", type=int, default=100000)
    _set_action(
        observations,
        lambda client, args: (
            client.iter_water_quality_observations(
                args.retrieval_id,
                page_size=args.limit,
                max_pages=args.max_pages,
                max_records=args.max_records,
            )
            if args.all_pages
            else client.water_quality_observations(
                args.retrieval_id, limit=args.limit, after_id=args.after_id
            )
        ),
    )

    severn = domains.add_parser("severn-trent", help="Severn Trent reservoir levels")
    st = severn.add_subparsers(dest="command", required=True)
    dataset = st.add_parser("dataset")
    dataset.add_argument("--snapshot-id")
    _set_action(
        dataset,
        lambda client, args: client.reservoir_level_dataset(snapshot_id=_uuid(args.snapshot_id)),
    )
    reservoirs = st.add_parser("reservoirs")
    _pagination(reservoirs)
    _set_action(
        reservoirs,
        _collection_action(
            lambda client, **kw: client.reservoirs(**kw),
            lambda client, **kw: client.iter_reservoirs(**kw),
        ),
    )
    near = st.add_parser("near")
    _near(near, 50_000)
    _set_action(
        near,
        lambda client, args: client.reservoirs_near(
            args.lon,
            args.lat,
            radius_m=args.radius_m,
            limit=args.limit,
            snapshot_id=_uuid(args.snapshot_id),
        ),
    )
    reservoir = st.add_parser("reservoir")
    _detail(reservoir, "reservoir_id")
    _set_action(
        reservoir,
        lambda client, args: client.reservoir(
            args.reservoir_id, snapshot_id=_uuid(args.snapshot_id)
        ),
    )
    readings = st.add_parser("readings")
    readings.add_argument("reservoir_id")
    readings.add_argument("--limit", type=int, default=100)
    readings.add_argument("--after")
    readings.add_argument("--snapshot-id")
    readings.add_argument("--all", action="store_true", dest="all_pages")
    readings.add_argument("--max-pages", type=int, default=1000)
    readings.add_argument("--max-records", type=int, default=100000)
    _set_action(
        readings,
        lambda client, args: (
            client.iter_reservoir_readings(
                args.reservoir_id,
                page_size=args.limit,
                max_pages=args.max_pages,
                max_records=args.max_records,
            )
            if args.all_pages
            else client.reservoir_readings(
                args.reservoir_id,
                limit=args.limit,
                after=_datetime(args.after),
                snapshot_id=_uuid(args.snapshot_id),
            )
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.base_url:
        parser.error("--base-url or WATERGEO_BASE_URL is required")
    try:
        with WaterGeoClient(args.base_url) as client:
            _emit(args.action(client, args), pretty=args.pretty)
    except WaterGeoTransportError as error:
        print(f"watergeo: transport error: {error}", file=sys.stderr)
        return EXIT_TRANSPORT
    except WaterGeoAPIError as error:
        print(f"watergeo: API error: {error}", file=sys.stderr)
        return EXIT_API
    except (WaterGeoConfigurationError, WaterGeoResponseError, ValueError) as error:
        print(f"watergeo: response/configuration error: {error}", file=sys.stderr)
        return EXIT_RESPONSE
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
