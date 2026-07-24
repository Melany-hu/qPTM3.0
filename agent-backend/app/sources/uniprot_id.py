"""UniProt identity helpers — canonical gene / accession resolution.

External databases (e.g. ProteomicsDB) may carry stale gene symbols or protein
names. Always resolve identity via UniProt REST before reporting results.

API: https://rest.uniprot.org
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


def _get(path: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
    url = f"{settings.uniprot_api_base_url.rstrip('/')}/{path.lstrip('/')}"
    try:
        with httpx.Client(timeout=settings.http_timeout_seconds) as client:
            resp = client.get(url, params=params, headers={"Accept": "application/json"})
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        logger.warning("UniProt identity request failed %s: %s", path, e)
        return None


def _parse_entry(data: dict[str, Any]) -> dict[str, Any]:
    """Normalize a UniProtKB JSON entry into a compact identity record."""
    gene_names: list[str] = []
    synonyms: list[str] = []
    for g in data.get("genes") or []:
        if not isinstance(g, dict):
            continue
        name = g.get("geneName")
        if isinstance(name, dict) and name.get("value"):
            gene_names.append(str(name["value"]))
        elif isinstance(name, str) and name:
            gene_names.append(name)
        for syn in g.get("synonyms") or []:
            if isinstance(syn, dict) and syn.get("value"):
                synonyms.append(str(syn["value"]))
            elif isinstance(syn, str) and syn:
                synonyms.append(syn)

    protein_name = ""
    desc = data.get("proteinDescription") or {}
    if isinstance(desc, dict):
        rec = desc.get("recommendedName") or {}
        if isinstance(rec, dict):
            full = rec.get("fullName") or {}
            protein_name = full.get("value", "") if isinstance(full, dict) else str(full or "")

    organism = ""
    org = data.get("organism") or {}
    if isinstance(org, dict):
        organism = org.get("scientificName") or ""
        taxon = org.get("taxonId")
    else:
        taxon = None

    return {
        "uniprot_ac": data.get("primaryAccession") or "",
        "entry_name": data.get("uniProtkbId") or "",
        "gene": gene_names[0] if gene_names else None,
        "gene_names": gene_names,
        "gene_synonyms": synonyms,
        "protein_name": protein_name or None,
        "organism": organism or None,
        "taxon_id": taxon,
        "reviewed": (data.get("entryType") or "").lower().find("reviewed") >= 0
        or data.get("entryType") == "UniProtKB reviewed (Swiss-Prot)",
        "source": "UniProt",
        "url": f"https://www.uniprot.org/uniprotkb/{data.get('primaryAccession') or ''}",
    }


def lookup_by_accession(uniprot_ac: str) -> dict[str, Any] | None:
    """Fetch canonical identity for a UniProt accession."""
    ac = (uniprot_ac or "").strip().upper()
    if not ac:
        return None
    data = _get(f"uniprotkb/{ac}", params={"format": "json"})
    if not data:
        return None
    return _parse_entry(data)


def lookup_by_gene(
    gene: str,
    *,
    organism_id: int = 9606,
    reviewed_only: bool = True,
) -> dict[str, Any] | None:
    """Resolve gene symbol → UniProt accession (human SwissProt by default)."""
    symbol = (gene or "").strip()
    if not symbol:
        return None
    # Escape special query chars lightly
    safe = symbol.replace("'", "")
    parts = [f"gene_exact:{safe}", f"organism_id:{organism_id}"]
    if reviewed_only:
        parts.append("reviewed:true")
    data = _get(
        "uniprotkb/search",
        params={"query": " AND ".join(parts), "format": "json", "size": "5"},
    )
    if not data:
        return None
    results = data.get("results") or []
    if not results and reviewed_only:
        # retry without reviewed filter
        return lookup_by_gene(gene, organism_id=organism_id, reviewed_only=False)
    if not results:
        return None
    return _parse_entry(results[0])


def resolve_identity(
    *,
    uniprot_ac: str | None = None,
    gene: str | None = None,
    organism_id: int = 9606,
) -> dict[str, Any] | None:
    """Resolve protein identity. Prefer accession; else gene → accession."""
    if uniprot_ac:
        ident = lookup_by_accession(uniprot_ac)
        if ident:
            return ident
    if gene:
        return lookup_by_gene(gene, organism_id=organism_id)
    return None
