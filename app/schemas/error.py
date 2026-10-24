from typing import Any, Dict
from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    code: str = Field(..., description="Machine-readable error code")
    message: str = Field(..., description="Human-readable error explanation")
    fieldErrors: Dict[str, str] = Field(
        default_factory=dict,
        description="Field-specific validation error messages",
    )
    requestId: str = Field(..., description="Correlation request ID")


class ErrorResponse(BaseModel):
    error: ErrorDetail
