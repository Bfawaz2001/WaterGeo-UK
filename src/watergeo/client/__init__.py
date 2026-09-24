"""First-party HTTP client for WaterGeo UK."""

from watergeo.client.client import WaterGeoClient
from watergeo.client.errors import (
    WaterGeoAPIError,
    WaterGeoConfigurationError,
    WaterGeoError,
    WaterGeoResponseError,
    WaterGeoTransportError,
)

__all__ = [
    "WaterGeoAPIError",
    "WaterGeoClient",
    "WaterGeoConfigurationError",
    "WaterGeoError",
    "WaterGeoResponseError",
    "WaterGeoTransportError",
]
