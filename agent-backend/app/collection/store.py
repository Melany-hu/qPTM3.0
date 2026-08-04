"""In-memory + filesystem collection job store."""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any

from app.config import settings

_PMID_RE = re.compile(r"\b(?:PMID[:\s#]*)?(\d{7,8})\b", re.I)
_STEM_PMID_RE = re.compile(r"^(\d{7,8})$")


def extract_pmid(text: str | None) -> str | None:
    if not text:
        return None
    m = _PMID_RE.search(text.strip())
    return m.group(1) if m else None


_FILENAME_PMID_RE = re.compile(r"(?<!\d)(\d{7,8})(?!\d)")


def extract_pmid_from_filename(filename: str | None) -> str | None:
    """Extract PMID from upload names like 39732660.pdf or pmid_39732660_fulltext.pdf."""
    if not filename:
        return None
    stem = Path(filename).stem
    if _STEM_PMID_RE.fullmatch(stem):
        return stem
    m = _FILENAME_PMID_RE.search(stem)
    if m:
        return m.group(1)
    m = _FILENAME_PMID_RE.search(filename)
    return m.group(1) if m else None


def resolve_pmid(
    *,
    pmid: str | None = None,
    message: str | None = None,
    filenames: list[str] | None = None,
) -> str | None:
    """Resolve PMID from explicit field, message text, or uploaded filenames."""
    if pmid:
        explicit = pmid.strip()
        if _STEM_PMID_RE.fullmatch(explicit):
            return explicit
        found = extract_pmid(explicit)
        if found:
            return found

    found = extract_pmid(message)
    if found:
        return found

    for name in filenames or []:
        found = extract_pmid_from_filename(name)
        if found:
            return found
    return None


def jobs_root() -> Path:
    root = Path(settings.collection_jobs_dir)
    root.mkdir(parents=True, exist_ok=True)
    return root


def job_dir(job_id: str) -> Path:
    path = jobs_root() / job_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def uploads_dir(job_id: str) -> Path:
    path = job_dir(job_id) / "uploads"
    path.mkdir(parents=True, exist_ok=True)
    return path


def read_job_json(job_id: str) -> dict[str, Any] | None:
    path = job_dir(job_id) / "job.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def new_job_id() -> str:
    return str(uuid.uuid4())


def _csv_has_data_rows(path: Path) -> bool:
    try:
        with path.open(encoding="utf-8", errors="replace") as fh:
            return sum(1 for _ in fh) > 1
    except OSError:
        return False


def stage3_artifact(job_id: str, name: str = "literature_info.csv") -> Path | None:
    path = job_dir(job_id) / "stage3" / name
    return path if path.is_file() else None


def stage5_artifact(job_id: str, name: str = "qratio.csv") -> Path | None:
    path = job_dir(job_id) / "stage5" / name
    if path.is_file() and _csv_has_data_rows(path):
        return path
    return None


def stage7_artifact(job_id: str, name: str) -> Path | None:
    """Legacy stage7 path; prefer stage3/stage5 artifacts."""
    if name == "literature_info.csv":
        return stage3_artifact(job_id, name)
    if name == "qratio.csv":
        return stage5_artifact(job_id, name)
    path = job_dir(job_id) / "stage7" / name
    if name == "qratio.csv" and path.is_file() and not _csv_has_data_rows(path):
        return stage5_artifact(job_id, name)
    return path if path.is_file() else None
