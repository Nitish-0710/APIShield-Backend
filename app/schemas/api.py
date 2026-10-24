from datetime import datetime
from typing import Any, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel


HttpMethod = Literal["GET", "POST", "PUT", "PATCH", "DELETE"]
AuthType = Literal["none", "bearer", "api_key", "basic"]
HealthStatus = Literal["healthy", "degraded", "failing", "unknown"]
RiskLevel = Literal["low", "medium", "high", "unknown"]


class BaseCamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


class KeyValueSchema(BaseCamelModel):
    key: str = Field(..., max_length=255)
    value: str = Field(..., max_length=4096)


class ApiEndpointInput(BaseCamelModel):
    name: str = Field(..., min_length=1, max_length=255)
    url: str = Field(..., min_length=1, max_length=2048)
    method: HttpMethod = "GET"
    query_params: List[KeyValueSchema] = Field(default_factory=list)
    headers: List[KeyValueSchema] = Field(default_factory=list)
    auth_type: AuthType = "none"
    secret: Optional[str] = Field(None, max_length=2048)
    body: Optional[str] = Field(None, max_length=1048576)  # 1MB limit
    expected_status: int = Field(default=200, ge=100, le=599)
    validation_rule: Optional[str] = Field(None, max_length=255)
    timeout_ms: int = Field(default=10000, ge=500, le=30000)
    interval_sec: int = Field(default=60, ge=5, le=86400)
    max_latency_ms: int = Field(default=1000, ge=10, le=60000)
    error_rate_threshold: float = Field(default=5.0, ge=0.0, le=100.0)
    expected_availability: float = Field(default=99.0, ge=0.0, le=100.0)
    risk_threshold: float = Field(default=70.0, ge=0.0, le=100.0)
    monitoring: bool = False

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        clean = v.strip()
        if not clean:
            raise ValueError("API name cannot be blank.")
        return clean

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        clean = v.strip()
        if not (clean.startswith("http://") or clean.startswith("https://")):
            raise ValueError("URL must start with http:// or https://")
        return clean


class ApiEndpointUpdate(BaseCamelModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    url: Optional[str] = Field(None, min_length=1, max_length=2048)
    method: Optional[HttpMethod] = None
    query_params: Optional[List[KeyValueSchema]] = None
    headers: Optional[List[KeyValueSchema]] = None
    auth_type: Optional[AuthType] = None
    secret: Optional[str] = Field(None, max_length=2048)
    body: Optional[str] = Field(None, max_length=1048576)
    expected_status: Optional[int] = Field(None, ge=100, le=599)
    validation_rule: Optional[str] = Field(None, max_length=255)
    timeout_ms: Optional[int] = Field(None, ge=500, le=30000)
    interval_sec: Optional[int] = Field(None, ge=5, le=86400)
    max_latency_ms: Optional[int] = Field(None, ge=10, le=60000)
    error_rate_threshold: Optional[float] = Field(None, ge=0.0, le=100.0)
    expected_availability: Optional[float] = Field(None, ge=0.0, le=100.0)
    risk_threshold: Optional[float] = Field(None, ge=0.0, le=100.0)
    monitoring: Optional[bool] = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            clean = v.strip()
            if not clean:
                raise ValueError("API name cannot be blank.")
            return clean
        return v

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            clean = v.strip()
            if not (clean.startswith("http://") or clean.startswith("https://")):
                raise ValueError("URL must start with http:// or https://")
            return clean
        return v


class ApiEndpointResponse(BaseCamelModel):
    id: str
    name: str
    url: str
    method: HttpMethod
    query_params: List[KeyValueSchema] = Field(default_factory=list)
    headers: List[KeyValueSchema] = Field(default_factory=list)
    auth_type: AuthType
    has_secret: bool
    body: Optional[str] = None
    expected_status: int
    validation_rule: Optional[str] = None
    timeout_ms: int
    interval_sec: int
    max_latency_ms: int
    error_rate_threshold: float
    expected_availability: float
    risk_threshold: float
    monitoring: bool
    health: HealthStatus
    last_status_code: Optional[int] = None
    last_latency_ms: Optional[float] = None
    last_checked_at: Optional[str] = None
    risk: RiskLevel
    risk_score: Optional[float] = None
    created_at: str
