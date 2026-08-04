"""Upload classification helpers for collection jobs."""

from __future__ import annotations

from pathlib import Path

FULLTEXT_EXTENSIONS = {".pdf", ".xml"}
SUPPLEMENTARY_EXTENSIONS = {".zip", ".xlsx", ".xls", ".csv", ".tsv"}


def classify_upload_filename(filename: str | None) -> str:
    ext = Path(filename or "").suffix.lower()
    if ext in FULLTEXT_EXTENSIONS:
        return "fulltext"
    if ext in SUPPLEMENTARY_EXTENSIONS:
        return "supplementary"
    return "unknown"
