"""Database sub-agent — tool retrieval, execution, interpretation, clue extraction."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncGenerator

from app.agent.knowledge_bases import is_literature_tool
from app.agent.memory import InvestigationMemory, tool_result_message
from app.agent.phases import phase_event
from app.agent.retriever import retrieve_tools
from app.config import settings
from app.llm.prompts import build_react_messages
from app.models.schemas import ToolResult
from app.orchestrator.clue_buffer import ClueBuffer
from app.orchestrator.clues import extract_clues_from_result
from app.orchestrator.llm_stream import llm_json, stream_llm_events
from app.orchestrator.prompts import DB_INTERPRET_SYSTEM
from app.orchestrator.schemas import DatabaseBrief, OrchestratorPlan
from app.tools.metadata import tool_database
from app.tools.registry import registry
from app.workflow.citations import attach_citations
from app.workflow.context import merge_citations

logger = logging.getLogger(__name__)


def _record_tool(memory: InvestigationMemory, state, enriched: ToolResult) -> None:
    memory.update_from_tool(enriched)
    if settings.evidence_graph_enabled:
        state.get_evidence_graph().add_from_tool_result(enriched)


async def run_database_agent(
    question: str,
    history: list[dict[str, str]],
    memory: InvestigationMemory,
    state,
    plan: OrchestratorPlan,
    llm: Any,
    clue_buffer: ClueBuffer,
    *,
    mode: str,
    lang: str,
    focus: str = "",
) -> AsyncGenerator[dict[str, Any], None]:
    """Execute database tools; yield orchestrator events."""
    yield {
        "type": "agent_started",
        "agent": "database",
        "label": "检索数据库…" if lang == "zh" else "Searching databases…",
        "focus": focus or question[:200],
    }

    yield phase_event("retrieving_tools", lang)
    catalog = registry.catalog()
    tool_names = await retrieve_tools(
        question, memory, catalog, llm,
        top_k=plan.top_k_tools,
        use_llm=settings.use_llm_tool_retriever,
        include_literature=False,
    )
    tool_schemas = registry.schemas_for_tools(tool_names)
    graph = state.get_evidence_graph()
    messages = build_react_messages(
        question,
        history,
        memory.to_prompt_block(),
        query_mode=mode,
        graph_summary=graph.retrieve_summary() if settings.evidence_graph_enabled else "",
    )
    enriched_results: list[ToolResult] = []

    for _round in range(plan.max_tool_rounds):
        round_calls: list[dict[str, Any]] = []
        async for event in stream_llm_events(llm, messages, tool_schemas, disable_thinking=True):
            if event["type"] == "tool_call":
                round_calls.append(event)
            elif event["type"] == "error":
                yield event
                return
            elif event["type"] == "done":
                break

        if not round_calls:
            break

        messages.append({
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {"name": tc["name"], "arguments": json.dumps(tc["arguments"])},
                }
                for tc in round_calls
            ],
        })

        for tc in round_calls:
            name = tc["name"]
            if is_literature_tool(name):
                continue
            args = tc["arguments"]
            yield {
                "type": "tool_call",
                "tool_name": name,
                "arguments": args,
                "kind": "database",
                "parent_agent": "database",
            }
            result = await asyncio.to_thread(registry.execute, name, args)
            db = tool_database(name)
            enriched = attach_citations(name, db, result)
            enriched_results.append(enriched)
            merge_citations(enriched_results)
            _record_tool(memory, state, enriched)
            yield {
                "type": "tool_result",
                "payload": enriched.model_dump_for_sse(),
                "kind": "database",
                "parent_agent": "database",
            }
            messages.append(tool_result_message(tc["id"], enriched))

            new_clues = extract_clues_from_result(
                enriched,
                gene=memory.gene,
                site=memory.position,
            )
            added = clue_buffer.add_many(new_clues)
            if added:
                yield {
                    "type": "agent_handoff",
                    "from_agent": "database",
                    "to_agent": "literature",
                    "clues": [c.to_dict() for c in added],
                    "pmid_count": len(added),
                }

        state.sync_memory_to_targets()

    brief = await _interpret_db(llm, question, enriched_results, memory)
    brief.tool_results = enriched_results
    brief.literature_clues = clue_buffer.all()

    yield {
        "type": "agent_brief",
        "agent": "database",
        "preview": brief.summary[:500],
    }
    yield {
        "type": "agent_completed",
        "agent": "database",
        "summary": brief.summary[:200] or ("完成数据库检索" if lang == "zh" else "Database search complete"),
    }
    yield {"type": "_database_brief", "brief": brief}


async def _interpret_db(
    llm: Any,
    question: str,
    results: list[ToolResult],
    memory: InvestigationMemory,
) -> DatabaseBrief:
    if not results:
        return DatabaseBrief(summary="No database results.", gaps=["No tools returned data"])

    snippets = []
    for tr in results[:8]:
        snippets.append(f"Tool {tr.tool}: {tr.summary or ''}"[:300])
    user = f"Question: {question}\nGene: {memory.gene}\nSite: {memory.position}\n\n" + "\n".join(snippets)

    if settings.subagent_interpret_enabled:
        data = await llm_json(llm, DB_INTERPRET_SYSTEM, user, max_tokens=800, timeout_s=10.0)
        if data:
            return DatabaseBrief(
                summary=str(data.get("summary") or ""),
                key_findings=[str(x) for x in (data.get("key_findings") or [])[:8]],
                gaps=[str(x) for x in (data.get("gaps") or [])[:4]],
            )

    findings = [tr.summary for tr in results if tr.success and tr.summary][:6]
    return DatabaseBrief(
        summary="; ".join(findings)[:400],
        key_findings=findings,
    )
