"""dSCOPE tools — LLPS-driving sequence regions (literature + predictions).

Stage 3 (phase_separation) tools:
  - dscope_literature — experimentally curated LLPS-driving segments
  - dscope_predictions — human proteome PS-driving region predictions

Data: data/phase_separation/dscope/
Homepage: https://dscope.omicsbio.info
PMID: 36528388  DOI: 10.1093/bib/bbac550
"""

from __future__ import annotations

import logging
import re
from typing import Any

from app.sources.catalog import get_catalog
from app.sources.query import index_exists, query_records
from app.sources.uniprot_id import resolve_identity
from app.tools.registry import registry

logger = logging.getLogger(__name__)

_LIT_FIELDS = (
    "uniprot", "protein", "position", "organism", "sequence",
    "peptide", "pmid", "interaction",
)
_PRED_FIELDS = ("uniprot", "gene", "protein", "ids")

_REGION_RE = re.compile(r"^(\d+)\s*-\s*(\d+)$")


def _meta() -> dict[str, str]:
    m = get_catalog().get("dscope")
    return {
        "homepage": m.homepage if m else "https://dscope.omicsbio.info",
        "pmid": m.pmid if m else "36528388",
        "doi": m.doi if m else "10.1093/bib/bbac550",
    }


def _pick(row: dict[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    return {k: row.get(k) for k in fields if row.get(k) not in (None, "")}


def _parse_region_span(region: str) -> tuple[int | None, int | None]:
    m = _REGION_RE.match((region or "").strip())
    if not m:
        return None, None
    return int(m.group(1)), int(m.group(2))


def _parse_region_scores(regions_str: str, scores_str: str) -> list[dict[str, Any]]:
    regions = [r.strip() for r in (regions_str or "").split(";") if r.strip()]
    scores = [s.strip() for s in (scores_str or "").split(";") if s.strip()]
    out: list[dict[str, Any]] = []
    for i, region in enumerate(regions):
        start, end = _parse_region_span(region)
        item: dict[str, Any] = {"region": region}
        if start is not None and end is not None:
            item["start"] = start
            item["end"] = end
        if i < len(scores):
            try:
                item["score"] = round(float(scores[i]), 4)
            except ValueError:
                pass
        out.append(item)
    return out


def _overlaps_position(item: dict[str, Any], position: int) -> bool:
    start = item.get("start")
    end = item.get("end")
    if start is not None and end is not None:
        return start <= position <= end
    pos_text = (item.get("region") or item.get("position") or "").strip()
    m = _REGION_RE.match(pos_text)
    if m:
        return int(m.group(1)) <= position <= int(m.group(2))
    return False


def _filter_by_position(
    items: list[dict[str, Any]],
    position: int | None,
    *,
    position_key: str = "position",
) -> list[dict[str, Any]]:
    if position is None:
        return items
    filtered = [
        item for item in items
        if _overlaps_position(item, position)
        or (
            position_key in item
            and _overlaps_position({"position": item[position_key]}, position)
        )
    ]
    return filtered


def _dscope_literature(
    gene: str | None = None,
    uniprot_ac: str | None = None,
    site_position: int | None = None,
    organism: str | None = None,
    limit: int = 30,
) -> dict[str, Any]:
    """Query literature-curated LLPS-driving sequence segments (dSCOPE training set)."""
    if not gene and not uniprot_ac:
        return {
            "error": "Provide gene or uniprot_ac",
            "summary": "Missing gene/uniprot for dSCOPE literature query",
        }
    if not index_exists("dscope", "literature"):
        return {
            "error": "dSCOPE literature index missing. Run: python -m app.sources.build_index dscope",
            "summary": "dSCOPE literature index not built",
        }

    identity = None
    try:
        identity = resolve_identity(uniprot_ac=uniprot_ac, gene=gene)
    except Exception as e:
        logger.warning("UniProt identity lookup failed: %s", e)

    canon_ac = (identity or {}).get("uniprot_ac") or uniprot_ac
    canon_gene = (identity or {}).get("gene") or gene

    equals_ci: dict[str, str] = {}
    if canon_ac:
        equals_ci["uniprot"] = canon_ac
    elif canon_gene:
        equals_ci["protein"] = canon_gene

    rows = query_records(
        "dscope",
        "literature",
        equals_ci=equals_ci or None,
        limit=min(limit * 4, 120),
    )

    if organism and organism.lower() not in ("all", ""):
        org_l = organism.strip().lower()
        rows = [
            r for r in rows
            if org_l in (r.get("organism") or "").lower()
        ]

    entries = [_pick(r, _LIT_FIELDS) for r in rows]
    if site_position is not None:
        entries = _filter_by_position(entries, site_position)
    entries = entries[: min(limit, 60)]

    keys = []
    if canon_gene:
        keys.append(f"gene={canon_gene}")
    if canon_ac:
        keys.append(f"uniprot={canon_ac}")
    if site_position is not None:
        keys.append(f"site={site_position}")
    if organism:
        keys.append(f"organism~{organism}")

    summary = (
        f"dSCOPE literature: {len(entries)} experimentally curated LLPS-driving "
        f"segment(s) for {', '.join(keys)}."
    )
    if not entries:
        summary += " No literature training-set hits."

    return {
        "summary": summary,
        "gene": canon_gene,
        "uniprot_ac": canon_ac,
        "protein_name": (identity or {}).get("protein_name"),
        "site_position": site_position,
        "organism_filter": organism,
        "total": len(entries),
        "segments": entries,
        "source": "dSCOPE",
        "evidence": "experimental",
        "access": "local",
        "uniprot_identity": identity,
        **_meta(),
    }


def _dscope_predictions(
    gene: str | None = None,
    uniprot_ac: str | None = None,
    site_position: int | None = None,
    min_score: float = 0.5,
    only_with_regions: bool = True,
    limit: int = 20,
) -> dict[str, Any]:
    """Query dSCOPE-predicted PS-driving regions on the human proteome."""
    if not gene and not uniprot_ac:
        return {
            "error": "Provide gene or uniprot_ac",
            "summary": "Missing gene/uniprot for dSCOPE prediction query",
        }
    if not index_exists("dscope", "predictions"):
        return {
            "error": "dSCOPE predictions index missing. Run: python -m app.sources.build_index dscope",
            "summary": "dSCOPE predictions index not built",
        }

    identity = None
    try:
        identity = resolve_identity(uniprot_ac=uniprot_ac, gene=gene)
    except Exception as e:
        logger.warning("UniProt identity lookup failed: %s", e)

    canon_ac = (identity or {}).get("uniprot_ac") or uniprot_ac
    canon_gene = (identity or {}).get("gene") or gene

    equals_ci: dict[str, str] = {}
    if canon_ac:
        equals_ci["uniprot"] = canon_ac
    elif canon_gene:
        equals_ci["gene"] = canon_gene

    rows = query_records(
        "dscope",
        "predictions",
        equals_ci=equals_ci or None,
        limit=5,
    )

    predictions: list[dict[str, Any]] = []
    for row in rows:
        regions_raw = row.get("regions") or ""
        if only_with_regions and not regions_raw.strip():
            continue
        region_items = _parse_region_scores(
            regions_raw,
            row.get("averagescores") or row.get("averagescore") or "",
        )
        if min_score > 0:
            region_items = [
                r for r in region_items
                if float(r.get("score") or 0) >= min_score
            ]
        if site_position is not None:
            region_items = _filter_by_position(region_items, site_position)
        if only_with_regions and not region_items:
            continue

        item = _pick(row, _PRED_FIELDS)
        item["regions"] = region_items
        item["region_count"] = len(region_items)
        if region_items:
            item["max_score"] = max(float(r.get("score") or 0) for r in region_items)
        predictions.append(item)

    predictions.sort(
        key=lambda x: float(x.get("max_score") or 0),
        reverse=True,
    )
    predictions = predictions[: min(limit, 40)]

    keys = []
    if canon_gene:
        keys.append(f"gene={canon_gene}")
    if canon_ac:
        keys.append(f"uniprot={canon_ac}")
    if site_position is not None:
        keys.append(f"site={site_position}")
    keys.append(f"min_score={min_score}")

    total_regions = sum(p.get("region_count", 0) for p in predictions)
    summary = (
        f"dSCOPE predictions: {total_regions} PS-driving region(s) across "
        f"{len(predictions)} protein hit(s) for {', '.join(keys)}."
    )
    if not predictions:
        summary += " No predicted PS-driving regions above threshold."

    return {
        "summary": summary,
        "gene": canon_gene,
        "uniprot_ac": canon_ac,
        "protein_name": (identity or {}).get("protein_name"),
        "site_position": site_position,
        "min_score": min_score,
        "only_with_regions": only_with_regions,
        "total": total_regions,
        "proteins": predictions,
        "source": "dSCOPE",
        "evidence": "predicted",
        "access": "local",
        "uniprot_identity": identity,
        **_meta(),
    }


def register_dscope_tools() -> None:
    registry.register(
        name="dscope_literature",
        description=(
            "Query dSCOPE literature-curated experimentally identified sequence "
            "segments that drive liquid–liquid phase separation (LLPS). Returns "
            "protein region, organism, PMID, and interaction partners. Use for "
            "experimental LLPS-driving evidence (training set of dSCOPE; PMID 36528388)."
        ),
        parameters={
            "type": "object",
            "properties": {
                "gene": {"type": "string", "description": "Gene symbol"},
                "uniprot_ac": {"type": "string", "description": "UniProt accession"},
                "site_position": {
                    "type": "integer",
                    "description": "Residue position to test overlap with reported regions",
                },
                "organism": {
                    "type": "string",
                    "description": "Organism filter (e.g. Homo sapiens)",
                },
            },
            "required": [],
        },
        handler=_dscope_literature,
    )

    registry.register(
        name="dscope_predictions",
        description=(
            "Query dSCOPE human proteome predictions of protein sequence segments "
            "critical for phase separation (PS-driving regions with probability "
            "scores). Prefer after checking literature evidence with dscope_literature."
        ),
        parameters={
            "type": "object",
            "properties": {
                "gene": {"type": "string", "description": "Gene symbol"},
                "uniprot_ac": {"type": "string", "description": "UniProt accession"},
                "site_position": {
                    "type": "integer",
                    "description": "Residue position to filter overlapping predicted regions",
                },
                "min_score": {
                    "type": "number",
                    "description": "Minimum dSCOPE prediction score (default 0.5)",
                },
                "only_with_regions": {
                    "type": "boolean",
                    "description": "Only return proteins with predicted regions (default true)",
                },
            },
            "required": [],
        },
        handler=_dscope_predictions,
    )
