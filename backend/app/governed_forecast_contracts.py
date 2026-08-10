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


class ForecastUpdateFileValidation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["capstone", "hma_plan", "gma_plan", "kia_plan"]
    filename: str
    size_bytes: int
    sha256: str
    valid: bool
    summary: str
    details: dict[str, Any] = Field(default_factory=dict)


class ForecastUpdateJob(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    status: Literal[
        "validated",
        "validation_failed",
        "queued",
        "running",
        "qa_failed",
        "awaiting_approval",
        "publishing",
        "published",
        "failed",
    ]
    created_at: str
    updated_at: str
    files: list[ForecastUpdateFileValidation]
    progress: dict[str, Any]
    qa: dict[str, Any] | None = None
    draft: dict[str, Any] | None = None
    approved_run_id: str | None = None
    error: str | None = None


class ForecastUpdateJobEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job: ForecastUpdateJob


class ForecastUpdateJobList(BaseModel):
    model_config = ConfigDict(extra="forbid")

    jobs: list[ForecastUpdateJob]
