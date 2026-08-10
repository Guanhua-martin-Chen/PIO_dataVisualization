from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class GovernedRunMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str
    run_id: str
    approval_status: Literal["approved"]
    registry_version: str
    generated_at: str
    published_at: str
    actual_data_through: str
    completed_training_data_through: str
    forecast_start: str
    forecast_end: str
    source_git_commit: str


class GovernedEndpointEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    meta: GovernedRunMetadata
    data: Any


class GovernedHealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ok", "degraded"]
    service: str
    schema_version: str
    approved_run_available: bool
    run_id: str | None = None


class GovernedRunSummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    meta: GovernedRunMetadata
    available_endpoints: list[str]
    sponsor_workbook_filename: str
    sponsor_workbook_sha256: str
    validation: dict[str, Any] = Field(default_factory=dict)
