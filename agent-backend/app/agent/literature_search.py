"""Iterative PubMed literature search for site mechanism questions."""

from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Any, AsyncGenerator

from app.agent.literature import collect_pmids_from_results
from app.agent.memory import InvestigationMemory
from app.config import settings
from app.models.schemas import ToolResult
from app.tools.metadata import tool_database
from app.tools.pubtator_tools import pubmed_fetch_abstracts, pubtator_literature_search
from app.workflow.citations import attach_citations

logger = logging.getLogger(__name__)

_DOWNSTREAM_GENE_RE = re.compile(
    r"(?:下游靶基因|靶基因|downstream\s+(?:target\s+)?gene[s]?)\s*"
    r"([A-Z][A-Z0-9]{1,9})",
    re.I,
)
_GENE_TOKEN_RE = re.compile(r"\b([A-Z][A-Z0-9]{1,9})\b")
_SITE_RE = re.compile(r"\b([STYKR]\d+|Ser\d+|Thr\d+|Tyr\d+)\b", re.I)


def parse_downstream_gene(question: str, memory: InvestigationMemory) -> str | None:
    """Extract downstream target gene symbol from the user question."""
    m = _DOWNSTREAM_GENE_RE.search(question or "")
    if m:
        return m.group(1).upper()
    main = (memory.gene or "").upper()
    for g in _GENE_TOKEN_RE.findall(question or ""):
        if g.upper() != main and len(g) >= 3:
            return g.upper()
    return None


def _site_label(memory: InvestigationMemory, question: str) -> str:
    pos = memory.position
    if pos:
        return f"Ser{pos}" if str(pos).isdigit() else str(pos)
    m = _SITE_RE.search(question or "")
    return m.group(1) if m else ""


def fallback_search_queries(question: str, memory: InvestigationMemory) -> list[str]:
    gene = (memory.gene or "TP53").upper()
    site = _site_label(memory, question)
    downstream = parse_downstream_gene(question, memory) or ""
    queries: list[str] = []
    if downstream:
        queries.append(f"{gene} {site} phosphorylation {downstream} transcription regulation")
    queries.append(f"{gene} {site} upstream kinases ATM ATR DNA-PK")
    queries.append(f"{gene} phosphorylation MDM2 stability transcription activation")
    return queries[:3]


async def _plan_searches(llm: Any, question: str, memory: InvestigationMemory) -> list[str]:
    from app.orchestrator.llm_stream import llm_json
    from app.orchestrator.prompts import LIT_SEARCH_PLAN_SYSTEM

    downstream = parse_downstream_gene(question, memory) or "unknown"
    user = (
        f"Question: {question}\n"
        f"Gene: {memory.gene or 'unknown'}\n"
        f"Site: {memory.position or 'unknown'}\n"
        f"Downstream gene: {downstream}\n"
    )
    data = await llm_json(llm, LIT_SEARCH_PLAN_SYSTEM, user, max_tokens=500, timeout_s=8.0)
    if data and isinstance(data.get("queries"), list):
        qs = [str(q).strip() for q in data["queries"] if str(q).strip()][:3]
        if qs:
            return qs
    return fallback_search_queries(question, memory)


def _abstract_snippets(results: list[ToolResult], limit: int = 8) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for tr in results:
        data = tr.data or {}
        for p in (data.get("abstracts") or data.get("papers") or [])[:limit]:
            if not isinstance(p, dict):
                continue
            pmid = str(p.get("pmid") or "")
            if not pmid:
                continue
            out.append({
                "pmid": pmid,
                "title": str(p.get("title") or "")[:160],
                "abstract": str(p.get("abstract") or p.get("text") or "")[:600],
            })
            if len(out) >= limit:
                return out
    return out


async def _reflect_coverage(
    llm: Any,
    question: str,
    memory: InvestigationMemory,
    abstracts: list[dict[str, str]],
) -> dict[str, Any]:
    from app.orchestrator.llm_stream import llm_json
    from app.orchestrator.prompts import LIT_SEARCH_REFLECT_SYSTEM

    downstream = parse_downstream_gene(question, memory) or "unknown"
    abs_txt = "\n".join(
        f"PMID:{a['pmid']} {a['title']}\n{a['abstract'][:400]}"
        for a in abstracts[:6]
    )
    user = (
        f"Question: {question}\n"
        f"Gene: {memory.gene or 'unknown'}\n"
        f"Site: {memory.position or 'unknown'}\n"
        f"Downstream: {downstream}\n\n"
        f"Abstracts:\n{abs_txt or '(none yet)'}"
    )
    data = await llm_json(llm, LIT_SEARCH_REFLECT_SYSTEM, user, max_tokens=400, timeout_s=8.0)
    return data if isinstance(data, dict) else {}


async def _run_one_search(
    query: str,
    *,
    skip_pmids: set[str],
    seen_pmids: set[str],
) -> tuple[ToolResult | None, ToolResult | None, list[str], int]:
    """PubTator search + abstract fetch for one query. Returns (search_tr, fetch_tr, new_pmids, paper_count)."""
    search_raw = await asyncio.to_thread(
        pubtator_literature_search, query, limit=8,
    )
    if "error" in search_raw:
        return None, None, [], 0

    enriched_search = attach_citations(
        "pubtator_literature_search",
        tool_database("pubtator_literature_search"),
        search_raw,
    )
    paper_count = len(search_raw.get("papers") or [])
    new_pmids: list[str] = []
    for paper in (search_raw.get("papers") or []):
        p = str(paper.get("pmid") or "")
        if p.isdigit() and p not in skip_pmids and p not in seen_pmids:
            seen_pmids.add(p)
            new_pmids.append(p)

    fetch_tr: ToolResult | None = None
    batch = new_pmids[:6]
    if batch:
        fetch_raw = await asyncio.to_thread(
            pubmed_fetch_abstracts,
            batch,
            max_chars=settings.literature_max_abstract_chars,
        )
        if "error" not in fetch_raw and fetch_raw.get("abstracts"):
            fetch_tr = attach_citations(
                "pubmed_fetch_abstracts",
                tool_database("pubmed_fetch_abstracts"),
                fetch_raw,
            )
    return enriched_search, fetch_tr, new_pmids, paper_count


async def iterative_literature_search_events(
    question: str,
    memory: InvestigationMemory,
    llm: Any,
    api_results: list[ToolResult],
    *,
    skip_pmids: set[str] | None = None,
) -> AsyncGenerator[dict[str, Any], None]:
    """Yield literature_search trace events; final event type _literature_search_done."""
    if not settings.literature_enrichment_enabled:
        yield {"type": "_literature_search_done", "results": [], "traces": []}
        return

    deadline = time.monotonic() + float(settings.literature_iterative_timeout_s)
    max_rounds = int(settings.literature_iterative_max_rounds)
    skip = {str(p).strip() for p in (skip_pmids or set()) if str(p).strip().isdigit()}
    seen_pmids: set[str] = set(skip)
    enriched_results: list[ToolResult] = []
    traces: list[dict[str, Any]] = []

    if settings.literature_auto_fetch_api_pmids:
        for p in collect_pmids_from_results(api_results):
            if p not in seen_pmids:
                seen_pmids.add(p)

    planned = await _plan_searches(llm, question, memory)
    queries: list[str] = list(planned)
    round_idx = 0

    while round_idx < max_rounds and queries:
        if time.monotonic() >= deadline:
            logger.info("Iterative literature search hit soft timeout after %d rounds", round_idx)
            break

        query = queries.pop(0)
        round_idx += 1
        t0 = time.monotonic()

        yield {
            "type": "tool_call",
            "tool_name": "pubtator_literature_search",
            "arguments": {"query": query},
            "kind": "literature",
            "parent_agent": "literature",
        }

        search_tr, fetch_tr, _new_pmids, paper_count = await _run_one_search(
            query, skip_pmids=skip, seen_pmids=seen_pmids,
        )
        elapsed = round(time.monotonic() - t0, 1)

        trace = {
            "round": round_idx,
            "query": query,
            "papers_found": paper_count,
            "elapsed_s": elapsed,
        }
        traces.append(trace)
        yield {
            "type": "literature_search",
            "round": round_idx,
            "query": query,
            "papers_found": paper_count,
            "elapsed_s": elapsed,
        }

        if search_tr:
            enriched_results.append(search_tr)
            yield {
                "type": "tool_result",
                "payload": search_tr.model_dump_for_sse(),
                "kind": "literature",
                "parent_agent": "literature",
            }
        if fetch_tr:
            enriched_results.append(fetch_tr)
            yield {
                "type": "tool_call",
                "tool_name": "pubmed_fetch_abstracts",
                "arguments": {"pmids": _new_pmids[:6]},
                "kind": "literature",
                "parent_agent": "literature",
            }
            yield {
                "type": "tool_result",
                "payload": fetch_tr.model_dump_for_sse(),
                "kind": "literature",
                "parent_agent": "literature",
            }

        if round_idx >= max_rounds or time.monotonic() >= deadline:
            break

        reflection = await _reflect_coverage(
            llm, question, memory, _abstract_snippets(enriched_results),
        )
        if reflection.get("sufficient"):
            break
        next_q = str(reflection.get("next_query") or "").strip()
        if next_q and next_q not in queries and next_q not in {t["query"] for t in traces}:
            queries.append(next_q)

    yield {
        "type": "_literature_search_done",
        "results": enriched_results,
        "traces": traces,
    }
