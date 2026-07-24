"""WERAM tools — histone acetylation / methylation writers, erasers, readers.

Stage 1 WHO tool:
  weram_regulators — look up whether a protein is a WERAM-classified histone
  PTM writer/eraser/reader (or list by role / modification).

Data: data/enzymes/WERAM/ (Xu et al. NAR 2017, PMID 27789692)
Homepage: http://weram.biocuckoo.org
"""

from __future__ import annotations

import logging
from collections import Counter
from typing import Any

from app.sources.catalog import get_catalog
from app.sources.query import index_exists, query_records
from app.sources.uniprot_id import resolve_identity
from app.tools.registry import registry

logger = logging.getLogger(__name__)

_DEFAULTS = {
    "name": "WERAM",
    "homepage": "http://weram.biocuckoo.org",
    "pmid": "27789692",
    "doi": "10.1093/nar/gkw1011",
}

_ROLE_LABEL = {
    "writer": "writer",
    "eraser": "eraser",
    "reader": "reader",
}


def _meta() -> dict[str, Any]:
    m = get_catalog().get("weram")
    return {
        "source": _DEFAULTS["name"],
        "access": "local",
        "homepage": (m.homepage if m else None) or _DEFAULTS["homepage"],
        "pmid": (m.pmid if m else None) or _DEFAULTS["pmid"],
        "doi": (m.doi if m else None) or _DEFAULTS["doi"],
    }


def _compact_row(row: dict[str, Any]) -> dict[str, Any]:
    out = {
        "weram_id": row.get("weram_id"),
        "gene": row.get("gene"),
        "uniprot": row.get("uniprot"),
        "role": row.get("role"),
        "family": row.get("family"),
        "class": row.get("class"),
        "modification": row.get("modification"),
        "evidence": row.get("evidence"),
        "ensembl_protein": row.get("ensembl_protein"),
    }
    wid = out.get("weram_id")
    if wid:
        out["url"] = f"http://weram.biocuckoo.org/searchResult.php?keyword={wid}"
    return {k: v for k, v in out.items() if v not in (None, "")}


def _summarize(hits: list[dict[str, Any]], keys: list[str]) -> str:
    if not hits:
        return f"WERAM: no histone Ac/Me writer/eraser/reader for {', '.join(keys)}."
    genes = sorted({h.get("gene") or h.get("uniprot") or "?" for h in hits})
    roles = Counter(f"{h.get('role')}/{h.get('modification')}" for h in hits)
    role_txt = ", ".join(f"{k}×{v}" for k, v in roles.most_common())
    examples = []
    for h in hits[:4]:
        g = h.get("gene") or h.get("uniprot") or h.get("weram_id")
        examples.append(
            f"{g} ({h.get('role')} {h.get('family')}/{h.get('class')}, "
            f"{h.get('modification')}, {h.get('evidence')})"
        )
    prefix = f"WERAM: {len(hits)} regulator record(s)"
    if len(genes) == 1:
        prefix += f" for {genes[0]}"
    else:
        prefix += f" across {len(genes)} gene(s)"
    return f"{prefix} [{role_txt}]. Examples: " + "; ".join(examples)


def _weram_regulators(
    gene: str | None = None,
    uniprot_ac: str | None = None,
    role: str | None = None,
    modification: str | None = None,
    family: str | None = None,
    evidence: str = "any",
    limit: int = 40,
) -> dict[str, Any]:
    """Query WERAM histone acetylation/methylation writers, erasers and readers."""
    if not any([gene, uniprot_ac, role, modification, family]):
        return {
            "error": (
                "Provide at least one of: gene, uniprot_ac, role, "
                "modification, family"
            ),
            "summary": "Missing query key for WERAM",
            "found": False,
            **_meta(),
        }

    if not index_exists("weram", "proteins"):
        return {
            "error": "WERAM index missing. Run: python -m app.sources.build_index weram",
            "summary": "WERAM index not built yet",
            "found": False,
            **_meta(),
        }

    identity = None
    resolved_ac = (uniprot_ac or "").strip().upper() or None
    resolved_gene = (gene or "").strip() or None
    if resolved_gene or resolved_ac:
        identity = resolve_identity(uniprot_ac=resolved_ac, gene=resolved_gene)
        if identity:
            resolved_ac = (identity.get("uniprot_ac") or resolved_ac or "").upper() or None
            resolved_gene = identity.get("gene") or resolved_gene

    equals_ci: dict[str, str] = {}
    if resolved_ac:
        equals_ci["uniprot"] = resolved_ac
    elif resolved_gene:
        equals_ci["gene"] = resolved_gene
    if role and role.strip().lower() not in ("any", "all", ""):
        equals_ci["role"] = role.strip().lower()
    if modification and modification.strip().lower() not in ("any", "all", ""):
        equals_ci["modification"] = modification.strip().lower()
    if family and family.strip().lower() not in ("any", "all", ""):
        equals_ci["family"] = family.strip()

    if not equals_ci:
        return {
            "error": "No usable query filters after normalization",
            "summary": "WERAM: empty query",
            "found": False,
            **_meta(),
        }

    try:
        rows = query_records(
            "weram",
            "proteins",
            equals_ci=equals_ci,
            limit=min(max(limit * 3, limit), 200),
        )
    except Exception as e:
        logger.error("WERAM query failed: %s", e, exc_info=True)
        return {
            "error": str(e),
            "summary": f"WERAM query failed: {e}",
            "found": False,
            **_meta(),
        }

    ev = (evidence or "any").strip().lower()
    if ev in ("collected", "predicted"):
        rows = [r for r in rows if str(r.get("evidence") or "").lower() == ev]

    # Prefer exact gene/uniprot matches; if queried by role/mod only, keep as-is
    hits = [_compact_row(r) for r in rows[: min(limit, 80)]]

    keys = []
    if resolved_gene:
        keys.append(f"gene={resolved_gene}")
    if resolved_ac:
        keys.append(f"uniprot={resolved_ac}")
    if role:
        keys.append(f"role={role}")
    if modification:
        keys.append(f"modification={modification}")
    if family:
        keys.append(f"family={family}")
    if ev not in ("any", "all", ""):
        keys.append(f"evidence={ev}")

    summary = _summarize(hits, keys or ["query"])
    roles = sorted({h.get("role") for h in hits if h.get("role")})
    mods = sorted({h.get("modification") for h in hits if h.get("modification")})

    return {
        "summary": summary,
        "found": bool(hits),
        "gene": (identity or {}).get("gene") or resolved_gene,
        "uniprot_ac": resolved_ac,
        "uniprot_identity": identity,
        "role": role,
        "modification": modification,
        "family": family,
        "evidence": evidence,
        "roles_found": roles,
        "modifications_found": mods,
        "total": len(hits),
        "regulators": hits,
        "note": (
            "WERAM classifies histone acetylation/methylation writers (HAT/HMT), "
            "erasers (HDAC/HDM) and readers (Ac_Reader/Me_Reader). "
            "Human subset from biocuckoo WERAM FASTA downloads."
        ),
        **_meta(),
    }


def register_weram_tools() -> None:
    registry.register(
        name="weram_regulators",
        description=(
            "Query WERAM for histone acetylation/methylation writers, erasers "
            "and readers (HAT/HDAC/Ac_Reader/HMT/HDM/Me_Reader). Use in Stage 1 "
            "WHO when asking whether a protein regulates histone Ac/Me, or to "
            "list regulators by role/modification. PMID 27789692."
        ),
        parameters={
            "type": "object",
            "properties": {
                "gene": {"type": "string", "description": "Gene symbol (e.g. HDAC1, EP300)"},
                "uniprot_ac": {"type": "string", "description": "UniProt accession"},
                "role": {
                    "type": "string",
                    "description": "Optional: writer | eraser | reader",
                },
                "modification": {
                    "type": "string",
                    "description": "Optional: acetylation | methylation",
                },
                "family": {
                    "type": "string",
                    "description": "Optional family: HAT, HDAC, Ac_Reader, HMT, HDM, Me_Reader",
                },
                "evidence": {
                    "type": "string",
                    "description": "any | collected | predicted (default any)",
                },
                "limit": {"type": "integer", "description": "Max hits (default 40)"},
            },
            "required": [],
        },
        handler=_weram_regulators,
    )
