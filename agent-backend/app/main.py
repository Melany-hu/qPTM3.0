"""FastAPI main application for the qPTM Agent.

Endpoints:
  GET  /health       — health check
  POST /chat         — streaming chat via SSE (Server-Sent Events)
  GET  /session/{id} — get session state
  DELETE /session/{id} — reset session

The agent loop:
  1. Receive user message + history
  2. Build messages with system prompt (stage-aware)
  3. Call DeepSeek with tools (streaming)
  4. Stream text chunks to client via SSE
  5. If tool calls are made: execute tools, send results, call DeepSeek again
  6. Repeat until no more tool calls
  7. Update workflow state, send stage update
"""

import json
import logging
import uuid
from typing import Any, AsyncGenerator

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from app.config import settings
from app.llm.deepseek_client import get_llm_client
from app.llm.prompts import build_system_prompt
from app.models.schemas import ChatRequest, WorkflowStage
from app.tools.registry import registry
from app.tools.qptm_tools import register_qptm_tools
from app.tools.iptmnet_tools import register_iptmnet_tools
from app.tools.uniprot_tools import register_uniprot_tools
from app.tools.psp_tools import register_psp_tools
from app.tools.dbptm_tools import register_dbptm_tools
from app.tools.stability_tools import register_stability_tools
from app.workflow.state import session_manager
from app.workflow.stages import (
    detect_stage_from_message,
    advance_stage,
    get_stage_suggestion,
    get_stage_label,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ── FastAPI app ───────────────────────────────────────────────────

app = FastAPI(
    title="qPTM Agent API",
    description="AI agent for the qPTM database — three-stage PTM research workflow",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Maximum tool-call rounds per user message (prevents infinite loops)
MAX_TOOL_ROUNDS = 5


# ── Startup: register all tools ───────────────────────────────────

_tools_registered = False


def register_all_tools() -> None:
    """Register all tools with the global registry (idempotent)."""
    global _tools_registered
    if _tools_registered:
        return
    register_qptm_tools()
    register_iptmnet_tools()
    register_uniprot_tools()
    register_psp_tools()
    register_dbptm_tools()
    register_stability_tools()
    _tools_registered = True
    logger.info(f"Registered {len(registry.tool_names)} tools: {registry.tool_names}")


@app.on_event("startup")
def _startup_register_tools() -> None:
    """Register all tools on FastAPI startup."""
    register_all_tools()


# ── SSE helpers ───────────────────────────────────────────────────

def _sse_event(event_type: str, data: dict[str, Any]) -> str:
    """Format a Server-Sent Event string."""
    return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _sse_text_chunk(text: str) -> str:
    """SSE event for a streaming text chunk."""
    return _sse_event("text", {"content": text})


def _sse_tool_call(tool_name: str, arguments: dict[str, Any]) -> str:
    """SSE event for a tool call."""
    return _sse_event("tool_call", {"tool_name": tool_name, "arguments": arguments})


def _sse_tool_result(tool_name: str, success: bool, summary: str, data_count: int) -> str:
    """SSE event for a tool result."""
    return _sse_event("tool_result", {
        "tool_name": tool_name,
        "success": success,
        "summary": summary,
        "data_count": data_count,
    })


def _sse_stage_update(stage: str, label: str, description: str) -> str:
    """SSE event for a workflow stage update."""
    return _sse_event("stage_update", {
        "stage": stage,
        "label": label,
        "description": description,
    })


def _sse_done() -> str:
    """SSE event marking the end of the stream."""
    return _sse_event("done", {})


def _sse_error(message: str) -> str:
    """SSE event for an error."""
    return _sse_event("error", {"message": message})


# ── Tool execution ────────────────────────────────────────────────

def _execute_tool_call(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Execute a single tool call and return the result dict."""
    logger.info(f"Executing tool: {name} with args: {arguments}")
    result = registry.execute(name, arguments)
    if "error" in result:
        logger.warning(f"Tool {name} returned error: {result['error']}")
    return result


def _tool_result_to_message(tool_call_id: str, result: dict[str, Any]) -> dict[str, str]:
    """Convert a tool result into a DeepSeek tool message."""
    # The LLM needs the result as a string in the "content" field
    # We pass the summary + key structured data
    content = result.get("summary", json.dumps(result, ensure_ascii=False))
    return {
        "role": "tool",
        "tool_call_id": tool_call_id,
        "content": content,
    }


# ── Workflow state update from tool results ───────────────────────

def _update_state_from_tools(
    state,
    tool_results: list[tuple[str, dict[str, Any]]],
) -> None:
    """Update conversation state based on tool results."""
    for tool_name, result in tool_results:
        if tool_name == "qptm_search":
            # Extract target protein from search results
            events = result.get("events", [])
            if events and not state.has_target:
                first = events[0]
                state.set_target(
                    gene=first.get("gene"),
                    uniprot_ac=first.get("uniprot_ac"),
                )

        elif tool_name == "qptm_site_conditions":
            conditions = result.get("conditions", [])
            if conditions:
                state.add_conditions(conditions, result.get("total_conditions", len(conditions)))
                if not state.has_target:
                    state.set_target(uniprot_ac=result.get("uniprot_ac"))

        elif tool_name == "qptm_kinases":
            kinases = result.get("kinases", [])
            if kinases:
                state.add_kinases(kinases)

        elif tool_name == "iptmnet_enzymes":
            enzymes = result.get("enzymes", [])
            if enzymes:
                state.add_enzymes(enzymes)

        elif tool_name == "iptmnet_ptm_ppi":
            interactions = result.get("interactions", [])
            if interactions:
                state.add_interactions(interactions)

        elif tool_name == "psp_regulatory":
            if result.get("found"):
                state.add_functions([{
                    "source": "PhosphoSitePlus",
                    "on_function": result.get("on_function", []),
                    "on_process": result.get("on_process", []),
                    "on_prot_interact": result.get("on_prot_interact", []),
                    "pmids": result.get("pmids", []),
                }])

        elif tool_name == "uniprot_annotation":
            if result.get("function") or result.get("disease_associations"):
                state.add_functions([{
                    "source": "UniProt",
                    "function": result.get("function"),
                    "ptm_description": result.get("ptm_description"),
                    "domains": result.get("domains", []),
                }])
                if result.get("disease_associations"):
                    state.add_disease([{
                        "source": "UniProt",
                        "diseases": result["disease_associations"],
                    }])

        elif tool_name == "dbptm_functional":
            if result.get("disease_associations"):
                state.add_disease(result["disease_associations"])
            if result.get("drug_binding_sites"):
                state.add_functions([{
                    "source": "dbPTM",
                    "drug_binding": result["drug_binding_sites"],
                }])

        elif tool_name == "ptm_stability":
            if result.get("found"):
                state.add_functions([{
                    "source": "PTM-stability curated (PMC9839724)",
                    "stability_entries": result.get("entries", []),
                    "stabilize_count": result.get("stabilize_count", 0),
                    "destabilize_count": result.get("destabilize_count", 0),
                }])


# ── Agent loop (streaming generator) ──────────────────────────────

async def _agent_loop(
    user_message: str,
    history: list[dict[str, str]],
    session_id: str,
) -> AsyncGenerator[str, None]:
    """Main agent loop — yields SSE events.

    1. Build messages with system prompt
    2. Call DeepSeek (streaming)
    3. Yield text chunks as SSE
    4. If tool calls: execute, yield tool events, call DeepSeek again
    5. Update workflow state, yield stage update
    6. Yield done event
    """
    state = session_manager.get_or_create(session_id)
    state.turn_count += 1

    # Detect stage from user message
    detected_stage = detect_stage_from_message(user_message)
    if detected_stage and state.current_stage == WorkflowStage.idle:
        state.advance_to(detected_stage)
    elif detected_stage:
        # User is asking about a different stage — update focus
        state.current_stage = detected_stage

    # Build system prompt with current stage focus
    system_prompt = build_system_prompt(state.current_stage.value)

    # Build message list for DeepSeek
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
    ]

    # Add conversation history
    for msg in history:
        messages.append({"role": msg["role"], "content": msg["content"]})

    # Add current user message
    messages.append({"role": "user", "content": user_message})

    # Get tool schemas
    tools = registry.schemas

    llm = get_llm_client()

    try:
        for round_num in range(MAX_TOOL_ROUNDS):
            logger.info(f"Session {session_id}: tool round {round_num + 1}")

            # Collect full response from streaming
            full_text = ""
            tool_calls: list[dict[str, Any]] = []

            # Stream the response
            for event in llm.chat_completion_stream(messages, tools=tools):
                if event["type"] == "text":
                    full_text += event["content"]
                    yield _sse_text_chunk(event["content"])

                elif event["type"] == "tool_call":
                    tool_calls.append({
                        "id": event.get("id", ""),
                        "name": event["name"],
                        "arguments": event["arguments"],
                    })

                elif event["type"] == "done":
                    finish_reason = event.get("finish_reason", "stop")

            # If no tool calls, we're done
            if not tool_calls:
                break

            # ── Execute tool calls ──
            # Add assistant message with tool calls to the conversation
            assistant_msg: dict[str, Any] = {"role": "assistant", "content": full_text}
            assistant_msg["tool_calls"] = [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": json.dumps(tc["arguments"], ensure_ascii=False),
                    },
                }
                for tc in tool_calls
            ]
            messages.append(assistant_msg)

            # Execute each tool call
            tool_results: list[tuple[str, dict[str, Any]]] = []
            for tc in tool_calls:
                # Send tool_call SSE event
                yield _sse_tool_call(tc["name"], tc["arguments"])

                # Execute the tool
                result = _execute_tool_call(tc["name"], tc["arguments"])
                tool_results.append((tc["name"], result))

                # Send tool_result SSE event
                success = "error" not in result
                summary = result.get("summary", result.get("error", ""))
                data_count = 0
                for key in ("events", "conditions", "kinases", "enzymes",
                            "interactions", "sites", "disease_associations",
                            "drug_binding_sites"):
                    val = result.get(key)
                    if isinstance(val, list):
                        data_count += len(val)
                yield _sse_tool_result(tc["name"], success, summary, data_count)

                # Add tool result to messages for the next DeepSeek call
                messages.append(_tool_result_to_message(tc["id"], result))

            # Update workflow state from tool results
            _update_state_from_tools(state, tool_results)

            # Try to advance the stage
            new_stage = advance_stage(state)
            if new_stage:
                yield _sse_stage_update(
                    new_stage.value,
                    get_stage_label(new_stage),
                    f"Advanced to {get_stage_label(new_stage)}",
                )

        # ── Post-response: generate stage suggestion ──
        suggestion = get_stage_suggestion(state)
        if suggestion["suggestion"]:
            yield _sse_stage_update(
                suggestion["stage"].value,
                get_stage_label(suggestion["stage"]),
                suggestion["suggestion"],
            )

    except Exception as e:
        logger.error(f"Agent loop error: {e}", exc_info=True)
        yield _sse_error(f"An error occurred: {e}")

    yield _sse_done()


# ── Endpoints ─────────────────────────────────────────────────────

@app.get("/health")
async def health() -> dict[str, Any]:
    """Health check endpoint."""
    return {
        "status": "ok",
        "tools_registered": len(registry.tool_names),
        "tool_names": registry.tool_names,
    }


@app.post("/chat")
async def chat(request: Request) -> StreamingResponse:
    """Streaming chat endpoint. Returns SSE stream.

    Request body (JSON):
      {
        "message": "user's question",
        "session_id": "optional session ID (auto-generated if absent)",
        "history": [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]
      }

    SSE events:
      - text: {"content": "chunk of text"}
      - tool_call: {"tool_name": "...", "arguments": {...}}
      - tool_result: {"tool_name": "...", "success": true, "summary": "...", "data_count": N}
      - stage_update: {"stage": "...", "label": "...", "description": "..."}
      - done: {}
      - error: {"message": "..."}
    """
    body = await request.json()
    chat_req = ChatRequest(**body)

    # Generate session ID if not provided
    session_id = chat_req.session_id or str(uuid.uuid4())

    # Convert history to dict format
    history = [{"role": m.role, "content": m.content} for m in chat_req.history]

    return StreamingResponse(
        _agent_loop(chat_req.message, history, session_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable Nginx buffering
            "X-Session-Id": session_id,
        },
    )


@app.get("/session/{session_id}")
async def get_session(session_id: str) -> JSONResponse:
    """Get the current workflow state for a session."""
    state = session_manager.get(session_id)
    if not state:
        return JSONResponse({"error": "Session not found"}, status_code=404)
    return JSONResponse(state.to_dict())


@app.delete("/session/{session_id}")
async def reset_session(session_id: str) -> JSONResponse:
    """Reset a session's workflow state (start a new investigation)."""
    state = session_manager.reset_session(session_id)
    return JSONResponse({"status": "reset", "state": state.to_dict()})


@app.get("/tools")
async def list_tools() -> dict[str, Any]:
    """List all registered tools and their schemas."""
    return {
        "tools": [
            {
                "name": s["function"]["name"],
                "description": s["function"]["description"],
                "parameters": s["function"]["parameters"],
            }
            for s in registry.schemas
        ]
    }


# ── Main entry point ──────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
    )
