"""Adaptive query depth — direct / light / full research paths."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.agent.gate import (
    QUERY_MODE_COMPARE,
    QUERY_MODE_FOLLOWUP,
    QUERY_MODE_LITERATURE,
    QUERY_MODE_PMID_LOOKUP,
    QUERY_MODE_RESEARCH,
    is_literature_request,
    is_site_mechanism_question,
)
from app.agent.memory import InvestigationMemory

_BROAD_RE = re.compile(
    r"\b(overview|comprehensive|全面|介绍|综述|summarize|summary|tell me about|"
    r"everything|all aspects|完整|整体)\b",
    re.I,
)
_LITERATURE_INTENT_RE = re.compile(
    r"\b(literature|paper|papers|pubmed|publication|recent studies|"
    r"文献|论文|最新研究|推荐文献)\b",
    re.I,
)
_NARROW_KINASE_RE = re.compile(
    r"\b(which kinase|what kinase|kinases?\s+(for|of|at|on)|who phosphorylat|"
    r"哪些激酶|哪个激酶|谁磷酸化)\b",
    re.I,
)
_NARROW_CONDITION_RE = re.compile(
    r"\b(fold change|log2|under what condition|which condition|time course|"
    r"条件下|倍数|时程)\b",
    re.I,
)
_NARROW_LOC_RE = re.compile(
    r"\b(where is|localization|localised|localized|subcellular|定位|在哪)\b",
    re.I,
)
_MULTI_DIM_RE = re.compile(
    r"\b(and also|as well as|plus|以及|并且|同时|另外)\b",
    re.I,
)


@dataclass(frozen=True)
class QueryDepth:
    """How much retrieval the agent should perform."""

    level: str  # direct | light | full
    max_tool_rounds: int
    top_k_tools: int
    run_literature: bool
    run_database_tools: bool
    label: str
    literature_independent: bool = False
    iterative_literature: bool = False

    @property
    def is_direct(self) -> bool:
        return self.level == "direct"

    @property
    def is_light(self) -> bool:
        return self.level == "light"


def _count_dimensions(question: str) -> int:
    msg = question.lower()
    dims = 0
    if re.search(r"\b(kinase|enzyme|upstream|激酶|调控)\b", msg, re.I):
        dims += 1
    if re.search(r"\b(condition|fold|log2|kinetics|treatment|条件|定量|时程)\b", msg, re.I):
        dims += 1
    if re.search(r"\b(locali[sz]|compartment|where|定位|细胞)\b", msg, re.I):
        dims += 1
    if re.search(r"\b(function|disease|mechanism|why|stability|功能|疾病|机制)\b", msg, re.I):
        dims += 1
    return dims


def _is_narrow_factual(question: str, memory: InvestigationMemory) -> bool:
    """Single-focus site question answerable from 1–2 databases."""
    msg = question.strip()
    if is_site_mechanism_question(msg, memory=memory):
        return False
    if len(msg) > 220:
        return False
    if _BROAD_RE.search(msg) or _MULTI_DIM_RE.search(msg):
        return False
    if _count_dimensions(msg) >= 2:
        return False
    if _NARROW_KINASE_RE.search(msg) or _NARROW_CONDITION_RE.search(msg) or _NARROW_LOC_RE.search(msg):
        return True
    # Short site-centric question (gene + position pattern)
    has_site = memory.position or re.search(r"\b([STYKR]\d+|Ser\d+)\b", msg, re.I)
    has_gene = memory.gene or re.search(r"\b[A-Z][A-Z0-9]{1,9}\b", msg)
    word_count = len(msg.split())
    if has_site and has_gene and word_count <= 18:
        return True
    return word_count <= 10 and bool(has_gene or has_site)


def classify_query_depth(
    question: str,
    memory: InvestigationMemory,
    mode: str,
) -> QueryDepth:
    """Choose direct (no tools), light (DB only), or full (DB + literature)."""
    msg = (question or "").strip()

    if mode in (QUERY_MODE_LITERATURE, QUERY_MODE_PMID_LOOKUP):
        return QueryDepth(
            level="full",
            max_tool_rounds=3,
            top_k_tools=4,
            run_literature=True,
            run_database_tools=mode != QUERY_MODE_LITERATURE,
            label="literature survey",
        )

    if mode in (QUERY_MODE_FOLLOWUP, QUERY_MODE_COMPARE) and not _BROAD_RE.search(msg):
        if mode == QUERY_MODE_FOLLOWUP and is_literature_request(msg):
            return QueryDepth(
                level="full",
                max_tool_rounds=2,
                top_k_tools=3,
                run_literature=True,
                run_database_tools=False,
                label="literature follow-up",
            )
        return QueryDepth(
            level="light",
            max_tool_rounds=1,
            top_k_tools=4,
            run_literature=False,
            run_database_tools=True,
            label="focused follow-up",
        )

    if mode != QUERY_MODE_RESEARCH:
        return QueryDepth(
            level="light",
            max_tool_rounds=2,
            top_k_tools=4,
            run_literature=False,
            run_database_tools=True,
            label="standard",
        )

    if _LITERATURE_INTENT_RE.search(msg) or _BROAD_RE.search(msg):
        return QueryDepth(
            level="full",
            max_tool_rounds=5,
            top_k_tools=8,
            run_literature=True,
            run_database_tools=True,
            label="comprehensive",
        )

    if _count_dimensions(msg) >= 2:
        return QueryDepth(
            level="full",
            max_tool_rounds=4,
            top_k_tools=7,
            run_literature=True,
            run_database_tools=True,
            label="multi-aspect",
        )

    if is_site_mechanism_question(msg, memory=memory):
        return QueryDepth(
            level="full",
            max_tool_rounds=3,
            top_k_tools=6,
            run_literature=True,
            run_database_tools=True,
            label="site mechanism",
            literature_independent=True,
            iterative_literature=True,
        )

    if _is_narrow_factual(msg, memory):
        return QueryDepth(
            level="light",
            max_tool_rounds=1,
            top_k_tools=3,
            run_literature=False,
            run_database_tools=True,
            label="narrow factual",
        )

    # Default research: light DB path without mandatory literature
    return QueryDepth(
        level="light",
        max_tool_rounds=1,
        top_k_tools=5,
        run_literature=False,
        run_database_tools=True,
        label="standard research",
    )
