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
import re
from typing import Any

from app.models.schemas import Citation, EvidenceLevel, SourceType, ToolResult
from app.workflow.citations import attach_citations
from app.workflow.planner import DATABASE_CATALOG

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


def _citation_db_key(database: str | None, citation: Citation | None = None) -> str:
    """Canonical database/tool key — one [Sx] per source name."""
    raw = (database or "").strip()
    if not raw and citation is not None:
        raw = (citation.source_db or "").strip()
    # Keep catalog names intact ("GPS 6.0"); only strip "qPTM (GPS)"-style suffixes
    if "(" in raw and not raw.startswith("GPS"):
        bare = raw.split("(")[0].strip()
        if bare:
            raw = bare
    return raw


_EVIDENCE_RANK: dict[str, int] = {
    EvidenceLevel.experimental.value: 0,
    EvidenceLevel.curated.value: 1,
    EvidenceLevel.predicted.value: 2,
    EvidenceLevel.unknown.value: 3,
}


def _evidence_rank(level: EvidenceLevel | str | None) -> int:
    if level is None:
        return _EVIDENCE_RANK[EvidenceLevel.unknown.value]
    key = level.value if isinstance(level, EvidenceLevel) else str(level)
    return _EVIDENCE_RANK.get(key, 99)


def merge_citations(enriched_results: list[ToolResult]) -> list[Citation]:
    """Flatten citations to **one global [Sx] per database/tool**.

    Multiple tool hits or PMIDs from the same source share a single ID so the
    answer can reuse e.g. [S1] for all qPTM facts.
    """
    merged: list[Citation] = []
    db_to_gid: dict[str, str] = {}
    db_to_idx: dict[str, int] = {}

    for tr in enriched_results:
        db = _citation_db_key(tr.database, tr.citations[0] if tr.citations else None)
        if not db:
            tr.citation_map = {}
            continue

        local_to_global: dict[str, str] = {}

        if db not in db_to_gid:
            # Prefer a non-literature citation as the representative row
            base: Citation | None = None
            for c in tr.citations:
                if c.source_type != SourceType.literature:
                    base = c
                    break
            if base is None and tr.citations:
                base = tr.citations[0]
            if base is None:
                tr.citation_map = {}
                continue

            pmids: list[str] = []
            for c in tr.citations:
                if c.pmid:
                    p = str(c.pmid).strip()
                    if p.isdigit() and p not in pmids:
                        pmids.append(p)

            best_level = base.evidence_level
            for c in tr.citations:
                if _evidence_rank(c.evidence_level) < _evidence_rank(best_level):
                    best_level = c.evidence_level

            gid = f"S{len(merged) + 1}"
            detail_parts: list[str] = []
            if base.detail:
                detail_parts.append(base.detail)
            if len(pmids) > 1:
                detail_parts.append("PMIDs: " + ", ".join(pmids[:8]))

            merged.append(
                base.model_copy(
                    update={
                        "id": gid,
                        "source_db": db,
                        "evidence_level": best_level,
                        "pmid": pmids[0] if pmids else base.pmid,
                        "detail": " · ".join(detail_parts) if detail_parts else base.detail,
                    }
                )
            )
            db_to_gid[db] = gid
            db_to_idx[db] = len(merged) - 1
        else:
            idx = db_to_idx[db]
            existing = merged[idx]
            pmids: list[str] = []
            if existing.pmid:
                pmids.append(str(existing.pmid).strip())
            if existing.detail:
                for m in re.finditer(r"\b(\d{6,9})\b", existing.detail):
                    if m.group(1) not in pmids:
                        pmids.append(m.group(1))
            for c in tr.citations:
                if c.pmid:
                    p = str(c.pmid).strip()
                    if p.isdigit() and p not in pmids:
                        pmids.append(p)
                if _evidence_rank(c.evidence_level) < _evidence_rank(existing.evidence_level):
                    existing = existing.model_copy(update={"evidence_level": c.evidence_level})

            detail = existing.detail or ""
            if len(pmids) > 1:
                # Refresh aggregated PMID list in detail
                detail_core = re.sub(
                    r"(?:\s*·\s*)?PMIDs?:\s*[\d,\s]+", "", detail, flags=re.I
                ).strip(" ·")
                detail = (
                    f"{detail_core} · PMIDs: {', '.join(pmids[:8])}".strip(" ·")
                    if detail_core
                    else f"PMIDs: {', '.join(pmids[:8])}"
                )
            merged[idx] = existing.model_copy(
                update={
                    "pmid": pmids[0] if pmids else existing.pmid,
                    "detail": detail or existing.detail,
                }
            )

        gid = db_to_gid[db]
        for local in tr.citations:
            local_to_global[local.id] = gid
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
        "Each [Sx] = ONE database/tool. Reuse the same tag for all facts from that source.",
        "Do not invent extra [Sx] IDs; do not assign different IDs to the same database.",
        level_hint,
        "Treat literature-curated and assay-backed resources as experimental; "
        "only mark computational predictors as predicted.",
        "When stating a fact, name the database AND the evidence level from this registry.",
        "IMPORTANT: When structured evidence rows include literature PMIDs "
        "(pmid / pmids / experimental_pmids), put those PMIDs inline in the answer "
        "sentence for that fact (before [Sx]). Registry PMID may be the database "
        "catalog paper — prefer hit-level PMIDs from the evidence JSON.",
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


def _extract_literature_pmids(obj: Any, *, limit: int = 24) -> list[str]:
    """Collect hit-level literature PMIDs from compact tool payloads."""
    found: list[str] = []
    seen: set[str] = set()
    pmid_keys = {
        "pmid", "pmids", "experimental_pmids", "literature_pmids", "primary_pmids",
    }

    def _add(raw: Any) -> None:
        if raw is None:
            return
        if isinstance(raw, (list, tuple, set)):
            for item in raw:
                _add(item)
            return
        text = str(raw).strip()
        if not text:
            return
        for part in re.split(r"[,;\s]+", text):
            p = part.strip()
            if p.isdigit() and 5 <= len(p) <= 9 and p not in seen:
                seen.add(p)
                found.append(p)

    def _walk(node: Any) -> None:
        if len(found) >= limit:
            return
        if isinstance(node, dict):
            for key, val in node.items():
                lk = str(key).lower()
                if lk in pmid_keys or lk.endswith("_pmid") or lk.endswith("_pmids"):
                    _add(val)
                else:
                    _walk(val)
                if len(found) >= limit:
                    return
        elif isinstance(node, list):
            for item in node:
                _walk(item)
                if len(found) >= limit:
                    return

    _walk(obj)
    return found[:limit]


def _has_positive_evidence(tr: ToolResult) -> bool:
    """True only when a tool returned usable hit rows (omit empty/no-hit blocks)."""
    if not tr.success:
        return False
    data = tr.data if isinstance(tr.data, dict) else {}
    return _record_count(data) > 0


def format_tool_results_block(enriched_results: list[ToolResult]) -> str:
    """Serialize tool evidence for the LLM context window.

    Empty / no-hit / failed tools are omitted so the model cannot narrate absences.
    """
    positive = [tr for tr in enriched_results if _has_positive_evidence(tr)]
    if not positive:
        return (
            "(No positive tool hits. Answer only with what is known from the question "
            "context if any; do **not** list databases that returned nothing.)"
        )

    blocks: list[str] = []
    for i, tr in enumerate(positive, 1):
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
        compact = _compact_tool_data(tr.data if isinstance(tr.data, dict) else {"value": tr.data})
        lit_pmids = _extract_literature_pmids(compact)
        payload = json.dumps(compact, ensure_ascii=False, indent=2)
        if len(payload) > 2500:
            payload = payload[:2500] + "\n…(truncated)"
        pmid_line = (
            f"Literature PMIDs in this block (put matching PMIDs inline in answer "
            f"sentences): {', '.join(lit_pmids)}\n"
            if lit_pmids
            else (
                "Literature PMIDs in this block: none detected in row fields — "
                "cite [Sx] only; do not invent PMIDs.\n"
            )
        )
        block = (
            f"### Evidence Block {i}: {tr.tool} [{tr.database}] — success\n"
            f"Evidence levels in this block: {', '.join(levels)}\n"
            f"Available citation IDs (with evidence): {cite_ids}\n"
            f"{pmid_line}"
            f"Summary: {tr.summary}\n"
            f"Structured data:\n```json\n"
            f"{payload}\n"
            f"```"
        )
        blocks.append(block)
    return "\n\n".join(blocks)

def _catalog_info(database: str) -> dict[str, str]:
    """Lookup DATABASE_CATALOG by exact name or bare prefix (e.g. 'qPTM (GPS)')."""
    if not database:
        return {}
    if database in DATABASE_CATALOG:
        return DATABASE_CATALOG[database]
    bare = database.split("(")[0].strip()
    if bare in DATABASE_CATALOG:
        return DATABASE_CATALOG[bare]
    return {}


def _record_count(data: dict[str, Any]) -> int:
    """Estimate how many result rows a tool returned."""
    if isinstance(data.get("total"), int):
        return int(data["total"])
    n = 0
    for v in data.values():
        if isinstance(v, list):
            n += len(v)
        elif isinstance(v, dict):
            for vv in v.values():
                if isinstance(vv, list):
                    n += len(vv)
    return n


def _catalog_pmid(database: str, info: dict[str, str], desc: str) -> str | None:
    """Fixed publication PMID for a database/tool (catalog only — not hit literature)."""
    raw = (info.get("pmid") or "").strip()
    if raw.isdigit():
        return raw
    m = re.search(r"PMID[:\s]+(\d+)", desc, flags=re.I)
    if m:
        return m.group(1)
    try:
        from app.sources.catalog import get_catalog

        catalog = get_catalog()
        db_l = (database or "").strip().lower()
        bare_l = db_l.split("(")[0].strip()
        for src in catalog.all():
            name = (src.name or "").strip().lower()
            sid = (src.id or "").strip().lower()
            if name in {db_l, bare_l} or sid.replace("-", "") == bare_l.replace(" ", "").replace("-", ""):
                pmid = str(src.pmid or "").strip()
                if pmid.isdigit():
                    return pmid
    except Exception:
        pass
    return None


def _source_notes(tr: ToolResult) -> str:
    """Short database/tool description + its fixed catalog PMID (if any)."""
    info = _catalog_info(tr.database)
    desc = (info.get("description") or "").strip()
    if not desc and tr.citations:
        desc = (tr.citations[0].label or "").strip()
    if not desc:
        desc = (tr.summary or "").strip()[:160]

    pmid = _catalog_pmid(tr.database, info, desc)
    desc = re.sub(r"\s*[;,]?\s*PMID[:\s]+\d+", "", desc, flags=re.I).strip(" ;,.")
    # Drop vague “primary PMIDs” wording when we have no single catalog PMID
    desc = re.sub(r"\s*\(primary PMIDs;[^)]*\)\s*", " ", desc, flags=re.I).strip()

    parts: list[str] = []
    if desc:
        parts.append(desc.replace("|", "/"))
    if pmid:
        parts.append(_md_link(f"PMID:{pmid}", f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"))
    return " · ".join(parts) if parts else "—"


def format_retrieval_summary_table(
    enriched_results: list[ToolResult],
    citations: list[Citation],
    *,
    lang: str | None = None,
) -> str:
    """Pre-built markdown table — one row per database/tool ([Sx])."""
    if not enriched_results:
        return (
            "| ID | Database | Evidence | Records | Source notes |\n"
            "|----|----------|----------|---------|--------------|\n"
            "| — | — | — | 0 | No tools executed |"
        )

    # Group positive tool results by canonical database name
    groups: dict[str, dict[str, Any]] = {}
    for tr in enriched_results:
        n = _record_count(tr.data if isinstance(tr.data, dict) else {})
        # No retrieved entries → omit from Sources (do not show Records=0 rows)
        if n <= 0 or not tr.success:
            continue

        db = _citation_db_key(tr.database, tr.citations[0] if tr.citations else None)
        if not db:
            continue
        g = groups.get(db)
        if g is None:
            g = {
                "database": db,
                "records": 0,
                "ids": [],
                "levels": [],
                "cite_url": None,
                "tool_results": [],
            }
            groups[db] = g
        g["records"] += n
        g["tool_results"].append(tr)
        for c in tr.citations:
            gid = tr.citation_map.get(c.id, c.id)
            if gid not in g["ids"]:
                g["ids"].append(gid)
            lab = evidence_label(c.evidence_level, lang=lang)
            if lab not in g["levels"]:
                g["levels"].append(lab)
            if not g["cite_url"] and c.url:
                g["cite_url"] = c.url

    # Prefer registry order (S1, S2, …) when available
    cite_by_db = {_citation_db_key(c.source_db): c for c in citations}
    ordered_dbs = []
    for c in citations:
        key = _citation_db_key(c.source_db)
        if key in groups and groups[key]["records"] > 0 and key not in ordered_dbs:
            ordered_dbs.append(key)
    for key, g in groups.items():
        if g["records"] > 0 and key not in ordered_dbs:
            ordered_dbs.append(key)

    lines = [
        "| ID | Database | Evidence | Records | Source notes |",
        "|----|----------|----------|---------|--------------|",
    ]
    for db in ordered_dbs:
        g = groups[db]
        reg = cite_by_db.get(db)
        id_cell = reg.id if reg else (", ".join(g["ids"]) or "—")
        if reg:
            evidence_cell = evidence_label(reg.evidence_level, lang=lang)
        else:
            evidence_cell = ", ".join(g["levels"]) or "—"
        # Catalog description + fixed database/tool PMID only
        note = _source_notes(g["tool_results"][0])
        db_cell = _database_link(db, g["cite_url"] or (reg.url if reg else None))
        lines.append(
            f"| {id_cell} | {db_cell} | {evidence_cell} | {g['records']} | {note} |"
        )

    if len(lines) <= 2:
        lines.append("| — | — | — | 0 | No positive evidence retrieved |")
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
