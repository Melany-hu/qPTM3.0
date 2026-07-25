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

# Display labels for synthesis / Sources table — language-dependent.
# curated is mapped to experimental for end users — the meaningful split is
# experimental/literature-backed vs computational prediction.
EVIDENCE_LABELS_EN: dict[str, str] = {
    EvidenceLevel.experimental.value: "experimental",
    EvidenceLevel.predicted.value: "predicted",
    EvidenceLevel.curated.value: "experimental",
    EvidenceLevel.unknown.value: "unknown",
}
EVIDENCE_LABELS_ZH: dict[str, str] = {
    EvidenceLevel.experimental.value: "实验验证",
    EvidenceLevel.predicted.value: "计算预测",
    EvidenceLevel.curated.value: "实验验证",
    EvidenceLevel.unknown.value: "未标注",
}
# Backward-compatible default (bilingual) — prefer lang-aware helpers below
EVIDENCE_LABELS: dict[str, str] = {
    EvidenceLevel.experimental.value: "experimental (实验验证)",
    EvidenceLevel.predicted.value: "predicted (计算预测)",
    EvidenceLevel.curated.value: "experimental (实验验证)",
    EvidenceLevel.unknown.value: "unknown (未标注)",
}


def _response_lang(question: str | None) -> str:
    """Return 'zh' or 'en' for evidence-label localization."""
    if not question:
        return "en"
    zh = sum(1 for ch in question if "\u4e00" <= ch <= "\u9fff")
    latin = sum(1 for ch in question if "a" <= ch.lower() <= "z")
    if zh >= 2 and zh >= latin * 0.35:
        return "zh"
    return "en"

# Homepage fallbacks when a citation has no URL (name variants included)
DATABASE_HOMEPAGES: dict[str, str] = {
    "qPTM": "https://qptm3.omicsbio.info",
    "qPTM (qPTM)": "https://qptm3.omicsbio.info",
    "iPTMnet": "https://research.bioinformatics.udel.edu/iptmnet/",
    "UniProt": "https://www.uniprot.org",
    "InterPro": "https://www.ebi.ac.uk/interpro/",
    "Pfam": "https://www.ebi.ac.uk/interpro/entry/pfam/",
    "PhosphoSitePlus": "https://www.phosphosite.org",
    "dbPTM": "https://biomics.lab.nycu.edu.tw/dbPTM/",
    "ActiveDriverDB": "https://activedriverdb.org",
    "PMADS": "https://pmads-db.org",
    "DrugBank": "https://go.drugbank.com",
    "WERAM": "http://weram.biocuckoo.org",
    "UbiBrowser": "http://ubibrowser.bio-it.cn/ubibrowser_v3/home/index",
    "GPS-Uber": "http://gpsuber.biocuckoo.cn/",
    "GPS 6.0": "https://gps.biocuckoo.cn",
    "GPS-SUMO 2.0": "https://sumo.biocuckoo.cn/",
    "KAKA": "https://kaka.omicsbio.info/",
    "eKPI": "https://ekpi.omicsbio.info/",
    "decryptM": "https://www.proteomicsdb.org/decryptm",
    "PTMPhaSe": "https://ptmphase.sjtu.edu.cn",
    "dSCOPE": "https://dscope.omicsbio.info",
    "PTMD": "https://ptmd.biocuckoo.cn/",
    "CancerProteome": "http://bio-bigdata.hrbmu.edu.cn/CancerProteome",
    "PTMint": "https://ptmint.sjtu.edu.cn/",
    "STRING": "https://string-db.org",
    "BioGRID": "https://thebiogrid.org",
    "IntAct": "https://www.ebi.ac.uk/intact",
    "Reactome": "https://reactome.org",
    "KEGG": "https://www.kegg.jp",
    "PathBank": "https://pathbank.org",
    "PTMcode2": "http://ptmcode.embl.de",
    "NLSdb": "https://rostlab.org/services/nlsdb/",
    "COMPARTMENTS": "https://compartments.jensenlab.org/",
    "SubCELL": "https://subcell.idrblab.cn/",
    "iNuLoC": "http://inuloc.omicsbio.info/",
    "Funcscore": "https://www.nature.com/articles/s41587-019-0344-3",
    "PTM-stability": "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC9839724/",
    "PubTator3": "https://www.ncbi.nlm.nih.gov/research/pubtator3/",
}


def evidence_label(
    level: EvidenceLevel | str | None,
    *,
    lang: str | None = None,
) -> str:
    """Human-readable evidence level for LLM and Sources table.

    curated → experimental for display (both are literature/assay backed;
    only predicted stays distinct).
    """
    labels = EVIDENCE_LABELS_ZH if lang == "zh" else (
        EVIDENCE_LABELS_EN if lang == "en" else EVIDENCE_LABELS
    )
    if level is None:
        return labels[EvidenceLevel.unknown.value]
    key = level.value if isinstance(level, EvidenceLevel) else str(level)
    return labels.get(key, labels[EvidenceLevel.unknown.value])


def _md_link(label: str, url: str | None) -> str:
    """Markdown hyperlink; falls back to plain label when URL is missing."""
    text = (label or "").strip() or "source"
    href = (url or "").strip()
    if not href:
        return text
    # Escape pipe so table cells stay intact
    safe_text = text.replace("|", "/")
    return f"[{safe_text}]({href})"


def _database_link(database: str, citation_url: str | None = None) -> str:
    """Clickable database name for the Sources table."""
    url = (citation_url or "").strip() or DATABASE_HOMEPAGES.get(database, "")
    return _md_link(database, url or None)

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


def format_citations_block(
    citations: list[Citation],
    *,
    lang: str | None = None,
) -> str:
    """Human-readable citation registry for the LLM."""
    if not citations:
        return "(No sources collected — state that no database evidence was retrieved.)"

    if lang == "zh":
        level_hint = "证据等级：实验验证 | 计算预测。"
    else:
        level_hint = "Evidence levels: experimental | predicted."

    lines = [
        "Each [Sx] carries: Database/tool · Evidence level · optional PMID/DOI/URL.",
        level_hint,
        "Treat literature-curated and assay-backed resources as experimental; "
        "only mark computational predictors as predicted.",
        "When stating a fact, name the database AND the evidence level from this registry.",
        "",
    ]
    for c in citations:
        parts = [
            f"[{c.id}] Database={c.source_db}",
            f"Evidence={evidence_label(c.evidence_level, lang=lang)}",
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


def _compact_tool_data(data: dict[str, Any], *, max_list_items: int = 12) -> dict[str, Any]:
    """Shrink tool payloads so synthesis prompts stay within model limits."""
    out: dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, list):
            trimmed = value[:max_list_items]
            out[key] = trimmed
            if len(value) > max_list_items:
                out[f"{key}_truncated"] = True
                out[f"{key}_total"] = len(value)
        elif isinstance(value, dict):
            nested: dict[str, Any] = {}
            for nk, nv in value.items():
                if isinstance(nv, list):
                    nested[nk] = nv[:max_list_items]
                    if len(nv) > max_list_items:
                        nested[f"{nk}_truncated"] = True
                        nested[f"{nk}_total"] = len(nv)
                else:
                    nested[nk] = nv
            out[key] = nested
        else:
            out[key] = value
    return out


def format_tool_results_block(enriched_results: list[ToolResult]) -> str:
    """Serialize tool evidence for the LLM context window."""
    if not enriched_results:
        return "(No tool results — plan steps were skipped or failed.)"

    blocks: list[str] = []
    for i, tr in enumerate(enriched_results, 1):
        if tr.citations:
            cite_bits = []
            for c in tr.citations[:12]:
                cid = tr.citation_map.get(c.id, c.id)
                cite_bits.append(f"{cid}:{evidence_label(c.evidence_level)}")
            if len(tr.citations) > 12:
                cite_bits.append(f"…(+{len(tr.citations) - 12} more)")
            cite_ids = ", ".join(cite_bits)
        else:
            cite_ids = "—"
        levels = sorted({evidence_label(c.evidence_level) for c in tr.citations}) or ["—"]
        status = "success" if tr.success else "failed"
        compact = _compact_tool_data(tr.data if isinstance(tr.data, dict) else {"value": tr.data})
        payload = json.dumps(compact, ensure_ascii=False, indent=2)
        if len(payload) > 2500:
            payload = payload[:2500] + "\n…(truncated)"
        block = (
            f"### Evidence Block {i}: {tr.tool} [{tr.database}] — {status}\n"
            f"Evidence levels in this block: {'; '.join(levels)}\n"
            f"Available citation IDs (with evidence): {cite_ids}\n"
            f"Summary: {tr.summary}\n"
            f"Structured data:\n```json\n"
            f"{payload}\n"
            f"```"
        )
        blocks.append(block)
    return "\n\n".join(blocks)


def format_retrieval_summary_table(
    enriched_results: list[ToolResult],
    citations: list[Citation],
    *,
    lang: str | None = None,
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
        cite_url = None
        if tr.citations:
            ids = []
            level_labels: list[str] = []
            for c in tr.citations:
                ids.append(tr.citation_map.get(c.id, c.id))
                level_labels.append(evidence_label(c.evidence_level, lang=lang))
                if not cite_url and c.url:
                    cite_url = c.url
            id_cell = ", ".join(dict.fromkeys(ids))
            evidence_cell = ", ".join(dict.fromkeys(level_labels))
            note = tr.citations[0].label
            # Prefer a short note; attach homepage as markdown link separately in Database col
            if tr.citations[0].pmid:
                pmid = tr.citations[0].pmid
                note = f"{note} · {_md_link(f'PMID:{pmid}', f'https://pubmed.ncbi.nlm.nih.gov/{pmid}/')}"
        else:
            id_cell = "—"
            evidence_cell = "—"
            note = (tr.summary or "")[:120]

        db_cell = _database_link(tr.database, cite_url)
        lines.append(
            f"| {id_cell} | {db_cell} | `{tr.tool}` | {evidence_cell} | "
            f"{status} | {n} | {note} |"
        )

    if citations:
        lines.append("")
        if lang == "zh":
            legend = (
                "图例：**实验验证** = 实验/文献支持证据；**计算预测** = 计算预测结果。"
                "数据库名称为来源主页超链接。引用 ID 对应正文中的 [Sx]。"
            )
        else:
            legend = (
                "Legend: **experimental** = assay / literature-backed evidence; "
                "**predicted** = computational prediction. "
                "Database names are hyperlinks to the source homepage. "
                "Citation IDs map to [Sx] in the Source Registry."
            )
        lines.append(legend)
    return "\n".join(lines)


def build_agent_context(
    question: str,
    plan_summary: str,
    enriched_results: list[ToolResult],
    history: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Build the full context object for LLM synthesis."""
    citations = merge_citations(enriched_results)
    lang = _response_lang(question)
    return {
        "question": question,
        "plan_summary": plan_summary,
        "history": (history or [])[-6:],
        "tool_results": enriched_results,
        "citations": [c.model_dump(mode="json") for c in citations],
        "citations_text": format_citations_block(citations, lang=lang),
        "evidence_text": format_tool_results_block(enriched_results),
        "retrieval_table": format_retrieval_summary_table(
            enriched_results, citations, lang=lang
        ),
        "response_lang": lang,
    }
