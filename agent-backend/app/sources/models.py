"""Pydantic models for external data-source manifests (SOURCE.yaml)."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class AccessMode(str, Enum):
    api = "api"
    local = "local"
    hybrid = "hybrid"  # prefer local index; fall back to API


class DataFile(BaseModel):
    """One downloadable / local table belonging to a source."""
    id: str
    path: str
    description: str = ""
    columns: list[str] = Field(default_factory=list)
    index_keys: list[str] = Field(default_factory=list)
    approx_rows: int | None = None
    # csv.reader delimiter; default tab for TSV dumps
    delimiter: str = "\t"
    encoding: str = "utf-8"
    # Skip license/preamble lines until a header row is found
    skip_until_header: bool = False
    # Optional exact first-cell value that identifies the header row
    header_startswith: str | None = None
    # For .xlsx inputs
    xlsx_sheet: str | None = None
    # Parse MOD_RSD / SUB_MOD_RSD (e.g. S15-p) into a numeric `position` column
    derive_mod_position_from: str | None = None


class SourceManifest(BaseModel):
    """Machine-readable description of an external PTM database."""
    id: str
    name: str
    aspect: str
    access: AccessMode
    description: str
    homepage: str | None = None
    api_base: str | None = None
    api_docs: str | None = None
    citation: str | None = None
    doi: str | None = None
    pmid: str | None = None
    license: str | None = None
    notes: str | None = None
    tools: list[str] = Field(default_factory=list)
    files: list[DataFile] = Field(default_factory=list)
    # Absolute root set at load time
    root: Path | None = None

    @classmethod
    def model_validate(cls, obj, *args, **kwargs):  # type: ignore[override]
        if isinstance(obj, dict) and obj.get("pmid") is not None:
            obj = {**obj, "pmid": str(obj["pmid"])}
        return super().model_validate(obj, *args, **kwargs)

    def resolve(self, relative: str) -> Path:
        if self.root is None:
            raise RuntimeError(f"Source {self.id} has no root path")
        return self.root / relative

    def file_by_id(self, file_id: str) -> DataFile | None:
        for f in self.files:
            if f.id == file_id:
                return f
        return None

    def citation_defaults(self) -> dict[str, Any]:
        return {
            "source_db": self.name,
            "url": self.homepage or self.api_docs or self.api_base,
            "doi": self.doi,
            "pmid": self.pmid,
            "detail": self.citation,
        }
