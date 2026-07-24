"""Funcscore tools — functional priority scores for human phosphosites.

Stage 3 (regulation) tool:
  - funcscore_phosphosite — look up Ochoa et al. functional scores

Data: data/regulation/Funcscore/
PMID: 31819260  DOI: 10.1038/s41587-019-0344-3
Paper: The functional landscape of the human phosphoproteome (Nat Biotechnol)
"""

from __future__ import annotations

import logging
import sqlite3
from typing import Any

from app.sources.build_index import index_path_for
from app.sources.catalog import get_catalog
from app.sources.query import index_exists
from app.tools.registry import registry

logger = logging.getLogger(__name__)


def _meta() -> dict[str, str]:
    m = get_catalog().get("funcscore")
    return {
        "homepage": m.homepage if m else "https://www.nature.com/articles/s41587-019-0344-3",
        "pmid": m.pmid if m else "31819260",
        "doi": m.doi if m else "10.1038/s41587-019-0344-3",
    }


def _score_float(row: dict[str, Any]) -> float:
    try:
        return float(row.get("functional_score") or 0)
    except (TypeError, ValueError):
        return 0.0


def _query_scores(
    uniprot_ac: str,
    *,
    site_position: int | None = None,
    min_score: float = 0.0,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Query Funcscore index ordered by functional_score descending."""
    manifest = get_catalog().require("funcscore")
    meta = manifest.file_by_id("functional_score")
    if meta is None:
        raise KeyError("functional_score file missing from Funcscore manifest")
    path = index_path_for(manifest, meta)
    if not path.exists():
        raise FileNotFoundError(
            "Funcscore index missing. Run: python -m app.sources.build_index funcscore"
        )

    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    try:
        where = ['UPPER("uniprot") = ?']
        params: list[Any] = [uniprot_ac.strip().upper()]
        if site_position is not None:
            where.append('"position" = ?')
            params.append(str(site_position))
        if min_score and min_score > 0:
            where.append('CAST("functional_score" AS REAL) >= ?')
            params.append(float(min_score))
        sql = (
            f'SELECT * FROM records WHERE {" AND ".join(where)} '
            f'ORDER BY CAST("functional_score" AS REAL) DESC LIMIT ?'
        )
        params.append(limit)
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def _funcscore_phosphosite(
    uniprot_ac: str | None = None,
    site_position: int | None = None,
    min_score: float = 0.0,
    top_n: int = 20,
    limit: int = 50,
) -> dict[str, Any]:
    """Query functional scores for human phosphosites (Ochoa et al.)."""
    if not uniprot_ac:
        return {
            "error": "Provide uniprot_ac",
            "summary": "Missing UniProt accession for Funcscore query",
        }
    if not index_exists("funcscore", "functional_score"):
        return {
            "error": "Funcscore index missing. Run: python -m app.sources.build_index funcscore",
            "summary": "Funcscore index not built",
        }

    keep_n = max(1, min(limit, top_n if site_position is None else limit))
    try:
        rows = _query_scores(
            uniprot_ac,
            site_position=site_position,
            min_score=float(min_score or 0.0),
            limit=keep_n,
        )
    except FileNotFoundError as e:
        return {"error": str(e), "summary": str(e)}

    keys = [f"uniprot={uniprot_ac}"]
    if site_position is not None:
        keys.append(f"position={site_position}")
    min_s = float(min_score or 0.0)
    if min_s > 0:
        keys.append(f"min_score={min_s}")

    high = sum(1 for r in rows if _score_float(r) >= 0.5)
    summary = (
        f"Funcscore: {len(rows)} phosphosite(s) for {', '.join(keys)} "
        f"(score≥0.5 in result: {high}). "
        f"Higher score ≈ more likely functionally important (Ochoa et al.)."
    )
    if not rows:
        summary += " No scored phosphosites found."

    sites = [
        {
            "uniprot": r.get("uniprot"),
            "position": r.get("position"),
            "functional_score": round(_score_float(r), 6),
        }
        for r in rows
    ]

    return {
        "summary": summary,
        "uniprot_ac": uniprot_ac,
        "site_position": site_position,
        "min_score": min_s,
        "total": len(sites),
        "sites": sites,
        "source": "Funcscore",
        "access": "local",
        **_meta(),
    }


def register_funcscore_tools() -> None:
    registry.register(
        name="funcscore_phosphosite",
        description=(
            "Query functional priority scores for human phosphosites from Ochoa "
            "et al. (Nat Biotechnol 2020; PMID 31819260). Scores integrate 59 "
            "proteomic/structural/regulatory/evolutionary features (0–1; higher "
            "≈ more likely functional). Requires UniProt accession; optional "
            "site position and min_score filter."
        ),
        parameters={
            "type": "object",
            "properties": {
                "uniprot_ac": {"type": "string"},
                "site_position": {"type": "integer"},
                "min_score": {"type": "number"},
                "top_n": {"type": "integer"},
            },
            "required": ["uniprot_ac"],
        },
        handler=_funcscore_phosphosite,
    )
