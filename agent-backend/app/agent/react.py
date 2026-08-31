"""ReAct agent loop — LLM decides tools, literature enrichment, synthesis."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, AsyncGenerator

from app.agent.clarification import (
    assess_clarification_need,
    build_literature_clarification_request,
    merge_clarification_answers,
    should_assess_clarification,
)
from app.agent.followups import generate_follow_up_questions
from app.agent.gate import (
    QUERY_MODES_SITE_RESOLVE,
    QUERY_MODES_WITH_TOOLS,
    QUERY_MODE_CLARIFY,
    QUERY_MODE_CONCEPT,
    QUERY_MODE_FOLLOWUP,
    QUERY_MODE_RESEARCH,
    build_gate_reply,
    classify_query_mode,
    is_literature_request,
)
from app.agent.knowledge_bases import is_literature_tool
from app.agent.literature import enrich_literature
from app.agent.memory import InvestigationMemory, prepare_investigation_context, tool_result_message
from app.agent.query_depth import classify_query_depth
from app.agent.retriever import retrieve_tools
from app.config import settings
from app.llm.deepseek_client import get_llm_client
from app.llm.prompts import build_concept_messages, build_react_messages, build_synthesis_messages
from app.models.schemas import ToolResult
from app.tools.metadata import tool_database
from app.tools.registry import registry
from app.workflow.citations import attach_citations
from app.workflow.context import build_agent_context, merge_citations
from app.workflow.state import session_manager

logger = logging.getLogger(__name__)

from app.agent.phases import phase_event


def _detect_lang(question: str) -> str:
    zh = sum(1 for ch in question if "\u4e00" <= ch <= "\u9fff")
    latin = sum(1 for ch in question if "a" <= ch.lower() <= "z")
    return "zh" if zh >= 2 and zh >= latin * 0.35 else "en"


def _needs_citation_pass(text: str) -> bool:
    return not re.search(r"\[S\d+\]", text or "")


async def _emit_followups(
    user_message: str,
    answer: str,
    memory: InvestigationMemory,
    mode: str,
    llm,
) -> AsyncGenerator[dict[str, Any], None]:
    try:
        questions = await generate_follow_up_questions(
            user_message, answer, memory, mode, llm,
        )
        if questions:
            yield {"type": "follow_up_questions", "questions": questions}
    except Exception as exc:
        logger.warning("Follow-up generation skipped: %s", exc)


async def _stream_llm_events(
    llm,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    *,
    max_tokens: int = 8192,
    disable_thinking: bool = False,
) -> AsyncGenerator[dict[str, Any], None]:
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[Any] = asyncio.Queue()

    def _producer() -> None:
        try:
            for event in llm.chat_completion_stream(
                messages,
                tools=tools,
                max_tokens=max_tokens,
                disable_thinking=disable_thinking,
            ):
                loop.call_soon_threadsafe(queue.put_nowait, event)
        except Exception as exc:
            logger.error("LLM stream error: %s", exc, exc_info=True)
            loop.call_soon_threadsafe(
                queue.put_nowait,
                {"type": "error", "message": str(exc)},
            )
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)

    loop.run_in_executor(None, _producer)

    while True:
        event = await queue.get()
        if event is None:
            break
        yield event


def _record_tool(
    memory: InvestigationMemory,
    state,
    enriched: ToolResult,
) -> None:
    memory.update_from_tool(enriched)
    if settings.evidence_graph_enabled:
        state.get_evidence_graph().add_from_tool_result(enriched)


async def run_react(
    user_message: str,
    history: list[dict[str, str]],
    session_id: str,
    *,
    clarification_response: dict[str, Any] | None = None,
) -> AsyncGenerator[dict[str, Any], None]:
    """ReAct loop → literature enrichment → synthesis."""
    state = session_manager.get_or_create(session_id)
    state.turn_count += 1
    memory = state.get_memory()
    prepare_investigation_context(memory, state, history)
    lang = _detect_lang(user_message)

    forced_research = False
    if clarification_response and state.pending_clarification:
        pending = state.pending_clarification
        original = str(pending.get("message") or user_message)
        if clarification_response.get("skip"):
            user_message = original
        else:
            user_message = merge_clarification_answers(
                original,
                clarification_response.get("selections") or {},
                clarification_response.get("free_text") or "",
            )
        state.pending_clarification = None
        entities = memory.update_from_message(user_message)
        mode = QUERY_MODE_RESEARCH
        memory.query_mode = mode
        forced_research = True
    else:
        entities = memory.update_from_message(user_message)
        mode = classify_query_mode(user_message, entities, state, history=history)
        memory.query_mode = mode
    entities["query_mode"] = mode

    if not forced_research and mode not in QUERY_MODES_WITH_TOOLS:
        yield {"type": "plan_created", "plan": {
            "question": user_message,
            "intent_summary": "Direct reply",
            "steps": [],
        }}
        if mode == QUERY_MODE_CONCEPT:
            llm = get_llm_client()
            concept_messages = build_concept_messages(user_message, history)
            full_text = ""
            try:
                async for event in _stream_llm_events(
                    llm, concept_messages, [], max_tokens=4096, disable_thinking=True,
                ):
                    if event["type"] == "text":
                        full_text += event["content"]
                        yield {"type": "text", "content": event["content"]}
                    elif event["type"] == "error":
                        yield event
                        return
            except Exception as exc:
                logger.error("Concept LLM error: %s", exc, exc_info=True)
                full_text = build_gate_reply(mode, user_message)
                chunk_size = 80
                for i in range(0, len(full_text), chunk_size):
                    yield {"type": "text", "content": full_text[i : i + chunk_size]}
            async for fu in _emit_followups(user_message, full_text, memory, mode, llm):
                yield fu
            yield {"type": "done"}
            return

        if mode == QUERY_MODE_CLARIFY and is_literature_request(user_message):
            clar_req = build_literature_clarification_request(user_message, lang=lang)
            if settings.clarification_enabled:
                state.pending_clarification = {
                    "message": user_message,
                    "entities": dict(memory.entities),
                }
                yield {"type": "plan_created", "plan": {
                    "question": user_message,
                    "intent_summary": "Clarifying literature scope…",
                    "steps": [],
                }}
                yield {"type": "clarification_request", **clar_req}
                yield {"type": "done"}
                return

        reply = build_gate_reply(mode, user_message)
        chunk_size = 80
        for i in range(0, len(reply), chunk_size):
            yield {"type": "text", "content": reply[i : i + chunk_size]}
        async for fu in _emit_followups(user_message, reply, memory, mode, None):
            yield fu
        yield {"type": "done"}
        return

    # LLM decides whether clarification would enable deeper research
    if (
        not forced_research
        and settings.clarification_enabled
        and should_assess_clarification(mode)
    ):
        llm = get_llm_client()
        clar_req = await assess_clarification_need(
            llm, user_message, entities, memory, history, lang=lang,
        )
        if clar_req:
            state.pending_clarification = {
                "message": user_message,
                "entities": dict(entities),
            }
            yield {"type": "plan_created", "plan": {
                "question": user_message,
                "intent_summary": "Planning deeper research…",
                "steps": [],
            }}
            yield {"type": "clarification_request", **clar_req}
            yield {"type": "done"}
            return

    if mode in QUERY_MODES_SITE_RESOLVE and memory.gene and not memory.uniprot_ac:
        try:
            from app.sources.uniprot_id import lookup_by_gene

            organism = (memory.organism or "human").lower()
            tax = {"human": 9606, "mouse": 10090, "rat": 10116}.get(organism, 9606)
            ident = lookup_by_gene(str(memory.gene), organism_id=tax)
            if ident and ident.get("uniprot_ac"):
                memory.uniprot_ac = ident["uniprot_ac"]
                if ident.get("gene"):
                    memory.gene = ident.get("gene") or memory.gene
        except Exception as exc:
            logger.debug("Early UniProt resolve skipped: %s", exc)

    llm = get_llm_client()
    catalog = registry.catalog()
    depth = classify_query_depth(user_message, memory, mode)
    max_rounds = depth.max_tool_rounds
    run_literature = depth.run_literature
    if settings.literature_enrichment_mode == "always":
        run_literature = settings.literature_enrichment_enabled
    elif settings.literature_enrichment_mode == "never":
        run_literature = False
    else:
        run_literature = depth.run_literature and settings.literature_enrichment_enabled

    yield {"type": "plan_created", "plan": {
        "question": user_message,
        "intent_summary": f"Investigating ({depth.label})…",
        "steps": [],
        "depth": depth.level,
    }}
    if depth.run_database_tools:
        yield phase_event("database", lang)

    tool_names = await retrieve_tools(
        user_message, memory, catalog, llm,
        top_k=depth.top_k_tools,
        use_llm=settings.use_llm_tool_retriever,
        include_literature=run_literature,
    )
    tool_schemas = registry.schemas_for_tools(tool_names)

    graph = state.get_evidence_graph()
    messages = build_react_messages(
        user_message,
        history,
        memory.to_prompt_block(),
        query_mode=mode,
        graph_summary=graph.retrieve_summary() if settings.evidence_graph_enabled else "",
    )
    enriched_results: list[ToolResult] = []

    try:
        for _round_idx in range(max_rounds):
            round_tool_calls: list[dict[str, Any]] = []

            async for event in _stream_llm_events(
                llm, messages, tool_schemas, disable_thinking=True,
            ):
                if event["type"] == "tool_call":
                    round_tool_calls.append(event)
                elif event["type"] == "error":
                    yield event
                    return
                elif event["type"] == "done":
                    break

            if not round_tool_calls:
                break

            assistant_msg: dict[str, Any] = {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {
                            "name": tc["name"],
                            "arguments": json.dumps(tc["arguments"]),
                        },
                    }
                    for tc in round_tool_calls
                ],
            }
            messages.append(assistant_msg)

            for tc in round_tool_calls:
                name = tc["name"]
                if is_literature_tool(name):
                    continue
                args = tc["arguments"]
                yield {"type": "tool_call", "tool_name": name, "arguments": args, "kind": "database"}

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
                }
                messages.append(tool_result_message(tc["id"], enriched))

            state.sync_memory_to_targets()

        # Literature enrichment — only for deep / explicit literature paths
        if run_literature:
            yield phase_event("literature", lang)
            lit_results = await enrich_literature(user_message, memory, enriched_results)
            for enriched in lit_results:
                enriched_results.append(enriched)
                merge_citations(enriched_results)
                _record_tool(memory, state, enriched)
                yield {
                    "type": "tool_call",
                    "tool_name": enriched.tool,
                    "arguments": {},
                    "kind": "literature",
                }
                yield {
                    "type": "tool_result",
                    "payload": enriched.model_dump_for_sse(),
                    "kind": "literature",
                }

        yield phase_event("synthesis", lang)

        if not enriched_results:
            reply = (
                "I could not retrieve evidence for that question with the available tools. "
                "Try specifying a gene and site (e.g. TP53 S15)."
            )
            if lang == "zh":
                reply = "未能检索到相关证据，请尝试指定蛋白与位点（例如 TP53 S15）。"
            for i in range(0, len(reply), 80):
                yield {"type": "text", "content": reply[i : i + 80]}
            async for fu in _emit_followups(user_message, reply, memory, mode, llm):
                yield fu
            yield {"type": "done"}
            return

        intent = f"ReAct investigation ({mode})"
        agent_context = build_agent_context(
            user_message, intent, enriched_results, history,
        )
        if settings.evidence_graph_enabled:
            gs = graph.retrieve_summary()
            if gs:
                agent_context["plan_summary"] = (
                    (agent_context.get("plan_summary") or "") + "\n\n" + gs
                )

        yield {"type": "sources", "citations": agent_context["citations"]}

        synth_messages = build_synthesis_messages(agent_context)
        full_text = ""
        async for event in _stream_llm_events(
            llm, synth_messages, [], max_tokens=8192, disable_thinking=True,
        ):
            if event["type"] == "text":
                full_text += event["content"]
                yield {"type": "text", "content": event["content"]}
            elif event["type"] == "error":
                yield event
                return

        if full_text.strip() and _needs_citation_pass(full_text):
            logger.info("Citation pass skipped — synthesis already streamed")

        async for fu in _emit_followups(user_message, full_text, memory, mode, llm):
            yield fu

    except Exception as exc:
        logger.error("ReAct loop error: %s", exc, exc_info=True)
        yield {"type": "error", "message": str(exc)}

    yield {"type": "done"}
