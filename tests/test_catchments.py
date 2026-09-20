import json

import pytest

from watergeo.ingestion.catchments import (
    CatchmentError,
    parse_entity_page,
    parse_rbd_geojson,
)


def test_parse_operational_page_preserves_publisher_hierarchy() -> None:
    body = b"""
    <html>
      <head>
        <title>Example Rivers Operational Catchment | Catchment Data Explorer</title>
      </head>
      <body>
        <a href="/catchment-planning/v/c3-plan/RiverBasinDistrict/4">RBD</a>
        <a href="/catchment-planning/v/c3-plan/ManagementCatchment/3101">MC</a>
        <a href="/catchment-planning/v/c3-plan/WaterBody/GB123">WB</a>
        <a href="/catchment-planning/v/c3-plan/OperationalCatchment/1/classifications">
          ignored
        </a>
      </body>
    </html>
    """

    page = parse_entity_page(
        body,
        kind="OperationalCatchment",
        entity_id="1",
    )

    assert page.name == "Example Rivers"
    assert page.links["RiverBasinDistrict"] == ("4",)
    assert page.links["ManagementCatchment"] == ("3101",)
    assert page.links["WaterBody"] == ("GB123",)


def test_geojson_preserves_multiple_features_for_one_water_body() -> None:
    body = json.dumps(
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {
                        "id": "GB123",
                        "name": "Example River",
                        "uri": (
                            "http://environment.data.gov.uk/catchment-planning/so/WaterBody/GB123"
                        ),
                        "water-body-type": {
                            "string": "River",
                            "lang": "en",
                        },
                        "geometry-type": (
                            "http://environment.data.gov.uk/"
                            "catchment-planning/def/geometry/Catchment"
                        ),
                    },
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [
                            [
                                [-2.0, 52.0],
                                [-1.9, 52.0],
                                [-1.9, 52.1],
                                [-2.0, 52.1],
                                [-2.0, 52.0],
                            ]
                        ],
                    },
                },
                {
                    "type": "Feature",
                    "properties": {
                        "id": "GB123",
                        "name": "Example River",
                        "uri": (
                            "http://environment.data.gov.uk/catchment-planning/so/WaterBody/GB123"
                        ),
                        "water-body-type": {
                            "string": "River",
                            "lang": "en",
                        },
                        "geometry-type": (
                            "http://environment.data.gov.uk/"
                            "catchment-planning/def/geometry/RiverLine"
                        ),
                    },
                    "geometry": {
                        "type": "MultiLineString",
                        "coordinates": [
                            [
                                [-1.99, 52.01],
                                [-1.95, 52.05],
                            ]
                        ],
                    },
                },
            ],
        }
    ).encode()

    water_bodies, geometries = parse_rbd_geojson(
        body,
        rbd_id="4",
    )

    assert set(water_bodies) == {"GB123"}
    assert len(geometries) == 2
    assert geometries[0]["geometry_kind"] == "Catchment"
    assert geometries[1]["geometry_kind"] == "RiverLine"
    assert geometries[0]["feature_index"] == 0
    assert geometries[1]["feature_index"] == 1


def test_geojson_rejects_geometry_kind_mismatch() -> None:
    body = json.dumps(
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {
                        "id": "GB123",
                        "name": "Example",
                        "uri": (
                            "http://environment.data.gov.uk/catchment-planning/so/WaterBody/GB123"
                        ),
                        "water-body-type": {
                            "string": "River",
                            "lang": "en",
                        },
                        "geometry-type": (
                            "http://environment.data.gov.uk/"
                            "catchment-planning/def/geometry/RiverLine"
                        ),
                    },
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [
                            [
                                [-2.0, 52.0],
                                [-1.9, 52.0],
                                [-1.9, 52.1],
                                [-2.0, 52.1],
                                [-2.0, 52.0],
                            ]
                        ],
                    },
                }
            ],
        }
    ).encode()

    with pytest.raises(
        CatchmentError,
        match="contradicts publisher geometry kind",
    ):
        parse_rbd_geojson(body, rbd_id="4")


def test_entity_page_ignores_unversioned_and_utility_links() -> None:
    body = b"""
    <html>
      <head>
        <title>Example Management Catchment | Catchment Data Explorer</title>
      </head>
      <body>
        <a href="/catchment-planning/OperationalCatchment/123">unversioned</a>
        <a href="/catchment-planning/v/c3-plan/RiverBasinDistrict/4">parent</a>
        <a href="/catchment-planning/v/c3-plan/OperationalCatchment/123">child</a>
        <a href="/catchment-planning/v/c3-plan/OperationalCatchment/123/print">
          utility
        </a>
      </body>
    </html>
    """

    page = parse_entity_page(
        body,
        kind="ManagementCatchment",
        entity_id="1",
    )

    assert page.links["RiverBasinDistrict"] == ("4",)
    assert page.links["OperationalCatchment"] == ("123",)
