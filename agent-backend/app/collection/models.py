"""Pydantic models for collection jobs."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


JobStatus = Literal[
    "pending",
    "running",
    "awaiting_continue",
    "awaiting_upload",
    "completed",
    "rejected",
    "error",
]
AwaitingUpload = Literal["fulltext", "supplementary"]


class CollectionJobCreate(BaseModel):
    message: str | None = None
    pmid: str | None = None


class CollectionJobResponse(BaseModel):
    job_id: str
    pmid: str | None = None
    status: JobStatus = "pending"
    current_stage: str | None = None
    next_stage: str | None = None
    awaiting_upload: AwaitingUpload | None = None
    message: str = ""
    stages: dict[str, str] = Field(default_factory=dict)
    summary: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    needs_pmid: bool = False


class CollectionUploadResponse(BaseModel):
    job_id: str
    upload_type: AwaitingUpload
    filename: str
    message: str
