"""Stable public exceptions raised by the WaterGeo HTTP client."""


class WaterGeoError(Exception):
    """Base class for client-side WaterGeo failures."""


class WaterGeoConfigurationError(WaterGeoError, ValueError):
    """The client configuration is unsafe or invalid."""


class WaterGeoTransportError(WaterGeoError):
    """The server could not be reached within the configured transport bounds."""


class WaterGeoAPIError(WaterGeoError):
    """The WaterGeo API returned a non-success status."""

    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"WaterGeo API returned HTTP {status_code}: {detail}")


class WaterGeoResponseError(WaterGeoError):
    """The server returned an unsupported or malformed success response."""
