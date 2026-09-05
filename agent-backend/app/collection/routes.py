"""FastAPI routes for Collection Agent jobs."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

from app.collection.models import (
    CollectionContributeRequest,
    CollectionGuidanceRequest,
    CollectionJobCreate,
    CollectionJobResponse,
    CollectionUploadResponse,
    CollectionTableHintsRequest,
    ResolveUrlsRequest,
)
from app.collection.runner import (
    ingest_fulltext,
    ingest_supplementary,
    job_state_to_response,
    resume_job,
    schedule_job,
    schedule_resolve_urls_job,
    watch_job_events,
)
from app.collection.pmid_from_files import resolve_pmid_from_uploads
from app.collection.uploads import classify_upload_filename
from app.collection.store import (
    append_contribution_record,
    empty_optional_csv_columns,
    extract_accessions,
    fulltext_artifact,
    job_dir,
    looks_like_resolve_urls_request,
    looks_like_stage5_guidance,
    mark_upload_ready,
    new_job_id,
    note_wants_protein_log2,
    parse_derived_ratio_specs,
    pmid_exists_in_pubmed,
    pmid_looks_valid,
    read_csv_preview,
    read_job_json,
    read_supp_previews,
    read_table_candidates,
    resolve_guidance_selections,
    resolve_pmid,
    stage3_artifact,
    stage5_artifact,
    stage6_urls_artifact,
    supplementary_zip_artifact,
    uploads_dir,
    write_user_table_hints,
)
from app.config import settings

router = APIRouter(prefix="/collection", tags=["collection"])

_STAGE_ORDER = ("stage1", "stage2", "stage3", "stage4", "stage5", "stage6")

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
    return _write_upload(job_id, upload.filename, content, prefix)


async def _read_upload(upload: UploadFile) -> tuple[str, bytes]:
    if not upload.filename:
        raise HTTPException(400, "Missing filename")
    content = await upload.read()
    _validate_upload(upload.filename, len(content))
    return upload.filename, content


def _safe_upload_name(filename: str) -> str:
    name = Path(filename).name.replace("\\", "_").replace("/", "_").strip()
    return name or "upload.bin"


def _write_upload(job_id: str, filename: str, content: bytes, prefix: str) -> Path:
    # Keep original basename for supplementary tables so multi-file ZIPs retain
    # distinct names (supp1.xlsx + supp2.xlsx). Fulltext still uses a stable prefix.
    if prefix == "supplementary":
        dest = uploads_dir(job_id) / _safe_upload_name(filename)
    else:
        dest = uploads_dir(job_id) / f"{prefix}{Path(filename).suffix.lower()}"
    dest.write_bytes(content)
    return dest


@router.post("/jobs", response_model=CollectionJobResponse)
async def create_job(
    message: str | None = Form(default=None),
    pmid: str | None = Form(default=None),
    fulltext: UploadFile | None = File(default=None),
    supplementary: list[UploadFile] | None = File(default=None),
) -> CollectionJobResponse:
    body = CollectionJobCreate(message=message, pmid=pmid)
    upload_names: list[str] = []
    fulltext_blob: tuple[str, bytes] | None = None
    supplementary_blobs: list[tuple[str, bytes]] = []

    if fulltext and fulltext.filename:
        name, content = await _read_upload(fulltext)
        if classify_upload_filename(name) != "fulltext":
            raise HTTPException(400, f"fulltext field accepts PDF/XML only, got: {name}")
        upload_names.append(name)
        fulltext_blob = (name, content)

    for item in supplementary or []:
        if not item or not item.filename:
            continue
        name, content = await _read_upload(item)
        if classify_upload_filename(name) != "supplementary":
            raise HTTPException(400, f"supplementary field accepts ZIP/Excel/CSV only, got: {name}")
        upload_names.append(name)
        supplementary_blobs.append((name, content))

    resolved_pmid = resolve_pmid(
        pmid=body.pmid if body else None,
        message=body.message if body else None,
        filenames=upload_names,
    )
    if not resolved_pmid:
        blobs: list[tuple[str, bytes]] = []
        if fulltext_blob:
            blobs.append(fulltext_blob)
        blobs.extend(supplementary_blobs)
        if blobs:
            resolved_pmid = await resolve_pmid_from_uploads(blobs)

    if resolved_pmid and not pmid_looks_valid(resolved_pmid):
        return CollectionJobResponse(
            job_id=new_job_id(),
            pmid=resolved_pmid,
            status="error",
            message=(
                f"PMID {resolved_pmid} is invalid. Please check the number "
                "or upload the PDF / supplementary tables instead."
            ),
            needs_pmid=True,
        )

    if resolved_pmid:
        exists = pmid_exists_in_pubmed(resolved_pmid)
        if exists is False:
            return CollectionJobResponse(
                job_id=new_job_id(),
                pmid=resolved_pmid,
                status="error",
                message=(
                    f"PMID {resolved_pmid} was not found in PubMed. "
                    "Please check the identifier or upload the PDF."
                ),
                needs_pmid=True,
            )

    if not resolved_pmid:
        # Accession-only MS URL resolution (PXD / IPX / …) — no PMID pipeline.
        accessions = extract_accessions(body.message or "")
        if accessions and looks_like_resolve_urls_request(body.message):
            job_id = new_job_id()
            root = job_dir(job_id)
            # Seed job.json so the UI can show Stage6 immediately.
            seed = {
                "jobId": job_id,
                "pmid": accessions[0],
                "status": "running",
                "currentStage": "stage6",
                "nextStage": None,
                "awaitingUpload": None,
                "message": f"Resolving MS download URLs for {'; '.join(accessions)}…",
                "stages": {"stage6": "running"},
                "summary": {
                    "resolveUrls": True,
                    "accessions": accessions,
                },
                "updatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            }
            (root / "job.json").write_text(json.dumps(seed, indent=2), encoding="utf-8")
            await schedule_resolve_urls_job(job_id, accessions, message=body.message)
            # resolve_urls is already set from job.json summary.resolveUrls
            return CollectionJobResponse(**job_state_to_response(job_id, accessions[0]))
        return CollectionJobResponse(
            job_id=new_job_id(),
            status="error",
            message=(
                "Could not resolve PMID from the upload. "
                "Tried reading PMID/DOI from the file and matching the article title to PubMed. "
                "Please type a PMID in the message (e.g. 38670996), "
                "or rename the PDF like 38670996.pdf. "
                "To fetch MS download links only, send an accession such as PXD012345."
            ),
            needs_pmid=True,
        )

    job_id = new_job_id()
    job_dir(job_id)
    fulltext_path: str | None = None
    supplementary_paths: list[str] = []

    if fulltext_blob:
        saved = _write_upload(job_id, fulltext_blob[0], fulltext_blob[1], "fulltext")
        fulltext_path = str(saved)

    for name, content in supplementary_blobs:
        saved = _write_upload(job_id, name, content, "supplementary")
        supplementary_paths.append(str(saved))

    await schedule_job(
        job_id,
        resolved_pmid,
        fulltext_path=fulltext_path,
        supplementary_paths=supplementary_paths or None,
    )
    return CollectionJobResponse(**job_state_to_response(job_id, resolved_pmid))


@router.get("/jobs/{job_id}", response_model=CollectionJobResponse)
async def get_job(job_id: str) -> CollectionJobResponse:
    if not job_dir(job_id).exists():
        raise HTTPException(404, "Job not found")
    return CollectionJobResponse(**job_state_to_response(job_id))


@router.post("/resolve-urls", response_model=CollectionJobResponse)
async def resolve_urls(body: ResolveUrlsRequest) -> CollectionJobResponse:
    """Resolve PRIDE / iProX / jPOST / MassIVE / PDC download URLs for accessions."""
    accessions: list[str] = []
    for raw in [body.accession, *(body.accessions or [])]:
        if raw:
            accessions.extend(extract_accessions(str(raw)))
    if body.message:
        accessions.extend(extract_accessions(body.message))
    # Dedupe preserving order
    seen: set[str] = set()
    uniq: list[str] = []
    for a in accessions:
        if a in seen:
            continue
        seen.add(a)
        uniq.append(a)
    if not uniq and body.message and looks_like_resolve_urls_request(body.message):
        uniq = extract_accessions(body.message)
    if not uniq:
        raise HTTPException(
            400,
            "Provide at least one MS accession (PXD… / IPX… / JPST… / MSV… / PDC…)",
        )

    job_id = new_job_id()
    root = job_dir(job_id)
    seed = {
        "jobId": job_id,
        "pmid": body.pmid or uniq[0],
        "status": "running",
        "currentStage": "stage6",
        "nextStage": None,
        "awaitingUpload": None,
        "message": f"Resolving MS download URLs for {'; '.join(uniq)}…",
        "stages": {"stage6": "running"},
        "summary": {
            "resolveUrls": True,
            "accessions": uniq,
        },
        "updatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    (root / "job.json").write_text(json.dumps(seed, indent=2), encoding="utf-8")
    await schedule_resolve_urls_job(
        job_id,
        uniq,
        pmid=body.pmid,
        title=body.title,
        organism=body.organism,
        modification=body.modification,
        message=body.message,
    )
    # resolve_urls is already set from job.json summary.resolveUrls
    return CollectionJobResponse(**job_state_to_response(job_id, body.pmid or uniq[0]))


@router.get("/jobs/{job_id}/stream")
async def stream_job(job_id: str) -> StreamingResponse:
    if not job_dir(job_id).exists():
        raise HTTPException(404, "Job not found")

    async def event_gen():
        async for item in watch_job_events(job_id):
            yield f"event: {item['event']}\ndata: {json.dumps(item['data'])}\n\n"

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/jobs/{job_id}/upload", response_model=CollectionJobResponse)
async def upload_file(
    job_id: str,
    upload_type: str = Form(""),
    file: UploadFile = File(...),
) -> CollectionJobResponse:
    if not job_dir(job_id).exists():
        raise HTTPException(404, "Job not found")

    state = job_state_to_response(job_id)
    pmid = state.get("pmid")
    if not pmid:
        raise HTTPException(400, "Job has no PMID")

    kind = (upload_type or "").strip().lower()
    if kind not in ("fulltext", "supplementary"):
        # Infer from job state or filename when the client omits / loses upload_type.
        awaiting = state.get("awaiting_upload")
        if awaiting in ("fulltext", "supplementary"):
            kind = awaiting
        else:
            kind = classify_upload_filename(file.filename or "") or ""
            if kind not in ("fulltext", "supplementary"):
                stage = state.get("current_stage") or ""
                if stage == "stage2":
                    kind = "fulltext"
                elif stage in ("stage4", "stage5"):
                    kind = "supplementary"
    if kind not in ("fulltext", "supplementary"):
        raise HTTPException(400, "upload_type must be fulltext or supplementary")

    saved = await _save_upload(job_id, file, kind)
    if kind == "fulltext":
        await ingest_fulltext(job_id, pmid, str(saved))
        msg = (
            "Full text is ready, "
            "then click Continue to extract literature metadata."
        )
    else:
        await ingest_supplementary(job_id, pmid, str(saved))
        msg = (
            "User-uploaded supplementary tables detected, "
            "then click Continue to parse quantitative data."
        )

    mark_upload_ready(job_id, upload_type=kind, message=msg)
    return CollectionJobResponse(**job_state_to_response(job_id, str(pmid)))


@router.post("/jobs/{job_id}/resume", response_model=CollectionJobResponse)
async def resume_collection_job(job_id: str, request: Request) -> CollectionJobResponse:
    if not job_dir(job_id).exists():
        raise HTTPException(404, "Job not found")
    state = job_state_to_response(job_id)
    pmid = state.get("pmid")
    if not pmid:
        raise HTTPException(400, "Job has no PMID")
    # Honor the stage the UI is showing (its "Continue" target) when provided.
    resume_from: str | None = None
    force_include = False
    try:
        body = await request.json()
        candidate = (body or {}).get("resume_from")
        if candidate:
            candidate = str(candidate).strip()
            if candidate in _STAGE_ORDER and candidate != "stage1":
                resume_from = candidate
        force_include = bool((body or {}).get("force_include"))
    except Exception:
        pass
    await resume_job(job_id, pmid, resume_from=resume_from, force_include=force_include)
    return CollectionJobResponse(**job_state_to_response(job_id, pmid))


@router.post("/jobs/{job_id}/contribute", response_model=CollectionJobResponse)
async def contribute_collection_job(
    job_id: str,
    body: CollectionContributeRequest,
) -> CollectionJobResponse:
    """Record whether the user is willing to contribute curated tables to qPTM."""
    root = job_dir(job_id)
    if not root.exists():
        raise HTTPException(404, "Job not found")
    state = read_job_json(job_id) or {}
    row_count = int((state.get("summary") or {}).get("qratioRowCount") or 0)
    status = state.get("status")
    # Allow after Stage5 parse (awaiting_continue) or final completion.
    if status not in ("completed", "awaiting_continue") or row_count <= 0:
        raise HTTPException(
            400,
            "Contribution is only available after quantitative tables have been parsed",
        )
    if body.willing and row_count <= 0:
        raise HTTPException(400, "No qratio rows available to contribute")

    state["contribution"] = {
        "willing": body.willing,
        "respondedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "note": (body.note or "").strip() or None,
    }
    state["offerContribute"] = False
    if body.willing:
        # Record the contribution intent centrally so curators can pull the
        # curated data (PMID links to the job's artifacts via jobId).
        append_contribution_record(
            str(state.get("pmid") or ""),
            job_id=job_id,
            note=body.note,
        )
        state["message"] = (
            (state.get("message") or "").rstrip()
            + "\n\nThank you for offering to contribute to qPTM! "
        )
    else:
        state["message"] = (
            (state.get("message") or "").rstrip()
            + "\n\nNoted: not contributing for now. "
            "You can still download the curated CSV files for your own use."
        )
    state["updatedAt"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    (root / "job.json").write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    # Also append a lightweight audit line for curators
    audit = root / "contribution.jsonl"
    with audit.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"pmid": state.get("pmid"), **state["contribution"]}, ensure_ascii=False) + "\n")
    return CollectionJobResponse(**job_state_to_response(job_id))


@router.get("/jobs/{job_id}/artifacts/metadata")
async def get_metadata_artifact(job_id: str) -> dict:
    if not job_dir(job_id).exists():
        raise HTTPException(404, "Job not found")
    state = job_state_to_response(job_id)
    row = (state.get("summary") or {}).get("stage3Row")
    if row:
        return {"row": row}
    pmid = str(state.get("pmid") or "").strip()
    path = stage3_artifact(job_id)
    if path:
        with path.open(encoding="utf-8", errors="replace") as fh:
            reader = csv.DictReader(fh)
            for raw in reader:
                if (raw.get("PMID") or "").strip() == pmid:
                    return {"row": raw}
    # Fall back to stage3_results.jsonl (includes error shells when literature_info is empty).
    jsonl = stage3_artifact(job_id, "stage3_results.jsonl")
    if jsonl and pmid:
        try:
            for line in jsonl.read_text(encoding="utf-8", errors="replace").splitlines():
                t = line.strip()
                if not t:
                    continue
                obj = json.loads(t)
                if str(obj.get("pmid") or "").strip() != pmid:
                    continue
                return {
                    "row": {
                        "PMID": obj.get("pmid") or "",
                        "Title": obj.get("title") or "",
                        "Sample": obj.get("sample") or "",
                        "Sample type": obj.get("sampleType") or "",
                        "Organism": obj.get("organism") or "",
                        "PTMs": obj.get("ptms") or "",
                        "Label method": obj.get("labelMethod") or "",
                        "Condition": obj.get("condition") or "",
                        "Detail condition": obj.get("detailCondition") or "",
                        "Enrichment method": obj.get("enrichmentMethod") or "",
                        "Mass spectrometer": obj.get("massSpectrometer") or "",
                        "MS data source": obj.get("msDataSource") or "",
                        "Identifier": obj.get("identifier") or "",
                        "status": obj.get("status") or "",
                        "notes": obj.get("notes") or "",
                        "error": obj.get("error") or "",
                    }
                }
        except (OSError, json.JSONDecodeError):
            pass
    raise HTTPException(404, "Metadata row not found")


@router.get("/jobs/{job_id}/artifacts/table-candidates")
async def get_table_candidates(job_id: str) -> dict:
    """List supplementary file/sheet candidates for user teaching / selection."""
    if not job_dir(job_id).exists():
        raise HTTPException(404, "Job not found")
    state = job_state_to_response(job_id)
    pmid = state.get("pmid")
    if not pmid:
        raise HTTPException(400, "Job has no PMID")
    candidates = read_table_candidates(job_id, str(pmid))
    summary = state.get("summary") or {}
    return {
        "pmid": pmid,
        "candidates": candidates,
        "stage4Scout": summary.get("stage4Scout"),
        "stage5Thinking": summary.get("stage5Thinking") or [],
        "needsTableHints": bool(summary.get("needsTableHints")),
    }


@router.get("/jobs/{job_id}/artifacts/supp-preview")
async def get_supp_preview(job_id: str) -> dict:
    """Peek top supplementary tables: column names + first rows for Stage4 UI."""
    if not job_dir(job_id).exists():
        raise HTTPException(404, "Job not found")
    state = job_state_to_response(job_id)
    pmid = state.get("pmid")
    if not pmid:
        raise HTTPException(400, "Job has no PMID")
    files = read_supp_previews(job_id, str(pmid))
    return {"pmid": pmid, "files": files}


_QRATIO_OPTIONAL_COLS = (
    "Localization probability",
    "Localization",  # legacy header from earlier builds
    "PEP",
)


@router.get("/jobs/{job_id}/artifacts/qratio-preview")
async def get_qratio_preview(job_id: str, max_rows: int = 10) -> dict:
    """First N rows of stage5/qratio.csv for Stage5 UI."""
    if not job_dir(job_id).exists():
        raise HTTPException(404, "Job not found")
    path = stage5_artifact(job_id)
    if not path:
        raise HTTPException(404, "qratio.csv not ready")
    rows = max(1, min(int(max_rows or 10), 50))
    preview = read_csv_preview(
        path,
        max_rows=rows,
        drop_empty_columns=list(_QRATIO_OPTIONAL_COLS),
    )
    return {"pmid": (job_state_to_response(job_id) or {}).get("pmid"), **preview}


@router.get("/jobs/{job_id}/artifacts/ms-urls-preview")
async def get_ms_urls_preview(job_id: str, max_rows: int = 5) -> dict:
    """First N rows of stage6/urls_all.csv for Stage6 UI."""
    if not job_dir(job_id).exists():
        raise HTTPException(404, "Job not found")
    path = stage6_urls_artifact(job_id)
    if not path:
        raise HTTPException(404, "urls_all.csv not ready")
    rows = max(1, min(int(max_rows or 5), 50))
    preview = read_csv_preview(path, max_rows=rows, drop_columns=["is_raw"])
    return {"pmid": (job_state_to_response(job_id) or {}).get("pmid"), **preview}


@router.post("/jobs/{job_id}/table-hints")
async def post_table_hints(job_id: str, body: CollectionTableHintsRequest) -> dict:
    """Save user-selected tables/sheets, optionally resume Stage 5 parse."""
    if not job_dir(job_id).exists():
        raise HTTPException(404, "Job not found")
    state = job_state_to_response(job_id)
    pmid = state.get("pmid")
    if not pmid:
        raise HTTPException(400, "Job has no PMID")

    selections = [s.model_dump() for s in body.selections]
    prefer = body.prefer_protein_log2
    if prefer is None:
        prefer = note_wants_protein_log2(body.note or "")

    derived = parse_derived_ratio_specs(body.note or "")

    # Allow note-only guidance: resolve filenames mentioned in the note.
    if not selections and body.note:
        resolved, prefer_note, _matched, derived_note = resolve_guidance_selections(
            job_id, str(pmid), body.note
        )
        selections = resolved
        prefer = prefer or prefer_note
        if not derived:
            derived = derived_note

    if not selections and not (body.note or "").strip():
        raise HTTPException(400, "Select at least one file/sheet, or describe it in the note")

    # Fill sheet names from note "file → Sheet" when checkbox selection omitted sheet
    if body.note and selections:
        resolved, _p, _m, derived_note = resolve_guidance_selections(
            job_id, str(pmid), body.note
        )
        if not derived:
            derived = derived_note
        by_entry = {
            str(r.get("entryPath") or "").lower(): r for r in resolved if r.get("sheetName")
        }
        for sel in selections:
            if sel.get("sheetName"):
                continue
            hit = by_entry.get(str(sel.get("entryPath") or "").lower())
            if hit and hit.get("sheetName"):
                sel["sheetName"] = hit["sheetName"]

    hints = write_user_table_hints(
        job_id,
        str(pmid),
        selections,
        note=body.note,
        prefer_protein_log2=prefer,
        derived_ratios=derived,
    )

    # Mirror into job summary for the UI
    root = job_dir(job_id)
    raw = read_job_json(job_id) or {}
    summary = dict(raw.get("summary") or {})
    summary["userTableHints"] = hints
    summary["needsTableHints"] = False
    summary["allowTableHints"] = True
    summary["allowSkipToMsUrls"] = False
    raw["summary"] = summary
    raw["status"] = "running" if body.resume else raw.get("status") or "awaiting_continue"
    raw["currentStage"] = "stage5"
    raw["nextStage"] = "stage5"
    raw["awaitingUpload"] = None
    derived_note = ""
    if hints.get("derivedRatios"):
        labels = [
            ("log2(" + d["condition"] + ")" if d.get("isLog2", True) else d["condition"])
            for d in hints["derivedRatios"]
        ]
        derived_note = f" Derived contrasts: {', '.join(labels)}."
    raw["message"] = (
        f"Saved table guidance ({len(hints.get('selections') or [])} file(s))."
        + derived_note
        + (" Re-parsing quantitative tables…" if body.resume else " Click Continue to re-parse.")
    )
    raw["updatedAt"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    (root / "job.json").write_text(json.dumps(raw, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if body.resume:
        await resume_job(job_id, str(pmid))

    return {
        "hints": hints,
        "job": job_state_to_response(job_id, str(pmid)),
    }


@router.post("/jobs/{job_id}/guidance")
async def post_stage5_guidance(job_id: str, body: CollectionGuidanceRequest) -> dict:
    """Interpret free-text Stage5 feedback, save hints, and optionally re-parse."""
    if not job_dir(job_id).exists():
        raise HTTPException(404, "Job not found")
    state = job_state_to_response(job_id)
    pmid = state.get("pmid")
    if not pmid:
        raise HTTPException(400, "Job has no PMID")
    message = (body.message or "").strip()
    if not message:
        raise HTTPException(400, "message is required")

    selections, prefer, matched, derived = resolve_guidance_selections(
        job_id, str(pmid), message
    )
    if (
        not selections
        and not prefer
        and not derived
        and not looks_like_stage5_guidance(message)
    ):
        raise HTTPException(
            400,
            "Could not interpret this as Stage5 table guidance. "
            "Mention an Excel/CSV filename (e.g. pr2c00756_si_002.xlsx), "
            "a sheet (file → Sheet), contrasts like log2(P5/P1), "
            "or sample/sheet mapping (e.g. each sheet is a different sample).",
        )

    # If user only asked about protein Log2Ratio / derived ratios with no file, still re-parse
    hints = write_user_table_hints(
        job_id,
        str(pmid),
        selections,
        note=message,
        prefer_protein_log2=prefer or note_wants_protein_log2(message),
        derived_ratios=derived,
    )

    root = job_dir(job_id)
    raw = read_job_json(job_id) or {}
    summary = dict(raw.get("summary") or {})
    summary["userTableHints"] = hints
    summary["needsTableHints"] = False
    summary["allowTableHints"] = True
    raw["summary"] = summary
    raw["status"] = "running" if body.resume else "awaiting_continue"
    raw["currentStage"] = "stage5"
    raw["nextStage"] = "stage5"
    raw["awaitingUpload"] = None

    parts: list[str] = []
    if matched:
        sheet_bits = []
        for sel in selections:
            ep = sel.get("entryPath") or ""
            sn = sel.get("sheetName")
            sheet_bits.append(f"{ep} → {sn}" if sn else ep)
        parts.append(f"will use {', '.join(sheet_bits)}")
    if prefer:
        parts.append("prefer protein Log2Ratio")
    if derived:
        labels = [
            f"log2({d['condition']})" if d.get("isLog2", True) else d["condition"]
            for d in derived
        ]
        parts.append(f"compute {', '.join(labels)}")
    detail = "; ".join(parts)
    if detail:
        ack = (
            f"Understood — {detail}. "
            + ("Re-parsing…" if body.resume else "Click Continue to re-parse.")
        )
    else:
        ack = (
            "Saved your Stage5 guidance. "
            + ("Re-parsing quantitative tables…" if body.resume else "Click Continue to re-parse.")
        )
    raw["message"] = ack
    raw["updatedAt"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    (root / "job.json").write_text(json.dumps(raw, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if body.resume:
        await resume_job(job_id, str(pmid))

    return {
        "hints": hints,
        "matched_files": matched,
        "prefer_protein_log2": bool(hints.get("preferProteinLog2")),
        "derived_ratios": hints.get("derivedRatios") or [],
        "message": ack,
        "job": job_state_to_response(job_id, str(pmid)),
    }


_UTF8_BOM = b"\xef\xbb\xbf"
_CSV_CHUNK = 1024 * 1024


def _download_pmid_tag(job_id: str) -> str:
    """Filename tag for Stage3/5/6 downloads: real PMID (or accession), not job UUID."""
    state = read_job_json(job_id) or {}
    raw = str(state.get("pmid") or "").strip()
    if not raw:
        accessions = (state.get("summary") or {}).get("accessions") or []
        if isinstance(accessions, list) and accessions:
            raw = str(accessions[0] or "").strip()
    safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in raw)
    return safe or job_id[:8]


def _iter_csv_with_bom(path: Path):
    """Stream a UTF-8 CSV, prepending a BOM so Excel decodes β/µ/etc. correctly.

    Files are written as plain UTF-8 (no BOM); Windows Excel opens them with the
    ANSI codepage (GBK on Chinese systems), which mis-reads multi-byte chars
    (UTF-8 β = CE B2 → GBK "尾"). A leading UTF-8 BOM forces Excel to use UTF-8.
    """
    with path.open("rb") as fh:
        head = fh.read(len(_UTF8_BOM))
        if head != _UTF8_BOM:
            yield _UTF8_BOM
            yield head
        else:
            yield head
        while True:
            chunk = fh.read(_CSV_CHUNK)
            if not chunk:
                break
            yield chunk


def _csv_response(path: Path, filename: str) -> StreamingResponse:
    return StreamingResponse(
        _iter_csv_with_bom(path),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _csv_response_drop_columns(
    path: Path,
    filename: str,
    drop: set[str],
) -> StreamingResponse:
    """Stream CSV with selected columns removed (e.g. hide Condition-Sample map)."""

    def _gen():
        text = path.read_text(encoding="utf-8", errors="replace")
        reader = csv.reader(text.splitlines())
        rows = list(reader)
        if not rows:
            yield _UTF8_BOM
            return
        header = [(h or "").lstrip("\ufeff") for h in rows[0]]
        keep = [i for i, h in enumerate(header) if h not in drop]
        out_lines: list[str] = []
        for row in rows:
            cells = [row[i] if i < len(row) else "" for i in keep]
            out_lines.append(",".join(_csv_escape_cell(c) for c in cells))
        body = ("\n".join(out_lines) + "\n").encode("utf-8")
        if not body.startswith(_UTF8_BOM):
            yield _UTF8_BOM
        yield body

    return StreamingResponse(
        _gen(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _csv_escape_cell(value: str) -> str:
    s = str(value)
    if any(c in s for c in (',', '"', "\n", "\r")):
        return '"' + s.replace('"', '""') + '"'
    return s


@router.get("/jobs/{job_id}/download/literature_info")
async def download_literature_info(job_id: str):
    path = stage3_artifact(job_id)
    if not path:
        raise HTTPException(404, "Experimental_info.csv not ready")
    tag = _download_pmid_tag(job_id)
    return _csv_response_drop_columns(
        path,
        f"Experimental_info_{tag}.csv",
        {"Condition-Sample map"},
    )

@router.get("/jobs/{job_id}/download/fulltext")
async def download_fulltext(job_id: str) -> FileResponse:
    if not job_dir(job_id).exists():
        raise HTTPException(404, "Job not found")
    path = fulltext_artifact(job_id)
    if not path:
        raise HTTPException(404, "Full text not available")
    media = "application/pdf" if path.suffix.lower() == ".pdf" else "application/xml"
    tag = _download_pmid_tag(job_id)
    return FileResponse(path, filename=f"{path.stem}_{tag}{path.suffix}", media_type=media)


@router.get("/jobs/{job_id}/download/supplementary")
async def download_supplementary(job_id: str) -> FileResponse:
    if not job_dir(job_id).exists():
        raise HTTPException(404, "Job not found")
    path = supplementary_zip_artifact(job_id)
    if not path:
        raise HTTPException(404, "Supplementary ZIP not available")
    tag = _download_pmid_tag(job_id)
    return FileResponse(
        path,
        filename=f"supplementary_{tag}.zip",
        media_type="application/zip",
    )


@router.get("/jobs/{job_id}/download/qratio")
async def download_qratio(job_id: str):
    path = stage5_artifact(job_id)
    if not path:
        raise HTTPException(404, "Quantitative_data.csv not ready")
    tag = _download_pmid_tag(job_id)
    drop = empty_optional_csv_columns(path, list(_QRATIO_OPTIONAL_COLS))
    if drop:
        return _csv_response_drop_columns(
            path,
            f"Quantitative_data_{tag}.csv",
            drop,
        )
    return _csv_response(path, f"Quantitative_data_{tag}.csv")


@router.get("/jobs/{job_id}/download/ms-urls")
async def download_ms_urls(job_id: str):
    path = stage6_urls_artifact(job_id)
    if not path:
        raise HTTPException(404, "MS_URLs.csv not ready")
    tag = _download_pmid_tag(job_id)
    return _csv_response(path, f"MS_URLs_{tag}.csv")
