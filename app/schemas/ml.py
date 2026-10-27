from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


# --- Prediction Schemas ---

class PredictRequest(BaseModel):
    api_id: str = Field(..., description="ID of the API endpoint to predict failure risk for")
    use_recent_telemetry: bool = Field(True, description="Whether to aggregate the latest telemetry from test results")
    override_features: Optional[Dict[str, float]] = Field(None, description="Optional manual feature overrides for testing")


class PredictionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    api_id: str
    risk_score: float = Field(..., description="Risk score from 0.0 to 100.0")
    risk_level: str = Field(..., description="'low' | 'medium' | 'high' | 'critical'")
    prediction: int = Field(..., description="0 = Healthy, 1 = Failure Risk")
    provenance: str = Field(..., description="'trained_model' | 'rules_baseline' | 'demo'")
    model_version: Optional[str] = None
    features: Dict[str, Any]
    explanation: Dict[str, Any]
    inference_duration_ms: Optional[float] = None
    created_at: datetime


class PredictionHistoryResponse(BaseModel):
    total: int
    items: List[PredictionResponse]
    limit: int
    offset: int


# --- Diagnostic Schemas ---

class DiagnosticFinding(BaseModel):
    category: str = Field(..., description="e.g. 'timeout', 'latency', '5xx_errors', '4xx_errors', 'availability'")
    severity: str = Field(..., description="'info' | 'warning' | 'critical'")
    certainty: str = Field(..., description="'confirmed_fact' | 'rule_inference' | 'ml_association'")
    title: str
    evidence: Dict[str, Any]
    recommendation: str


class DiagnosticReport(BaseModel):
    api_id: str
    api_name: str
    time_window: str
    overall_status: str
    findings: List[DiagnosticFinding]
    summary: str
    generated_at: datetime


# --- Alert Schemas ---

class AlertResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    api_id: Optional[str] = None
    title: str
    description: str
    severity: str
    status: str
    source: str
    fingerprint: str
    created_at: datetime
    resolved_at: Optional[datetime] = None


class AlertStatusUpdate(BaseModel):
    status: str = Field(..., pattern="^(open|acknowledged|resolved)$")


class AlertListResponse(BaseModel):
    total: int
    items: List[AlertResponse]


# --- Settings Schemas ---

class UserSettingsSchema(BaseModel):
    alert_cooldown_minutes: int = Field(15, ge=1, le=1440)
    latency_warning_threshold_ms: float = Field(1000.0, ge=10.0, le=60000.0)
    error_rate_threshold_percent: float = Field(5.0, ge=0.0, le=100.0)
    availability_target_percent: float = Field(99.0, ge=0.0, le=100.0)
    risk_alert_threshold: float = Field(70.0, ge=0.0, le=100.0)
    enable_auto_diagnostics: bool = True
    webhook_url: Optional[str] = None


class UserSettingsUpdate(BaseModel):
    alert_cooldown_minutes: Optional[int] = Field(None, ge=1, le=1440)
    latency_warning_threshold_ms: Optional[float] = Field(None, ge=10.0, le=60000.0)
    error_rate_threshold_percent: Optional[float] = Field(None, ge=0.0, le=100.0)
    availability_target_percent: Optional[float] = Field(None, ge=0.0, le=100.0)
    risk_alert_threshold: Optional[float] = Field(None, ge=0.0, le=100.0)
    enable_auto_diagnostics: Optional[bool] = None
    webhook_url: Optional[str] = None


# --- Report Schemas ---

class MonitoringReportSummary(BaseModel):
    api_id: str
    api_name: str
    time_range: str
    total_observations: int
    availability: Optional[float] = None
    avg_latency_ms: Optional[float] = None
    p95_latency_ms: Optional[float] = None
    error_rate: float
    timeout_rate: float
    prediction_count: int
    high_risk_predictions: int
    open_alerts: int
    generated_at: datetime


# --- ML Management Schemas ---

class ExperimentRunSchema(BaseModel):
    run_id: str
    experiment_name: str
    model_version: Optional[str] = None
    model_type: Optional[str] = None
    params: Dict[str, Any] = Field(default_factory=dict)
    metrics: Dict[str, Any] = Field(default_factory=dict)
    is_promoted: bool = False
    promotion_status: Optional[str] = None
    backend: str = "mlflow_native"
    timestamp: Optional[str] = None
    status: Optional[str] = None
    artifact_uri: Optional[str] = None


class ExperimentListResponse(BaseModel):
    total: int
    items: List[ExperimentRunSchema]


class ModelVersionSchema(BaseModel):
    model_name: str
    version: str
    status: str
    stage: Optional[str] = None
    aliases: List[str] = Field(default_factory=list)
    run_id: Optional[str] = None
    created_at: Optional[str] = None
    metrics: Optional[Dict[str, Any]] = None


class ModelListResponse(BaseModel):
    total: int
    items: List[ModelVersionSchema]


class ServingModelResponse(BaseModel):
    model_name: str
    model_version: Optional[str] = None
    model_type: str
    provenance: str
    is_loaded: bool
    artifact_exists: bool
    expected_features: List[str]
    candidate_metrics: Optional[Dict[str, Any]] = None
    trained_at: Optional[str] = None
    health_status: str


class TrainingRunRequest(BaseModel):
    dataset_path: Optional[str] = None
    api_id: Optional[str] = None


class TrainingRunResponse(BaseModel):
    success: bool
    status: str
    model_version: Optional[str] = None
    model_type: Optional[str] = None
    is_promoted: Optional[bool] = None
    candidate_metrics: Optional[Dict[str, Any]] = None
    baseline_metrics: Optional[Dict[str, Any]] = None
    reason: Optional[str] = None


class FairnessReportResponse(BaseModel):
    status: str
    is_synthetic_demonstration: bool
    libraries: Optional[Dict[str, str]] = None
    disclaimer: str
    evaluated_at: str
    summary: Dict[str, Any]
    aif360_metrics: Optional[Dict[str, Any]] = None
    groups: Dict[str, Any]
