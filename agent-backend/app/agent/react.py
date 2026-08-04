"""ReAct agent loop — LLM decides tools, iterates until answer is ready."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncGenerator

from app.agent.gate import (
    QUERY_MODES_SITE_RESOLVE,
    QUERY_MODES_WITH_TOOLS,
    build_gate_reply,
    classify_query_mode,
)
from app.agent.memory import InvestigationMemory, tool_result_message
from app.agent.retriever import retrieve_tools
from app.config import settings
from app.llm.deepseek_client import get_llm_client
from app.llm.prompts import build_react_messages, build_synthesis_messages
from app.models.schemas import ToolResult
from app.tools.metadata import tool_database
from app.tools.registry import registry
from app.workflow.citations import attach_citations
from app.workflow.context import build_agent_context, merge_citations
from app.workflow.state import session_manager

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 5


async def _stream_llm_events(
    llm,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    *,
    max_tokens: int = 8192,
    disable_thinking: bool = False,
) -> AsyncGenerator[dict[str, Any], None]:
    """Run sync LLM streaming in a worker thread."""
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


async def run_react(
    user_message: str,
    history: list[dict[str, str]],
    session_id: str,
) -> AsyncGenerator[dict[str, Any], None]:
    """ReAct agent loop yielding structured events for SSE conversion."""
    state = session_manager.get_or_create(session_id)
    state.turn_count += 1
    memory = state.get_memory()

    entities = memory.update_from_message(user_message)
    mode = classify_query_mode(user_message, entities, state)
    memory.query_mode = mode
    entities["query_mode"] = mode

    # Gate: no tools for conversational modes
    if mode not in QUERY_MODES_WITH_TOOLS:
        reply = build_gate_reply(mode, user_message)
        yield {"type": "plan_created", "plan": {
            "question": user_message,
            "intent_summary": f"Gate: {mode}",
            "steps": [],
        }}
        chunk_size = 80
        for i in range(0, len(reply), chunk_size):
            yield {"type": "text", "content": reply[i : i + chunk_size]}
        yield {"type": "done"}
        return

    # Early gene → UniProt resolve
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

    yield {"type": "plan_created", "plan": {
        "question": user_message,
        "intent_summary": f"ReAct investigation ({mode})",
        "steps": [],
    }}

    tool_names = await retrieve_tools(
        user_message, memory, catalog, llm,
        use_llm=settings.use_llm_tool_retriever,
    )
    tool_schemas = registry.schemas_for_tools(tool_names)

    yield {"type": "plan_created", "plan": {
        "question": user_message,
        "intent_summary": f"ReAct — tools: {', '.join(tool_names[:8])}",
        "steps": [{"tool": n, "step": i + 1} for i, n in enumerate(tool_names)],
    }}

    messages = build_react_messages(
        user_message, history, memory.to_prompt_block(), query_mode=mode,
    )
    enriched_results: list[ToolResult] = []
    answer_started = False

    try:
        for _round_idx in range(MAX_TOOL_ROUNDS):
            round_tool_calls: list[dict[str, Any]] = []
            round_text = ""

            async for event in _stream_llm_events(
                llm, messages, tool_schemas, disable_thinking=True,
            ):
                if event["type"] == "text":
                    round_text += event["content"]
                elif event["type"] == "tool_call":
                    round_tool_calls.append(event)
                elif event["type"] == "error":
                    yield event
                    return
                elif event["type"] == "done":
                    break

            if round_tool_calls:
                assistant_msg: dict[str, Any] = {
                    "role": "assistant",
                    "content": round_text or None,
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
                    args = tc["arguments"]
                    yield {"type": "tool_call", "tool_name": name, "arguments": args}

                    result = await asyncio.to_thread(registry.execute, name, args)
                    db = tool_database(name)
                    enriched = attach_citations(name, db, result)
                    enriched_results.append(enriched)
                    merge_citations(enriched_results)
                    memory.update_from_tool(enriched)

                    yield {
                        "type": "tool_result",
                        "payload": enriched.model_dump_for_sse(),
                    }
                    messages.append(tool_result_message(tc["id"], enriched))

                state.sync_memory_to_targets()
                continue

            # No tool calls — stream final answer
            if round_text.strip():
                answer_started = True
                if enriched_results:
                    agent_context = build_agent_context(
                        user_message,
                        f"ReAct investigation ({mode})",
                        enriched_results,
                        history,
                    )
                    yield {"type": "sources", "citations": agent_context["citations"]}
                chunk_size = 80
                for i in range(0, len(round_text), chunk_size):
                    yield {"type": "text", "content": round_text[i : i + chunk_size]}
                break

        # Forced synthesis if max rounds exhausted with only tool calls
        if not answer_started and enriched_results:
            agent_context = build_agent_context(
                user_message,
                f"ReAct investigation ({mode})",
                enriched_results,
                history,
            )
            yield {"type": "sources", "citations": agent_context["citations"]}
            synth_messages = build_synthesis_messages(agent_context)
            async for event in _stream_llm_events(
                llm, synth_messages, [], disable_thinking=True,
            ):
                if event["type"] == "text":
                    yield {"type": "text", "content": event["content"]}
                elif event["type"] == "error":
                    yield event
                    return

        elif enriched_results and answer_started:
            # Emit sources for citation table when we have evidence
            agent_context = build_agent_context(
                user_message,
                f"ReAct investigation ({mode})",
                enriched_results,
                history,
            )
            if agent_context.get("citations"):
                yield {"type": "sources", "citations": agent_context["citations"]}

    except Exception as exc:
        logger.error("ReAct loop error: %s", exc, exc_info=True)
        yield {"type": "error", "message": str(exc)}

    yield {"type": "done"}
