"""Extract PMID (and DOI→PMID / title→PMID) from uploaded collection files."""

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
    # Publisher footers / headers: "PubMed: 12345678"
    re.compile(r"PubMed\s*[=:]\s*(\d{7,8})\b", re.I),
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
_TITLE_HTTP_TIMEOUT = 10.0
_PDF_TEXT_PAGES = 8


def _normalize_pdf_text(text: str) -> str:
    """Fix common PDF extraction artifacts that break DOI / PMID matching."""
    if not text:
        return ""
    # Soft hyphen / hyphenation across line breaks: "modifi-\ncation" → "modification"
    t = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", text)
    # DOI often split: "10.1038/\nncb.1234" or "doi.org/10.\n1038/..."
    t = re.sub(r"(10\.\d{4,9}/)\s*\n\s*", r"\1", t)
    t = re.sub(r"(doi\.org/)\s*\n\s*", r"\1", t, flags=re.I)
    t = re.sub(r"\s*\n\s*", " ", t)
    return t


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


def _pdf_reader(content: bytes):
    try:
        from pypdf import PdfReader
    except ImportError:
        logger.warning("pypdf not installed; cannot extract text from PDF uploads")
        return None
    try:
        return PdfReader(io.BytesIO(content))
    except Exception as exc:
        logger.warning("PDF open failed: %s", exc)
        return None


def _pdf_page_texts(content: bytes, max_pages: int = _PDF_TEXT_PAGES) -> list[str]:
    reader = _pdf_reader(content)
    if reader is None:
        return []
    try:
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
        found = _first_pmid(_normalize_pdf_text(text), allow_bare=False)
        if found:
            return found
    if pages:
        found = _first_pmid(_normalize_pdf_text("\n".join(pages)), allow_bare=False)
        if found:
            return found
    # pypdf failed / empty text: still allow labeled PMID strings in the stream
    return extract_pmid_from_bytes(content, allow_bare=False)


_TITLE_STOP_RE = re.compile(
    r"^(abstract|introduction|keywords?|background|results?|methods?|"
    r"materials?\s+and\s+methods|references|acknowledg|copyright|received|"
    r"accepted|published|online|volume|article|research\s+article|"
    r"original\s+article|brief\s+communication|letter\s+to|doi|pmid|http|"
    r"www\.|supplementary|supporting\s+information)\b",
    re.I,
)
_AUTHOR_LINE_RE = re.compile(
    r"(,\s*[A-Z]\.){2,}|"  # Doe, J., Smith, A.
    r"\b(university|institute|department|school of|hospital|laboratory)\b|"
    r"@|"
    r"^\d+\s*$|"
    r"^[A-Z][a-z]+(?:\s+[A-Z]\.?)+(?:\s*,\s*[A-Z][a-z]+(?:\s+[A-Z]\.?)+)+$",
    re.I,
)


def extract_title_from_pdf(content: bytes) -> str | None:
    """Best-effort article title from PDF metadata or first-page text."""
    reader = _pdf_reader(content)
    if reader is not None:
        try:
            meta = reader.metadata
            raw = None
            if meta is not None:
                raw = getattr(meta, "title", None) or (
                    meta.get("/Title") if hasattr(meta, "get") else None
                )
            if raw:
                title = str(raw).strip()
                # Ignore filename-like or empty metadata titles
                if (
                    len(title) >= 15
                    and not re.fullmatch(r"[\w.\- ]+\.pdf", title, re.I)
                    and not re.fullmatch(r"\d{7,8}", title)
                    and "untitled" not in title.lower()
                ):
                    return re.sub(r"\s+", " ", title)[:300]
        except Exception:
            pass

    pages = _pdf_page_texts(content, max_pages=2)
    if not pages:
        return None
    text = pages[0]
    lines = [re.sub(r"\s+", " ", ln).strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln]

    # Cut at Abstract / Introduction block
    cut = len(lines)
    for i, ln in enumerate(lines):
        if _TITLE_STOP_RE.match(ln) or re.fullmatch(r"abstract", ln, re.I):
            cut = i
            break
    candidates = lines[:cut] if cut > 0 else lines[:12]

    # Skip leading journal / running-head noise (short ALL-CAPS or volume lines)
    body: list[str] = []
    for ln in candidates:
        if len(ln) < 8:
            continue
        if _TITLE_STOP_RE.match(ln):
            break
        if _AUTHOR_LINE_RE.search(ln) and len(body) > 0:
            break
        if re.fullmatch(r"[A-Z0-9 \-–—,.:;/&]{8,60}", ln) and ln.isupper() and len(body) == 0:
            # Likely journal running head — skip
            continue
        if re.search(r"\b(vol\.?|pp\.?|pages?)\b", ln, re.I) and len(ln) < 40:
            continue
        body.append(ln)
        # Titles are rarely more than ~3 extracted lines
        joined = " ".join(body)
        if len(joined) >= 40 and (
            len(body) >= 2 or joined.endswith((".", "?", "!")) or len(joined) >= 80
        ):
            break
        if len(body) >= 3:
            break

    if not body:
        return None
    title = re.sub(r"\s+", " ", " ".join(body)).strip(" .,;:")
    if len(title) < 15:
        return None
    return title[:300]


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
            texts.extend(_normalize_pdf_text(p) for p in pages)
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


def extract_title_from_upload(filename: str, content: bytes) -> str | None:
    ext = Path(filename).suffix.lower()
    if ext == ".pdf":
        return extract_title_from_pdf(content)
    if ext == ".xml":
        text = content.decode("utf-8", errors="replace")
        m = re.search(r"<article-title[^>]*>(.*?)</article-title>", text, re.I | re.S)
        if m:
            title = re.sub(r"<[^>]+>", "", m.group(1))
            title = re.sub(r"\s+", " ", title).strip()
            if len(title) >= 15:
                return title[:300]
    return None


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


def _norm_title_key(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


async def title_to_pmid(title: str) -> str | None:
    """Resolve article title → PMID via PubMed / Europe PMC / Crossref→DOI."""
    title = re.sub(r"\s+", " ", (title or "").strip())
    if len(title) < 15:
        return None
    # Trim trailing junk often captured from first page
    title = re.sub(r"\s+(Abstract|Introduction|Keywords)\b.*$", "", title, flags=re.I).strip()
    if len(title) < 15:
        return None

    timeout = httpx.Timeout(_TITLE_HTTP_TIMEOUT)
    want = _norm_title_key(title)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        # 1) PubMed title search
        try:
            res = await client.get(
                "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
                params={
                    "db": "pubmed",
                    "term": f"{title}[Title]",
                    "retmode": "json",
                    "retmax": "5",
                    "tool": "qptm-agent",
                    "email": "qptm@localhost",
                },
            )
            if res.status_code == 200:
                ids = (res.json().get("esearchresult") or {}).get("idlist") or []
                ids = [str(i) for i in ids if re.fullmatch(r"\d{7,8}", str(i))]
                if len(ids) == 1:
                    return ids[0]
                if ids:
                    # Disambiguate via ESummary titles
                    sum_res = await client.get(
                        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi",
                        params={
                            "db": "pubmed",
                            "id": ",".join(ids),
                            "retmode": "json",
                            "tool": "qptm-agent",
                            "email": "qptm@localhost",
                        },
                    )
                    if sum_res.status_code == 200:
                        result = (sum_res.json().get("result") or {})
                        best_id = None
                        best_score = 0
                        for pid in ids:
                            rec = result.get(pid) or {}
                            rt = str(rec.get("title") or "")
                            key = _norm_title_key(rt)
                            if not key:
                                continue
                            if key == want or want in key or key in want:
                                score = min(len(key), len(want))
                                if score > best_score:
                                    best_score = score
                                    best_id = pid
                        if best_id and best_score >= 20:
                            return best_id
        except Exception as exc:
            logger.debug("PubMed title search failed: %s", exc)

        # 2) Europe PMC title search
        try:
            res = await client.get(
                "https://www.ebi.ac.uk/europepmc/webservices/rest/search",
                params={
                    "query": f'TITLE:"{title[:180]}"',
                    "format": "json",
                    "pageSize": 3,
                },
            )
            if res.status_code == 200:
                results = (res.json().get("resultList") or {}).get("result") or []
                for rec in results:
                    pmid = rec.get("pmid") or rec.get("id")
                    if not pmid or not re.fullmatch(r"\d{7,8}", str(pmid)):
                        continue
                    rt = str(rec.get("title") or "")
                    key = _norm_title_key(rt)
                    if key == want or want in key or key in want or len(results) == 1:
                        return str(pmid)
        except Exception as exc:
            logger.debug("EuropePMC title search failed: %s", exc)

        # 3) Crossref bibliographic → DOI → PMID
        try:
            res = await client.get(
                "https://api.crossref.org/works",
                params={"query.bibliographic": title[:200], "rows": 3},
                headers={"User-Agent": "qPTM-Agent/1.0 (mailto:qptm@localhost)"},
            )
            if res.status_code == 200:
                items = ((res.json().get("message") or {}).get("items")) or []
                for item in items:
                    rt = " ".join(item.get("title") or [])
                    key = _norm_title_key(rt)
                    doi = item.get("DOI")
                    if not doi:
                        continue
                    if key == want or want in key or key in want or len(items) == 1:
                        pmid = await doi_to_pmid(str(doi))
                        if pmid:
                            return pmid
        except Exception as exc:
            logger.debug("Crossref title search failed: %s", exc)

    return None


async def resolve_pmid_from_uploads(uploads: Iterable[tuple[str, bytes]]) -> str | None:
    """Try labeled PMID from file bodies; then DOI→PMID; then title→PMID."""
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
                break
            logger.info("Trying DOI→PMID for %s (from %s)", doi, filename)
            pmid = await doi_to_pmid(doi)
            if pmid:
                logger.info("Resolved PMID %s via DOI %s", pmid, doi)
                return pmid

    # Last resort: article title from PDF/XML → PubMed / EuropePMC / Crossref
    for filename, content in items:
        title = extract_title_from_upload(filename, content)
        if not title:
            continue
        logger.info("Trying title→PMID for %r (from %s)", title[:120], filename)
        pmid = await title_to_pmid(title)
        if pmid:
            logger.info("Resolved PMID %s via title %r", pmid, title[:80])
            return pmid
    return None
