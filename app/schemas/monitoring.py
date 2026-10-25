from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, Field

TimeRange = Literal["1h", "6h", "24h", "7d"]


class MetricPoint(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    t: str
    avg_latency: float = Field(..., serialization_alias="avgLatency", alias="avgLatency")
    p95_latency: float = Field(..., serialization_alias="p95Latency", alias="p95Latency")
    requests: int = Field(..., serialization_alias="requests", alias="requests")
    error_rate4xx: float = Field(..., serialization_alias="errorRate4xx", alias="errorRate4xx")
    error_rate5xx: float = Field(..., serialization_alias="errorRate5xx", alias="errorRate5xx")
    error_rate: float = Field(..., serialization_alias="errorRate", alias="errorRate")
    timeouts: int = Field(..., serialization_alias="timeouts", alias="timeouts")
    availability: Optional[float] = Field(None, serialization_alias="availability", alias="availability")
