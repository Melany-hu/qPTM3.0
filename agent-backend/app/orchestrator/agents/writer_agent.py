"""Writer sub-agent — final synthesis from briefs."""

from __future__ import annotations

import logging
from typing import Any, AsyncGenerator

from app.orchestrator.llm_stream import stream_llm_events
from app.orchestrator.schemas import DatabaseBrief, LiteratureBrief, OrchestratorPlan
from app.workflow.context import build_writer_agent_context, _writer_max_tokens
from app.llm.prompts import build_synthesis_messages

logger = logging.getLogger(__name__)


async def run_writer_agent(
    question: str,
    history: list[dict[str, str]],
    plan: OrchestratorPlan,
    db_brief: DatabaseBrief | None,
    lit_brief: LiteratureBrief | None,
    llm: Any,
    *,
    mode: str,
    lang: str,
    graph_summary: str = "",
) -> AsyncGenerator[dict[str, Any], None]:
    yield {
        "type": "agent_started",
        "agent": "writer",
        "label": "撰写回答…" if lang == "zh" else "Writing answer…",
        "focus": plan.user_goal,
    }

    all_results = []
    if db_brief:
        all_results.extend(db_brief.tool_results)
    if lit_brief:
        all_results.extend(lit_brief.tool_results)

    if not all_results:
        msg = "未能检索到相关证据。" if lang == "zh" else "No evidence retrieved."
        yield {"type": "text", "content": msg}
        yield {"type": "agent_completed", "agent": "writer", "summary": msg}
        return

    agent_context = build_writer_agent_context(
        question,
        plan,
        db_brief,
        lit_brief,
        all_results,
        history,
        graph_summary=graph_summary,
    )

    yield {"type": "sources", "citations": agent_context["citations"]}

    synth_messages = build_synthesis_messages(agent_context)
    max_tokens = _writer_max_tokens(plan.depth_hint)
    full_text = ""
    async for event in stream_llm_events(
        llm, synth_messages, [], max_tokens=max_tokens, disable_thinking=True,
    ):
        if event["type"] == "text":
            full_text += event["content"]
            yield {"type": "text", "content": event["content"]}
        elif event["type"] == "error":
            yield event
            return

    yield {
        "type": "agent_completed",
        "agent": "writer",
        "summary": "回答完成" if lang == "zh" else "Answer complete",
    }
    yield {"type": "_writer_text", "text": full_text}
