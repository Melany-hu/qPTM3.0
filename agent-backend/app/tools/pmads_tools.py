"""PMADS tools — drug–PTM–disease associations (local index).

Stage 3 (disease_drug) tool:
  pmads_drug_ptm — curated/inferred associations linking drugs, PTMs, and diseases

Data: data/drug/PMADS/ (NAR 2025, PMID 41099621, doi:10.1093/nar/gkaf1033)
Homepage: https://pmads-db.org
"""

from __future__ import annotations

import logging
import re
from typing import Any

from app.sources.catalog import get_catalog
from app.sources.query import index_exists, query_records
from app.tools.registry import registry

logger = logging.getLogger(__name__)

_COMPACT_FIELDS = (
    "id", "status", "gene_manual", "protein_uniprot", "protein", "ptm", "site",
    "drug", "drug_class", "disease", "disease_fine", "kw", "regulatory_class",
    "ptm_regulation", "disease_regulation", "confidence_score", "confidence_level",
    "pmid", "sentence",
)


def _compact_row(row: dict[str, Any]) -> dict[str, Any]:
    out = {k: row.get(k) for k in _COMPACT_FIELDS if row.get(k) not in (None, "")}
    sent = out.get("sentence")
    if isinstance(sent, str) and len(sent) > 280:
        out["sentence"] = sent[:277] + "..."
    return out


def _parse_site_pos(site: str | None) -> int | None:
    if not site:
        return None
    m = re.search(r"(\d+)", str(site))
    return int(m.group(1)) if m else None


def _pmads_drug_ptm(
    gene: str | None = None,
    uniprot_ac: str | None = None,
    drug: str | None = None,
    disease: str | None = None,
    ptm_type: str | None = None,
    status: str = "Curated",
    site_position: int | None = None,
    limit: int = 40,
) -> dict[str, Any]:
    """Query PMADS drug–PTM–disease associations."""
    if not any([gene, uniprot_ac, drug, disease]):
        return {
            "error": "Provide at least one of: gene, uniprot_ac, drug, disease",
            "summary": "Missing query key for PMADS",
        }

    if not index_exists("pmads", "associations"):
        return {
            "error": "PMADS index missing. Run: python -m app.sources.build_index pmads",
            "summary": "PMADS index not built yet",
        }

    equals_ci: dict[str, str] = {}
    equals: dict[str, str] = {}

    if uniprot_ac:
        equals_ci["protein_uniprot"] = uniprot_ac
    elif gene:
        equals_ci["gene_manual"] = gene
    if drug:
        equals_ci["drug"] = drug
    if disease:
        equals_ci["disease"] = disease
    if ptm_type and ptm_type.lower() not in ("all", ""):
        equals_ci["ptm"] = ptm_type

    status_n = (status or "Curated").strip()
    if status_n.lower() not in ("all", "any", ""):
        # Curated | Inferred
        if status_n.lower() in ("predicted", "inferred"):
            status_n = "Inferred"
        elif status_n.lower() == "curated":
            status_n = "Curated"
        equals["status"] = status_n

    # Over-fetch when filtering by site residue number inside free-text Site
    fetch_limit = min(max(limit * 5, limit), 200) if site_position else min(limit, 80)
    try:
        rows = query_records(
            "pmads",
            "associations",
            equals=equals or None,
            equals_ci=equals_ci or None,
            limit=fetch_limit,
        )
    except Exception as e:
        logger.error("PMADS query failed: %s", e)
        return {"error": str(e), "summary": f"PMADS query failed: {e}"}

    if site_position is not None:
        rows = [
            r for r in rows
            if _parse_site_pos(r.get("site")) == site_position
        ]

    rows = rows[: min(limit, 80)]
    curated_n = sum(1 for r in rows if r.get("status") == "Curated")
    inferred_n = sum(1 for r in rows if r.get("status") == "Inferred")

    keys = []
    if gene:
        keys.append(f"gene={gene}")
    if uniprot_ac:
        keys.append(f"uniprot={uniprot_ac}")
    if drug:
        keys.append(f"drug={drug}")
    if disease:
        keys.append(f"disease={disease}")
    if site_position is not None:
        keys.append(f"site={site_position}")

    summary = (
        f"PMADS: {len(rows)} association(s) for {', '.join(keys)} "
        f"(Curated={curated_n}, Inferred={inferred_n}; filter status={status_n})."
    )
    if not rows:
        summary += " No matching entries in local PMADS table."

    manifest = get_catalog().get("pmads")
    return {
        "summary": summary,
        "gene": gene,
        "uniprot_ac": uniprot_ac,
        "drug": drug,
        "disease": disease,
        "ptm_type": ptm_type,
        "site_position": site_position,
        "status_filter": status_n,
        "total": len(rows),
        "associations": [_compact_row(r) for r in rows],
        "source": "PMADS",
        "access": "local",
        "homepage": manifest.homepage if manifest else "https://pmads-db.org",
        "pmid": manifest.pmid if manifest else "41099621",
        "doi": manifest.doi if manifest else "10.1093/nar/gkaf1033",
    }


def register_pmads_tools() -> None:
    registry.register(
        name="pmads_drug_ptm",
        description=(
            "Query PMADS for drug–PTM–disease associations (curated literature + "
            "inferred proteomics). Use for drug sensitivity/resistance linked to PTMs, "
            "drug-induced PTM changes, and disease context. Prefer status='Curated' first."
        ),
        parameters={
            "type": "object",
            "properties": {
                "gene": {
                    "type": "string",
                    "description": "Gene symbol (e.g. EGFR, TP53)",
                },
                "uniprot_ac": {
                    "type": "string",
                    "description": "UniProt accession (e.g. P00533)",
                },
                "drug": {
                    "type": "string",
                    "description": "Drug name (e.g. Gefitinib)",
                },
                "disease": {
                    "type": "string",
                    "description": "Disease name (e.g. Lung Cancer)",
                },
                "ptm_type": {
                    "type": "string",
                    "description": "PTM type filter (e.g. phosphorylation, acetylation)",
                },
                "status": {
                    "type": "string",
                    "enum": ["Curated", "Inferred", "all"],
                    "description": "Evidence class (default Curated)",
                },
                "site_position": {
                    "type": "integer",
                    "description": "Optional residue position filter parsed from Site field",
                },
            },
            "required": [],
        },
        handler=_pmads_drug_ptm,
    )
