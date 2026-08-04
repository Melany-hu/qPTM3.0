"""SignalP tools — secretory signal peptide predictions (local).

Stage 3 (localization) tool:
  signalp_prediction — SignalP 6.0 Sec/SPI prediction + cleavage site

Data: data/localization/SignalP/
PMID: 35132240  DOI: 10.1038/s41587-021-01156-3
"""

from __future__ import annotations

import logging
from typing import Any

from app.sources.catalog import get_catalog
from app.sources.query import index_exists, query_records
from app.sources.uniprot_id import resolve_identity
from app.tools.registry import registry

logger = logging.getLogger(__name__)

_DEFAULTS = {
    "homepage": "https://services.healthtech.dtu.dk/services/SignalP-6.0/",
    "pmid": "35132240",
    "doi": "10.1038/s41587-021-01156-3",
}


def _meta() -> dict[str, str]:
    m = get_catalog().get("signalp")
    return {
        "source": "SignalP",
        "homepage": (m.homepage if m else None) or _DEFAULTS["homepage"],
        "pmid": (m.pmid if m else None) or _DEFAULTS["pmid"],
        "doi": (m.doi if m else None) or _DEFAULTS["doi"],
    }


def _int_or_none(value: Any) -> int | None:
    text = str(value or "").strip()
    return int(text) if text.isdigit() else None


def _float_or_none(value: Any) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _site_context(row: dict[str, Any], site_position: int | None) -> dict[str, Any]:
    if site_position is None:
        return {}
    prediction = (row.get("prediction") or "").strip().upper()
    cs_start = _int_or_none(row.get("cleavage_start"))
    cs_end = _int_or_none(row.get("cleavage_end"))
    ctx: dict[str, Any] = {"site_position": site_position}
    if prediction != "SP" or cs_start is None:
        ctx["site_in_signal_peptide"] = False
        ctx["site_near_cleavage_site"] = False
        return ctx
    # Signal peptide spans N-terminus through the residue before cleavage.
    ctx["signal_peptide_region"] = f"1-{cs_start}"
    ctx["site_in_signal_peptide"] = 1 <= site_position <= cs_start
    ctx["site_near_cleavage_site"] = (
        (cs_start - 2 <= site_position <= cs_start + 2)
        or (cs_end is not None and cs_end - 2 <= site_position <= cs_end + 2)
    )
    return ctx


def _compact(row: dict[str, Any], *, site_position: int | None = None) -> dict[str, Any]:
    cs_start = _int_or_none(row.get("cleavage_start"))
    cs_end = _int_or_none(row.get("cleavage_end"))
    out: dict[str, Any] = {
        "uniprot": row.get("uniprot"),
        "prediction": row.get("prediction"),
        "other_score": _float_or_none(row.get("other_score")),
        "sp_score": _float_or_none(row.get("sp_score")),
        "cleavage_start": cs_start,
        "cleavage_end": cs_end,
        "cleavage_probability": _float_or_none(row.get("cleavage_probability")),
        "cs_position": row.get("cs_position") or None,
        "evidence": "predicted",
    }
    if cs_start is not None:
        out["signal_peptide_region"] = f"1-{cs_start}"
    out.update(_site_context(row, site_position))
    return {k: v for k, v in out.items() if v is not None}


def _signalp_prediction(
    gene: str | None = None,
    uniprot_ac: str | None = None,
    site_position: int | None = None,
    sp_only: bool = False,
) -> dict[str, Any]:
    """Query SignalP 6.0 signal-peptide predictions for a protein."""
    if not gene and not uniprot_ac:
        return {
            "error": "Provide gene or uniprot_ac",
            "summary": "Missing gene/uniprot for SignalP query",
        }
    if not index_exists("signalp", "predictions"):
        return {
            "error": "SignalP index missing. Run: python -m app.sources.prepare_signalp "
                     "&& python -m app.sources.build_index signalp",
            "summary": "SignalP index not built",
        }

    identity = resolve_identity(gene=gene, uniprot_ac=uniprot_ac)
    ac = (identity or {}).get("uniprot_ac") or (uniprot_ac or "").strip().upper()
    gene_resolved = (identity or {}).get("gene") or gene

    equals_ci: dict[str, str] = {}
    if ac:
        equals_ci["uniprot"] = ac
    elif gene_resolved:
        return {
            "error": "Gene-only lookup requires UniProt resolution",
            "summary": f"Could not resolve UniProt for gene {gene_resolved}",
        }

    if sp_only:
        equals_ci["prediction"] = "SP"

    try:
        rows = query_records(
            "signalp", "predictions",
            equals_ci=equals_ci or None,
            limit=5,
        )
    except FileNotFoundError as exc:
        return {"error": str(exc), "summary": str(exc)}

    if not rows:
        return {
            "summary": f"SignalP: no prediction for {gene_resolved or ac}",
            "gene": gene_resolved,
            "uniprot_ac": ac,
            "total": 0,
            "predictions": [],
            **_meta(),
        }

    predictions = [_compact(r, site_position=site_position) for r in rows]
    primary = predictions[0]
    parts = [
        f"SignalP: {primary.get('prediction', 'OTHER')}",
        f"for {gene_resolved or ac}",
    ]
    if primary.get("prediction") == "SP" and primary.get("cleavage_start"):
        parts.append(f"cleavage≈{primary['cleavage_start']}")
    if site_position is not None:
        if primary.get("site_in_signal_peptide"):
            parts.append(f"site {site_position} in signal peptide (predicted)")
        elif primary.get("site_near_cleavage_site"):
            parts.append(f"site {site_position} near cleavage site (predicted)")
        else:
            parts.append(f"site {site_position} outside signal peptide (predicted)")

    return {
        "summary": " — ".join(parts),
        "gene": gene_resolved,
        "uniprot_ac": ac,
        "uniprot_identity": identity,
        "site_position": site_position,
        "total": len(predictions),
        "predictions": predictions,
        **_meta(),
    }


def register_signalp_tools() -> None:
    registry.register(
        name="signalp_prediction",
        description=(
            "Query SignalP 6.0 secretory signal-peptide predictions (Sec/SPI) and "
            "cleavage-site coordinates for a human protein. Use for Stage 3 WHERE / "
            "site-importance: check whether a PTM site lies in the N-terminal signal "
            "peptide or near the cleavage site (may affect secretion or processing). "
            "Evidence is predicted."
        ),
        parameters={
            "type": "object",
            "properties": {
                "gene": {"type": "string", "description": "Gene symbol (e.g. TP53)"},
                "uniprot_ac": {"type": "string", "description": "UniProt accession"},
                "site_position": {
                    "type": "integer",
                    "description": "Residue position to test for signal-peptide overlap",
                },
                "sp_only": {
                    "type": "boolean",
                    "description": "If true, return only SP-positive proteins",
                    "default": False,
                },
            },
        },
        handler=_signalp_prediction,
    )
