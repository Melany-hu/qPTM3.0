"""Extract PMID (and DOI→PMID) from uploaded collection files."""

from __future__ import annotations

import io
import logging
import re
import zipfile
from pathlib import Path
from typing import Iterable

import httpx

logger = logging.getLogger(__name__)

# Prefer labeled / URL forms — never treat bare 7–8 digit runs in PDF binary as PMIDs.
_PMID_PATTERNS = (
    re.compile(r"(?:PMID|PubMed(?:\s+ID)?)\s*[:#]?\s*(\d{7,8})\b", re.I),
    re.compile(r"pubmed\.ncbi\.nlm\.nih\.gov/(?:pmid/)?(\d{7,8})\b", re.I),
    re.compile(r"ncbi\.nlm\.nih\.gov/pubmed/(\d{7,8})\b", re.I),
    re.compile(r"europepmc\.org/article/MED/(\d{7,8})\b", re.I),
)
_JATS_PMID_RE = re.compile(
    r'<article-id[^>]+pub-id-type=["\']pmid["\'][^>]*>(\d{7,8})</article-id>',
    re.I,
)
_DOI_PATTERNS = (
    re.compile(r"(?:doi[:\s]*|https?://(?:dx\.)?doi\.org/)(10\.\d{4,9}/[^\s\"'<>]+)", re.I),
    re.compile(r"<article-id[^>]+pub-id-type=[\"']doi[\"'][^>]*>(10\.\d{4,9}/[^<]+)</article-id>", re.I),
)
# Broader DOI matcher — only used on extracted page text, not raw PDF binary.
_DOI_LOOSE_RE = re.compile(r"\b(10\.\d{4,9}/[-._;()/:A-Z0-9]+)\b", re.I)

_MAX_DOI_LOOKUPS = 3
_DOI_HTTP_TIMEOUT = 8.0


def _collect_dois(text: str, *, loose: bool = False) -> list[str]:
    seen: set[str] = set()
    dois: list[str] = []
    patterns = list(_DOI_PATTERNS)
    if loose:
        patterns.append(_DOI_LOOSE_RE)
    for pattern in patterns:
        for match in pattern.finditer(text or ""):
            doi = match.group(1).rstrip(".,;)]}>\"'")
            doi = re.sub(r"[/._-]+$", "", doi)
            if not doi.lower().startswith("10."):
                continue
            key = doi.lower()
            if key in seen:
                continue
            seen.add(key)
            dois.append(doi)
    return dois

_PDF_TEXT_PAGES = 8


def _first_pmid(text: str, *, allow_bare: bool = False) -> str | None:
    """Find a PMID in text. Bare digits only when allow_bare (CSV headers, etc.)."""
    if not text:
        return None
    for pattern in _PMID_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(1)
    if allow_bare:
        # Optional "PMID" prefix, then 7–8 digits — used for messages / filenames / tables.
        m = re.search(r"\b(?:PMID[:\s#]*)?(\d{7,8})\b", text, re.I)
        if m:
            return m.group(1)
    return None


def extract_pmid_from_text(text: str, *, allow_bare: bool = False) -> str | None:
    return _first_pmid(text, allow_bare=allow_bare)


def extract_pmid_from_bytes(content: bytes, *, allow_bare: bool = False) -> str | None:
    for encoding in ("utf-8", "latin-1"):
        try:
            found = _first_pmid(content.decode(encoding), allow_bare=allow_bare)
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
    return extract_pmid_from_text(text, allow_bare=False)


def _pdf_page_texts(content: bytes, max_pages: int = _PDF_TEXT_PAGES) -> list[str]:
    try:
        from pypdf import PdfReader
    except ImportError:
        logger.warning("pypdf not installed; cannot extract text from PDF uploads")
        return []

    try:
        reader = PdfReader(io.BytesIO(content))
        out: list[str] = []
        for page in reader.pages[:max_pages]:
            text = page.extract_text() or ""
            if text.strip():
                out.append(text)
        return out
    except Exception as exc:
        logger.warning("PDF text extraction failed: %s", exc)
        return []


def extract_pmid_from_pdf(content: bytes) -> str | None:
    """Extract PMID from PDF page text (labeled forms only).

    Never treat bare 7–8 digit runs inside the raw PDF binary as PMIDs — that
    produced false IDs (e.g. 7533353) and blocked DOI→PMID resolution.
    """
    pages = _pdf_page_texts(content)
    for text in pages:
        found = _first_pmid(text, allow_bare=False)
        if found:
            return found
    if pages:
        found = _first_pmid("\n".join(pages), allow_bare=False)
        if found:
            return found
    # pypdf failed / empty text: still allow labeled PMID strings in the stream
    return extract_pmid_from_bytes(content, allow_bare=False)


def extract_pmid_from_tabular(content: bytes) -> str | None:
    text = content.decode("utf-8", errors="replace")
    lines = text.splitlines()[:80]
    for line in lines:
        found = _first_pmid(line, allow_bare=False)
        if found:
            return found
        lower = line.lower()
        if "pmid" in lower or "pubmed" in lower:
            cells = re.split(r"[\t,;|]", line)
            for cell in cells:
                cell = cell.strip().strip("\"'")
                if re.fullmatch(r"\d{7,8}", cell):
                    return cell
    # Column of bare PMIDs under a PMID header is common — allow bare on first rows.
    return _first_pmid("\n".join(lines[:40]), allow_bare=True)


def extract_pmid_from_xlsx(content: bytes) -> str | None:
    try:
        import openpyxl
    except ImportError:
        return extract_pmid_from_bytes(content, allow_bare=True)

    try:
        wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        ws = wb.active
        if ws is None:
            return extract_pmid_from_bytes(content, allow_bare=True)
        for row in ws.iter_rows(min_row=1, max_row=30, max_col=20, values_only=True):
            for value in row:
                if value is None:
                    continue
                text = str(value).strip()
                if not text:
                    continue
                found = _first_pmid(text, allow_bare=False)
                if found:
                    return found
                if re.fullmatch(r"\d{7,8}", text):
                    return text
        return None
    except Exception:
        return extract_pmid_from_bytes(content, allow_bare=True)


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
    return extract_pmid_from_bytes(content, allow_bare=False)


def extract_dois_from_upload(filename: str, content: bytes) -> list[str]:
    ext = Path(filename).suffix.lower()
    texts: list[str] = []
    loose = False
    if ext == ".xml":
        texts.append(content.decode("utf-8", errors="replace"))
        loose = True
    elif ext == ".pdf":
        pages = _pdf_page_texts(content)
        if pages:
            texts.extend(pages)
            loose = True  # page text is safe for loose DOI matching
        else:
            # Binary fallback: only strict doi.org / doi: patterns
            texts.append(content.decode("latin-1", errors="replace")[:80_000])
            loose = False
    elif ext in {".csv", ".tsv", ".xlsx", ".xls"}:
        texts.append(content.decode("utf-8", errors="replace"))
        loose = True
    else:
        texts.append(content.decode("latin-1", errors="replace")[:80_000])
        loose = False

    seen: set[str] = set()
    dois: list[str] = []
    for text in texts:
        for doi in _collect_dois(text, loose=loose):
            key = doi.lower()
            if key in seen:
                continue
            seen.add(key)
            dois.append(doi)
    return dois[:_MAX_DOI_LOOKUPS]


async def doi_to_pmid(doi: str) -> str | None:
    """Resolve DOI → PMID via NCBI E-utilities, then PMC id converter / Europe PMC."""
    doi = (doi or "").strip().rstrip(".,;)")
    if not doi:
        return None

    timeout = httpx.Timeout(_DOI_HTTP_TIMEOUT)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        # 1) PubMed ESearch by DOI (usually fastest / most reliable)
        try:
            res = await client.get(
                "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
                params={
                    "db": "pubmed",
                    "term": f"{doi}[doi]",
                    "retmode": "json",
                    "retmax": "1",
                    "tool": "qptm-agent",
                    "email": "qptm@localhost",
                },
            )
            if res.status_code == 200:
                ids = (res.json().get("esearchresult") or {}).get("idlist") or []
                if ids and re.fullmatch(r"\d{7,8}", str(ids[0])):
                    return str(ids[0])
        except Exception as exc:
            logger.debug("ESearch DOI lookup failed for %s: %s", doi, exc)

        # 2) PMC ID Converter
        try:
            res = await client.get(
                "https://pmc.ncbi.nlm.nih.gov/tools/idconv/api/v1/articles/",
                params={"ids": doi, "format": "json", "tool": "qptm-agent", "email": "qptm@localhost"},
            )
            if res.status_code == 200:
                payload = res.json()
                for record in payload.get("records") or []:
                    pmid = record.get("pmid")
                    if pmid and re.fullmatch(r"\d{7,8}", str(pmid)):
                        return str(pmid)
        except Exception as exc:
            logger.debug("PMC idconv failed for %s: %s", doi, exc)

        # 3) Europe PMC
        try:
            res = await client.get(
                "https://www.ebi.ac.uk/europepmc/webservices/rest/search",
                params={"query": f'DOI:"{doi}"', "format": "json", "pageSize": 1},
            )
            if res.status_code == 200:
                results = (res.json().get("resultList") or {}).get("result") or []
                if results:
                    pmid = results[0].get("pmid") or results[0].get("id")
                    if pmid and re.fullmatch(r"\d{7,8}", str(pmid)):
                        return str(pmid)
        except Exception as exc:
            logger.debug("EuropePMC DOI lookup failed for %s: %s", doi, exc)

    return None


async def resolve_pmid_from_uploads(uploads: Iterable[tuple[str, bytes]]) -> str | None:
    """Try labeled PMID from file bodies; fall back to DOI → PMID lookup."""
    items = list(uploads)
    for filename, content in items:
        found = extract_pmid_from_upload(filename, content)
        if found:
            logger.info("Resolved PMID %s from upload content (%s)", found, filename)
            return found

    seen_dois: set[str] = set()
    tried = 0
    for filename, content in items:
        for doi in extract_dois_from_upload(filename, content):
            key = doi.lower()
            if key in seen_dois:
                continue
            seen_dois.add(key)
            tried += 1
            if tried > _MAX_DOI_LOOKUPS:
                return None
            logger.info("Trying DOI→PMID for %s (from %s)", doi, filename)
            pmid = await doi_to_pmid(doi)
            if pmid:
                logger.info("Resolved PMID %s via DOI %s", pmid, doi)
                return pmid
    return None
