"""Extract literature clues from database tool results."""

from __future__ import annotations

import re
from typing import Any

from app.models.schemas import ToolResult
from app.orchestrator.schemas import LiteratureClue
from app.tools.metadata import tool_database

_PMID_KEYS = frozenset({"pmid", "pmids", "experimental_pmids"})
_ROW_CONTEXT_KEYS = (
    "kinase", "enzyme", "site", "position", "condition", "residue",
    "gene", "substrate", "summary",
)


def _row_context(row: dict[str, Any], gene: str | None, site: str | None) -> str:
    parts: list[str] = []
    for k in _ROW_CONTEXT_KEYS:
        v = row.get(k)
        if v and str(v).strip():
            parts.append(f"{k}={v}")
    if not parts:
        parts.append(str(row.get("summary") or "database hit"))
    ctx = "; ".join(str(p) for p in parts[:4])[:200]
    g = gene or row.get("gene") or row.get("substrate")
    s = site or row.get("site") or row.get("position")
    if g:
        ctx = f"{g} {s or ''} — {ctx}".strip()
    return ctx[:220]


def _evidence_level(row: dict[str, Any], tool: str) -> str:
    el = str(row.get("evidence_level") or row.get("evidence") or "").lower()
    if "predict" in el:
        return "predicted"
    if "experiment" in el or "curated" in el:
        return "experimental"
    if "gps" in tool.lower():
        return "predicted"
    return "experimental"


def extract_clues_from_result(
    enriched: ToolResult,
    *,
    gene: str | None = None,
    site: str | None = None,
) -> list[LiteratureClue]:
    if not enriched.success:
        return []
    tool = enriched.tool or ""
    db = enriched.database or tool_database(tool) or tool
    clues: list[LiteratureClue] = []
    seen: set[str] = set()

    def _emit(pmid: str, context: str, row: dict[str, Any] | None = None) -> None:
        p = str(pmid).strip()
        if not p.isdigit() or p in seen:
            return
        seen.add(p)
        row = row or {}
        clues.append(LiteratureClue(
            pmid=p,
            source_tool=tool,
            source_db=str(db),
            context=context[:220] or f"Hit from {db}",
            gene=gene or (str(row.get("gene") or row.get("substrate") or "") or None),
            site=site or (str(row.get("site") or row.get("position") or "") or None),
            evidence_level=_evidence_level(row, tool),
        ))

    def _walk(obj: Any, row_ctx: dict[str, Any] | None = None, depth: int = 0) -> None:
        if depth > 10:
            return
        if isinstance(obj, dict):
            local_row = row_ctx or obj
            for k, v in obj.items():
                if k in _PMID_KEYS and v:
                    ctx = _row_context(local_row, gene, site)
                    if isinstance(v, list):
                        for item in v:
                            _emit(str(item), ctx, local_row)
                    else:
                        _emit(str(v), ctx, local_row)
                elif isinstance(v, (dict, list)):
                    child_row = obj if any(x in obj for x in ("kinase", "site", "gene")) else row_ctx
                    _walk(v, child_row, depth + 1)
        elif isinstance(obj, list):
            for item in obj[:50]:
                if isinstance(item, dict):
                    _walk(item, item, depth + 1)
                else:
                    _walk(item, row_ctx, depth + 1)
        elif isinstance(obj, str):
            for m in re.findall(r"\b(\d{7,8})\b", obj):
                _emit(m, _row_context(row_ctx or {}, gene, site), row_ctx)

    data = enriched.data or {}
    if isinstance(data, dict):
        for key in ("results", "kinases", "papers", "hits", "records", "data"):
            if key in data and isinstance(data[key], list):
                for row in data[key][:40]:
                    if isinstance(row, dict):
                        _walk(row, row, 0)
        _walk(data, None, 0)
    return clues
