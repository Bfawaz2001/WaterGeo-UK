"""Exact reviewed presentation outputs; canonical ingestion has its own policy."""

WGS84_PRESENTATION_VERSION = "ofwat-water-supply-v1_5-wgs84-structure-v2"
WGS84_PRESENTATION_REVIEW = "docs/adr/0006-water-supply-wgs84-presentation.md"

# source_id: (canonical little-endian WKB SHA-256, oriented 15-digit GeoJSON SHA-256)
REVIEWED_WGS84_GEOMETRIES: dict[int, tuple[str, str]] = {
    3: (
        "7b9b04ff78a4c228f73154436dac4926d425607d4ced08dc9a73c66225d9850f",
        "859c9536bed336a2c4c7387ed64fb1b12bbfa2f11f09c866fb0a22441cc93fbc",
    ),
    4: (
        "829928770402be6b318f86cf9e9e28212c8d8f6314071db89c3de39e6d01a4a3",
        "5afb38893fa0b05726acc41d09ef03ab1ac09709be41502db7797e0606ca82bd",
    ),
    16: (
        "a39c9121ad32cf638c2fbcb7ecb23c2d0aceb149ba2385399edb86d2355987d2",
        "7ec160dc7ab45af63ab953152af862819b5747e22346a4d14ae63bf47415fa6f",
    ),
    21: (
        "76687d1f4b3482351ec3cb7db307e2638bf4c1643e860866a787b84d15459cb4",
        "36103aa15aa03246d1d085f1bb9de65cdf00d7c690179ae8f5f6164310c4a1cb",
    ),
}

# Additional exact PostGIS GeoJSON outputs reviewed on Linux/AMD64. The primary
# hashes above are the corresponding Linux/ARM64 outputs. Both runtimes use the
# same PostGIS, GEOS and PROJ versions; their sub-nanometre floating-point
# differences are documented by ADR 0006. No other output hash is accepted.
REVIEWED_WGS84_GEOJSON_VARIANTS: dict[int, tuple[str, ...]] = {
    3: ("f6b3ef2eeef030d1a609e581dabfc9b140f95d60861333e988604d8ff2c6aa32",),
    4: ("3a7b084ee8b0e970ac5dfbbc651ce863572e013e201f76f8dd65ab2f4ef7e897",),
    16: ("145affc3afbc72d56135f85c72409e6574ffbed0aca59efbdc5bfb4962463583",),
    21: ("022a9e01dcf14fe3ab0b63302da6082551e0d7f5557171f3972e9003982380bc",),
}
