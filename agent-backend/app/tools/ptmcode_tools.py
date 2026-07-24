"""PTMcode2 tools — functional associations of PTM pairs (curated multi-species subset).

Stage 4 (WHY / interactions) tool:
  ptmcode_associations — intra-protein and inter-protein PTM–PTM links

Kept organisms: human, mouse, rat, yeast — with manual / structure /
same-residue competition evidence (raw dumps are ~35M rows).

Data: data/interactions/PTMcode2/
Homepage: http://ptmcode.embl.de
PMID: 25361965  DOI: 10.1093/nar/gku1081
"""

from __future__ import annotations

import logging
from typing import Any

from app.sources.catalog import get_catalog
from app.sources.query import index_exists, open_index
from app.tools.registry import registry

logger = logging.getLogger(__name__)

_ORG_ALIASES = {
    "human": "human",
    "homo sapiens": "human",
    "mouse": "mouse",
    "mus musculus": "mouse",
    "rat": "rat",
    "rattus norvegicus": "rat",
    "yeast": "yeast",
    "saccharomyces cerevisiae": "yeast",
}


def _normalize_organism(organism: str | None) -> str | None:
    if not organism or organism.strip().lower() in ("all", ""):
        return None
    return _ORG_ALIASES.get(organism.strip().lower(), organism.strip().lower())


def _meta() -> dict[str, Any]:
    m = get_catalog().get("ptmcode2")
    return {
        "homepage": (m.homepage if m else None) or "http://ptmcode.embl.de",
        "doi": (m.doi if m else None) or "10.1093/nar/gku1081",
        "pmid": (m.pmid if m else None) or "25361965",
        "source": "PTMcode2",
        "note": (
            "Curated subset for human/mouse/rat/yeast with manual, structure-distance, "
            "or same-residue competition evidence (coevolution-only discarded)."
        ),
    }


def _flag(row: dict[str, Any], key: str) -> bool:
    return str(row.get(key) or "0").strip() == "1"


def _evidence_labels(row: dict[str, Any], *, within: bool) -> list[str]:
    labels = []
    if _flag(row, "manual"):
        labels.append("manual")
    if _flag(row, "structure"):
        labels.append("structure")
    if within and _flag(row, "same_residue"):
        labels.append("same_residue_competition")
    if _flag(row, "coevolution"):
        labels.append("coevolution")
    return labels


def _query_within(
    gene: str,
    position: int | None,
    organism: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    if not index_exists("ptmcode2", "within"):
        raise FileNotFoundError(
            "PTMcode2 within index missing. Run: python -m app.sources.build_index ptmcode2"
        )
    manifest = get_catalog().require("ptmcode2")
    meta = manifest.file_by_id("within")
    assert meta is not None
    conn = open_index(manifest, meta)
    if conn is None:
        raise FileNotFoundError("PTMcode2 within index missing")
    try:
        where = ['UPPER("gene") = ?']
        params: list[Any] = [gene.upper()]
        if organism:
            where.append('LOWER("organism") = ?')
            params.append(organism)
        if position is not None:
            where.append('("position1" = ? OR "position2" = ?)')
            params.extend([str(position), str(position)])
        sql = f'SELECT * FROM records WHERE {" AND ".join(where)} LIMIT ?'
        params.append(limit)
        rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()

    out = []
    for r in rows:
        out.append({
            "scope": "within_protein",
            "organism": r.get("organism"),
            "species": r.get("species"),
            "gene": r.get("gene"),
            "site1": f"{r.get('residue1')} ({r.get('ptm1')})",
            "site2": f"{r.get('residue2')} ({r.get('ptm2')})",
            "ptm1": r.get("ptm1"),
            "residue1": r.get("residue1"),
            "position1": r.get("position1"),
            "ptm2": r.get("ptm2"),
            "residue2": r.get("residue2"),
            "position2": r.get("position2"),
            "propagated1": r.get("propagated1"),
            "propagated2": r.get("propagated2"),
            "evidence": _evidence_labels(r, within=True),
        })
    return out


def _query_between(
    gene: str,
    position: int | None,
    partner: str | None,
    organism: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    if not index_exists("ptmcode2", "between"):
        raise FileNotFoundError(
            "PTMcode2 between index missing. Run: python -m app.sources.build_index ptmcode2"
        )
    manifest = get_catalog().require("ptmcode2")
    meta = manifest.file_by_id("between")
    assert meta is not None
    conn = open_index(manifest, meta)
    if conn is None:
        raise FileNotFoundError("PTMcode2 between index missing")
    try:
        gene_u = gene.upper()
        where = ['(UPPER("gene1") = ? OR UPPER("gene2") = ?)']
        params: list[Any] = [gene_u, gene_u]
        if organism:
            where.append('LOWER("organism") = ?')
            params.append(organism)
        if partner:
            pu = partner.upper()
            where.append('(UPPER("gene1") = ? OR UPPER("gene2") = ?)')
            params.extend([pu, pu])
        if position is not None:
            where.append('("position1" = ? OR "position2" = ?)')
            params.extend([str(position), str(position)])
        sql = f'SELECT * FROM records WHERE {" AND ".join(where)} LIMIT ?'
        params.append(limit)
        rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()

    out = []
    for r in rows:
        out.append({
            "scope": "between_proteins",
            "organism": r.get("organism"),
            "species": r.get("species"),
            "gene1": r.get("gene1"),
            "gene2": r.get("gene2"),
            "site1": f"{r.get('gene1')} {r.get('residue1')} ({r.get('ptm1')})",
            "site2": f"{r.get('gene2')} {r.get('residue2')} ({r.get('ptm2')})",
            "ptm1": r.get("ptm1"),
            "residue1": r.get("residue1"),
            "position1": r.get("position1"),
            "ptm2": r.get("ptm2"),
            "residue2": r.get("residue2"),
            "position2": r.get("position2"),
            "propagated1": r.get("propagated1"),
            "propagated2": r.get("propagated2"),
            "evidence": _evidence_labels(r, within=False),
        })
    return out


def _ptmcode_associations(
    gene: str | None = None,
    position: int | None = None,
    partner_gene: str | None = None,
    organism: str | None = "human",
    scope: str = "both",
    limit: int = 40,
) -> dict[str, Any]:
    """Query curated PTMcode2 PTM–PTM functional associations."""
    if not gene:
        return {
            "error": "Provide gene symbol",
            "summary": "Missing gene for PTMcode2",
        }

    sc = (scope or "both").strip().lower()
    if sc not in ("both", "within", "between"):
        return {
            "error": "scope must be both|within|between",
            "summary": f"Invalid PTMcode2 scope '{scope}'",
        }

    org = _normalize_organism(organism)

    within: list[dict[str, Any]] = []
    between: list[dict[str, Any]] = []
    try:
        if sc in ("both", "within"):
            within = _query_within(gene, position, org, limit)
        if sc in ("both", "between"):
            between = _query_between(gene, position, partner_gene, org, limit)
    except FileNotFoundError as e:
        return {"error": str(e), "summary": str(e)}
    except Exception as e:
        logger.error("PTMcode2 query failed: %s", e, exc_info=True)
        return {"error": str(e), "summary": f"PTMcode2 query failed: {e}"}

    keys = [gene]
    if org:
        keys.append(org)
    if position is not None:
        keys.append(f"pos {position}")
    if partner_gene:
        keys.append(f"partner {partner_gene}")
    total = len(within) + len(between)
    examples: list[str] = []
    for r in within[:3]:
        ev = ",".join(r.get("evidence") or []) or "association"
        examples.append(
            f"within {r.get('gene')}: {r.get('site1')} ↔ {r.get('site2')} [{ev}]"
        )
    for r in between[:3]:
        ev = ",".join(r.get("evidence") or []) or "association"
        examples.append(
            f"between {r.get('gene1')} {r.get('site1')} ↔ "
            f"{r.get('gene2')} {r.get('site2')} [{ev}]"
        )

    summary = (
        f"PTMcode2: {len(within)} within-protein + {len(between)} between-protein "
        f"association(s) for {', '.join(keys)}."
    )
    if examples:
        summary += " Examples: " + " ".join(examples)

    return {
        "summary": summary,
        "total": total,
        "within_total": len(within),
        "between_total": len(between),
        "organism_filter": org,
        "within": within,
        "between": between,
        **_meta(),
    }


def register_ptmcode_tools() -> None:
    registry.register(
        name="ptmcode_associations",
        description=(
            "Query PTMcode v2 for functional associations between PTM sites: "
            "within the same protein (competition / structure / manual) or between "
            "interacting proteins. Curated subset for human, mouse, rat, and yeast. "
            "Use for Stage 4 WHY when asking how a site functionally couples to "
            "other PTMs or PPIs."
        ),
        parameters={
            "type": "object",
            "properties": {
                "gene": {"type": "string", "description": "Gene symbol (required)"},
                "position": {
                    "type": "integer",
                    "description": "Optional residue position to focus associations",
                },
                "partner_gene": {
                    "type": "string",
                    "description": "Optional PPI partner gene (between-protein filter)",
                },
                "organism": {
                    "type": "string",
                    "enum": ["human", "mouse", "rat", "yeast", "all"],
                    "description": "Organism filter (default human; use all for any)",
                },
                "scope": {
                    "type": "string",
                    "enum": ["both", "within", "between"],
                    "description": "within protein / between proteins / both (default)",
                },
                "limit": {"type": "integer", "description": "Max hits per table (default 40)"},
            },
            "required": ["gene"],
        },
        handler=_ptmcode_associations,
    )
