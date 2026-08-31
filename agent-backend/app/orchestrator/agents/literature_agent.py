"""Literature sub-agent — seed PMID fetch, PubTator search, interpretation."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, AsyncGenerator

from app.agent.literature import enrich_literature
from app.agent.literature_search import iterative_literature_search_events
from app.agent.memory import InvestigationMemory
from app.config import settings
from app.models.schemas import ToolResult
from app.orchestrator.clue_buffer import ClueBuffer
from app.orchestrator.llm_stream import llm_json
from app.orchestrator.prompts import LIT_INTERPRET_SYSTEM
from app.orchestrator.schemas import DatabaseBrief, LiteratureBrief, OrchestratorPlan
from app.tools.metadata import tool_database
from app.tools.pubtator_tools import pubmed_fetch_abstracts
from app.workflow.citations import attach_citations

logger = logging.getLogger(__name__)


async def run_literature_agent(
    question: str,
    memory: InvestigationMemory,
    llm: Any,
    clue_buffer: ClueBuffer,
    db_brief: DatabaseBrief | None,
    plan: OrchestratorPlan | None = None,
    *,
    lang: str,
    focus: str = "",
) -> AsyncGenerator[dict[str, Any], None]:
    yield {
        "type": "agent_started",
        "agent": "literature",
        "label": "检索文献…" if lang == "zh" else "Searching literature…",
        "focus": focus or question[:200],
    }

    enriched_results: list[ToolResult] = []
    search_traces: list[dict[str, Any]] = []
    seed_pmids = clue_buffer.pmids()
    clues_addressed: list[str] = []
    mechanism_mode = bool(plan and plan.mechanism_question)

    if seed_pmids and settings.literature_enrichment_enabled and not mechanism_mode:
        limit = min(len(seed_pmids), settings.literature_abstract_limit)
        batch = seed_pmids[:limit]
        yield {
            "type": "tool_call",
            "tool_name": "pubmed_fetch_abstracts",
            "arguments": {"pmids": batch},
            "kind": "literature",
            "parent_agent": "literature",
        }
        fetch_raw = await asyncio.to_thread(
            pubmed_fetch_abstracts,
            batch,
            max_chars=settings.literature_max_abstract_chars,
        )
        if "error" not in fetch_raw and fetch_raw.get("abstracts"):
            enriched = attach_citations(
                "pubmed_fetch_abstracts",
                tool_database("pubmed_fetch_abstracts"),
                fetch_raw,
            )
            enriched_results.append(enriched)
            clues_addressed.extend(batch)
            yield {
                "type": "tool_result",
                "payload": enriched.model_dump_for_sse(),
                "kind": "literature",
                "parent_agent": "literature",
            }

    api_results = (db_brief.tool_results if db_brief else [])

    if mechanism_mode and settings.literature_enrichment_enabled:
        async for event in iterative_literature_search_events(
            question, memory, llm, api_results, skip_pmids=set(seed_pmids),
        ):
            if event.get("type") == "_literature_search_done":
                for tr in event.get("results") or []:
                    if not any(e.tool == tr.tool and e.data == tr.data for e in enriched_results):
                        enriched_results.append(tr)
                search_traces = event.get("traces") or []
                continue
            yield event
    else:
        lit_more = await enrich_literature(
            question, memory, api_results, skip_pmids=set(seed_pmids),
        )
        for enriched in lit_more:
            if any(e.tool == enriched.tool for e in enriched_results):
                continue
            enriched_results.append(enriched)
            yield {
                "type": "tool_call",
                "tool_name": enriched.tool,
                "arguments": {},
                "kind": "literature",
                "parent_agent": "literature",
            }
            yield {
                "type": "tool_result",
                "payload": enriched.model_dump_for_sse(),
                "kind": "literature",
                "parent_agent": "literature",
            }

    brief = await _interpret_lit(
        llm, question, enriched_results, clue_buffer, focus, mechanism_mode=mechanism_mode,
    )
    brief.tool_results = enriched_results
    brief.seed_pmids_fetched = clues_addressed
    brief.clues_addressed = clues_addressed
    brief.search_traces = search_traces

    yield {"type": "agent_brief", "agent": "literature", "preview": brief.summary[:500]}
    yield {
        "type": "agent_completed",
        "agent": "literature",
        "summary": brief.summary[:200] or ("文献检索完成" if lang == "zh" else "Literature search complete"),
    }
    yield {"type": "_literature_brief", "brief": brief}


async def _interpret_lit(
    llm: Any,
    question: str,
    results: list[ToolResult],
    clue_buffer: ClueBuffer,
    focus: str,
    *,
    mechanism_mode: bool = False,
) -> LiteratureBrief:
    papers: list[dict[str, Any]] = []
    abstract_text = ""
    for tr in results:
        data = tr.data or {}
        for p in (data.get("papers") or data.get("abstracts") or [])[:12]:
            if isinstance(p, dict) and p.get("pmid"):
                papers.append({
                    "pmid": str(p.get("pmid")),
                    "title": str(p.get("title") or "")[:160],
                    "relevance": "",
                })
                abstract_text += (
                    f"\nPMID:{p.get('pmid')} {p.get('title', '')}\n"
                    f"{str(p.get('abstract') or p.get('text') or '')[:800]}\n"
                )

    clues_txt = "\n".join(
        f"PMID:{c.pmid} — {c.context}" for c in clue_buffer.all()[:8]
    )
    user = (
        f"Question: {question}\nFocus: {focus}\n"
        f"Database clues:\n{clues_txt}\n\n"
        f"Papers found: {len(papers)}\n"
        f"Abstract excerpts:{abstract_text[:4000]}"
    )

    mechanism_steps: list[dict[str, Any]] = []
    if settings.subagent_interpret_enabled and results:
        max_tokens = 1200 if mechanism_mode else 900
        data = await llm_json(llm, LIT_INTERPRET_SYSTEM, user, max_tokens=max_tokens, timeout_s=12.0)
        if data:
            rec = data.get("recommended_papers") or papers
            if isinstance(rec, list):
                papers = [p for p in rec if isinstance(p, dict)][:6]
            raw_steps = data.get("mechanism_steps") or []
            if isinstance(raw_steps, list):
                mechanism_steps = [s for s in raw_steps if isinstance(s, dict)][:6]
            return LiteratureBrief(
                summary=str(data.get("summary") or ""),
                recommended_papers=papers,
                mechanism_steps=mechanism_steps,
            )

    return LiteratureBrief(
        summary=f"Retrieved {len(papers)} paper(s).",
        recommended_papers=papers[:6],
        mechanism_steps=mechanism_steps,
    )
