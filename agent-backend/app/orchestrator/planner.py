"""Build orchestrator execution plan."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from app.agent.llm_fallback import log_llm_fallback
from app.agent.memory import InvestigationMemory
from app.agent.query_depth import QueryDepth, classify_query_depth
from app.config import settings
from app.orchestrator.prompts import ORCHESTRATOR_PLAN_SYSTEM
from app.orchestrator.schemas import AgentTask, OrchestratorPlan

logger = logging.getLogger(__name__)

# Soft cap: heuristic plan is ready immediately; don't block the pipeline on a slow planner LLM.
_PLAN_LLM_SOFT_TIMEOUT_S = 10.0


def _parse_json(raw: str) -> dict[str, Any] | None:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None


def _plan_from_depth(question: str, memory: InvestigationMemory, mode: str, depth: QueryDepth) -> OrchestratorPlan:
    run_lit = depth.run_literature and settings.literature_enrichment_enabled
    is_mechanism = depth.label == "site mechanism"
    lit_focus = (
        "Iterative PubMed search: upstream kinases, regulatory intermediates, downstream transcription"
        if is_mechanism
        else "Fetch and interpret papers supporting database findings"
    )
    tasks: list[AgentTask] = [
        AgentTask(
            agent="database",
            parallel_group=1,
            focus=question[:200],
            enabled=depth.run_database_tools,
        ),
    ]
    if run_lit:
        tasks.append(AgentTask(
            agent="literature",
            parallel_group=2,
            focus=lit_focus,
            enabled=True,
        ))
    return OrchestratorPlan(
        user_goal=question[:300],
        tasks=tasks,
        run_literature=run_lit,
        literature_independent=depth.literature_independent,
        depth_hint="full" if is_mechanism else depth.level,
        reasoning=f"Heuristic plan ({depth.label})",
        max_tool_rounds=depth.max_tool_rounds,
        top_k_tools=depth.top_k_tools,
        mechanism_question=is_mechanism,
    )


async def build_orchestrator_plan(
    llm: Any,
    question: str,
    memory: InvestigationMemory,
    mode: str,
    *,
    lang: str = "en",
) -> OrchestratorPlan:
    depth = classify_query_depth(question, memory, mode)
    fallback = _plan_from_depth(question, memory, mode, depth)

    prompt = (
        f"User question:\n{question}\n\n"
        f"Parsed gene: {memory.gene or 'unknown'}\n"
        f"Site: {memory.position or 'unknown'}\n"
        f"Query depth signal: {depth.level} ({depth.label})\n"
        f"run_literature default: {depth.run_literature}\n"
        f"literature_independent default: {depth.literature_independent}\n"
        f"mechanism_question: {depth.label == 'site mechanism'}\n"
    )

    def _call() -> str:
        r = llm.chat_completion(
            messages=[
                {"role": "system", "content": ORCHESTRATOR_PLAN_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=600,
            disable_thinking=True,
        )
        return r.get("content") or ""

    timeout_s = float(getattr(settings, "orchestrator_plan_timeout", 30) or 30)
    soft_timeout = min(timeout_s, _PLAN_LLM_SOFT_TIMEOUT_S)
    try:
        raw = await asyncio.wait_for(asyncio.to_thread(_call), timeout=soft_timeout)
    except Exception as exc:
        log_llm_fallback(
            "Orchestrator plan",
            exc,
            timeout_s=soft_timeout,
            detail=f"heuristic plan ({depth.label})",
        )
        return fallback

    data = _parse_json(raw)
    if not data:
        logger.info(
            "Orchestrator plan LLM returned unparseable JSON; using heuristic plan (%s)",
            depth.label,
        )
        return fallback

    tasks: list[AgentTask] = []
    for t in data.get("tasks") or []:
        if not isinstance(t, dict):
            continue
        agent = t.get("agent")
        if agent not in ("database", "literature"):
            continue
        tasks.append(AgentTask(
            agent=agent,
            parallel_group=int(t.get("parallel_group") or 1),
            focus=str(t.get("focus") or ""),
            enabled=bool(t.get("enabled", True)),
        ))
    if not tasks:
        return fallback

    return OrchestratorPlan(
        user_goal=str(data.get("user_goal") or question)[:300],
        tasks=tasks,
        run_literature=bool(data.get("run_literature", fallback.run_literature)),
        literature_independent=bool(
            data.get("literature_independent", fallback.literature_independent)
        ),
        depth_hint=str(data.get("depth_hint") or fallback.depth_hint),
        reasoning=str(data.get("reasoning") or "")[:400],
        max_tool_rounds=int(data.get("max_tool_rounds") or depth.max_tool_rounds),
        top_k_tools=int(data.get("top_k_tools") or depth.top_k_tools),
        mechanism_question=bool(data.get("mechanism_question", fallback.mechanism_question)),
    )
