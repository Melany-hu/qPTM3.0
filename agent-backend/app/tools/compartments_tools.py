"""COMPARTMENTS tools — protein subcellular localization evidence (local).

Stage 3 (localization) tool:
  compartments_localization — GO cellular-component localizations with confidence

Data: data/localization/COMPARTMENTS/
PMID: 24573882  DOI: 10.1093/database/bau012
Homepage: https://compartments.jensenlab.org/
"""

from __future__ import annotations

import logging
import sqlite3
from typing import Any

from app.sources.build_index import index_path_for
from app.sources.catalog import get_catalog
from app.sources.query import index_exists
from app.sources.uniprot_id import resolve_identity
from app.tools.registry import registry

logger = logging.getLogger(__name__)

# Very generic GO roots that dominate every protein — demote unless asked
_GENERIC_GO = {
    "GO:0005575",  # cellular_component
    "GO:0110165",  # cellular anatomical entity
    "GO:0005622",  # intracellular anatomical structure
    "GO:0043226",  # organelle
    "GO:0043229",  # intracellular organelle
    "GO:0043227",  # membrane-bounded organelle
    "GO:0043231",  # intracellular membrane-bounded organelle
    "GO:0043228",  # non-membrane-bounded organelle
    "GO:0043232",  # intracellular non-membrane-bounded organelle
    "GO:0032991",  # protein-containing complex
    "GO:0005623",  # cell
    "GO:0044464",  # cell part
}

_GENERIC_NAME = {
    "cellular_component",
    "cellular anatomical entity",
    "intracellular anatomical structure",
    "organelle",
    "intracellular organelle",
    "membrane-bounded organelle",
    "intracellular membrane-bounded organelle",
    "non-membrane-bounded organelle",
    "intracellular non-membrane-bounded organelle",
    "protein-containing complex",
}


def _meta() -> dict[str, str]:
    m = get_catalog().get("compartments")
    return {
        "homepage": m.homepage if m else "https://compartments.jensenlab.org/",
        "pmid": m.pmid if m else "24573882",
        "doi": m.doi if m else "10.1093/database/bau012",
    }


def _conf(row: dict[str, Any]) -> float:
    try:
        return float(row.get("confidence") or 0)
    except (TypeError, ValueError):
        return 0.0


def _is_generic(row: dict[str, Any]) -> bool:
    go = (row.get("go") or "").strip().upper()
    name = (row.get("localization") or "").strip().lower()
    return go in _GENERIC_GO or name in _GENERIC_NAME


def _query_localizations(
    *,
    uniprot_ac: str | None,
    gene: str | None,
    localization: str | None,
    min_confidence: float,
    limit: int,
) -> list[dict[str, Any]]:
    manifest = get_catalog().require("compartments")
    meta = manifest.file_by_id("localizations")
    if meta is None:
        raise KeyError("localizations file missing from COMPARTMENTS manifest")
    path = index_path_for(manifest, meta)
    if not path.exists():
        raise FileNotFoundError(
            "COMPARTMENTS index missing. Run: python -m app.sources.build_index compartments"
        )

    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    try:
        where: list[str] = []
        params: list[Any] = []
        if uniprot_ac:
            where.append('UPPER("uniprot") = ?')
            params.append(uniprot_ac.strip().upper())
        elif gene:
            where.append('UPPER("gene") = ?')
            params.append(gene.strip().upper())
        else:
            return []

        if localization:
            where.append('UPPER("localization") LIKE ?')
            params.append(f"%{localization.strip().upper()}%")

        if min_confidence and min_confidence > 0:
            where.append('CAST("confidence" AS REAL) >= ?')
            params.append(float(min_confidence))

        # Over-fetch then rank / demote generics in Python
        fetch_n = max(limit * 8, 200)
        sql = (
            f'SELECT * FROM records WHERE {" AND ".join(where)} '
            f'ORDER BY CAST("confidence" AS REAL) DESC LIMIT ?'
        )
        params.append(fetch_n)
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def _compartments_localization(
    gene: str | None = None,
    uniprot_ac: str | None = None,
    localization: str | None = None,
    min_confidence: float = 3.0,
    include_generic: bool = False,
    limit: int = 25,
) -> dict[str, Any]:
    """Query COMPARTMENTS subcellular localization evidence."""
    if not gene and not uniprot_ac:
        return {
            "error": "Provide gene or uniprot_ac",
            "summary": "Missing key for COMPARTMENTS query",
        }
    if not index_exists("compartments", "localizations"):
        return {
            "error": "COMPARTMENTS index missing. Run: python -m app.sources.build_index compartments",
            "summary": "COMPARTMENTS index not built",
        }

    identity = None
    try:
        identity = resolve_identity(uniprot_ac=uniprot_ac, gene=gene)
    except Exception as e:
        logger.warning("UniProt identity lookup failed: %s", e)

    canon_ac = (identity or {}).get("uniprot_ac") or uniprot_ac
    canon_gene = (identity or {}).get("gene") or gene

    try:
        rows = _query_localizations(
            uniprot_ac=canon_ac,
            gene=None if canon_ac else canon_gene,
            localization=localization,
            min_confidence=float(min_confidence or 0),
            limit=limit,
        )
        # Fallback: if UniProt AC not in table, try original gene symbol in file
        if not rows and canon_gene and canon_ac:
            rows = _query_localizations(
                uniprot_ac=None,
                gene=canon_gene,
                localization=localization,
                min_confidence=float(min_confidence or 0),
                limit=limit,
            )
    except FileNotFoundError as e:
        return {"error": str(e), "summary": str(e), **_meta()}

    if not include_generic:
        specific = [r for r in rows if not _is_generic(r)]
        # If filtering wiped everything, keep high-confidence generics
        rows = specific if specific else rows

    rows = sorted(rows, key=_conf, reverse=True)[: max(1, min(limit, 80))]

    keys = []
    if canon_gene:
        keys.append(f"gene={canon_gene}")
    if canon_ac:
        keys.append(f"uniprot={canon_ac}")
    if localization:
        keys.append(f"localization~{localization}")
    keys.append(f"min_confidence={min_confidence}")

    summary = (
        f"COMPARTMENTS: {len(rows)} localization(s) for {', '.join(keys)} "
        f"(confidence scale ~0–5; higher = stronger evidence)."
    )
    if not rows:
        summary += " No matching localization evidence."

    locs = [
        {
            "uniprot": r.get("uniprot"),
            "gene": canon_gene or r.get("gene"),
            "go": r.get("go"),
            "localization": r.get("localization"),
            "confidence": round(_conf(r), 3),
            "ensp": r.get("ensp"),
        }
        for r in rows
    ]

    return {
        "summary": summary,
        "gene": canon_gene,
        "uniprot_ac": canon_ac,
        "protein_name": (identity or {}).get("protein_name"),
        "localization_filter": localization,
        "min_confidence": float(min_confidence or 0),
        "include_generic": include_generic,
        "total": len(locs),
        "localizations": locs,
        "uniprot_identity": identity,
        "source": "COMPARTMENTS",
        "access": "local",
        **_meta(),
    }


def register_compartments_tools() -> None:
    registry.register(
        name="compartments_localization",
        description=(
            "Query COMPARTMENTS for protein subcellular localization evidence "
            "(PMID 24573882). Returns GO cellular-component terms with confidence "
            "scores (0–5). Useful for PTM context: where a modified protein resides. "
            "Default min_confidence=3; generic root GO terms are demoted."
        ),
        parameters={
            "type": "object",
            "properties": {
                "gene": {"type": "string"},
                "uniprot_ac": {"type": "string"},
                "localization": {
                    "type": "string",
                    "description": "Optional substring filter (e.g. Nucleus, Mitochondrion)",
                },
                "min_confidence": {
                    "type": "number",
                    "description": "Minimum confidence score (default 3.0)",
                },
                "include_generic": {
                    "type": "boolean",
                    "description": "Include generic GO roots (default false)",
                },
            },
            "required": [],
        },
        handler=_compartments_localization,
    )
