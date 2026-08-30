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


class ResolveUrlsRequest(BaseModel):
    """Standalone MS accession → download URL resolution (Stage 6 only)."""

    accession: str | None = None
    accessions: list[str] = Field(default_factory=list)
    message: str | None = None
    pmid: str | None = None
    title: str | None = None
    organism: str | None = None
    modification: str | None = None


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
    offer_contribute: bool = False
    contribution: dict[str, Any] | None = None
    error: str | None = None
    needs_pmid: bool = False
    # True when this is a resolve-urls (accession-only) job.
    resolve_urls: bool = False


class CollectionContributeRequest(BaseModel):
    willing: bool
    note: str | None = None


class CollectionTableSelection(BaseModel):
    entryPath: str
    sheetName: str | None = None


class CollectionTableHintsRequest(BaseModel):
    selections: list[CollectionTableSelection] = Field(default_factory=list)
    note: str | None = None
    prefer_protein_log2: bool | None = None
    # When true, resume Stage 5 after saving hints.
    resume: bool = True


class CollectionGuidanceRequest(BaseModel):
    """Free-text Stage5 feedback → table hints + optional re-parse."""

    message: str
    resume: bool = True


class CollectionUploadResponse(BaseModel):
    job_id: str
    upload_type: AwaitingUpload
    filename: str
    message: str
