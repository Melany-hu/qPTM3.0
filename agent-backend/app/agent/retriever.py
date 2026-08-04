"""ToolRetriever — select top-K relevant tools per user question."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from app.agent.gate import QUERY_MODE_LITERATURE, QUERY_MODE_PMID_LOOKUP
from app.agent.memory import InvestigationMemory
from app.models.schemas import WorkflowStage
from app.workflow.stages import _STAGE_KEYWORDS, _keyword_hit

logger = logging.getLogger(__name__)

DEFAULT_TOP_K = 6
IMPORTANCE_TOP_K = 10

# Always-available utility tools for certain modes
_LITERATURE_TOOLS = ["pubtator_literature_search"]
_SITE_CORE_TOOLS = ["qptm_search", "qptm_kinases", "iptmnet_enzymes", "uniprot_annotation"]

# Cross-stage tools for site-importance / WHY questions:
# mechanism + stability + disease + localization-motif overlap + LLPS regions + PPI rewiring
_SITE_IMPORTANCE_TOOLS = [
    "psp_regulatory",
    "ptm_stability",
    "ptmd_disease",
    "funcscore_phosphosite",
    "inuloc_nls_nes",
    "signalp_prediction",
    "compartments_localization",
    "interpro_domains",
    "uniprot_annotation",
    "ptmphase_llps",
    "dscope_predictions",
    "ptmint_ppi",
    "iptmnet_ptm_ppi",
]

_IMPORTANCE_KEYWORDS = [
    "important", "importance", "matter", "matters", "significance", "significant",
    "so what", "role", "purpose", "meaning", "worth",
    "重要", "重要性", "意义", "价值", "有何作用", "有什么用",
]

_STAGE_TOOL_HINTS: dict[WorkflowStage, list[str]] = {
    WorkflowStage.kinase: [
        "qptm_kinases", "iptmnet_enzymes", "psp_kinase_substrate", "gps6_kinases",
        "weram_regulators", "ubibrowser_interactions", "pmads_drug_ptm",
    ],
    WorkflowStage.conditions: [
        "qptm_site_conditions", "qptm_search", "ekpi_quantitative", "cancerproteome_disease",
    ],
    WorkflowStage.where: [
        "uniprot_annotation", "compartments_localization", "subcell_scsi",
        "inuloc_nls_nes", "signalp_prediction", "interpro_domains",
    ],
    WorkflowStage.function: [
        "psp_regulatory", "ptm_stability", "ptmcode_associations", "string_ppi",
        "activedriver_mutations", "ptmd_disease", "funcscore_phosphosite",
        "inuloc_nls_nes", "ptmphase_llps", "dscope_predictions",
        "compartments_localization", "interpro_domains",
    ],
}


def _is_importance_question(question: str, scores: dict[WorkflowStage, int]) -> bool:
    if scores.get(WorkflowStage.function, 0) > 0:
        return True
    msg_lower = question.lower()
    return any(_keyword_hit(kw, msg_lower) for kw in _IMPORTANCE_KEYWORDS)


def _has_site(question: str, memory: InvestigationMemory) -> bool:
    if memory.position:
        return True
    return bool(re.search(r"\b([STYKR]\d+|Ser\d+)\b", question, re.I))


def _score_stages(message: str) -> dict[WorkflowStage, int]:
    msg_lower = message.lower()
    scores: dict[WorkflowStage, int] = {
        WorkflowStage.kinase: 0,
        WorkflowStage.conditions: 0,
        WorkflowStage.where: 0,
        WorkflowStage.function: 0,
    }
    for stage, keywords in _STAGE_KEYWORDS.items():
        for kw in keywords:
            if _keyword_hit(kw, msg_lower):
                scores[stage] += 1
    return scores


def _heuristic_tools(
    question: str,
    memory: InvestigationMemory,
    catalog: list[dict[str, str]],
    top_k: int,
) -> list[str]:
    """Keyword-based fallback when LLM retrieval fails."""
    valid = {item["tool"] for item in catalog}
    picked: list[str] = []
    effective_k = top_k

    mode = memory.query_mode or ""
    if mode == QUERY_MODE_LITERATURE or mode == QUERY_MODE_PMID_LOOKUP:
        for t in _LITERATURE_TOOLS:
            if t in valid and t not in picked:
                picked.append(t)

    scores = _score_stages(question)
    importance = _is_importance_question(question, scores)
    has_site = _has_site(question, memory)

    if importance and (has_site or memory.has_target):
        effective_k = max(top_k, IMPORTANCE_TOP_K)
        for tool in _SITE_IMPORTANCE_TOOLS:
            if tool in valid and tool not in picked:
                picked.append(tool)
            if len(picked) >= effective_k:
                break

    ranked_stages = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    top_stage, top_score = ranked_stages[0] if ranked_stages else (None, 0)
    second_score = ranked_stages[1][1] if len(ranked_stages) > 1 else 0

    # Focus tool budget on the dominant question type when one stage clearly leads.
    if top_stage and top_score > 0 and top_score >= second_score + 1:
        for tool in _STAGE_TOOL_HINTS.get(top_stage, []):
            if tool in valid and tool not in picked:
                picked.append(tool)
            if len(picked) >= effective_k:
                break

    if len(picked) < effective_k:
        for stage, score in ranked_stages:
            if score <= 0:
                continue
            if top_stage and top_score > 0 and top_score >= second_score + 1 and stage != top_stage:
                continue
            for tool in _STAGE_TOOL_HINTS.get(stage, []):
                if tool in valid and tool not in picked:
                    picked.append(tool)
                if len(picked) >= effective_k:
                    break
            if len(picked) >= effective_k:
                break

    if memory.has_target or re.search(r"\b([STYKR]\d+|Ser\d+)\b", question, re.I):
        for t in _SITE_CORE_TOOLS:
            if t in valid and t not in picked:
                picked.append(t)

    if len(picked) < effective_k:
        for t in _SITE_CORE_TOOLS:
            if t in valid and t not in picked:
                picked.append(t)

    if len(picked) < 3:
        for item in catalog:
            name = item["tool"]
            if name not in picked:
                picked.append(name)
            if len(picked) >= effective_k:
                break

    return picked[:effective_k]


def _parse_tool_list(raw: str, valid: set[str]) -> list[str]:
    """Parse LLM JSON response into validated tool names."""
    text = (raw or "").strip()
    if not text:
        return []
    # Strip markdown fences
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    names = data if isinstance(data, list) else data.get("tools") or data.get("tool_names") or []
    result = []
    for name in names:
        if isinstance(name, str) and name in valid and name not in result:
            result.append(name)
    return result


async def retrieve_tools(
    question: str,
    memory: InvestigationMemory,
    catalog: list[dict[str, str]],
    llm: Any,
    *,
    top_k: int = DEFAULT_TOP_K,
    use_llm: bool = False,
) -> list[str]:
    """Pick top-K tool names for the current question."""
    valid = {item["tool"] for item in catalog}
    if not valid:
        return []

    if use_llm:
        catalog_lines = "\n".join(
            f"- {item['tool']}: {item['description'][:200]}"
            for item in catalog
        )
        memory_block = memory.to_prompt_block()
        prompt = (
            f"You are a tool router for a PTM research agent.\n"
            f"Pick up to {top_k} tools most relevant to answer the user question.\n"
            f"Return ONLY a JSON array of tool name strings, e.g. "
            f'["qptm_kinases","iptmnet_enzymes"].\n\n'
            f"Investigation context:\n{memory_block}\n\n"
            f"User question:\n{question}\n\n"
            f"Available tools:\n{catalog_lines}\n"
        )
        try:
            resp = await asyncio.wait_for(_llm_pick(llm, prompt), timeout=20.0)
            picked = _parse_tool_list(resp, valid)
            if picked:
                logger.info("ToolRetriever LLM picked: %s", picked)
                return picked[:top_k]
        except Exception as exc:
            logger.warning("ToolRetriever LLM failed: %s", exc)

    fallback = _heuristic_tools(question, memory, catalog, top_k)
    logger.info("ToolRetriever heuristic picked: %s", fallback)
    return fallback


async def _llm_pick(llm: Any, prompt: str) -> str:
    """Non-streaming LLM call for tool selection."""
    import asyncio

    def _call() -> str:
        result = llm.chat_completion(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=512,
            disable_thinking=True,
        )
        return result.get("content") or ""

    return await asyncio.to_thread(_call)
