"""CancerProteome tools — cancer vs normal PTM / protein quantification.

Stage 4 (WHY / disease) tool:
  cancerproteome_disease — tumor vs control PTM site ratios and protein abundance

Data: data/disease/CancerProteome/
Homepage: http://bio-bigdata.hrbmu.edu.cn/CancerProteome
PMID: 37823596  DOI: 10.1093/nar/gkad824
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.sources.catalog import get_catalog
from app.sources.query import index_exists, query_records
from app.tools.registry import registry

logger = logging.getLogger(__name__)

_PTM_FIELDS = (
    "gene", "uniprot", "position", "ptm_ome", "pep",
    "cancer", "cancer_name", "sample", "samplecondition",
    "qratio", "fdr", "dataset_id",
)
_PROT_FIELDS = (
    "gene", "uniprot", "protein", "cancer", "cancer_name",
    "mean_control", "mean_tumor", "fc", "fdr", "source",
)


@lru_cache(maxsize=1)
def _cancer_abbrev() -> dict[str, str]:
    """Map abbreviated cancer codes → full names."""
    m = get_catalog().get("cancerproteome")
    mapping: dict[str, str] = {}
    if not m or not m.root:
        return mapping
    path = Path(m.root) / "Cancer-abbreviation.txt"
    if not path.exists():
        return mapping
    with path.open(encoding="utf-8") as f:
        next(f, None)  # header
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) >= 2 and parts[0].strip():
                mapping[parts[0].strip().upper()] = parts[1].strip()
    return mapping


def _resolve_cancer(cancer: str | None) -> str | None:
    if not cancer or cancer.strip().lower() in ("all", ""):
        return None
    raw = cancer.strip()
    abbrev = _cancer_abbrev()
    upper = raw.upper()
    if upper in abbrev:
        return upper
    # Match full name → code
    for code, name in abbrev.items():
        if name.lower() == raw.lower() or raw.lower() in name.lower():
            return code
    return upper


def _cancer_from_sample(sample: str | None) -> str:
    if not sample:
        return ""
    return sample.strip().split()[0].upper()


def _direction(ratio: float | None) -> str | None:
    if ratio is None:
        return None
    if ratio >= 1.5:
        return "up_in_tumor"
    if ratio <= 1 / 1.5:
        return "down_in_tumor"
    return "unchanged"


def _to_float(val: Any) -> float | None:
    if val is None or val == "":
        return None
    try:
        return float(str(val).strip())
    except (TypeError, ValueError):
        return None


def _meta() -> dict[str, Any]:
    m = get_catalog().get("cancerproteome")
    if not m:
        return {
            "homepage": "http://bio-bigdata.hrbmu.edu.cn/CancerProteome",
            "doi": "10.1093/nar/gkad824",
            "pmid": "37823596",
        }
    return {
        "homepage": m.homepage,
        "doi": m.doi,
        "pmid": m.pmid,
        "citation": m.citation,
    }


def _compact_ptm(row: dict[str, Any]) -> dict[str, Any]:
    cancer = _cancer_from_sample(row.get("sample"))
    qratio = _to_float(row.get("qratio"))
    out = {
        "gene": row.get("gene"),
        "uniprot": row.get("uniprot") or row.get("up"),
        "position": row.get("position") or row.get("pos"),
        "ptm_ome": row.get("ptm_ome") or row.get("mods"),
        "pep": row.get("pep"),
        "cancer": cancer,
        "cancer_name": _cancer_abbrev().get(cancer, cancer),
        "sample": row.get("sample"),
        "samplecondition": row.get("samplecondition"),
        "qratio": row.get("qratio"),
        "fdr": row.get("fdr"),
        "dataset_id": row.get("pmid"),  # PDC accession in source file
        "direction": _direction(qratio),
    }
    return {k: v for k, v in out.items() if v not in (None, "")}


def _compact_protein(row: dict[str, Any]) -> dict[str, Any]:
    cancer = str(row.get("cancer") or "").strip().upper()
    fc = _to_float(row.get("fc") or row.get("FC"))
    out = {
        "gene": row.get("gene") or row.get("genename"),
        "uniprot": row.get("uniprot"),
        "protein": row.get("protein"),
        "cancer": cancer,
        "cancer_name": _cancer_abbrev().get(cancer, cancer),
        "mean_control": row.get("mean_control"),
        "mean_tumor": row.get("mean_tumor"),
        "fc": row.get("fc") or row.get("FC"),
        "fdr": (row.get("fdr") or row.get("FDR") or "").strip()
        if isinstance(row.get("fdr") or row.get("FDR"), str)
        else row.get("fdr") or row.get("FDR"),
        "source": row.get("source"),
        "direction": _direction(fc),
    }
    return {k: v for k, v in out.items() if v not in (None, "")}


def _query_ptm(
    *,
    gene: str | None,
    uniprot_ac: str | None,
    position: int | None,
    cancer: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    if not index_exists("cancerproteome", "ptm"):
        raise FileNotFoundError(
            "CancerProteome PTM index missing. "
            "Run: python -m app.sources.build_index cancerproteome"
        )
    equals_ci: dict[str, str] = {}
    equals: dict[str, str] = {}
    like_prefix_ci: dict[str, str] = {}

    if uniprot_ac:
        equals_ci["uniprot"] = uniprot_ac
    elif gene:
        equals_ci["gene"] = gene
    if position is not None:
        equals["position"] = str(position)
    if cancer:
        # sample values look like "LUNG Tumor/Control"
        like_prefix_ci["sample"] = cancer

    # Over-fetch then filter when cancer set (prefix match is enough usually)
    rows = query_records(
        "cancerproteome",
        "ptm",
        equals=equals or None,
        equals_ci=equals_ci or None,
        like_prefix_ci=like_prefix_ci or None,
        limit=max(limit * 3, limit),
    )
    out = [_compact_ptm(r) for r in rows]
    if cancer:
        out = [r for r in out if r.get("cancer") == cancer]
    return out[:limit]


def _query_protein(
    *,
    gene: str | None,
    uniprot_ac: str | None,
    cancer: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    if not index_exists("cancerproteome", "protein"):
        raise FileNotFoundError(
            "CancerProteome protein index missing. "
            "Run: python -m app.sources.build_index cancerproteome"
        )
    equals_ci: dict[str, str] = {}
    if uniprot_ac:
        equals_ci["uniprot"] = uniprot_ac
    elif gene:
        equals_ci["gene"] = gene
    if cancer:
        equals_ci["cancer"] = cancer

    rows = query_records(
        "cancerproteome",
        "protein",
        equals_ci=equals_ci or None,
        limit=limit,
    )
    return [_compact_protein(r) for r in rows][:limit]


def _cancerproteome_disease(
    gene: str | None = None,
    uniprot_ac: str | None = None,
    position: int | None = None,
    cancer: str | None = None,
    query_type: str = "both",
    limit: int = 40,
) -> dict[str, Any]:
    """Query CancerProteome tumor-vs-control PTM and/or protein quantification."""
    if not any([gene, uniprot_ac]):
        return {
            "error": "Provide gene and/or uniprot_ac",
            "summary": "Missing query key for CancerProteome",
        }

    qtype = (query_type or "both").strip().lower()
    if qtype not in ("both", "ptm", "protein"):
        return {
            "error": "query_type must be both|ptm|protein",
            "summary": f"Invalid CancerProteome query_type '{query_type}'",
        }

    cancer_code = _resolve_cancer(cancer)
    ptm_hits: list[dict[str, Any]] = []
    protein_hits: list[dict[str, Any]] = []

    try:
        if qtype in ("both", "ptm"):
            ptm_hits = _query_ptm(
                gene=gene,
                uniprot_ac=uniprot_ac,
                position=position,
                cancer=cancer_code,
                limit=limit,
            )
        if qtype in ("both", "protein"):
            protein_hits = _query_protein(
                gene=gene,
                uniprot_ac=uniprot_ac,
                cancer=cancer_code,
                limit=limit,
            )
    except FileNotFoundError as e:
        return {"error": str(e), "summary": str(e)}
    except Exception as e:
        logger.error("CancerProteome query failed: %s", e, exc_info=True)
        return {"error": str(e), "summary": f"CancerProteome query failed: {e}"}

    keys = []
    if gene:
        keys.append(gene)
    if uniprot_ac:
        keys.append(uniprot_ac)
    if position is not None:
        keys.append(f"pos {position}")
    if cancer_code:
        keys.append(cancer_code)

    total = len(ptm_hits) + len(protein_hits)
    abbrev = _cancer_abbrev()
    summary = (
        f"CancerProteome: {len(ptm_hits)} PTM tumor/control hit(s), "
        f"{len(protein_hits)} protein abundance hit(s) "
        f"for {', '.join(keys) or 'query'}"
    )
    if total == 0:
        summary += " (no local matches)"

    return {
        "summary": summary,
        "total": total,
        "ptm_total": len(ptm_hits),
        "protein_total": len(protein_hits),
        "ptm_hits": ptm_hits,
        "protein_hits": protein_hits,
        "cancer_filter": cancer_code,
        "cancer_legend": abbrev,
        "note": (
            "PTM qratio / protein FC compare tumor vs control within each cancer type. "
            "dataset_id values are Proteomic Data Commons (PDC) accessions, not PubMed IDs."
        ),
        "source": "CancerProteome",
        **_meta(),
    }


def register_cancerproteome_tools() -> None:
    registry.register(
        name="cancerproteome_disease",
        description=(
            "Query CancerProteome for tumor-vs-control differential PTM site "
            "quantification and/or protein abundance across cancer types "
            "(PMID 37823596). Use for Stage 2 WHEN (cancer quantitative "
            "conditions) and Stage 4 WHY (cancer relevance / biomarker). "
            "Filters: gene, UniProt, site position, cancer abbreviation "
            "(e.g. LUNG, BRCA) or full name."
        ),
        parameters={
            "type": "object",
            "properties": {
                "gene": {
                    "type": "string",
                    "description": "Gene symbol (e.g. TP53, EGFR)",
                },
                "uniprot_ac": {
                    "type": "string",
                    "description": "UniProt accession",
                },
                "position": {
                    "type": "integer",
                    "description": "PTM site residue position (PTM table only)",
                },
                "cancer": {
                    "type": "string",
                    "description": (
                        "Cancer type code (LUNG, BRCA, …) or full name "
                        "(e.g. Lung Cancer). Optional."
                    ),
                },
                "query_type": {
                    "type": "string",
                    "enum": ["both", "ptm", "protein"],
                    "description": "Which table(s) to query (default both)",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max rows per table (default 40)",
                },
            },
        },
        handler=_cancerproteome_disease,
    )
