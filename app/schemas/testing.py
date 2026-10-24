from typing import Any, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel
from app.schemas.api import AuthType, BaseCamelModel, HttpMethod, KeyValueSchema


class TestRequestSchema(BaseCamelModel):
    url: str = Field(..., min_length=1, max_length=2048)
    method: HttpMethod = "GET"
    query_params: List[KeyValueSchema] = Field(default_factory=list)
    headers: List[KeyValueSchema] = Field(default_factory=list)
    auth_type: AuthType = "none"
    secret: Optional[str] = Field(None, max_length=2048)
    body: Optional[str] = Field(None, max_length=1048576)
    expected_status: int = Field(default=200, ge=100, le=599)
    validation_rule: Optional[str] = Field(None, max_length=255)
    timeout_ms: int = Field(default=10000, ge=500, le=30000)

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        clean = v.strip()
        if not (clean.startswith("http://") or clean.startswith("https://")):
            raise ValueError("URL must start with http:// or https://")
        return clean


class ValidationResultSchema(BaseCamelModel):
    rule: str
    passed: bool
    detail: str


class TestResultResponse(BaseCamelModel):
    id: str
    api_id: Optional[str] = None
    passed: bool
    outcome: Literal["success", "failure", "timeout", "error"]
    status_code: Optional[int] = None
    expected_status: int
    latency_ms: Optional[float] = None
    headers: List[KeyValueSchema] = Field(default_factory=list)
    body: str = ""
    validations: List[ValidationResultSchema] = Field(default_factory=list)
    error: Optional[str] = None
    tested_at: str
    simulated: bool = False
