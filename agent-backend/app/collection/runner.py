"""Subprocess runner for collection-agent CLI."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any, AsyncIterator

from app.collection.store import job_dir, read_job_json
from app.config import settings

logger = logging.getLogger(__name__)

_running: dict[str, asyncio.Task] = {}

_STAGE_ORDER = ("stage1", "stage2", "stage3", "stage4", "stage5", "stage6")


def _node_bin() -> str:
    return settings.collection_node_bin


def _npx_bin() -> str:
    node_dir = Path(_node_bin()).parent
    candidate = node_dir / "npx"
    return str(candidate) if candidate.is_file() else "npx"


def _collection_env() -> dict[str, str]:
    env = os.environ.copy()
    env["NODE_ENV"] = env.get("NODE_ENV", "production")
    if settings.deepseek_api_key and not env.get("OPENCODE_API_KEY"):
        env["OPENCODE_API_KEY"] = settings.deepseek_api_key
    if settings.deepseek_model and not env.get("MODEL"):
        env["MODEL"] = f"opencode-go/{settings.deepseek_model}"
    if settings.unpaywall_email:
        env["UNPAYWALL_EMAIL"] = settings.unpaywall_email
    if settings.ncbi_api_key:
        env["NCBI_API_KEY"] = settings.ncbi_api_key
    if settings.ncbi_email:
        env["NCBI_EMAIL"] = settings.ncbi_email
    if settings.qptm3_get_url_dir:
        env["QPTM3_GET_URL_DIR"] = settings.qptm3_get_url_dir
    env["PATH"] = f"{Path(_node_bin()).parent}:{env.get('PATH', '')}"
    return env


def _cli_base() -> list[str]:
    index = Path(settings.collection_agent_dir) / "src" / "index.ts"
    return [_npx_bin(), "tsx", str(index)]


async def _run_cli(
    job_id: str,
    args: list[str],
    *,
    log_name: str = "job.log",
) -> tuple[int, str]:
    out = job_dir(job_id)
    log_path = out / log_name
    cmd = _cli_base() + args
    logger.info("collection job %s: %s", job_id, " ".join(cmd))
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=settings.collection_agent_dir,
        env=_collection_env(),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    chunks: list[str] = []
    assert proc.stdout is not None
    async for raw in proc.stdout:
        text = raw.decode("utf-8", errors="replace")
        chunks.append(text)
    code = await proc.wait()
    log_path.write_text("".join(chunks), encoding="utf-8")
    return code, "".join(chunks)


async def run_collection_job(
    job_id: str,
    pmid: str,
    *,
    fulltext_path: str | None = None,
    supplementary_path: str | None = None,
    resume_from: str | None = None,
) -> dict[str, Any] | None:
    args = [
        "run-job",
        "--pmid",
        pmid,
        "--out-dir",
        str(job_dir(job_id)),
        "--job-id",
        job_id,
        "--concurrency",
        "2",
    ]
    if fulltext_path:
        args.extend(["--file", fulltext_path])
    if supplementary_path:
        args.extend(["--supp-file", supplementary_path])
    if resume_from:
        args.extend(["--resume-from", resume_from])

    code, output = await _run_cli(job_id, args)
    state = read_job_json(job_id)
    if state is None:
        raise RuntimeError(f"Job finished without job.json (exit {code}): {output[-2000:]}")
    terminal = state.get("status") in (
        "awaiting_upload",
        "awaiting_continue",
        "completed",
        "rejected",
    )
    if code != 0 and not terminal:
        raise RuntimeError(state.get("error") or output[-2000:] or f"exit code {code}")
    return state


async def ingest_fulltext(job_id: str, pmid: str, file_path: str) -> None:
    code, output = await _run_cli(
        job_id,
        [
            "ingest-fulltext",
            "--pmid",
            pmid,
            "--file",
            file_path,
            "--out-dir",
            str(job_dir(job_id)),
        ],
        log_name="ingest-fulltext.log",
    )
    if code != 0:
        raise RuntimeError(output[-2000:] or f"ingest-fulltext failed ({code})")


async def ingest_supplementary(job_id: str, pmid: str, file_path: str) -> None:
    code, output = await _run_cli(
        job_id,
        [
            "ingest-supp",
            "--pmid",
            pmid,
            "--file",
            file_path,
            "--out-dir",
            str(job_dir(job_id)),
        ],
        log_name="ingest-supp.log",
    )
    if code != 0:
        raise RuntimeError(output[-2000:] or f"ingest-supp failed ({code})")


def _resume_from_state(state: dict[str, Any]) -> str | None:
    next_stage = state.get("nextStage")
    if next_stage:
        return str(next_stage)
    awaiting = state.get("awaitingUpload")
    if awaiting == "fulltext":
        return "stage2"
    if awaiting == "supplementary":
        return "stage5"
    return None


async def schedule_job(
    job_id: str,
    pmid: str,
    *,
    fulltext_path: str | None = None,
    supplementary_path: str | None = None,
    resume_from: str | None = None,
) -> None:
    if job_id in _running and not _running[job_id].done():
        return

    async def _worker() -> None:
        try:
            await run_collection_job(
                job_id,
                pmid,
                fulltext_path=fulltext_path,
                supplementary_path=supplementary_path,
                resume_from=resume_from,
            )
        except Exception as exc:
            logger.exception("collection job %s failed", job_id)
            job_path = job_dir(job_id) / "job.json"
            payload = read_job_json(job_id) or {
                "jobId": job_id,
                "pmid": pmid,
                "stages": {},
                "summary": {},
            }
            payload.update(
                {
                    "status": "error",
                    "error": str(exc),
                    "message": f"Collection failed: {exc}",
                }
            )
            job_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        finally:
            _running.pop(job_id, None)

    _running[job_id] = asyncio.create_task(_worker())


async def resume_job(job_id: str, pmid: str) -> None:
    state = read_job_json(job_id) or {}
    resume_from = _resume_from_state(state)
    if not resume_from:
        resume_from = "stage1"
    # Clear pause flags before resuming
    job_path = job_dir(job_id) / "job.json"
    if job_path.is_file():
        payload = read_job_json(job_id) or {}
        payload["status"] = "running"
        payload["awaitingUpload"] = None
        job_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    await schedule_job(job_id, pmid, resume_from=resume_from)


async def resume_after_upload(job_id: str, pmid: str) -> None:
    await resume_job(job_id, pmid)


def job_state_to_response(job_id: str, pmid: str | None = None) -> dict[str, Any]:
    state = read_job_json(job_id) or {}
    return {
        "job_id": job_id,
        "pmid": state.get("pmid") or pmid,
        "status": state.get("status", "pending"),
        "current_stage": state.get("currentStage"),
        "next_stage": state.get("nextStage"),
        "awaiting_upload": state.get("awaitingUpload"),
        "message": state.get("message", ""),
        "stages": state.get("stages") or {},
        "summary": state.get("summary") or {},
        "error": state.get("error"),
        "needs_pmid": False,
    }


async def watch_job_events(job_id: str) -> AsyncIterator[dict[str, Any]]:
    """Poll job.json and emit SSE-friendly events."""
    last = ""
    while True:
        state = read_job_json(job_id)
        if state:
            blob = json.dumps(state, sort_keys=True)
            if blob != last:
                last = blob
                yield {"event": "status", "data": job_state_to_response(job_id)}
            status = state.get("status")
            if status in ("completed", "rejected", "error", "awaiting_upload", "awaiting_continue"):
                if status == "completed":
                    yield {"event": "done", "data": job_state_to_response(job_id)}
                elif status == "rejected":
                    yield {"event": "rejected", "data": job_state_to_response(job_id)}
                elif status == "awaiting_upload":
                    yield {
                        "event": "awaiting_upload",
                        "data": job_state_to_response(job_id),
                    }
                elif status == "awaiting_continue":
                    yield {
                        "event": "awaiting_continue",
                        "data": job_state_to_response(job_id),
                    }
                else:
                    yield {"event": "error", "data": job_state_to_response(job_id)}
                return
        await asyncio.sleep(1.0)
