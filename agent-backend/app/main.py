"""FastAPI main application for the qPTM Agent.

Architecture: Agent = LLM (brain) + Context (eyes) + Tools (hands)

  Phase 1 — Planning:  deterministic routing to databases/tools
  Phase 2 — Execution: tools return structured evidence + citations
  Phase 3 — Synthesis: LLM reads full context and writes source-attributed answer

Endpoints:
  GET  /health       — health check
  POST /chat         — streaming chat via SSE
  GET  /session/{id} — get session state
  DELETE /session/{id} — reset session
"""

import asyncio
import json
import logging
import re
import uuid
from typing import Any, AsyncGenerator, Optional

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse

from app.config import settings
from app.llm.deepseek_client import get_llm_client
from app.llm.prompts import build_synthesis_messages
from app.models.schemas import ChatRequest, PdfExportRequest, WorkflowStage, PlanStepStatus, ToolResult
from app.export.pdf import build_answer_pdf
from app.collection.routes import router as collection_router
from app.agent.entities import parse_query_entities
from app.agent.gate import classify_query_mode as classify_intent_mode, QUERY_MODE_COLLECTION
from app.tools.registry import registry
from app.tools.qptm_tools import register_qptm_tools
from app.tools.iptmnet_tools import register_iptmnet_tools
from app.tools.uniprot_tools import register_uniprot_tools
from app.tools.psp_tools import register_psp_tools
from app.tools.dbptm_tools import register_dbptm_tools
from app.tools.stability_tools import register_stability_tools
from app.tools.activedriver_tools import register_activedriver_tools
from app.tools.pmads_tools import register_pmads_tools
from app.tools.drugbank_tools import register_drugbank_tools
from app.tools.weram_tools import register_weram_tools
from app.tools.ubibrowser_tools import register_ubibrowser_tools
from app.tools.gpsuber_tools import register_gpsuber_tools
from app.tools.gps6_tools import register_gps6_tools
from app.tools.gpssumo2_tools import register_gpssumo2_tools
from app.tools.kaka_tools import register_kaka_tools
from app.tools.ekpi_tools import register_ekpi_tools
from app.tools.ptmphase_tools import register_ptmphase_tools
from app.tools.dscope_tools import register_dscope_tools
from app.tools.ptmd_tools import register_ptmd_tools
from app.tools.cancerproteome_tools import register_cancerproteome_tools
from app.tools.ptmint_tools import register_ptmint_tools
from app.tools.ppi_api_tools import register_ppi_api_tools
from app.tools.pathway_tools import register_pathway_tools
from app.tools.ptmcode_tools import register_ptmcode_tools
from app.tools.inuloc_tools import register_inuloc_tools
from app.tools.funcscore_tools import register_funcscore_tools
from app.tools.decryptm_tools import register_decryptm_tools
from app.tools.compartments_tools import register_compartments_tools
from app.tools.subcell_tools import register_subcell_tools
from app.tools.domain_tools import register_domain_tools
from app.tools.pubtator_tools import register_pubtator_tools
from app.workflow.state import session_manager
from app.workflow.planner import (
    build_research_plan,
    infer_tool_arguments,
    parse_query_entities,
    classify_query_mode,
    build_gate_reply,
    QUERY_MODE_RESEARCH,
)
from app.workflow.stages import (
    advance_stage,
    get_stage_suggestion,
    get_stage_label,
)
from app.workflow.citations import attach_citations
from app.workflow.context import build_agent_context
from app.storage import conversations as conv_store

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ── FastAPI app ───────────────────────────────────────────────────

app = FastAPI(
    title="qPTM Agent API",
    description="AI agent for the qPTM database — WHO→WHEN→WHERE→WHY PTM research workflow",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(collection_router)

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
    register_activedriver_tools()
    register_pmads_tools()
    register_drugbank_tools()
    register_weram_tools()
    register_ubibrowser_tools()
    register_gpsuber_tools()
    register_gps6_tools()
    register_gpssumo2_tools()
    register_kaka_tools()
    register_ekpi_tools()
    register_ptmphase_tools()
    register_dscope_tools()
    register_ptmd_tools()
    register_cancerproteome_tools()
    register_ptmint_tools()
    register_ppi_api_tools()
    register_pathway_tools()
    register_ptmcode_tools()
    register_inuloc_tools()
    register_funcscore_tools()
    register_decryptm_tools()
    register_compartments_tools()
    register_subcell_tools()
    register_domain_tools()
    register_pubtator_tools()
    _tools_registered = True
    logger.info(f"Registered {len(registry.tool_names)} tools: {registry.tool_names}")


@app.on_event("startup")
def _startup_register_tools() -> None:
    """Register all tools on FastAPI startup."""
    register_all_tools()
    conv_store.init_db()


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


def _sse_tool_result(
    tool_name: str,
    success: bool,
    summary: str,
    data_count: int,
    database: str = "",
    citations: Optional[list] = None,
) -> str:
    """SSE event for a tool result."""
    return _sse_event("tool_result", {
        "tool_name": tool_name,
        "database": database,
        "success": success,
        "summary": summary,
        "data_count": data_count,
        "citations": citations or [],
    })


def _sse_sources(citations: list[dict[str, Any]]) -> str:
    """SSE event: source registry for the answer."""
    return _sse_event("sources", {"citations": citations})


def _sse_stage_update(stage: str, label: str, description: str) -> str:
    """SSE event for a workflow stage update."""
    return _sse_event("stage_update", {
        "stage": stage,
        "label": label,
        "description": description,
    })


def _sse_plan_created(plan) -> str:
    """SSE event: research plan generated by the planning layer."""
    return _sse_event("plan_created", {
        "question": plan.question,
        "intent_summary": plan.intent_summary,
        "steps": [s.model_dump() for s in plan.steps],
    })


def _sse_step_started(step) -> str:
    return _sse_event("step_started", step.model_dump())


def _sse_step_completed(step) -> str:
    return _sse_event("step_completed", step.model_dump())


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

        elif tool_name == "cancerproteome_disease":
            # WHEN: tumor/control PTM & protein quantification; WHY: cancer context
            ptm_hits = result.get("ptm_hits") or []
            protein_hits = result.get("protein_hits") or []
            quant_rows: list[dict[str, Any]] = []
            for hit in ptm_hits:
                quant_rows.append({
                    "source": "CancerProteome",
                    "kind": "ptm_tumor_vs_control",
                    **(hit if isinstance(hit, dict) else {"value": hit}),
                })
            for hit in protein_hits:
                quant_rows.append({
                    "source": "CancerProteome",
                    "kind": "protein_tumor_vs_control",
                    **(hit if isinstance(hit, dict) else {"value": hit}),
                })
            if quant_rows:
                merged = list(state.conditions_found) + quant_rows
                state.add_conditions(merged, len(merged))
            if ptm_hits or protein_hits or (result.get("summary") and not result.get("error")):
                state.add_disease([{
                    "source": "CancerProteome",
                    "ptm_hits": ptm_hits[:20] if isinstance(ptm_hits, list) else ptm_hits,
                    "protein_hits": protein_hits[:20] if isinstance(protein_hits, list) else protein_hits,
                    "cancer_filter": result.get("cancer_filter"),
                    "summary": result.get("summary"),
                }])

        elif tool_name == "qptm_kinases":
            kinases = result.get("kinases", [])
            if kinases:
                state.add_kinases(kinases)

        elif tool_name == "iptmnet_enzymes":
            enzymes = result.get("enzymes", [])
            if enzymes:
                state.add_enzymes(enzymes)

        elif tool_name in ("pmads_drug_ptm", "decryptm_drug_ptm", "drugbank_targets"):
            associations = (
                result.get("associations")
                or result.get("records")
                or result.get("drugs")
                or result.get("results")
                or []
            )
            if associations:
                state.add_drugs(associations if isinstance(associations, list) else [associations])
            elif result.get("summary") and not result.get("error"):
                state.add_drugs([{"source": tool_name, "summary": result.get("summary")}])

        elif tool_name in (
            "iptmnet_ptm_ppi",
            "ptmint_ppi",
            "string_ppi",
            "biogrid_interactions",
            "intact_interactions",
        ):
            interactions = (
                result.get("interactions")
                or result.get("as_substrate")
                or result.get("as_partner")
                or []
            )
            if interactions:
                state.add_interactions(interactions if isinstance(interactions, list) else [interactions])
            elif result.get("summary") and not result.get("error"):
                state.add_interactions([{"source": tool_name, "summary": result.get("summary")}])

        elif tool_name in (
            "reactome_pathways",
            "kegg_pathways",
            "pathbank_pathways",
        ):
            pathways = result.get("pathways") or []
            if pathways:
                state.add_functions([{
                    "source": result.get("source") or tool_name,
                    "pathways": pathways if isinstance(pathways, list) else [pathways],
                    "total": result.get("total"),
                }])
            elif result.get("summary") and not result.get("error"):
                state.add_functions([{"source": tool_name, "summary": result.get("summary")}])

        elif tool_name == "subcell_scsi":
            interactions = result.get("interactions") or []
            locations = result.get("locations") or []
            if interactions:
                state.add_interactions(interactions)
            if locations:
                state.add_localization(locations)
            elif result.get("summary") and not result.get("error") and not interactions:
                state.add_localization([{"source": "SubCELL", "summary": result.get("summary")}])

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
            if result.get("function") or result.get("disease_associations") or result.get("domains"):
                state.add_localization([{
                    "source": "UniProt",
                    "function": result.get("function"),
                    "ptm_description": result.get("ptm_description"),
                    "domains": result.get("domains", []),
                }])
                state.add_functions([{
                    "source": "UniProt",
                    "function": result.get("function"),
                    "ptm_description": result.get("ptm_description"),
                    "domains": result.get("domains", []),
                }])
                if result.get("disease_associations") or result.get("disease_entries"):
                    state.add_disease([{
                        "source": "UniProt",
                        "diseases": result.get("disease_associations", []),
                        "disease_entries": result.get("disease_entries", []),
                    }])

        elif tool_name in ("interpro_domains", "pfam_domains"):
            domains = result.get("domains") or []
            if domains:
                state.add_functions([{
                    "source": result.get("source") or tool_name,
                    "domains": domains,
                    "total": result.get("total"),
                }])
            elif result.get("summary") and not result.get("error"):
                state.add_functions([{
                    "source": result.get("source") or tool_name,
                    "summary": result.get("summary"),
                }])

        elif tool_name == "compartments_localization":
            locs = result.get("localizations") or result.get("records") or result.get("results") or []
            if locs:
                state.add_localization(locs if isinstance(locs, list) else [locs])
            elif result.get("summary") and not result.get("error"):
                state.add_localization([{"source": "COMPARTMENTS", "summary": result.get("summary")}])

        elif tool_name in ("inuloc_nls_nes", "inuloc_nuclear_prob"):
            if result.get("summary") and not result.get("error"):
                state.add_localization([{"source": tool_name, "summary": result.get("summary")}])
            elif any(result.get(k) for k in ("motifs", "dnl", "records", "results", "probabilities")):
                state.add_localization([{"source": tool_name, "data": result}])

        elif tool_name == "dbptm_functional":
            if result.get("disease_associations"):
                state.add_disease(result["disease_associations"])

        elif tool_name == "ptm_stability":
            if result.get("found"):
                state.add_functions([{
                    "source": "PTM-stability curated",
                    "curated_from": result.get("curated_from", "PMC9839724"),
                    "primary_pmids": result.get("primary_pmids", [])[:10],
                    "stability_entries": result.get("entries", []),
                    "stabilize_count": result.get("stabilize_count", 0),
                    "destabilize_count": result.get("destabilize_count", 0),
                }])

        elif tool_name == "activedriver_mutations":
            by_ds = result.get("mutations_by_dataset") or {}
            rows: list[dict[str, Any]] = []
            for ds, items in by_ds.items():
                if isinstance(items, list):
                    for item in items[:25]:
                        row = dict(item) if isinstance(item, dict) else {"value": item}
                        row["dataset"] = ds
                        rows.append(row)
            if rows:
                state.add_disease([{
                    "source": "ActiveDriverDB",
                    "site_position": result.get("site_position"),
                    "mutations": rows,
                    "total": result.get("total"),
                    "summary": result.get("summary"),
                }])

        elif tool_name == "psp_ptmvar":
            hits = result.get("hits") or result.get("variants") or []
            if hits:
                state.add_disease([{
                    "source": "PhosphoSitePlus PTMVar",
                    "variants": hits if isinstance(hits, list) else [hits],
                    "summary": result.get("summary"),
                }])

        elif tool_name == "kaka_kinase_mutations":
            alts = result.get("alterations") or []
            if alts:
                state.add_disease([{
                    "source": "KAKA",
                    "alterations": alts if isinstance(alts, list) else [alts],
                    "activity_counts": result.get("activity_counts"),
                    "total": result.get("total"),
                    "summary": result.get("summary"),
                }])

        elif tool_name == "ekpi_kinases":
            kinases = result.get("kinases") or []
            if kinases:
                state.add_kinases([{
                    "source": "eKPI",
                    "site": result.get("site"),
                    "position": result.get("position"),
                    "experimental_kinases": result.get("experimental_kinases") or [],
                    "predicted_only_kinases": result.get("predicted_only_kinases") or [],
                    "kinases": kinases[:25],
                    "summary": result.get("summary"),
                }])

        elif tool_name == "ekpi_quantitative":
            corrs = result.get("correlations") or []
            if corrs:
                state.add_kinases([{
                    "source": "eKPI Quantitative",
                    "site": result.get("site"),
                    "position": result.get("position"),
                    "kinases": result.get("kinases_found") or [],
                    "correlations": corrs[:25],
                    "summary": result.get("summary"),
                }])
                state.add_conditions([{
                    "source": "eKPI Quantitative",
                    "site": result.get("site"),
                    "cohort": result.get("cohort"),
                    "correlations": corrs[:15],
                    "summary": result.get("summary"),
                }])

        elif tool_name == "activedriver_kinase_network":
            edges = (result.get("as_substrate") or []) + (result.get("as_kinase") or [])
            if edges:
                state.add_kinases(edges if isinstance(edges, list) else [edges])

        elif tool_name == "psp_kinase_substrate":
            kinases = (
                result.get("kinases")
                or result.get("hits")
                or result.get("records")
                or []
            )
            if kinases:
                state.add_kinases(kinases if isinstance(kinases, list) else [kinases])


# ── Agent loop (streaming generator) ──────────────────────────────

async def _stream_llm_events(
    llm,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    *,
    max_tokens: int = 8192,
    disable_thinking: bool = False,
) -> AsyncGenerator[dict[str, Any], None]:
    """Run sync LLM streaming in a worker thread so the event loop stays responsive."""
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
            logger.error(f"LLM stream error: {exc}", exc_info=True)
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


async def _agent_loop(
    user_message: str,
    history: list[dict[str, str]],
    session_id: str,
) -> AsyncGenerator[str, None]:
    """Planning-first agent loop.

    Phase 0 — Gate:      greeting / help / clarify / off-topic → direct reply (no tools)
    Phase 1 — Planning:  route question → databases/tools → step1/2/3 plan
    Phase 2 — Execution: run each planned tool deterministically
    Phase 3 — Synthesis: LLM writes the final answer from collected results
    """
    state = session_manager.get_or_create(session_id)
    state.turn_count += 1

    entities = parse_query_entities(user_message)
    mode = classify_query_mode(user_message, entities, state)
    entities["query_mode"] = mode

    # ── Phase 0: Conversational gate (no database tools) ──────────
    if mode != QUERY_MODE_RESEARCH:
        plan = build_research_plan(user_message, state)  # empty steps
        state.plan_entities = entities
        state.current_plan = plan.model_dump()
        yield _sse_plan_created(plan)
        yield _sse_stage_update(
            WorkflowStage.idle.value,
            get_stage_label(WorkflowStage.idle),
            plan.intent_summary,
        )
        reply = build_gate_reply(mode, user_message)
        # Stream in small chunks so the UI still feels responsive
        chunk_size = 80
        for i in range(0, len(reply), chunk_size):
            yield _sse_text_chunk(reply[i : i + chunk_size])
        yield _sse_done()
        return

    # Early gene → UniProt so site-specific tools are not skipped before qptm_search
    if entities.get("gene") and not entities.get("uniprot_ac"):
        try:
            from app.sources.uniprot_id import lookup_by_gene

            organism = (entities.get("organism") or "human").lower()
            tax = {"human": 9606, "mouse": 10090, "rat": 10116}.get(organism, 9606)
            ident = lookup_by_gene(str(entities["gene"]), organism_id=tax)
            if ident and ident.get("uniprot_ac"):
                entities["uniprot_ac"] = ident["uniprot_ac"]
                state.set_target(
                    uniprot_ac=ident["uniprot_ac"],
                    gene=ident.get("gene") or entities.get("gene"),
                )
        except Exception as exc:
            logger.debug("Early UniProt resolve skipped: %s", exc)

    # ── Phase 1: Planning ───────────────────────────────────────
    plan = build_research_plan(user_message, state)
    if "mutation → PTM" in (plan.intent_summary or ""):
        entities["narrative"] = "mutation_precision"
    # Keep planner-annotated gaps / skips visible to synthesis via plan text
    state.plan_entities = entities
    state.current_plan = plan.model_dump()

    yield _sse_plan_created(plan)

    if plan.steps:
        state.advance_to(plan.steps[0].stage)
        yield _sse_stage_update(
            plan.steps[0].stage.value,
            get_stage_label(plan.steps[0].stage),
            plan.intent_summary,
        )

    enriched_results: list[ToolResult] = []
    llm = get_llm_client()

    try:
        # ── Phase 2: Execute plan steps ───────────────────────────
        for idx, step in enumerate(plan.steps):
            state.current_step_index = idx
            step.status = PlanStepStatus.running
            yield _sse_step_started(step)

            args = infer_tool_arguments(step.tool, entities, state)
            if not args:
                step.status = PlanStepStatus.skipped
                yield _sse_step_completed(step)
                continue

            yield _sse_tool_call(step.tool, args)
            result = await asyncio.to_thread(_execute_tool_call, step.tool, args)

            enriched = attach_citations(step.tool, step.database, result)
            enriched_results.append(enriched)
            yield _sse_event("tool_result", enriched.model_dump_for_sse())

            _update_state_from_tools(state, [(step.tool, result)])

            # Propagate resolved identifiers to later steps — prefer the
            # user-requested site so we never drift to another residue (e.g. S315).
            if step.tool == "qptm_search":
                events = result.get("events", []) or []
                requested_pos = entities.get("position")
                chosen = None
                if requested_pos is not None:
                    for ev in events:
                        try:
                            if int(ev.get("position") or -1) == int(requested_pos):
                                chosen = ev
                                break
                        except (TypeError, ValueError):
                            continue
                if chosen is None and events:
                    chosen = events[0]
                if chosen:
                    if chosen.get("uniprot_ac"):
                        entities["uniprot_ac"] = chosen["uniprot_ac"]
                        state.set_target(uniprot_ac=chosen["uniprot_ac"])
                    if chosen.get("gene"):
                        entities["gene"] = chosen["gene"]
                        state.set_target(gene=chosen["gene"])
                    # Only adopt position from search when the user did not specify one
                    if chosen.get("position") and not entities.get("position"):
                        entities["position"] = chosen["position"]
                        state.set_target(position=chosen["position"])
                    if chosen.get("ptm_type") and not entities.get("ptm_type"):
                        entities["ptm_type"] = chosen["ptm_type"]
                        state.set_target(ptm_type=chosen["ptm_type"])
                    elif chosen.get("ptm_type") and entities.get("position"):
                        # Keep user's PTM type; do not overwrite with a drifted site type
                        pass

            step.status = (
                PlanStepStatus.completed if enriched.success else PlanStepStatus.failed
            )
            yield _sse_step_completed(step)

            new_stage = advance_stage(state)
            if new_stage:
                yield _sse_stage_update(
                    new_stage.value,
                    get_stage_label(new_stage),
                    f"Advanced to {get_stage_label(new_stage)}",
                )

        # ── Phase 3: Synthesis — LLM reads full context + cites sources ──
        agent_context = build_agent_context(
            user_message, plan.intent_summary, enriched_results, history,
        )
        yield _sse_sources(agent_context["citations"])

        messages = build_synthesis_messages(agent_context)

        # Disable model "thinking" for synthesis: deepseek-v4-flash otherwise can
        # exhaust max_tokens on reasoning_content and emit zero visible text
        # (frontend then shows "No response received.").
        async for event in _stream_llm_events(
            llm,
            messages,
            tools=[],
            max_tokens=8192,
            disable_thinking=True,
        ):
            if event["type"] == "text":
                yield _sse_text_chunk(event["content"])
            elif event["type"] == "error":
                yield _sse_error(event.get("message", "Synthesis error"))
                return

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


def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For") or request.headers.get("X-Real-IP")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def _title_from_message(message: str) -> str:
    text = " ".join(message.strip().split())
    if len(text) > 60:
        return text[:57] + "..."
    return text or "New conversation"


def _collect_text_from_sse(chunk: str, accumulator: list[str]) -> None:
    """Parse an SSE chunk and append any text content."""
    event_type = None
    for line in chunk.split("\n"):
        if line.startswith("event: "):
            event_type = line[7:].strip()
        elif line.startswith("data: ") and event_type == "text":
            try:
                data = json.loads(line[6:])
                accumulator.append(data.get("content", ""))
            except json.JSONDecodeError:
                pass


def _update_meta_plan_step(meta: dict[str, Any], step_data: dict[str, Any]) -> None:
    plan = meta.get("plan")
    if not isinstance(plan, dict):
        return
    step_num = step_data.get("step")
    for step in plan.get("steps") or []:
        if step.get("step") == step_num:
            if step_data.get("status"):
                step["status"] = step_data["status"]
            break


def _collect_turn_meta_from_sse(chunk: str, meta: dict[str, Any]) -> None:
    """Accumulate plan/tool UI state from SSE events for conversation restore."""
    event_type = None
    for line in chunk.split("\n"):
        if line.startswith("event: "):
            event_type = line[7:].strip()
        elif line.startswith("data: ") and event_type:
            try:
                data = json.loads(line[6:])
            except json.JSONDecodeError:
                event_type = None
                continue

            if event_type == "plan_created":
                meta["plan"] = {
                    "intent_summary": data.get("intent_summary") or "",
                    "steps": data.get("steps") or [],
                }
            elif event_type in ("step_started", "step_completed"):
                _update_meta_plan_step(meta, data)
            elif event_type == "tool_call":
                meta.setdefault("tools", []).append({
                    "tool_name": data.get("tool_name") or "",
                    "arguments": data.get("arguments") or {},
                    "success": None,
                    "summary": "",
                })
            elif event_type == "tool_result":
                tools = meta.setdefault("tools", [])
                payload = {
                    "tool_name": data.get("tool_name") or "",
                    "arguments": {},
                    "success": bool(data.get("success")),
                    "summary": data.get("summary") or "",
                }
                if tools and tools[-1].get("success") is None:
                    tools[-1]["success"] = payload["success"]
                    tools[-1]["summary"] = payload["summary"]
                    if not tools[-1].get("tool_name"):
                        tools[-1]["tool_name"] = payload["tool_name"]
                else:
                    tools.append(payload)

            event_type = None


async def _agent_loop_with_persist(
    user_message: str,
    history: list[dict[str, str]],
    session_id: str,
    conversation_id: str,
) -> AsyncGenerator[str, None]:
    """Wrap agent loop and persist assistant reply when complete.

    Persist before yielding ``done`` (and again in ``finally`` as a safety net):
    browsers close the SSE connection as soon as the stream ends, which can
    cancel this generator before any code after the ``async for`` would run.
    """
    text_parts: list[str] = []
    turn_meta: dict[str, Any] = {}
    saved = False

    def _persist_assistant() -> None:
        nonlocal saved
        if saved:
            return
        full_text = "".join(text_parts)
        if not full_text.strip():
            return
        meta = turn_meta or None
        if meta:
            # Drop unresolved in-flight tool rows before save.
            tools = [
                t for t in (meta.get("tools") or [])
                if t.get("success") is not None
            ]
            meta = {k: v for k, v in meta.items() if k != "tools"}
            if tools:
                meta["tools"] = tools
            if not meta:
                meta = None
        try:
            conv_store.add_message(conversation_id, "assistant", full_text, meta=meta)
            saved = True
        except Exception:
            logger.exception(
                "Failed to persist assistant message for conversation %s",
                conversation_id,
            )

    try:
        async for chunk in _agent_loop(user_message, history, session_id):
            _collect_text_from_sse(chunk, text_parts)
            _collect_turn_meta_from_sse(chunk, turn_meta)
            # Save before the client can close on ``done``.
            if chunk.startswith("event: done"):
                _persist_assistant()
            yield chunk
        _persist_assistant()
    except asyncio.CancelledError:
        _persist_assistant()
        raise
    finally:
        _persist_assistant()


# ── Endpoints ─────────────────────────────────────────────────────

@app.post("/classify")
async def classify_intent(request: Request) -> JSONResponse:
    """Classify user message intent for chat vs collection routing."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    message = str(body.get("message") or "").strip()
    upload_filenames = body.get("upload_filenames") or []
    if not isinstance(upload_filenames, list):
        upload_filenames = []
    upload_filenames = [str(f) for f in upload_filenames if f]

    entities = parse_query_entities(message)
    mode = classify_intent_mode(
        message,
        entities,
        state=None,
        upload_filenames=upload_filenames,
    )
    return JSONResponse({
        "mode": mode,
        "pmid": entities.get("pmid"),
        "entities": {
            k: entities[k]
            for k in ("gene", "uniprot_ac", "position", "ptm_type", "pmid", "mutation_label")
            if entities.get(k)
        },
        "route_collection": mode == QUERY_MODE_COLLECTION,
    })


@app.get("/health")
async def health() -> dict[str, Any]:
    """Health check endpoint."""
    return {
        "status": "ok",
        "tools_registered": len(registry.tool_names),
        "tool_names": registry.tool_names,
    }


@app.get("/conversations")
async def list_conversations(request: Request) -> JSONResponse:
    """List conversations for the current client IP."""
    client_ip = _get_client_ip(request)
    items = conv_store.list_conversations(client_ip)
    return JSONResponse({"conversations": items})


@app.post("/conversations")
async def create_conversation(request: Request) -> JSONResponse:
    """Create a new empty conversation for the current client IP."""
    client_ip = _get_client_ip(request)
    title = "New conversation"
    try:
        body = await request.json()
        if isinstance(body, dict) and body.get("title"):
            title = str(body["title"])
    except Exception:
        pass
    conv = conv_store.create_conversation(client_ip, title)
    return JSONResponse(conv, status_code=201)


@app.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: str, request: Request) -> JSONResponse:
    """Get a conversation with all messages."""
    client_ip = _get_client_ip(request)
    conv = conv_store.get_conversation(conversation_id, client_ip)
    if not conv:
        return JSONResponse({"error": "Conversation not found"}, status_code=404)
    return JSONResponse(conv)


@app.delete("/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str, request: Request) -> JSONResponse:
    """Delete a conversation."""
    client_ip = _get_client_ip(request)
    if not conv_store.delete_conversation(conversation_id, client_ip):
        return JSONResponse({"error": "Conversation not found"}, status_code=404)
    return JSONResponse({"status": "deleted"})


@app.post("/conversations/{conversation_id}/messages")
async def append_conversation_messages(conversation_id: str, request: Request) -> JSONResponse:
    """Append one or more messages to an existing conversation (used by collection agent)."""
    client_ip = _get_client_ip(request)
    if not conv_store.belongs_to_ip(conversation_id, client_ip):
        return JSONResponse({"error": "Conversation not found"}, status_code=404)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)
    items = body.get("messages") if isinstance(body, dict) else None
    if not isinstance(items, list) or not items:
        return JSONResponse({"error": "messages array required"}, status_code=400)
    for item in items:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip()
        content = str(item.get("content") or "")
        if role not in ("user", "assistant") or not content.strip():
            continue
        meta = item.get("meta") if isinstance(item.get("meta"), dict) else None
        conv_store.add_message(conversation_id, role, content, meta=meta)
    if isinstance(body, dict) and body.get("title"):
        conv_store.update_title(conversation_id, str(body["title"]))
    conv = conv_store.get_conversation(conversation_id, client_ip)
    return JSONResponse(conv or {"id": conversation_id})


@app.post("/export/pdf")
async def export_pdf(body: PdfExportRequest) -> Response:
    """Render markdown answer to a sharp, compact PDF with qPTM watermark."""
    md = (body.markdown or "").strip()
    if not md:
        return JSONResponse({"error": "markdown is required"}, status_code=400)
    if len(md) > 400_000:
        return JSONResponse({"error": "markdown too large"}, status_code=413)

    try:
        pdf_bytes = await asyncio.to_thread(build_answer_pdf, md)
    except Exception as exc:
        logger.exception("PDF export failed")
        return JSONResponse({"error": f"PDF export failed: {exc}"}, status_code=500)

    title = (body.title or "qptm-agent").strip() or "qptm-agent"
    # HTTP headers are Latin-1 only; keep an ASCII filename (Chinese titles used to 500 here).
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", title).strip("._")[:40] or "qptm-agent"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{safe}.pdf"',
            "Cache-Control": "no-store",
        },
    )


@app.post("/chat")
async def chat(request: Request) -> StreamingResponse:
    """Streaming chat endpoint. Returns SSE stream.

    Request body (JSON):
      {
        "message": "user's question",
        "session_id": "optional session ID (auto-generated if absent)",
        "conversation_id": "optional conversation ID (created if absent)",
        "history": [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]
      }

    SSE events:
      - plan_created / step_started / step_completed
      - text: {"content": "chunk of text"}
      - tool_call / tool_result
      - stage_update
      - done / error
    """
    body = await request.json()
    chat_req = ChatRequest(**body)
    client_ip = _get_client_ip(request)

    conversation_id = chat_req.conversation_id
    if conversation_id and not conv_store.belongs_to_ip(conversation_id, client_ip):
        return JSONResponse({"error": "Conversation not found"}, status_code=403)

    is_new = False
    if not conversation_id:
        conv = conv_store.create_conversation(client_ip, _title_from_message(chat_req.message))
        conversation_id = conv["id"]
        is_new = True

    conv_store.add_message(conversation_id, "user", chat_req.message)
    if is_new:
        conv_store.update_title(conversation_id, _title_from_message(chat_req.message))

    session_id = chat_req.session_id or str(uuid.uuid4())
    history = [{"role": m.role, "content": m.content} for m in chat_req.history]

    return StreamingResponse(
        _agent_loop_with_persist(
            chat_req.message, history, session_id, conversation_id,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "X-Session-Id": session_id,
            "X-Conversation-Id": conversation_id,
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
