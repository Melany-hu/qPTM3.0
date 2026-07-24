"""Agent context builder — assembles everything the LLM can see at synthesis time.

Agent = LLM (brain) + Context (eyes) + Tools (hands)

This module builds the structured context bundle passed to the LLM:
  - user question + conversation history
  - research plan
  - tool results with compact structured data
  - standardized source citations for attribution
"""

from __future__ import annotations

import json
from typing import Any

from app.models.schemas import Citation, EvidenceLevel, ToolResult
from app.workflow.citations import attach_citations

# Display labels for synthesis / Sources table (bilingual for zh+en users)
EVIDENCE_LABELS: dict[str, str] = {
    EvidenceLevel.experimental.value: "experimental (实验验证)",
    EvidenceLevel.predicted.value: "predicted (计算预测)",
    EvidenceLevel.curated.value: "curated (文献策展)",
    EvidenceLevel.unknown.value: "unknown (未标注)",
}


def evidence_label(level: EvidenceLevel | str | None) -> str:
    """Human-readable evidence level for LLM and Sources table."""
    if level is None:
        return EVIDENCE_LABELS[EvidenceLevel.unknown.value]
    key = level.value if isinstance(level, EvidenceLevel) else str(level)
    return EVIDENCE_LABELS.get(key, EVIDENCE_LABELS[EvidenceLevel.unknown.value])


def enrich_tool_result(
    tool: str,
    database: str,
    success: bool,
    raw_result: dict[str, Any],
) -> ToolResult:
    """Compatibility wrapper; prefers error key in raw_result over success flag."""
    _ = success  # success is derived inside attach_citations
    return attach_citations(tool, database, raw_result)


def _citation_key(c: Citation) -> str:
    return "|".join([c.source_db, c.label, c.pmid or "", c.doi or ""])


def merge_citations(enriched_results: list[ToolResult]) -> list[Citation]:
    """Flatten and re-number citations across all tool results (global S1..Sn)."""
    merged: list[Citation] = []
    seen: set[str] = set()

    for tr in enriched_results:
        local_to_global: dict[str, str] = {}
        for local in tr.citations:
            k = _citation_key(local)
            if k not in seen:
                seen.add(k)
                gid = f"S{len(merged) + 1}"
                merged.append(local.model_copy(update={"id": gid}))
            for global_cite in merged:
                if _citation_key(global_cite) == k:
                    local_to_global[local.id] = global_cite.id
                    break
        tr.citation_map = local_to_global

    return merged


def format_citations_block(citations: list[Citation]) -> str:
    """Human-readable citation registry for the LLM."""
    if not citations:
        return "(No sources collected — state that no database evidence was retrieved.)"

    lines = [
        "Each [Sx] carries: Database/tool · Evidence level · optional PMID/DOI/URL.",
        "Evidence levels: experimental (实验验证) | curated (文献策展) | predicted (计算预测).",
        "When stating a fact, name the database AND the evidence level from this registry.",
        "",
    ]
    for c in citations:
        parts = [
            f"[{c.id}] Database={c.source_db}",
            f"Evidence={evidence_label(c.evidence_level)}",
            f"Label={c.label}",
        ]
        if c.pmid:
            parts.append(f"PMID:{c.pmid}")
        if c.doi:
            parts.append(f"DOI:{c.doi}")
        if c.url:
            parts.append(f"URL:{c.url}")
        if c.detail:
            parts.append(f"— {c.detail}")
        lines.append(" | ".join(parts))
    return "\n".join(lines)


def format_tool_results_block(enriched_results: list[ToolResult]) -> str:
    """Serialize tool evidence for the LLM context window."""
    if not enriched_results:
        return "(No tool results — plan steps were skipped or failed.)"

    blocks: list[str] = []
    for i, tr in enumerate(enriched_results, 1):
        if tr.citations:
            cite_bits = []
            for c in tr.citations:
                cid = tr.citation_map.get(c.id, c.id)
                cite_bits.append(f"{cid}:{evidence_label(c.evidence_level)}")
            cite_ids = ", ".join(cite_bits)
        else:
            cite_ids = "—"
        levels = sorted({evidence_label(c.evidence_level) for c in tr.citations}) or ["—"]
        status = "success" if tr.success else "failed"
        block = (
            f"### Evidence Block {i}: {tr.tool} [{tr.database}] — {status}\n"
            f"Evidence levels in this block: {'; '.join(levels)}\n"
            f"Available citation IDs (with evidence): {cite_ids}\n"
            f"Summary: {tr.summary}\n"
            f"Structured data:\n```json\n"
            f"{json.dumps(tr.data, ensure_ascii=False, indent=2)[:6000]}\n"
            f"```"
        )
        blocks.append(block)
    return "\n\n".join(blocks)


def format_retrieval_summary_table(
    enriched_results: list[ToolResult],
    citations: list[Citation],
) -> str:
    """Pre-built markdown table of retrieved evidence + sources for the answer footer."""
    if not enriched_results:
        return (
            "| ID | Database | Tool | Evidence | Status | Records | Notes |\n"
            "|----|----------|------|----------|--------|---------|-------|\n"
            "| — | — | — | — | — | 0 | No tools executed |"
        )

    lines = [
        "| ID | Database | Tool | Evidence | Status | Records | Source notes |",
        "|----|----------|------|----------|--------|---------|--------------|",
    ]
    for tr in enriched_results:
        n = 0
        if isinstance(tr.data.get("total"), int):
            n = tr.data["total"]
        else:
            for v in tr.data.values():
                if isinstance(v, list):
                    n += len(v)
                elif isinstance(v, dict):
                    for vv in v.values():
                        if isinstance(vv, list):
                            n += len(vv)
        status = "ok" if tr.success else "failed"
        if tr.citations:
            ids = []
            level_labels: list[str] = []
            for c in tr.citations:
                ids.append(tr.citation_map.get(c.id, c.id))
                level_labels.append(evidence_label(c.evidence_level))
            id_cell = ", ".join(dict.fromkeys(ids))
            evidence_cell = ", ".join(dict.fromkeys(level_labels))
            note = tr.citations[0].label
            url = tr.citations[0].url or ""
            if url:
                note = f"{note} ({url})"
        else:
            id_cell = "—"
            evidence_cell = "—"
            note = tr.summary[:120]
        lines.append(
            f"| {id_cell} | {tr.database} | `{tr.tool}` | {evidence_cell} | "
            f"{status} | {n} | {note} |"
        )

    if citations:
        lines.append("")
        lines.append(
            "Legend: **experimental** = 实验验证; **curated** = 文献策展/人工整理; "
            "**predicted** = 计算预测. Citation IDs map to [Sx] in the Source Registry."
        )
    return "\n".join(lines)


def build_agent_context(
    question: str,
    plan_summary: str,
    enriched_results: list[ToolResult],
    history: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Build the full context object for LLM synthesis."""
    citations = merge_citations(enriched_results)
    return {
        "question": question,
        "plan_summary": plan_summary,
        "history": (history or [])[-6:],
        "tool_results": enriched_results,
        "citations": [c.model_dump(mode="json") for c in citations],
        "citations_text": format_citations_block(citations),
        "evidence_text": format_tool_results_block(enriched_results),
        "retrieval_table": format_retrieval_summary_table(enriched_results, citations),
    }
