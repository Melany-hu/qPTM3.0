"""PTMPhaSe tools — PTM regulation of liquid–liquid phase separation (local).

Stage 3 (phase_separation) tools:
  - ptmphase_llps — curated experimental PTM→LLPS evidence
  - ptmphase_phosllps — PhosLLPS predicted functional phosphorylation sites

Data: data/phase_separation/ptmphase/
Homepage: https://ptmphase.sjtu.edu.cn
PMID: 41360972  DOI: 10.1038/s42004-025-01773-y
"""

from __future__ import annotations

import logging
from typing import Any

from app.sources.catalog import get_catalog
from app.sources.query import index_exists, query_records
from app.tools.registry import registry

logger = logging.getLogger(__name__)

_EXP_FIELDS = (
    "gene", "uniprot", "ptm", "site", "aa", "effect", "enzymes",
    "llps_regions", "llps_partners", "mlos", "methods", "diseases",
    "organism", "pmid", "sequence_window",
)
_PRED_FIELDS = (
    "uniprot", "gene", "protein", "site", "residue", "pred", "prob", "length",
)


def _pick(row: dict[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    return {k: row.get(k) for k in fields if row.get(k) not in (None, "")}


def _ptmphase_llps(
    gene: str | None = None,
    uniprot_ac: str | None = None,
    site_position: int | None = None,
    ptm_type: str | None = None,
    effect: str | None = None,
    limit: int = 40,
) -> dict[str, Any]:
    """Query curated experimental PTM–LLPS associations from PTMPhaSe."""
    if not gene and not uniprot_ac:
        return {
            "error": "Provide gene or uniprot_ac",
            "summary": "Missing gene/uniprot for PTMPhaSe experimental query",
        }
    if not index_exists("ptmphase", "experimental"):
        return {
            "error": "PTMPhaSe experimental index missing. Run: python -m app.sources.build_index ptmphase",
            "summary": "PTMPhaSe experimental index not built",
        }

    equals_ci: dict[str, str] = {}
    equals: dict[str, str] = {}
    if uniprot_ac:
        equals_ci["uniprot"] = uniprot_ac
    elif gene:
        equals_ci["gene"] = gene
    if site_position is not None:
        equals["site"] = str(site_position)
    if ptm_type and ptm_type.lower() not in ("all", ""):
        equals_ci["ptm"] = ptm_type
    if effect and effect.lower() not in ("all", ""):
        equals_ci["effect"] = effect

    rows = query_records(
        "ptmphase",
        "experimental",
        equals=equals or None,
        equals_ci=equals_ci or None,
        limit=min(limit, 80),
    )
    keys = []
    if gene:
        keys.append(f"gene={gene}")
    if uniprot_ac:
        keys.append(f"uniprot={uniprot_ac}")
    if site_position is not None:
        keys.append(f"site={site_position}")
    promo = sum(1 for r in rows if "promo" in (r.get("effect") or "").lower())
    inhib = sum(1 for r in rows if "inhib" in (r.get("effect") or "").lower())
    summary = (
        f"PTMPhaSe experimental: {len(rows)} PTM–LLPS association(s) for "
        f"{', '.join(keys)} (promotion≈{promo}, inhibition≈{inhib})."
    )
    if not rows:
        summary += " No curated experimental hits."

    manifest = get_catalog().get("ptmphase")
    return {
        "summary": summary,
        "gene": gene,
        "uniprot_ac": uniprot_ac,
        "site_position": site_position,
        "total": len(rows),
        "associations": [_pick(r, _EXP_FIELDS) for r in rows],
        "source": "PTMPhaSe",
        "evidence": "experimental",
        "access": "local",
        "homepage": manifest.homepage if manifest else "https://ptmphase.sjtu.edu.cn",
        "pmid": manifest.pmid if manifest else "41360972",
        "doi": manifest.doi if manifest else "10.1038/s42004-025-01773-y",
    }


def _ptmphase_phosllps(
    gene: str | None = None,
    uniprot_ac: str | None = None,
    site_position: int | None = None,
    min_prob: float = 0.5,
    only_func: bool = True,
    limit: int = 40,
) -> dict[str, Any]:
    """Query PhosLLPS predicted functional phosphorylation sites regulating LLPS."""
    if not gene and not uniprot_ac:
        return {
            "error": "Provide gene or uniprot_ac",
            "summary": "Missing gene/uniprot for PhosLLPS prediction query",
        }
    if not index_exists("ptmphase", "predictions"):
        return {
            "error": "PTMPhaSe predictions index missing. Run: python -m app.sources.build_index ptmphase",
            "summary": "PhosLLPS predictions index not built",
        }

    equals_ci: dict[str, str] = {}
    equals: dict[str, str] = {}
    if uniprot_ac:
        equals_ci["uniprot"] = uniprot_ac
    elif gene:
        equals_ci["gene"] = gene
    if site_position is not None:
        equals["site"] = str(site_position)
    if only_func:
        equals_ci["pred"] = "func"

    fetch = min(max(limit * 3, limit), 200)
    rows = query_records(
        "ptmphase",
        "predictions",
        equals=equals or None,
        equals_ci=equals_ci or None,
        limit=fetch,
    )

    filtered: list[dict[str, Any]] = []
    for r in rows:
        try:
            prob = float(r.get("prob") or 0)
        except ValueError:
            prob = 0.0
        if prob < min_prob:
            continue
        item = _pick(r, _PRED_FIELDS)
        item["prob"] = prob
        filtered.append(item)
    filtered.sort(key=lambda x: float(x.get("prob") or 0), reverse=True)
    filtered = filtered[: min(limit, 80)]

    keys = []
    if gene:
        keys.append(f"gene={gene}")
    if uniprot_ac:
        keys.append(f"uniprot={uniprot_ac}")
    if site_position is not None:
        keys.append(f"site={site_position}")
    summary = (
        f"PhosLLPS predictions: {len(filtered)} site(s) for {', '.join(keys)} "
        f"(min_prob={min_prob}, only_func={only_func})."
    )
    if not filtered:
        summary += " No predicted functional sites above threshold."

    manifest = get_catalog().get("ptmphase")
    return {
        "summary": summary,
        "gene": gene,
        "uniprot_ac": uniprot_ac,
        "site_position": site_position,
        "min_prob": min_prob,
        "total": len(filtered),
        "predictions": filtered,
        "source": "PTMPhaSe/PhosLLPS",
        "evidence": "predicted",
        "access": "local",
        "homepage": (manifest.api_docs if manifest else None)
        or "https://ptmphase.sjtu.edu.cn/Predictor",
        "pmid": manifest.pmid if manifest else "41360972",
        "doi": manifest.doi if manifest else "10.1038/s42004-025-01773-y",
    }


def register_ptmphase_tools() -> None:
    registry.register(
        name="ptmphase_llps",
        description=(
            "Query PTMPhaSe curated experimental evidence that a PTM promotes or "
            "inhibits liquid–liquid phase separation (LLPS). Returns site, effect, "
            "partners, MLOs, methods, diseases, and PMIDs."
        ),
        parameters={
            "type": "object",
            "properties": {
                "gene": {"type": "string", "description": "Gene symbol"},
                "uniprot_ac": {"type": "string", "description": "UniProt accession"},
                "site_position": {
                    "type": "integer",
                    "description": "Residue position of the PTM site",
                },
                "ptm_type": {
                    "type": "string",
                    "description": "PTM type filter (e.g. Phosphorylation)",
                },
                "effect": {
                    "type": "string",
                    "enum": ["promotion", "inhibition", "all"],
                    "description": "LLPS effect filter",
                },
            },
            "required": [],
        },
        handler=_ptmphase_llps,
    )

    registry.register(
        name="ptmphase_phosllps",
        description=(
            "Query PhosLLPS (PTMPhaSe) predicted functional phosphorylation sites "
            "that regulate LLPS (human proteome-scale; AUC≈0.91). Prefer after "
            "checking curated experimental evidence with ptmphase_llps."
        ),
        parameters={
            "type": "object",
            "properties": {
                "gene": {"type": "string", "description": "Gene symbol"},
                "uniprot_ac": {"type": "string", "description": "UniProt accession"},
                "site_position": {
                    "type": "integer",
                    "description": "Residue position filter",
                },
                "min_prob": {
                    "type": "number",
                    "description": "Minimum prediction probability (default 0.5)",
                },
                "only_func": {
                    "type": "boolean",
                    "description": "Only rows labeled pred=func (default true)",
                },
            },
            "required": [],
        },
        handler=_ptmphase_phosllps,
    )
