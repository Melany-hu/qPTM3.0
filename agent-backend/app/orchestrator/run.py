"""Orchestrator main loop — multi-agent research pipeline."""

from __future__ import annotations

import asyncio
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
from app.agent.memory import prepare_investigation_context
from app.agent.phases import phase_event
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
from app.config import settings
from app.llm.deepseek_client import get_llm_client
from app.llm.prompts import build_concept_messages
from app.orchestrator.agents.database_agent import run_database_agent
from app.orchestrator.agents.literature_agent import run_literature_agent
from app.orchestrator.agents.writer_agent import run_writer_agent
from app.orchestrator.clue_buffer import ClueBuffer
from app.orchestrator.planner import build_orchestrator_plan
from app.orchestrator.schemas import DatabaseBrief, LiteratureBrief, OrchestratorPlan
from app.orchestrator.llm_stream import stream_llm_events
from app.workflow.state import session_manager

logger = logging.getLogger(__name__)


def _detect_lang(question: str) -> str:
    zh = sum(1 for ch in question if "\u4e00" <= ch <= "\u9fff")
    latin = sum(1 for ch in question if "a" <= ch.lower() <= "z")
    return "zh" if zh >= 2 and zh >= latin * 0.35 else "en"


async def _emit_followups(user_message, answer, memory, mode, llm):
    try:
        questions = await asyncio.wait_for(
            generate_follow_up_questions(
                user_message, answer, memory, mode, llm,
            ),
            timeout=8.0,
        )
        if questions:
            yield {"type": "follow_up_questions", "questions": questions}
    except asyncio.TimeoutError:
        logger.warning("Follow-up generation timed out after 8s — skipped")
    except Exception as exc:
        logger.warning("Follow-up generation skipped: %s", exc)


async def _resolve_uniprot(memory, mode: str) -> None:
    if mode not in QUERY_MODES_SITE_RESOLVE or not memory.gene or memory.uniprot_ac:
        return
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
        logger.debug("UniProt resolve skipped: %s", exc)


async def run_orchestrator(
    user_message: str,
    history: list[dict[str, str]],
    session_id: str,
    *,
    clarification_response: dict[str, Any] | None = None,
) -> AsyncGenerator[dict[str, Any], None]:
    state = session_manager.get_or_create(session_id)
    state.turn_count += 1
    memory = state.get_memory()
    prepare_investigation_context(memory, state, history)
    lang = _detect_lang(user_message)

    forced_research = False
    entities: dict = {}
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
            async for event in stream_llm_events(
                llm, concept_messages, [], max_tokens=4096, disable_thinking=True,
            ):
                if event["type"] == "text":
                    full_text += event["content"]
                    yield {"type": "text", "content": event["content"]}
                elif event["type"] == "error":
                    yield event
                    return
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
        for i in range(0, len(reply), 80):
            yield {"type": "text", "content": reply[i : i + 80]}
        async for fu in _emit_followups(user_message, reply, memory, mode, None):
            yield fu
        yield {"type": "done"}
        return

    if (
        not forced_research
        and settings.clarification_enabled
        and should_assess_clarification(mode)
    ):
        yield phase_event("clarifying", lang)
        llm = get_llm_client()
        clar_req = await assess_clarification_need(
            llm, user_message, entities, memory, history, lang=lang,
        )
        if clar_req:
            state.pending_clarification = {"message": user_message, "entities": dict(memory.entities)}
            yield {"type": "plan_created", "plan": {
                "question": user_message,
                "intent_summary": "Planning deeper research…",
                "steps": [],
            }}
            yield {"type": "clarification_request", **clar_req}
            yield {"type": "done"}
            return

    if mode in QUERY_MODES_SITE_RESOLVE and memory.gene and not memory.uniprot_ac:
        yield phase_event("resolving", lang)
    await _resolve_uniprot(memory, mode)
    llm = get_llm_client()

    agent_question = user_message
    if mode == QUERY_MODE_FOLLOWUP and is_literature_request(user_message) and memory.has_target:
        site = f"S{memory.position}" if memory.position else ""
        gene = memory.gene or "the protein"
        ptm = memory.ptm_type or "modification"
        agent_question = (
            f"Recommend relevant peer-reviewed literature for {gene} {site} {ptm}. "
            f"Prioritize papers directly studying this site and mechanistic studies. "
            f"User request: {user_message}"
        )

    yield phase_event("planning", lang)
    plan = await build_orchestrator_plan(llm, agent_question, memory, mode, lang=lang)

    yield {"type": "orchestrator_plan", **plan.to_dict()}
    yield {"type": "plan_created", "plan": {
        "question": user_message,
        "intent_summary": plan.reasoning or plan.user_goal,
        "steps": [],
        "depth": plan.depth_hint,
    }}

    clue_buffer = ClueBuffer()
    db_brief: DatabaseBrief | None = None
    lit_brief: LiteratureBrief | None = None
    full_text = ""

    run_db = any(t.enabled and t.agent == "database" for t in plan.tasks)
    run_lit = plan.run_literature and any(
        t.enabled and t.agent == "literature" for t in plan.tasks
    )

    try:
        if run_db:
            yield phase_event("database", lang)
            db_focus = next((t.focus for t in plan.tasks if t.agent == "database"), "")
            async for event in run_database_agent(
                agent_question, history, memory, state, plan, llm, clue_buffer,
                mode=mode, lang=lang, focus=db_focus,
            ):
                if event.get("type") == "_database_brief":
                    db_brief = event["brief"]
                    continue
                yield event

        if run_lit:
            yield phase_event("literature", lang)
            lit_focus = next((t.focus for t in plan.tasks if t.agent == "literature"), "")
            async for event in run_literature_agent(
                agent_question, memory, llm, clue_buffer, db_brief, plan,
                lang=lang, focus=lit_focus,
            ):
                if event.get("type") == "_literature_brief":
                    lit_brief = event["brief"]
                    continue
                yield event

        graph_summary = ""
        if settings.evidence_graph_enabled:
            graph_summary = state.get_evidence_graph().retrieve_summary()

        yield phase_event("synthesis", lang)
        async for event in run_writer_agent(
            agent_question, history, plan, db_brief, lit_brief, llm,
            mode=mode, lang=lang, graph_summary=graph_summary,
        ):
            if event.get("type") == "_writer_text":
                full_text = event.get("text") or full_text
                continue
            if event["type"] == "text":
                full_text += event["content"]
            yield event

        async for fu in _emit_followups(user_message, full_text, memory, mode, llm):
            yield fu

    except Exception as exc:
        logger.error("Orchestrator error: %s", exc, exc_info=True)
        yield {"type": "error", "message": str(exc)}

    yield {"type": "done"}
