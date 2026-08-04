"""Extract PMID (and DOI→PMID) from uploaded collection files."""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path
from typing import Iterable

import httpx

from app.collection.store import extract_pmid

_PMID_PATTERNS = (
    re.compile(r"(?:PMID|PubMed(?:\s+ID)?)\s*[:#]?\s*(\d{7,8})\b", re.I),
    re.compile(r"pubmed\.ncbi\.nlm\.nih\.gov/(\d{7,8})\b", re.I),
    re.compile(r"ncbi\.nlm\.nih\.gov/pubmed/(\d{7,8})\b", re.I),
)
_JATS_PMID_RE = re.compile(
    r'<article-id[^>]+pub-id-type=["\']pmid["\'][^>]*>(\d{7,8})</article-id>',
    re.I,
)
_DOI_PATTERNS = (
    re.compile(r"(?:doi[:\s]*|https?://(?:dx\.)?doi\.org/)(10\.\d{4,9}/[^\s\"'<>]+)", re.I),
    re.compile(r"<article-id[^>]+pub-id-type=[\"']doi[\"'][^>]*>(10\.\d{4,9}/[^<]+)</article-id>", re.I),
)


def _first_pmid(text: str) -> str | None:
    for pattern in _PMID_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(1)
    return extract_pmid(text)


def _collect_dois(text: str) -> list[str]:
    seen: set[str] = set()
    dois: list[str] = []
    for pattern in _DOI_PATTERNS:
        for match in pattern.finditer(text):
            doi = match.group(1).rstrip(".,;)")
            if doi not in seen:
                seen.add(doi)
                dois.append(doi)
    return dois


def extract_pmid_from_text(text: str) -> str | None:
    return _first_pmid(text)


def extract_pmid_from_bytes(content: bytes) -> str | None:
    for encoding in ("utf-8", "latin-1"):
        try:
            found = _first_pmid(content.decode(encoding))
            if found:
                return found
        except UnicodeDecodeError:
            continue
    return None


def extract_pmid_from_xml(content: bytes) -> str | None:
    text = content.decode("utf-8", errors="replace")
    match = _JATS_PMID_RE.search(text)
    if match:
        return match.group(1)
    return extract_pmid_from_text(text)


def extract_pmid_from_pdf(content: bytes) -> str | None:
    found = extract_pmid_from_bytes(content)
    if found:
        return found
    try:
        from pypdf import PdfReader
    except ImportError:
        return None

    try:
        reader = PdfReader(io.BytesIO(content))
        chunks: list[str] = []
        for page in reader.pages[:5]:
            text = page.extract_text() or ""
            if text.strip():
                chunks.append(text)
            found = _first_pmid(text)
            if found:
                return found
        return _first_pmid("\n".join(chunks))
    except Exception:
        return None


def extract_pmid_from_tabular(content: bytes) -> str | None:
    text = content.decode("utf-8", errors="replace")
    lines = text.splitlines()[:80]
    for line in lines:
        found = _first_pmid(line)
        if found:
            return found
        lower = line.lower()
        if "pmid" in lower or "pubmed" in lower:
            cells = re.split(r"[\t,;|]", line)
            for cell in cells:
                cell = cell.strip().strip("\"'")
                if re.fullmatch(r"\d{7,8}", cell):
                    return cell
    return _first_pmid("\n".join(lines[:40]))


def extract_pmid_from_xlsx(content: bytes) -> str | None:
    try:
        import openpyxl
    except ImportError:
        return extract_pmid_from_bytes(content)

    try:
        wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        ws = wb.active
        if ws is None:
            return extract_pmid_from_bytes(content)
        for row in ws.iter_rows(min_row=1, max_row=30, max_col=20, values_only=True):
            for value in row:
                if value is None:
                    continue
                text = str(value).strip()
                if not text:
                    continue
                found = _first_pmid(text)
                if found:
                    return found
                if re.fullmatch(r"\d{7,8}", text):
                    return text
        return None
    except Exception:
        return extract_pmid_from_bytes(content)


def extract_pmid_from_zip(content: bytes) -> str | None:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            for name in zf.namelist()[:30]:
                lower = name.lower()
                if lower.endswith((".pdf", ".xml", ".csv", ".tsv", ".txt")):
                    try:
                        blob = zf.read(name)
                    except KeyError:
                        continue
                    found = extract_pmid_from_upload(name, blob)
                    if found:
                        return found
    except zipfile.BadZipFile:
        return None
    return None


def extract_pmid_from_upload(filename: str, content: bytes) -> str | None:
    ext = Path(filename).suffix.lower()
    if ext == ".xml":
        return extract_pmid_from_xml(content)
    if ext == ".pdf":
        return extract_pmid_from_pdf(content)
    if ext in {".csv", ".tsv"}:
        return extract_pmid_from_tabular(content)
    if ext in {".xlsx", ".xls"}:
        return extract_pmid_from_xlsx(content)
    if ext == ".zip":
        return extract_pmid_from_zip(content)
    return extract_pmid_from_bytes(content)


def extract_dois_from_upload(filename: str, content: bytes) -> list[str]:
    ext = Path(filename).suffix.lower()
    texts: list[str] = []
    if ext == ".xml":
        texts.append(content.decode("utf-8", errors="replace"))
    elif ext == ".pdf":
        try:
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(content))
            for page in reader.pages[:3]:
                texts.append(page.extract_text() or "")
        except Exception:
            texts.append(content.decode("latin-1", errors="replace"))
    elif ext in {".csv", ".tsv", ".xlsx", ".xls"}:
        if ext in {".xlsx", ".xls"}:
            pmid = extract_pmid_from_xlsx(content)
            if pmid:
                return []
        texts.append(content.decode("utf-8", errors="replace"))
    else:
        texts.append(content.decode("latin-1", errors="replace"))

    seen: set[str] = set()
    dois: list[str] = []
    for text in texts:
        for doi in _collect_dois(text):
            if doi not in seen:
                seen.add(doi)
                dois.append(doi)
    return dois


async def doi_to_pmid(doi: str) -> str | None:
    url = "https://pubmed.ncbi.nlm.nih.gov/idconv/"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.get(url, params={"id": doi, "format": "json"})
            res.raise_for_status()
            payload = res.json()
    except Exception:
        return None
    for record in payload.get("records") or []:
        pmid = record.get("pmid")
        if pmid and re.fullmatch(r"\d{7,8}", str(pmid)):
            return str(pmid)
    return None


async def resolve_pmid_from_uploads(uploads: Iterable[tuple[str, bytes]]) -> str | None:
    """Try PMID from file bodies; fall back to DOI lookup via NCBI."""
    items = list(uploads)
    for filename, content in items:
        found = extract_pmid_from_upload(filename, content)
        if found:
            return found

    seen_dois: set[str] = set()
    for filename, content in items:
        for doi in extract_dois_from_upload(filename, content):
            if doi in seen_dois:
                continue
            seen_dois.add(doi)
            pmid = await doi_to_pmid(doi)
            if pmid:
                return pmid
    return None
