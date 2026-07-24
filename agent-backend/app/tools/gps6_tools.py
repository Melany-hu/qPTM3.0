"""GPS 6.0 tools — predicted kinase-specific phosphorylation sites.

Stage 1 WHO tool:
  gps6_kinases — GPS 6.0 predicted kinases for human S/T/Y sites
                 (or substrates predicted for a kinase)

Data: data/enzymes/GPS6.0/ (Chen et al. NAR 2023, PMID 37158278)
Homepage: https://gps.biocuckoo.cn
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
    "name": "GPS 6.0",
    "homepage": "https://gps.biocuckoo.cn",
    "pmid": "37158278",
    "doi": "10.1093/nar/gkad383",
}


def _meta() -> dict[str, Any]:
    m = get_catalog().get("gps6")
    return {
        "source": _DEFAULTS["name"],
        "access": "local",
        "homepage": (m.homepage if m else None) or _DEFAULTS["homepage"],
        "pmid": (m.pmid if m else None) or _DEFAULTS["pmid"],
        "doi": (m.doi if m else None) or _DEFAULTS["doi"],
    }


def _score_float(val: Any) -> float | None:
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _compact(row: dict[str, Any]) -> dict[str, Any]:
    sc = _score_float(row.get("score"))
    pos = row.get("position")
    residue = (row.get("residue") or "").upper()
    out = {
        "gene": row.get("gene"),
        "uniprot": row.get("uniprot"),
        "position": int(pos) if str(pos or "").isdigit() else pos,
        "residue": residue or None,
        "site": f"{residue}{pos}" if residue and pos else None,
        "kinase_gene": row.get("kinase_gene"),
        "kinase_group": row.get("kinase_group"),
        "kinase_family": row.get("kinase_family"),
        "kinase_hierarchy": row.get("kinase_hierarchy"),
        "score": f"{sc:.4g}" if sc is not None else None,
        "evidence": "predicted",
    }
    return {k: v for k, v in out.items() if v not in (None, "")}


def _summarize(hits: list[dict[str, Any]], keys: list[str]) -> str:
    if not hits:
        return f"GPS 6.0: no predicted kinase–site hits for {', '.join(keys)}."
    kinases = sorted({h.get("kinase_gene") or "?" for h in hits})
    sites = sorted({
        h.get("site") or f"{h.get('residue') or ''}{h.get('position') or ''}"
        for h in hits
    })
    groups = Counter(h.get("kinase_group") or "?" for h in hits)
    examples = []
    for h in hits[:4]:
        examples.append(
            f"{h.get('kinase_gene')} → {h.get('gene') or h.get('uniprot')} "
            f"{h.get('site')} (score={h.get('score')}, "
            f"{h.get('kinase_group')}/{h.get('kinase_family') or '-'})"
        )
    return (
        f"GPS 6.0: {len(hits)} predicted kinase–site hit(s) for {', '.join(keys)} "
        f"({len(kinases)} kinase(s), {len(sites)} site(s); "
        f"groups: {', '.join(f'{k}×{v}' for k, v in groups.most_common(5))}). "
        f"Examples: " + "; ".join(examples)
    )


def _gps6_kinases(
    gene: str | None = None,
    uniprot_ac: str | None = None,
    position: int | None = None,
    kinase: str | None = None,
    kinase_group: str | None = None,
    min_score: float = 1.0,
    limit: int = 40,
) -> dict[str, Any]:
    """Query GPS 6.0 predicted kinase-specific phosphorylation sites."""
    if not any([gene, uniprot_ac, kinase]):
        return {
            "error": "Provide substrate gene/uniprot_ac and/or kinase",
            "summary": "Missing query key for GPS 6.0",
            "found": False,
            **_meta(),
        }

    if not index_exists("gps6", "predictions"):
        return {
            "error": "GPS 6.0 index missing. Run: python -m app.sources.build_index gps6",
            "summary": "GPS 6.0 index not built yet",
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
    equals: dict[str, str] = {}

    if resolved_ac:
        equals_ci["uniprot_base"] = resolved_ac.split("-")[0]
    elif resolved_gene:
        equals_ci["gene"] = resolved_gene

    if kinase and kinase.strip().lower() not in ("any", "all", ""):
        equals_ci["kinase_gene"] = kinase.strip()
    if kinase_group and kinase_group.strip().lower() not in ("any", "all", ""):
        equals_ci["kinase_group"] = kinase_group.strip()
    if position is not None:
        equals["position"] = str(int(position))

    if not equals_ci and not equals:
        return {
            "error": "No usable filters after identity resolution",
            "summary": "GPS 6.0: empty query",
            "found": False,
            **_meta(),
        }

    fetch = min(max(limit * 5, 80), 400)
    try:
        rows = query_records(
            "gps6",
            "predictions",
            equals=equals or None,
            equals_ci=equals_ci or None,
            limit=fetch,
        )
    except Exception as e:
        logger.error("GPS 6.0 query failed: %s", e, exc_info=True)
        return {
            "error": str(e),
            "summary": f"GPS 6.0 query failed: {e}",
            "found": False,
            **_meta(),
        }

    # Prefer exact UniProt isoform if provided
    if resolved_ac and "-" in resolved_ac:
        exact = [r for r in rows if (r.get("uniprot") or "").upper() == resolved_ac]
        if exact:
            rows = exact

    scored: list[tuple[float, dict[str, Any]]] = []
    for r in rows:
        sc = _score_float(r.get("score"))
        if sc is None:
            continue
        if sc < float(min_score or 0):
            continue
        scored.append((sc, r))
    scored.sort(key=lambda x: -x[0])
    hits = [_compact(r) for _, r in scored[: min(limit, 80)]]

    keys = []
    if resolved_gene:
        keys.append(f"gene={resolved_gene}")
    if resolved_ac:
        keys.append(f"uniprot={resolved_ac}")
    if position is not None:
        aa = hits[0].get("residue") if hits else ""
        keys.append(f"{aa or ''}{position}")
    if kinase:
        keys.append(f"kinase={kinase}")
    if kinase_group:
        keys.append(f"group={kinase_group}")
    if min_score:
        keys.append(f"min_score>={min_score}")

    return {
        "summary": _summarize(hits, keys or ["query"]),
        "found": bool(hits),
        "gene": resolved_gene,
        "uniprot_ac": resolved_ac,
        "uniprot_identity": identity,
        "position": position,
        "kinase": kinase,
        "kinase_group": kinase_group,
        "min_score": min_score,
        "kinases_found": sorted({h.get("kinase_gene") for h in hits if h.get("kinase_gene")}),
        "sites_found": sorted({h.get("site") for h in hits if h.get("site")}),
        "total": len(hits),
        "predictions": hits,
        "note": (
            "GPS 6.0 computational predictions of kinase-specific phosphorylation "
            "sites (not experimental). Higher score = stronger predicted support. "
            "Complement with PhosphoSitePlus / qPTM / iPTMnet for curated evidence."
        ),
        **_meta(),
    }


def register_gps6_tools() -> None:
    registry.register(
        name="gps6_kinases",
        description=(
            "Query GPS 6.0 predicted kinase-specific phosphorylation sites for "
            "human proteins (or substrates predicted for a kinase). Returns "
            "kinase gene/hierarchy and GPS score. Use in Stage 1 WHO as "
            "complementary predicted evidence. PMID 37158278."
        ),
        parameters={
            "type": "object",
            "properties": {
                "gene": {"type": "string", "description": "Substrate gene symbol"},
                "uniprot_ac": {"type": "string", "description": "Substrate UniProt accession"},
                "position": {"type": "integer", "description": "Site position (e.g. 15)"},
                "kinase": {"type": "string", "description": "Kinase gene symbol filter (e.g. AKT1)"},
                "kinase_group": {
                    "type": "string",
                    "description": "Optional kinase group (AGC, CAMK, CMGC, TK, STE, TKL, CK1, Other, Atypical, Dual, …)",
                },
                "min_score": {
                    "type": "number",
                    "description": "Minimum GPS score (default 1.0)",
                },
                "limit": {"type": "integer", "description": "Max hits (default 40)"},
            },
            "required": [],
        },
        handler=_gps6_kinases,
    )
