"""In-memory + filesystem collection job store."""

from __future__ import annotations

import csv
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import settings

_PMID_RE = re.compile(r"\b(?:PMID[:\s#]*)?(\d{7,8})\b", re.I)
_STEM_PMID_RE = re.compile(r"^(\d{7,8})$")
# Do not use \\b: CJK chars are Unicode "word" chars, so "中PXD…" would miss.
_ACCESSION_RE = re.compile(
    r"(?<![A-Za-z0-9_])((?:PXD|IPX|JPST|MSV|PDC)\d+)(?![A-Za-z0-9_])",
    re.I,
)
_RESOLVE_URLS_RE = re.compile(
    r"("
    r"download\s*url|download\s*link|ftp\s*link|raw\s*file|"
    r"ms\s*url|pride|iprox|jpost|massive|cptac|proteomexchange|"
    r"resolve[- ]?url|get[- ]?url|"
    r"下载链接|下载地址|质谱.*下载|原始数据|获取.*链接|解析.*链接"
    r")",
    re.I,
)


def extract_accessions(text: str | None) -> list[str]:
    """Unique MS repository accessions in appearance order."""
    if not text:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for m in _ACCESSION_RE.finditer(text):
        acc = m.group(1).upper()
        if acc in seen:
            continue
        seen.add(acc)
        out.append(acc)
    return out


def looks_like_resolve_urls_request(message: str | None) -> bool:
    """True when the user asks for MS download links by accession (no PMID job)."""
    text = (message or "").strip()
    if not text:
        return False
    accessions = extract_accessions(text)
    if not accessions:
        return False
    if _RESOLVE_URLS_RE.search(text):
        return True
    # Bare accession(s) only, e.g. "PXD012345" or "PXD1; IPX2"
    stripped = _ACCESSION_RE.sub(" ", text)
    stripped = re.sub(r"[\s,;:/|=#\-]+", "", stripped)
    return len(stripped) == 0

# agent-backend/ — relative CONVERSATIONS / COLLECTION_JOBS paths resolve here.
# Collection job dirs themselves live under collection-agent/runtime (absolute
# default); relative env values like ../collection-agent/runtime/... still work.
_BACKEND_ROOT = Path(__file__).resolve().parent.parent


def resolve_backend_path(path: str | Path) -> Path:
    """Absolute path under agent-backend when `path` is relative."""
    p = Path(path)
    if not p.is_absolute():
        p = _BACKEND_ROOT / p
    return p.resolve()


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
    root = resolve_backend_path(settings.collection_jobs_dir)
    root.mkdir(parents=True, exist_ok=True)
    return root


def collection_root() -> Path:
    """Parent of jobs dir — holds cross-job logs (e.g. contributions.jsonl)."""
    root = resolve_backend_path(settings.collection_jobs_dir).parent
    root.mkdir(parents=True, exist_ok=True)
    return root


def contributions_log_path() -> Path:
    """Centralized log of users who chose "Yes, contribute" (curator-facing)."""
    return collection_root() / "contributions.jsonl"


def append_contribution_record(
    pmid: str,
    *,
    job_id: str | None = None,
    note: str | None = None,
) -> None:
    """Append one contributor intent line to the centralized curator log.

    The frontend only sends the intent ("Yes, contribute"); the PMID is the key
    payload — the full curated data stays in the job's own directory and is
    linked here via jobId so curators can pull the artifacts.
    """
    record = {
        "pmid": pmid,
        "contributedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    if job_id:
        record["jobId"] = job_id
    if note and note.strip():
        record["note"] = note.strip()
    with contributions_log_path().open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


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


def write_job_json(job_id: str, state: dict[str, Any]) -> None:
    path = job_dir(job_id) / "job.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def refresh_artifact_summary(job_id: str, summary: dict[str, Any] | None = None) -> dict[str, Any]:
    """Attach downloadable artifact flags for the interactive UI."""
    out = dict(summary or {})
    ft = fulltext_artifact(job_id)
    if ft is None:
        kind = None
    elif ft.suffix.lower() == ".pdf":
        kind = "pdf"
    else:
        kind = "xml"
    out["artifacts"] = {
        "fulltextKind": kind,
        "hasSupplementary": supplementary_zip_artifact(job_id) is not None,
        "hasQratio": stage5_artifact(job_id) is not None,
        "hasMsUrls": stage6_urls_artifact(job_id) is not None,
        # Only offer download chips for agent-fetched artifacts (not user uploads).
        "fulltextUserUpload": fulltext_is_user_upload(job_id),
        "supplementaryUserUpload": supplementary_is_user_upload(job_id)
        or str(out.get("stage4Source") or "") == "user_upload",
    }
    return out


def mark_upload_ready(
    job_id: str,
    *,
    upload_type: str,
    message: str,
) -> dict[str, Any]:
    """After a successful user upload, move job to awaiting_continue for the UI."""
    state = read_job_json(job_id) or {}
    state["status"] = "awaiting_continue"
    state["awaitingUpload"] = None
    state["message"] = message
    state["updatedAt"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    # Keep the user on the stage that asked for the upload.
    current = state.get("currentStage")
    if upload_type == "fulltext":
        state["currentStage"] = "stage2"
        if not state.get("nextStage"):
            state["nextStage"] = "stage3"
        stages = dict(state.get("stages") or {})
        stages["stage2"] = "completed"
        state["stages"] = stages
    elif upload_type == "supplementary":
        # Upload was requested from stage4 (or stage5 empty-parse). Stay focused there.
        if current not in ("stage4", "stage5"):
            state["currentStage"] = "stage4"
        # Fresh supplementary upload always re-runs Stage5 parse — even when the
        # prior pause offered skip-to-Stage6 (allowSkipToMsUrls / nextStage=stage6).
        if current == "stage5":
            state["nextStage"] = "stage5"
        elif not state.get("nextStage"):
            state["nextStage"] = "stage5"
        stages = dict(state.get("stages") or {})
        stages["stage4"] = "completed"
        state["stages"] = stages
        # Fresh upload: clear prior parse-failure hints so UI waits for auto-parse first.
        prior_summary = state.get("summary") if isinstance(state.get("summary"), dict) else {}
        prior_summary = dict(prior_summary)
        prior_summary["needsTableHints"] = False
        prior_summary["allowSkipToMsUrls"] = False
        prior_summary["stage4Source"] = "user_upload"
        state["summary"] = prior_summary

    summary = refresh_artifact_summary(job_id, state.get("summary") if isinstance(state.get("summary"), dict) else {})
    state["summary"] = summary
    write_job_json(job_id, state)
    return state


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


def fulltext_artifact(job_id: str, pmid: str | None = None) -> Path | None:
    """Prefer PDF, then XML under stage2/fulltext/<pmid>/ (legacy: stage2/<pmid>/)."""
    state_pmid = pmid or (read_job_json(job_id) or {}).get("pmid")
    if not state_pmid:
        return None
    pmid_s = str(state_pmid).strip()
    bases = [
        job_dir(job_id) / "stage2" / "fulltext" / pmid_s,
        job_dir(job_id) / "stage2" / pmid_s,
    ]
    for base in bases:
        for name in ("fulltext.pdf", "fulltext.xml"):
            path = base / name
            if path.is_file():
                return path
    return None


def fulltext_is_user_upload(job_id: str, pmid: str | None = None) -> bool:
    """True when fulltext came from a user upload (meta.sources includes user_upload)."""
    state_pmid = pmid or (read_job_json(job_id) or {}).get("pmid")
    if not state_pmid:
        return False
    pmid_s = str(state_pmid).strip()
    for base in (
        job_dir(job_id) / "stage2" / "fulltext" / pmid_s,
        job_dir(job_id) / "stage2" / pmid_s,
    ):
        meta = base / "meta.json"
        if not meta.is_file():
            continue
        try:
            data = json.loads(meta.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        sources = data.get("sources") or []
        if isinstance(sources, list) and "user_upload" in sources:
            return True
        notes = str(data.get("notes") or "")
        if "user-uploaded" in notes.lower() or "user_upload" in notes.lower():
            return True
    return False


def supplementary_zip_artifact(job_id: str, pmid: str | None = None) -> Path | None:
    state_pmid = pmid or (read_job_json(job_id) or {}).get("pmid")
    if not state_pmid:
        return None
    pmid_s = str(state_pmid).strip()
    candidates = [
        job_dir(job_id) / "stage4" / "supp" / pmid_s / "supplementary.zip",
        job_dir(job_id) / "stage4" / pmid_s / "supplementary.zip",
    ]
    for path in candidates:
        if path.is_file():
            return path
    return None


def supplementary_is_user_upload(job_id: str, pmid: str | None = None) -> bool:
    """True when supplementary ZIP was provided by the user."""
    state_pmid = pmid or (read_job_json(job_id) or {}).get("pmid")
    if not state_pmid:
        return False
    pmid_s = str(state_pmid).strip()
    markers = [
        job_dir(job_id) / "stage4" / "supp" / pmid_s / "source_user_upload.txt",
        job_dir(job_id) / "stage4" / pmid_s / "source_user_upload.txt",
    ]
    return any(p.is_file() for p in markers)


def stage4_supp_dir(job_id: str, pmid: str) -> Path:
    return job_dir(job_id) / "stage4" / "supp" / str(pmid).strip()


def stage5_inventory_path(job_id: str, pmid: str) -> Path | None:
    path = job_dir(job_id) / "stage5" / "inventory" / f"{str(pmid).strip()}.json"
    return path if path.is_file() else None


def user_hints_path(job_id: str, pmid: str) -> Path:
    return stage4_supp_dir(job_id, pmid) / "user_hints.json"


def read_table_candidates(job_id: str, pmid: str) -> list[dict[str, Any]]:
    """List file/sheet candidates from Stage5 inventory (preferred) or Stage4 listing.

    Also appends ZIP tabular members that were not inventoried (beyond Top-N),
    so users can teach the agent to force-include them.
    """
    inv = stage5_inventory_path(job_id, pmid)
    out: list[dict[str, Any]] = []
    seen_entries: set[str] = set()
    if inv:
        try:
            data = json.loads(inv.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = {}
        for f in data.get("files") or []:
            entry = str(f.get("entryPath") or "").strip()
            if not entry:
                continue
            seen_entries.add(entry.replace("\\", "/").lower())
            sheets = f.get("sheets") or []
            if not sheets:
                out.append(
                    {
                        "entryPath": entry,
                        "sheetName": "",
                        "headers": [],
                        "dataRowCount": 0,
                        "ext": f.get("ext") or "",
                    }
                )
                continue
            for sh in sheets:
                out.append(
                    {
                        "entryPath": entry,
                        "sheetName": str(sh.get("name") or ""),
                        "headers": list(sh.get("headers") or [])[:20],
                        "dataRowCount": int(sh.get("dataRowCount") or 0),
                        "ext": f.get("ext") or "",
                    }
                )

    for entry in list_zip_table_entries(job_id, pmid):
        key = entry.replace("\\", "/").lower()
        if key in seen_entries:
            continue
        seen_entries.add(key)
        out.append(
            {
                "entryPath": entry,
                "sheetName": "",
                "headers": [],
                "dataRowCount": 0,
                "ext": Path(entry).suffix.lower(),
                "notInventoried": True,
            }
        )

    if out:
        return out

    listing = stage4_supp_dir(job_id, pmid) / "listing.json"
    if listing.is_file():
        try:
            hits = json.loads(listing.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            hits = []
        if isinstance(hits, list):
            for h in hits:
                path = str((h or {}).get("path") or "").strip()
                kind = str((h or {}).get("kind") or "")
                if not path:
                    continue
                if kind not in ("excel", "csv", "tsv") and not path.lower().endswith(
                    (".xlsx", ".xls", ".csv", ".tsv", ".txt")
                ):
                    continue
                out.append(
                    {
                        "entryPath": path,
                        "sheetName": "",
                        "headers": [],
                        "dataRowCount": 0,
                        "ext": Path(path).suffix.lower(),
                        "score": (h or {}).get("score"),
                        "clues": (h or {}).get("clues") or [],
                    }
                )
    return out


def write_user_table_hints(
    job_id: str,
    pmid: str,
    selections: list[dict[str, Any]],
    note: str | None = None,
    prefer_protein_log2: bool | None = None,
    derived_ratios: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    cleaned = []
    for raw in selections:
        entry = str((raw or {}).get("entryPath") or "").strip()
        if not entry:
            continue
        sheet = str((raw or {}).get("sheetName") or "").strip()
        item: dict[str, Any] = {"entryPath": entry}
        if sheet:
            item["sheetName"] = sheet
        cleaned.append(item)
    derived_clean: list[dict[str, Any]] = []
    for raw in derived_ratios or []:
        num = str((raw or {}).get("numerator") or "").strip()
        den = str((raw or {}).get("denominator") or "").strip()
        if not num or not den:
            continue
        derived_clean.append(
            {
                "numerator": num,
                "denominator": den,
                "isLog2": bool((raw or {}).get("isLog2", True)),
                "condition": str((raw or {}).get("condition") or f"{num}/{den}").strip(),
            }
        )
    proteome_cols = extract_proteome_columns(note)
    hints = {
        "selections": cleaned,
        "note": (note or "").strip() or None,
        "preferProteinLog2": bool(prefer_protein_log2) if prefer_protein_log2 else None,
        "derivedRatios": derived_clean or None,
        "proteomeColumns": proteome_cols or None,
        "updatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    # Drop null optional fields for cleaner JSON
    if not hints["preferProteinLog2"]:
        hints.pop("preferProteinLog2", None)
    if not hints["derivedRatios"]:
        hints.pop("derivedRatios", None)
    if not hints["proteomeColumns"]:
        hints.pop("proteomeColumns", None)
    path = user_hints_path(job_id, pmid)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(hints, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return hints


_TABLE_NAME_RE = re.compile(
    # Disallow spaces outside parentheses so "use mmc3.xlsx" does not capture "use …"
    r"([A-Za-z0-9][\w.\-]*(?:\([\w.\- ]+\))?[\w.\-]*\.(?:xlsx|xls|csv|tsv|txt))(?![A-Za-z0-9])",
    re.I,
)
_LOG2_PAIR_RE = re.compile(
    r"log\s*2\s*\(\s*([A-Za-z0-9][\w.\-]*)\s*[\/÷]\s*([A-Za-z0-9][\w.\-]*)\s*\)",
    re.I,
)
_SHEET_ARROW_RE = re.compile(
    r"([A-Za-z0-9][\w.\-]*(?:\([\w.\- ]+\))?[\w.\-]*\.(?:xlsx|xls|csv|tsv|txt))\s*(?:→|->|=>|—)\s*[\"']?"
    r"([A-Za-z][\w .\-]{0,80}?)[\"']?(?=\s|$|[,;:]|to\s)",
    re.I,
)
_SHEET_HASH_RE = re.compile(
    r"([A-Za-z0-9][\w.\-]*(?:\([\w.\- ]+\))?[\w.\-]*\.(?:xlsx|xls|csv|tsv|txt))\s*#\s*([A-Za-z][\w .\-]{0,80})",
    re.I,
)


def extract_table_filenames(text: str) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for m in _TABLE_NAME_RE.finditer(text or ""):
        name = m.group(1).strip()
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(name)
    return out


def extract_sheet_hints(text: str) -> dict[str, str]:
    """Map filename → sheet from 'file → Sheet' / 'file#Sheet' phrases."""
    out: dict[str, str] = {}
    t = text or ""
    for m in _SHEET_ARROW_RE.finditer(t):
        file = m.group(1).strip()
        sheet = m.group(2).strip().rstrip(".,;:")
        if file and sheet:
            out[file] = sheet
    for m in _SHEET_HASH_RE.finditer(t):
        file = m.group(1).strip()
        sheet = m.group(2).strip().rstrip(".,;:")
        if file and sheet and file not in out:
            out[file] = sheet
    return out


def extract_proteome_columns(text: str | None) -> dict[str, str]:
    """Parse user guidance naming the protein-level columns, e.g.

    "proteome data should collected from total proteome Log(ASB2/MCS) |
    total proteome p-value" → {"ratioCol": "total proteome Log(ASB2/MCS)",
                               "pValueCol": "total proteome p-value"}
    """
    t = (text or "").strip()
    if not t:
        return {}

    def _clean(s: str) -> str:
        return s.strip().strip('"\'“”‘’ ')

    def _looks_like_prose(s: str) -> bool:
        low = s.lower()
        if len(s) > 80:
            return True
        if re.search(
            r"\b(missing|contains?|matched|should|do not|skip|please|only|protein-level data)\b",
            low,
        ):
            return True
        if s.count(" ") >= 6:
            return True
        return False

    _RATIO_MARK = re.compile(r"log\s*2?|ratio|fc\b|fold", re.I)
    _PVAL_MARK = re.compile(r"p\s*[- ]?value|pval|q\s*[- ]?value", re.I)

    ratio: str | None = None
    pval: str | None = None

    # Prefer explicit "from A | B" / "columns A | B" patterns only
    m_from = re.search(
        r"(?:from|columns?|use)\s+['\"]?([^|\n]+?)['\"]?\s*\|\s*['\"]?([^|\n]+?)['\"]?",
        t,
        re.I,
    )
    if m_from:
        a, b = _clean(m_from.group(1)), _clean(m_from.group(2))
        if _RATIO_MARK.search(a) and not _looks_like_prose(a):
            ratio = a
        elif _RATIO_MARK.search(b) and not _looks_like_prose(b):
            ratio = b
        if _PVAL_MARK.search(a) and not _looks_like_prose(a):
            pval = a
        elif _PVAL_MARK.search(b) and not _looks_like_prose(b):
            pval = b
    else:
        # Quoted column names near proteome / protein Log2 wording
        for m in re.finditer(r'["\']([^"\']{2,80})["\']', t):
            col = _clean(m.group(1))
            if _looks_like_prose(col):
                continue
            if not ratio and _RATIO_MARK.search(col) and not _PVAL_MARK.search(col):
                ratio = col
            elif not pval and _PVAL_MARK.search(col):
                pval = col

    def _trim_col(s: str | None) -> str | None:
        if not s:
            return None
        if _looks_like_prose(s):
            return None
        s = re.sub(r"\s*(?:column|col\.?|field|header|for\s+protein.*)$", "", s, flags=re.I)
        m = re.search(
            r"(?:total\s+proteome|total\s+protein|"
            r"proteome\s+(?:log2?|ratio|fc|fold|quant)|"
            r"protein\s+(?:log2?|ratio|fc|fold|quant))",
            s,
            re.I,
        )
        if m:
            s = s[m.start() :]
        s = s.strip().strip('"\'“”‘’ ').strip(".,;: ")
        if _looks_like_prose(s):
            return None
        return s or None

    ratio = _trim_col(ratio)
    pval = _trim_col(pval)

    out: dict[str, str] = {}
    if ratio and ratio != pval:
        out["ratioCol"] = ratio
    if pval:
        out["pValueCol"] = pval
    return out


def parse_derived_ratio_specs(text: str | None) -> list[dict[str, Any]]:
    """Parse log2(P5/P1)-style contrasts from Teach / chat guidance."""
    t = (text or "").strip()
    if not t:
        return []
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for m in _LOG2_PAIR_RE.finditer(t):
        num = m.group(1).strip()
        den = m.group(2).strip()
        if not num or not den or num.lower() == den.lower():
            continue
        if re.match(r"^(log|ratio|fc|fold|sheet|use|file)$", num, re.I):
            continue
        if re.match(r"^(log|ratio|fc|fold|sheet|use|file)$", den, re.I):
            continue
        cond = f"{num}/{den}"
        key = cond.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "numerator": num,
                "denominator": den,
                "isLog2": True,
                "condition": cond,
            }
        )
    return out


def note_wants_protein_log2(text: str | None) -> bool:
    t = (text or "").lower()
    if not t:
        return False
    if re.search(r"log2?\s*ratio\s*\(\s*protein\s*\)", t, re.I):
        return True
    if re.search(r"protein[-\s_]*(?:level\s+)?(?:log2?\s*)?(?:ratio|fc|fold)", t, re.I):
        return True
    raw = text or ""
    if "蛋白质" in raw and re.search(r"(定量|log|ratio|比值)", t, re.I):
        return True
    if "蛋白" in raw and re.search(r"(log2?ratio|定量值|定量表)", t, re.I):
        return True
    return False


def list_zip_table_entries(job_id: str, pmid: str) -> list[str]:
    """All tabular member paths inside the supplementary ZIP (not just Top-N inventory)."""
    zpath = supplementary_zip_artifact(job_id, pmid)
    if not zpath:
        return []
    try:
        import zipfile

        out: list[str] = []
        with zipfile.ZipFile(zpath, "r") as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                name = info.filename.replace("\\", "/")
                if name.lower().endswith((".xlsx", ".xls", ".csv", ".tsv", ".txt")):
                    out.append(name)
        return out
    except OSError:
        return []


def _entry_path_matches(hint: str, actual: str) -> bool:
    h = (hint or "").replace("\\", "/").strip().lower()
    a = (actual or "").replace("\\", "/").strip().lower()
    if not h or not a:
        return False
    if h == a:
        return True
    if a.endswith("/" + h) or h.endswith("/" + a):
        return True
    return Path(h).name == Path(a).name


def resolve_guidance_selections(
    job_id: str,
    pmid: str,
    message: str,
) -> tuple[list[dict[str, Any]], bool, list[str], list[dict[str, Any]]]:
    """
    Map free-text Stage5 feedback → table selections + derived ratios.
    Returns (selections, prefer_protein_log2, matched_filenames, derived_ratios).
    """
    names = extract_table_filenames(message)
    prefer = note_wants_protein_log2(message)
    sheet_hints = extract_sheet_hints(message)
    derived = parse_derived_ratio_specs(message)
    zip_entries = list_zip_table_entries(job_id, pmid)
    candidates = read_table_candidates(job_id, pmid)
    # Prefer matching against full ZIP listing, then inventoried paths.
    pool = list(dict.fromkeys(zip_entries + [str(c.get("entryPath") or "") for c in candidates]))
    pool = [p for p in pool if p]

    # Known sheet names from inventory (for fuzzy sheet attach)
    sheets_by_entry: dict[str, list[str]] = {}
    for c in candidates:
        ep = str(c.get("entryPath") or "")
        sn = str(c.get("sheetName") or "").strip()
        if ep and sn:
            sheets_by_entry.setdefault(ep, [])
            if sn not in sheets_by_entry[ep]:
                sheets_by_entry[ep].append(sn)

    def _resolve_sheet(actual: str, hint_file: str) -> str | None:
        wanted = sheet_hints.get(hint_file)
        if not wanted:
            # Try any sheet hint if only one file
            if len(sheet_hints) == 1:
                wanted = next(iter(sheet_hints.values()))
        if not wanted:
            return None
        known = sheets_by_entry.get(actual) or []
        for s in known:
            if s.lower() == wanted.lower():
                return s
        # Fall back to the user-provided name (Stage5 inventory may still match)
        return wanted

    selections: list[dict[str, Any]] = []
    matched: list[str] = []
    seen: set[str] = set()
    for name in names:
        for actual in pool:
            if not _entry_path_matches(name, actual):
                continue
            key = actual.lower()
            if key in seen:
                continue
            seen.add(key)
            item: dict[str, Any] = {"entryPath": actual}
            sheet = _resolve_sheet(actual, name)
            if sheet:
                item["sheetName"] = sheet
            selections.append(item)
            matched.append(actual)
            break

    return selections, prefer, matched, derived


def looks_like_stage5_guidance(message: str) -> bool:
    """Heuristic: user is correcting / questioning Stage5 parse results."""
    t = (message or "").strip()
    if not t or len(t) < 4:
        return False
    if extract_table_filenames(t):
        return True
    if note_wants_protein_log2(t):
        return True
    if parse_derived_ratio_specs(t):
        return True
    if extract_sheet_hints(t):
        return True
    # Sample / sheet-as-sample corrections (e.g. MCF7 / MDA-MB-231 sheets)
    if re.search(r"mismatch\s*sample", t, re.I):
        return True
    if re.search(r"sheet.+as.+(?:different\s+)?samples?", t, re.I):
        return True
    if re.search(r"(?:different|separate|distinct)\s+samples?", t, re.I) and re.search(
        r"sheet", t, re.I
    ):
        return True
    if re.search(r"use.+sheets?.+as.+samples?", t, re.I):
        return True
    if re.search(r"each\s+sheet.+(?:sample|cell\s*line)", t, re.I):
        return True
    if re.search(r"三个|不同", t) and re.search(
        r"sample|样品|细胞系|sheet", t, re.I
    ):
        return True
    if re.search(r"样品不对|样品错|sample\s*(?:wrong|mismatch|incorrect)", t, re.I):
        return True
    if re.search(r"\bsamples?\b", t, re.I) and re.search(r"\bsheets?\b", t, re.I):
        return True
    if re.search(r"cell\s*lines?", t, re.I) and re.search(
        r"\b(sample|sheet|different|three)\b", t, re.I
    ):
        return True
    keys = (
        r"为什么",
        r"为啥",
        r"没有",
        r"漏了",
        r"没读",
        r"读入",
        r"重新解析",
        r"condition",
        r"log2?\s*ratio",
        r"log\s*2\s*\(",
        r"quantitative",
        r"wrong",
        r"missing",
        r"re-?parse",
        r"should (?:use|include|read)",
        r"\buse\b.+\.(?:xlsx|xls|csv)",
        r"xlsx",
        r"附表",
        r"定量表",
        r"count\s+log",
        r"extract\s+ptm",
        r"\bcolumn\b",
        r"表头",
        r"列名",
        r"amino\s*acid",
        r"position",
        r"\bsty\b",
        r"\bsample\b",
        r"样品",
        r"细胞系",
        r"\bsheet\b",
        r"site[- ]level",
        r"split\s+(?:this\s+)?column",
        r"phosphosite",
        r"protein\s*\+\s*phosphosite",
    )
    return any(re.search(k, t, re.I) for k in keys)


def _is_real_sheet_name(name: str) -> bool:
    n = (name or "").strip()
    if not n:
        return False
    if n.startswith("_xlnm."):
        return False
    if n.lower().startswith("microsoft.com:"):
        return False
    return True


def _preview_delimited_bytes(raw: bytes, max_rows: int = 5) -> dict[str, Any]:
    text = raw.decode("utf-8", errors="replace")
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return {"name": "Sheet1", "headers": [], "preview": []}
    first = lines[0]
    delim = "\t" if first.count("\t") > first.count(",") else ","
    import csv as _csv
    from io import StringIO

    rows = list(_csv.reader(StringIO("\n".join(lines[: max_rows + 1])), delimiter=delim))
    if not rows:
        return {"name": "Sheet1", "headers": [], "preview": []}
    headers = [str(c or "").strip() for c in rows[0]][:20]
    preview = [[str(c or "").strip() for c in r[: len(headers) or 20]] for r in rows[1 : max_rows + 1]]
    return {"name": "Sheet1", "headers": headers, "preview": preview}


def _matrix_to_sheet_preview(
    name: str,
    matrix: list[list[str]],
    max_rows: int = 5,
) -> dict[str, Any] | None:
    """Pick a header-like row from the first lines; build {name, headers, preview}."""
    if not matrix:
        return None
    header_idx = 0
    best = -1
    for i, row in enumerate(matrix[:8]):
        filled = [c for c in row if c]
        if len(filled) < 2:
            score = -10
        else:
            blob = " ".join(filled).lower()
            score = min(len(filled), 20)
            if any(k in blob for k in ("uniprot", "accession", "gene", "site", "position", "ratio", "log2")):
                score += 8
            numeric = sum(1 for c in filled if re.fullmatch(r"-?\d+(\.\d+)?([eE][-+]?\d+)?", c))
            if numeric >= len(filled) * 0.5:
                score -= 10
        if score > best:
            best = score
            header_idx = i
    headers = [c or f"col_{j+1}" for j, c in enumerate(matrix[header_idx][:20])]
    preview = []
    for row in matrix[header_idx + 1 : header_idx + 1 + max_rows]:
        preview.append([(row[j] if j < len(row) else "") for j in range(len(headers))])
    return {"name": name, "headers": headers, "preview": preview}


def _preview_xlsx_bytes(raw: bytes, max_sheets: int = 4, max_rows: int = 5) -> list[dict[str, Any]]:
    from io import BytesIO

    from openpyxl import load_workbook

    wb = load_workbook(BytesIO(raw), read_only=True, data_only=True)
    out: list[dict[str, Any]] = []
    try:
        for name in wb.sheetnames:
            if not _is_real_sheet_name(name):
                continue
            # Skip obvious non-data sheets for the stage4 glance
            if re.search(r"legend|note|readme|instruction|study\s*information|sample\s*info", name, re.I):
                continue
            ws = wb[name]
            matrix: list[list[str]] = []
            for i, row in enumerate(ws.iter_rows(values_only=True)):
                if i >= max_rows + 8:
                    break
                matrix.append(["" if c is None else str(c).strip() for c in row])
            sheet = _matrix_to_sheet_preview(name, matrix, max_rows)
            # Prefer sheets that actually have data rows under the header
            if sheet and not (sheet.get("preview") or []):
                continue
            if sheet:
                out.append(sheet)
            if len(out) >= max_sheets:
                break
    finally:
        wb.close()
    return out


def _preview_xls_bytes(raw: bytes, max_sheets: int = 4, max_rows: int = 5) -> list[dict[str, Any]]:
    """Preview legacy BIFF .xls workbooks (xlrd) — openpyxl cannot read them."""
    try:
        import xlrd

        book = xlrd.open_workbook(file_contents=raw)
    except Exception:
        # Some "*.xls" files are actually tab/comma-delimited text masquerading as .xls.
        return [_preview_delimited_bytes(raw, max_rows=max_rows)]
    out: list[dict[str, Any]] = []
    for sheet in book.sheets():
        name = sheet.name
        if not _is_real_sheet_name(name):
            continue
        if re.search(r"legend|note|readme|instruction|study\s*information|sample\s*info", name, re.I):
            continue
        nrows = min(sheet.nrows, max_rows + 8)
        matrix: list[list[str]] = []
        for r in range(nrows):
            matrix.append(
                ["" if c in (None, "") else str(c).strip() for c in sheet.row_values(r)]
            )
        sheet_preview = _matrix_to_sheet_preview(name, matrix, max_rows)
        if sheet_preview and not (sheet_preview.get("preview") or []):
            continue
        if sheet_preview:
            out.append(sheet_preview)
        if len(out) >= max_sheets:
            break
    return out


def read_supp_previews(
    job_id: str,
    pmid: str,
    *,
    max_files: int = 6,
    max_sheets_per_file: int = 3,
    max_rows: int = 5,
) -> list[dict[str, Any]]:
    """Peek top supplementary tabular files: sheet names, headers, first rows."""
    zip_path = supplementary_zip_artifact(job_id, pmid)
    if not zip_path:
        return []

    listing_path = stage4_supp_dir(job_id, pmid) / "listing.json"
    entries: list[dict[str, Any]] = []
    if listing_path.is_file():
        try:
            hits = json.loads(listing_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            hits = []
        if isinstance(hits, list):
            for h in hits:
                path = str((h or {}).get("path") or "").strip()
                kind = str((h or {}).get("kind") or "")
                if not path:
                    continue
                low = path.lower()
                if kind not in ("excel", "csv", "tsv") and not low.endswith(
                    (".xlsx", ".xls", ".csv", ".tsv", ".txt")
                ):
                    continue
                entries.append(
                    {
                        "path": path,
                        "kind": kind or Path(path).suffix.lstrip(".").lower(),
                        "score": int((h or {}).get("score") or 0),
                        "size": int((h or {}).get("size") or 0),
                    }
                )
    entries.sort(key=lambda e: (-e["score"], -e["size"], e["path"]))
    entries = entries[:max_files]

    import zipfile

    previews: list[dict[str, Any]] = []
    try:
        zf = zipfile.ZipFile(zip_path)
    except (OSError, zipfile.BadZipFile):
        return []

    with zf:
        names = set(zf.namelist())
        for ent in entries:
            path = ent["path"]
            member = path if path in names else next((n for n in names if n.endswith(path)), None)
            if not member:
                previews.append(
                    {
                        "entryPath": path,
                        "kind": ent["kind"],
                        "sheets": [],
                        "error": "not found in zip",
                    }
                )
                continue
            try:
                raw = zf.read(member)
            except Exception as exc:  # noqa: BLE001
                previews.append(
                    {
                        "entryPath": path,
                        "kind": ent["kind"],
                        "sheets": [],
                        "error": str(exc),
                    }
                )
                continue
            low = path.lower()
            try:
                if low.endswith(".xls"):
                    sheets = _preview_xls_bytes(
                        raw, max_sheets=max_sheets_per_file, max_rows=max_rows
                    )
                elif low.endswith((".xlsx", ".xlsm", ".xltx", ".xltm")) or (
                    ent["kind"] == "excel" and not low.endswith(".xls")
                ):
                    sheets = _preview_xlsx_bytes(raw, max_sheets=max_sheets_per_file, max_rows=max_rows)
                elif low.endswith((".csv", ".tsv", ".txt")) or ent["kind"] in ("csv", "tsv"):
                    sheets = [_preview_delimited_bytes(raw, max_rows=max_rows)]
                else:
                    sheets = []
            except Exception as exc:  # noqa: BLE001
                previews.append(
                    {
                        "entryPath": path,
                        "kind": ent["kind"],
                        "sheets": [],
                        "error": "Could not preview this file (unsupported format)",
                    }
                )
                continue
            previews.append({"entryPath": path, "kind": ent["kind"], "sheets": sheets})
    return previews


def stage5_artifact(job_id: str, name: str = "qratio.csv") -> Path | None:
    path = job_dir(job_id) / "stage5" / name
    if path.is_file() and _csv_has_data_rows(path):
        return path
    return None


def stage6_urls_artifact(job_id: str, name: str = "urls_all.csv") -> Path | None:
    path = job_dir(job_id) / "stage6" / name
    if path.is_file() and _csv_has_data_rows(path):
        return path
    return None


def read_csv_preview(
    path: Path,
    max_rows: int = 10,
    drop_columns: list[str] | None = None,
    drop_empty_columns: list[str] | None = None,
) -> dict[str, Any]:
    """Return CSV headers + first max_rows data rows for UI table previews.

    drop_empty_columns: omit these columns when every data cell is blank
    (e.g. Localization probability / PEP with no search-engine scores).
    """
    headers: list[str] = []
    preview: list[list[str]] = []
    total = 0
    drop = {str(c).strip().lower() for c in (drop_columns or []) if c}
    if drop_empty_columns:
        for name in empty_optional_csv_columns(path, list(drop_empty_columns)):
            drop.add(name.strip().lower())
    try:
        with path.open(encoding="utf-8", errors="replace", newline="") as fh:
            reader = csv.reader(fh)
            try:
                raw_headers = next(reader)
            except StopIteration:
                return {"headers": [], "preview": [], "totalRows": 0}
            headers = [str(c or "").strip().lstrip("\ufeff") for c in raw_headers]
            keep_idx = [
                i for i, h in enumerate(headers) if h.strip().lower() not in drop
            ]
            headers = [headers[i] for i in keep_idx]
            width = len(keep_idx) or 20
            for row in reader:
                total += 1
                if len(preview) >= max_rows:
                    continue
                if keep_idx:
                    preview.append([(row[i] if i < len(row) else "") for i in keep_idx])
                else:
                    preview.append([(row[i] if i < len(row) else "") for i in range(width)])
    except OSError:
        return {"headers": [], "preview": [], "totalRows": 0}
    return {"headers": headers, "preview": preview, "totalRows": total}


def empty_optional_csv_columns(
    path: Path,
    candidates: list[str],
) -> set[str]:
    """Return candidate column names that exist but are blank in every data row."""
    want = {c.strip().lower() for c in candidates if c and str(c).strip()}
    if not want or not path.is_file():
        return set()
    try:
        with path.open(encoding="utf-8", errors="replace", newline="") as fh:
            reader = csv.reader(fh)
            try:
                raw_headers = next(reader)
            except StopIteration:
                return set()
            headers = [str(c or "").strip().lstrip("\ufeff") for c in raw_headers]
            idx_map = {
                i: headers[i]
                for i in range(len(headers))
                if headers[i].strip().lower() in want
            }
            if not idx_map:
                return set()
            nonempty: set[int] = set()
            for row in reader:
                for i in idx_map:
                    if i in nonempty:
                        continue
                    if i < len(row) and str(row[i]).strip():
                        nonempty.add(i)
                if len(nonempty) == len(idx_map):
                    break
            return {idx_map[i] for i in idx_map if i not in nonempty}
    except OSError:
        return set()

