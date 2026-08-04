"""FastAPI routes for Collection Agent jobs."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

from app.collection.models import CollectionJobCreate, CollectionJobResponse, CollectionUploadResponse
from app.collection.runner import (
    ingest_fulltext,
    ingest_supplementary,
    job_state_to_response,
    resume_job,
    schedule_job,
    watch_job_events,
)
from app.collection.pmid_from_files import resolve_pmid_from_uploads
from app.collection.uploads import classify_upload_filename
from app.collection.store import job_dir, new_job_id, resolve_pmid, stage3_artifact, stage5_artifact, uploads_dir
from app.config import settings

router = APIRouter(prefix="/collection", tags=["collection"])

_ALLOWED_EXT = {".pdf", ".xml", ".zip", ".xlsx", ".xls", ".csv", ".tsv"}
_MAX_BYTES = settings.collection_max_upload_bytes


def _validate_upload(filename: str, size: int) -> str:
    ext = Path(filename).suffix.lower()
    if ext not in _ALLOWED_EXT:
        raise HTTPException(400, f"Unsupported file type: {ext}")
    if size > _MAX_BYTES:
        raise HTTPException(400, f"File too large (max {_MAX_BYTES // (1024 * 1024)} MB)")
    return ext


async def _save_upload(job_id: str, upload: UploadFile, prefix: str) -> Path:
    if not upload.filename:
        raise HTTPException(400, "Missing filename")
    content = await upload.read()
    _validate_upload(upload.filename, len(content))
    dest = uploads_dir(job_id) / f"{prefix}{Path(upload.filename).suffix.lower()}"
    dest.write_bytes(content)
    return dest


async def _read_upload(upload: UploadFile) -> tuple[str, bytes]:
    if not upload.filename:
        raise HTTPException(400, "Missing filename")
    content = await upload.read()
    _validate_upload(upload.filename, len(content))
    return upload.filename, content


def _write_upload(job_id: str, filename: str, content: bytes, prefix: str) -> Path:
    dest = uploads_dir(job_id) / f"{prefix}{Path(filename).suffix.lower()}"
    dest.write_bytes(content)
    return dest


@router.post("/jobs", response_model=CollectionJobResponse)
async def create_job(
    message: str | None = Form(default=None),
    pmid: str | None = Form(default=None),
    fulltext: UploadFile | None = File(default=None),
    supplementary: UploadFile | None = File(default=None),
) -> CollectionJobResponse:
    body = CollectionJobCreate(message=message, pmid=pmid)
    upload_names: list[str] = []
    fulltext_blob: tuple[str, bytes] | None = None
    supplementary_blob: tuple[str, bytes] | None = None

    if fulltext and fulltext.filename:
        name, content = await _read_upload(fulltext)
        if classify_upload_filename(name) != "fulltext":
            raise HTTPException(400, f"fulltext 字段仅支持 PDF/XML，收到: {name}")
        upload_names.append(name)
        fulltext_blob = (name, content)

    if supplementary and supplementary.filename:
        name, content = await _read_upload(supplementary)
        if classify_upload_filename(name) != "supplementary":
            raise HTTPException(400, f"supplementary 字段仅支持 ZIP/Excel/CSV，收到: {name}")
        upload_names.append(name)
        supplementary_blob = (name, content)

    resolved_pmid = resolve_pmid(
        pmid=body.pmid if body else None,
        message=body.message if body else None,
        filenames=upload_names,
    )
    if not resolved_pmid:
        blobs: list[tuple[str, bytes]] = []
        if fulltext_blob:
            blobs.append(fulltext_blob)
        if supplementary_blob:
            blobs.append(supplementary_blob)
        if blobs:
            resolved_pmid = await resolve_pmid_from_uploads(blobs)

    if not resolved_pmid:
        return CollectionJobResponse(
            job_id=new_job_id(),
            status="error",
            message=(
                "Could not resolve PMID. Upload a PDF/XML that contains a PMID, "
                "enter a PMID in the message box, or rename the file (e.g. 39732660.pdf)."
            ),
            needs_pmid=True,
        )

    job_id = new_job_id()
    job_dir(job_id)
    fulltext_path: str | None = None
    supplementary_path: str | None = None

    if fulltext_blob:
        saved = _write_upload(job_id, fulltext_blob[0], fulltext_blob[1], "fulltext")
        fulltext_path = str(saved)

    if supplementary_blob:
        saved = _write_upload(job_id, supplementary_blob[0], supplementary_blob[1], "supplementary")
        supplementary_path = str(saved)

    await schedule_job(
        job_id,
        resolved_pmid,
        fulltext_path=fulltext_path,
        supplementary_path=supplementary_path,
    )
    return CollectionJobResponse(**job_state_to_response(job_id, resolved_pmid))


@router.get("/jobs/{job_id}", response_model=CollectionJobResponse)
async def get_job(job_id: str) -> CollectionJobResponse:
    if not job_dir(job_id).exists():
        raise HTTPException(404, "Job not found")
    return CollectionJobResponse(**job_state_to_response(job_id))


@router.get("/jobs/{job_id}/stream")
async def stream_job(job_id: str) -> StreamingResponse:
    if not job_dir(job_id).exists():
        raise HTTPException(404, "Job not found")

    async def event_gen():
        async for item in watch_job_events(job_id):
            yield f"event: {item['event']}\ndata: {json.dumps(item['data'])}\n\n"

    return StreamingResponse(event_gen(), media_type="text/event-stream")


@router.post("/jobs/{job_id}/upload", response_model=CollectionUploadResponse)
async def upload_file(
    job_id: str,
    upload_type: str = Form(...),
    file: UploadFile = File(...),
) -> CollectionUploadResponse:
    if not job_dir(job_id).exists():
        raise HTTPException(404, "Job not found")
    if upload_type not in ("fulltext", "supplementary"):
        raise HTTPException(400, "upload_type must be fulltext or supplementary")

    state = job_state_to_response(job_id)
    pmid = state.get("pmid")
    if not pmid:
        raise HTTPException(400, "Job has no PMID")

    saved = await _save_upload(job_id, file, upload_type)
    if upload_type == "fulltext":
        await ingest_fulltext(job_id, pmid, str(saved))
        msg = "Full text uploaded. Click Continue to proceed."
    else:
        await ingest_supplementary(job_id, pmid, str(saved))
        msg = "Supplementary file uploaded. Click Continue to proceed."

    return CollectionUploadResponse(
        job_id=job_id,
        upload_type=upload_type,  # type: ignore[arg-type]
        filename=file.filename or saved.name,
        message=msg,
    )


@router.post("/jobs/{job_id}/resume", response_model=CollectionJobResponse)
async def resume_collection_job(job_id: str) -> CollectionJobResponse:
    if not job_dir(job_id).exists():
        raise HTTPException(404, "Job not found")
    state = job_state_to_response(job_id)
    pmid = state.get("pmid")
    if not pmid:
        raise HTTPException(400, "Job has no PMID")
    await resume_job(job_id, pmid)
    return CollectionJobResponse(**job_state_to_response(job_id, pmid))


@router.get("/jobs/{job_id}/artifacts/metadata")
async def get_metadata_artifact(job_id: str) -> dict:
    if not job_dir(job_id).exists():
        raise HTTPException(404, "Job not found")
    state = job_state_to_response(job_id)
    row = (state.get("summary") or {}).get("stage3Row")
    if row:
        return {"row": row}
    path = stage3_artifact(job_id)
    if not path:
        raise HTTPException(404, "Metadata not ready")
    with path.open(encoding="utf-8", errors="replace") as fh:
        reader = csv.DictReader(fh)
        for raw in reader:
            if (raw.get("PMID") or "").strip() == str(state.get("pmid") or ""):
                return {"row": raw}
    raise HTTPException(404, "Metadata row not found")


@router.get("/jobs/{job_id}/download/literature_info")
async def download_literature_info(job_id: str) -> FileResponse:
    path = stage3_artifact(job_id)
    if not path:
        raise HTTPException(404, "literature_info.csv not ready")
    return FileResponse(path, filename=f"literature_info_{job_id[:8]}.csv", media_type="text/csv")


@router.get("/jobs/{job_id}/download/qratio")
async def download_qratio(job_id: str) -> FileResponse:
    path = stage5_artifact(job_id)
    if not path:
        raise HTTPException(404, "qratio.csv not ready")
    return FileResponse(path, filename=f"qratio_{job_id[:8]}.csv", media_type="text/csv")
