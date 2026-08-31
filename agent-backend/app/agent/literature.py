"""Literature enrichment — PubTator search + PubMed abstract fetch."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from app.agent.memory import InvestigationMemory
from app.config import settings
from app.models.schemas import ToolResult
from app.tools.metadata import tool_database
from app.tools.pubtator_tools import pubmed_fetch_abstracts, pubtator_literature_search
from app.workflow.citations import attach_citations
from app.workflow.planner import _build_pubtator_query

logger = logging.getLogger(__name__)

_PMID_RE = re.compile(r"\b(\d{7,8})\b")


def collect_pmids_from_results(results: list[ToolResult]) -> list[str]:
    """Extract PMIDs embedded in API tool JSON."""
    seen: set[str] = set()
    ordered: list[str] = []

    def _add(pmid: str) -> None:
        p = str(pmid).strip()
        if p.isdigit() and p not in seen:
            seen.add(p)
            ordered.append(p)

    def _walk(obj: Any, depth: int = 0) -> None:
        if depth > 8:
            return
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k in ("pmid", "pmids", "experimental_pmids") and v:
                    if isinstance(v, list):
                        for item in v:
                            _add(str(item))
                    else:
                        _add(str(v))
                else:
                    _walk(v, depth + 1)
        elif isinstance(obj, list):
            for item in obj[:40]:
                _walk(item, depth + 1)
        elif isinstance(obj, str):
            for m in _PMID_RE.findall(obj):
                _add(m)

    for tr in results:
        if tr.tool in ("pubtator_literature_search", "pubmed_fetch_abstracts"):
            continue
        _walk(tr.data or {})
    return ordered


def build_literature_query(question: str, memory: InvestigationMemory) -> str:
    entities = dict(memory.entities or {})
    entities.setdefault("gene", memory.gene)
    entities.setdefault("uniprot_ac", memory.uniprot_ac)
    entities.setdefault("position", memory.position)
    entities.setdefault("ptm_type", memory.ptm_type)
    entities.setdefault("mutation_label", memory.mutation_label)
    return _build_pubtator_query(entities, question)


async def enrich_literature(
    question: str,
    memory: InvestigationMemory,
    api_results: list[ToolResult],
    *,
    skip_pmids: set[str] | None = None,
) -> list[ToolResult]:
    """Search PubTator + fetch abstracts; return new ToolResult rows."""
    if not settings.literature_enrichment_enabled:
        return []

    out: list[ToolResult] = []
    limit = settings.literature_abstract_limit
    pmids: list[str] = []
    skip = {str(p).strip() for p in (skip_pmids or set()) if str(p).strip().isdigit()}

    if settings.literature_auto_fetch_api_pmids:
        pmids.extend(collect_pmids_from_results(api_results))

    # PubTator search for additional papers
    query = build_literature_query(question, memory)
    if query:
        search_raw = await asyncio.to_thread(
            pubtator_literature_search, query, limit=min(8, limit + 3),
        )
        if "error" not in search_raw:
            enriched_search = attach_citations(
                "pubtator_literature_search", tool_database("pubtator_literature_search"), search_raw,
            )
            out.append(enriched_search)
            for paper in (search_raw.get("papers") or []):
                p = str(paper.get("pmid") or "")
                if p.isdigit() and p not in pmids:
                    pmids.append(p)

    pmids = [p for p in pmids if p not in skip][:limit]
    if not pmids:
        return out

    fetch_raw = await asyncio.to_thread(
        pubmed_fetch_abstracts,
        pmids,
        max_chars=settings.literature_max_abstract_chars,
    )
    if "error" not in fetch_raw and fetch_raw.get("abstracts"):
        enriched_fetch = attach_citations(
            "pubmed_fetch_abstracts", tool_database("pubmed_fetch_abstracts"), fetch_raw,
        )
        out.append(enriched_fetch)

    return out
