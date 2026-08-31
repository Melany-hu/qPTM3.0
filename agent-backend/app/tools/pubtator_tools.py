"""PubTator3 literature search — supplementary PubMed recommendations.

When integrated databases cannot fully answer a question, this tool queries
the NCBI PubTator3 search API for relevant publications.

API docs: https://www.ncbi.nlm.nih.gov/research/pubtator3/api
Endpoint: GET /research/pubtator3-api/search/?text=<query>&page=<n>
"""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import quote

import httpx

from app.config import settings
from app.tools.registry import registry

logger = logging.getLogger(__name__)

PUBTATOR_HOME = "https://www.ncbi.nlm.nih.gov/research/pubtator3/"
PUBTATOR_PMID = "38460829"
PUBTATOR_DOI = "10.1093/nar/gkae263"


def _api_base() -> str:
    return (settings.pubtator_api_base_url or "").rstrip("/") or (
        "https://www.ncbi.nlm.nih.gov/research/pubtator3-api"
    )


def _client() -> httpx.Client:
    return httpx.Client(
        timeout=settings.http_timeout_seconds,
        follow_redirects=True,
        headers={"User-Agent": "qPTM_agent/1.0 (academic research)"},
    )


def _strip_html(text: str | None) -> str:
    if not text:
        return ""
    return re.sub(r"<[^>]+>", "", str(text))


def _format_authors(authors: list[str] | None, max_authors: int = 4) -> str:
    if not authors:
        return ""
    if len(authors) <= max_authors:
        return ", ".join(authors)
    return ", ".join(authors[:max_authors]) + ", et al."


def pubtator_literature_search(
    query: str,
    *,
    page: int = 1,
    limit: int = 8,
) -> dict[str, Any]:
    """Search PubTator3 for biomedical literature matching keywords."""
    q = (query or "").strip()
    if not q:
        return {"error": "Search query is required"}

    page = max(1, int(page or 1))
    limit = max(1, min(int(limit or 8), 10))

    url = f"{_api_base()}/search/?text={quote(q)}&page={page}"

    try:
        with _client() as client:
            resp = client.get(url)
            resp.raise_for_status()
            payload = resp.json()
    except httpx.HTTPError as exc:
        logger.warning("PubTator3 search failed: %s", exc)
        return {"error": f"PubTator3 API request failed: {exc}"}
    except ValueError as exc:
        return {"error": f"PubTator3 returned invalid JSON: {exc}"}

    raw_results = payload.get("results") or []
    if not isinstance(raw_results, list):
        raw_results = []

    papers: list[dict[str, Any]] = []
    for row in raw_results[:limit]:
        if not isinstance(row, dict):
            continue
        pmid = row.get("pmid")
        title = _strip_html(row.get("title"))
        if not pmid or not title:
            continue
        papers.append({
            "pmid": str(pmid),
            "title": title,
            "journal": row.get("journal") or "",
            "year": (row.get("meta_date_publication") or row.get("date") or "")[:4],
            "authors": _format_authors(row.get("authors")),
            "doi": row.get("doi") or "",
            "score": row.get("score"),
            "highlight": _strip_html(row.get("text_hl"))[:300] or None,
            "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
        })

    total = payload.get("total")
    if total is None:
        total = len(raw_results)

    summary = (
        f"PubTator3 found {total} publication(s) for '{q}'; "
        f"returning top {len(papers)} recommendation(s)"
        if papers
        else f"PubTator3 found no publications for '{q}'"
    )

    return {
        "summary": summary,
        "query": q,
        "page": page,
        "total": total,
        "homepage": PUBTATOR_HOME,
        "pmid": PUBTATOR_PMID,
        "doi": PUBTATOR_DOI,
        "papers": papers,
    }


def _ncbi_params() -> dict[str, str]:
    params: dict[str, str] = {"tool": "qptm-agent", "email": settings.ncbi_email or "qptm@localhost"}
    if settings.ncbi_api_key:
        params["api_key"] = settings.ncbi_api_key
    return params


def _parse_efetch_xml(xml_text: str) -> list[dict[str, Any]]:
    import xml.etree.ElementTree as ET

    abstracts: list[dict[str, Any]] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return abstracts

    for article in root.findall(".//PubmedArticle"):
        pmid_el = article.find(".//PMID")
        pmid = (pmid_el.text or "").strip() if pmid_el is not None else ""
        if not pmid.isdigit():
            continue
        title_el = article.find(".//ArticleTitle")
        title = _strip_html(title_el.text if title_el is not None else "")
        abstract_parts: list[str] = []
        for ab in article.findall(".//AbstractText"):
            label = ab.get("Label") or ""
            text = _strip_html("".join(ab.itertext()))
            if text:
                abstract_parts.append(f"{label}: {text}" if label else text)
        journal_el = article.find(".//Journal/Title")
        journal = _strip_html(journal_el.text if journal_el is not None else "")
        year_el = article.find(".//PubDate/Year")
        year = (year_el.text or "")[:4] if year_el is not None else ""
        abstract = " ".join(abstract_parts).strip()
        abstracts.append({
            "pmid": pmid,
            "title": title,
            "abstract": abstract,
            "journal": journal,
            "year": year,
            "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
        })
    return abstracts


def pubmed_fetch_abstracts(
    pmids: list[str] | str,
    *,
    max_chars: int = 2000,
) -> dict[str, Any]:
    """Fetch PubMed abstracts via NCBI eutils efetch."""
    if isinstance(pmids, str):
        raw = [p.strip() for p in re.split(r"[\s,;]+", pmids) if p.strip()]
    else:
        raw = [str(p).strip() for p in pmids]
    ids = []
    for p in raw:
        if p.isdigit() and len(p) >= 7:
            ids.append(p)
    ids = list(dict.fromkeys(ids))[:10]
    if not ids:
        return {"error": "At least one valid PMID is required"}

    params = {
        **_ncbi_params(),
        "db": "pubmed",
        "id": ",".join(ids),
        "retmode": "xml",
    }
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

    try:
        with _client() as client:
            resp = client.get(url, params=params)
            resp.raise_for_status()
            xml_text = resp.text
    except httpx.HTTPError as exc:
        logger.warning("PubMed efetch failed: %s", exc)
        return {"error": f"PubMed efetch failed: {exc}"}

    rows = _parse_efetch_xml(xml_text)
    cap = max(400, int(max_chars or 2000))
    for row in rows:
        ab = row.get("abstract") or ""
        if len(ab) > cap:
            row["abstract"] = ab[: cap - 3] + "..."

    summary = (
        f"Fetched {len(rows)} PubMed abstract(s) for PMIDs: {', '.join(ids[:5])}"
        + ("…" if len(ids) > 5 else "")
    )
    return {
        "summary": summary,
        "pmids": ids,
        "abstracts": rows,
        "papers": rows,
        "homepage": "https://pubmed.ncbi.nlm.nih.gov/",
    }


def register_pubtator_tools() -> None:
    registry.register(
        name="pubtator_literature_search",
        description=(
            "Search PubTator3 (NCBI) for relevant PubMed literature when integrated "
            "databases cannot fully answer the user's question. Provide keywords from "
            "the research context (gene, PTM site, modification type, disease, pathway, "
            "or mechanism terms)."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "Keyword search query, e.g. 'TP53 S15 phosphorylation DNA damage', "
                        "'BRCA1 ubiquitination breast cancer', or '@GENE_BRCA1 phosphorylation'"
                    ),
                },
                "page": {
                    "type": "integer",
                    "description": "Results page (1-based; default 1)",
                    "default": 1,
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum papers to return (1–10; default 8)",
                    "default": 8,
                },
            },
            "required": ["query"],
        },
        handler=pubtator_literature_search,
    )
    registry.register(
        name="pubmed_fetch_abstracts",
        description=(
            "Fetch PubMed article abstracts by PMID list. Use after identifying relevant "
            "papers from database hit PMIDs or PubTator search."
        ),
        parameters={
            "type": "object",
            "properties": {
                "pmids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of PubMed IDs (7–8 digits)",
                },
                "max_chars": {
                    "type": "integer",
                    "description": "Max characters per abstract (default 2000)",
                    "default": 2000,
                },
            },
            "required": ["pmids"],
        },
        handler=pubmed_fetch_abstracts,
    )
