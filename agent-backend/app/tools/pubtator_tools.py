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
