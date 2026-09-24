"""Named SDK response contracts backed by the API's authoritative Pydantic models.

The API and first-party client ship in one distribution. Re-exporting the response
models under domain-specific names gives SDK users a stable import surface without
maintaining a second schema that can drift from the server.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict

from watergeo.api.catchment_models import (
    Dataset as CatchmentDataset,
)
from watergeo.api.catchment_models import (
    ManagementCatchment,
    ManagementCatchmentDetail,
    ManagementCatchmentPage,
    OperationalCatchment,
    OperationalCatchmentDetail,
    OperationalCatchmentPage,
    RiverBasinDistrict,
    RiverBasinDistrictDetail,
    RiverBasinDistrictPage,
    WaterBody,
    WaterBodyDetail,
    WaterBodyGeometryCollection,
    WaterBodyPage,
)
from watergeo.api.hydrology_history_models import (
    HistoricalObservation,
    HistoryRetrievalResponse,
)
from watergeo.api.hydrology_models import (
    Dataset as HydrologyDataset,
)
from watergeo.api.hydrology_models import (
    Measure,
    Station,
    StationDetail,
    StationPage,
)
from watergeo.api.hydrology_models import (
    Observation as HydrologyObservation,
)
from watergeo.api.source_models import SourceStatus, SourceStatuses
from watergeo.api.stream_reservoir_models import (
    Dataset as ReservoirLevelDataset,
)
from watergeo.api.stream_reservoir_models import (
    Reading as ReservoirReading,
)
from watergeo.api.stream_reservoir_models import (
    ReadingPage as ReservoirReadingPage,
)
from watergeo.api.stream_reservoir_models import (
    Reservoir,
    ReservoirDetail,
    ReservoirPage,
)
from watergeo.api.water_quality_models import (
    Dataset as WaterQualityDataset,
)
from watergeo.api.water_quality_models import (
    SamplingPoint,
    SamplingPointDetail,
    SamplingPointPage,
)
from watergeo.api.water_quality_observation_models import (
    Observation as WaterQualityObservation,
)
from watergeo.api.water_quality_observation_models import (
    ObservationRetrieval as WaterQualityObservationRetrieval,
)
from watergeo.api.water_supply_models import (
    AreaDetail,
    AreaFeature,
    AreaPage,
    AreaSummary,
)
from watergeo.api.water_supply_models import (
    DatasetMetadata as WaterSupplyDataset,
)


class Health(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["ok"]


class Readiness(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["ready", "not_ready"]


__all__ = [
    "AreaDetail",
    "AreaFeature",
    "AreaPage",
    "AreaSummary",
    "CatchmentDataset",
    "Health",
    "HistoricalObservation",
    "HistoryRetrievalResponse",
    "HydrologyDataset",
    "HydrologyObservation",
    "ManagementCatchment",
    "ManagementCatchmentDetail",
    "ManagementCatchmentPage",
    "Measure",
    "OperationalCatchment",
    "OperationalCatchmentDetail",
    "OperationalCatchmentPage",
    "Readiness",
    "Reservoir",
    "ReservoirDetail",
    "ReservoirLevelDataset",
    "ReservoirPage",
    "ReservoirReading",
    "ReservoirReadingPage",
    "RiverBasinDistrict",
    "RiverBasinDistrictDetail",
    "RiverBasinDistrictPage",
    "SamplingPoint",
    "SamplingPointDetail",
    "SamplingPointPage",
    "SourceStatus",
    "SourceStatuses",
    "Station",
    "StationDetail",
    "StationPage",
    "WaterBody",
    "WaterBodyDetail",
    "WaterBodyGeometryCollection",
    "WaterBodyPage",
    "WaterQualityDataset",
    "WaterQualityObservation",
    "WaterQualityObservationRetrieval",
    "WaterSupplyDataset",
]
