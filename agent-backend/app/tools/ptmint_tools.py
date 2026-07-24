"""PTMint tools — PTM regulation of protein–protein interactions (local).

Stage 3 (interactions) tool:
  ptmint_ppi — curated experimental PTM→PPI enhance/inhibit evidence

Data: data/interactions/PTMint/
Homepage: https://ptmint.sjtu.edu.cn/
PMID: 36548389  DOI: 10.1093/bioinformatics/btac823
"""

from __future__ import annotations

import logging
from typing import Any

from app.sources.catalog import get_catalog
from app.sources.query import index_exists, query_records
from app.tools.registry import registry

logger = logging.getLogger(__name__)

_FIELDS = (
    "organism", "gene", "uniprot", "ptm", "site", "aa", "sequence_window",
    "int_gene", "int_uniprot", "effect", "method", "disease", "co_localized", "pmid",
)


def _pick(row: dict[str, Any]) -> dict[str, Any]:
    return {k: row.get(k) for k in _FIELDS if row.get(k) not in (None, "")}


def _ptmint_ppi(
    gene: str | None = None,
    uniprot_ac: str | None = None,
    partner_gene: str | None = None,
    partner_uniprot: str | None = None,
    site_position: int | None = None,
    effect: str | None = None,
    ptm_type: str | None = None,
    limit: int = 40,
) -> dict[str, Any]:
    """Query PTMint curated PTM–PPI regulation associations."""
    if not any([gene, uniprot_ac, partner_gene, partner_uniprot]):
        return {
            "error": "Provide gene/uniprot_ac and/or partner_gene/partner_uniprot",
            "summary": "Missing query key for PTMint",
        }

    if not index_exists("ptmint", "experimental"):
        return {
            "error": "PTMint index missing. Run: python -m app.sources.build_index ptmint",
            "summary": "PTMint index not built yet",
        }

    equals_ci: dict[str, str] = {}
    equals: dict[str, str] = {}

    # Substrate side
    if uniprot_ac:
        equals_ci["uniprot"] = uniprot_ac
    elif gene:
        equals_ci["gene"] = gene

    # Partner side
    if partner_uniprot:
        equals_ci["int_uniprot"] = partner_uniprot
    elif partner_gene:
        equals_ci["int_gene"] = partner_gene

    if site_position is not None:
        equals["site"] = str(site_position)
    if effect and effect.lower() not in ("all", ""):
        # Enhance / Inhibit
        equals_ci["effect"] = effect
    if ptm_type and ptm_type.lower() not in ("all", ""):
        equals_ci["ptm"] = ptm_type

    try:
        rows = query_records(
            "ptmint",
            "experimental",
            equals=equals or None,
            equals_ci=equals_ci or None,
            limit=min(limit, 80),
        )
    except Exception as e:
        logger.error("PTMint query failed: %s", e)
        return {"error": str(e), "summary": f"PTMint query failed: {e}"}

    # If user only gave a gene, also include rows where it is the interactor
    as_partner: list[dict[str, Any]] = []
    if (gene or uniprot_ac) and not partner_gene and not partner_uniprot:
        peq_ci: dict[str, str] = {}
        if uniprot_ac:
            peq_ci["int_uniprot"] = uniprot_ac
        elif gene:
            peq_ci["int_gene"] = gene
        try:
            as_partner = query_records(
                "ptmint",
                "experimental",
                equals_ci=peq_ci,
                limit=min(limit, 40),
            )
        except Exception as e:
            logger.warning("PTMint partner-side query failed: %s", e)

    # Deduplicate by pmid+site+int_gene if both lists overlap
    seen = {
        (r.get("pmid"), r.get("site"), r.get("gene"), r.get("int_gene"))
        for r in rows
    }
    extra = []
    for r in as_partner:
        key = (r.get("pmid"), r.get("site"), r.get("gene"), r.get("int_gene"))
        if key not in seen:
            extra.append(r)
            seen.add(key)

    enhance = sum(1 for r in rows + extra if "enhance" in (r.get("effect") or "").lower())
    inhibit = sum(1 for r in rows + extra if "inhib" in (r.get("effect") or "").lower())

    keys = []
    if gene:
        keys.append(f"gene={gene}")
    if uniprot_ac:
        keys.append(f"uniprot={uniprot_ac}")
    if partner_gene:
        keys.append(f"partner={partner_gene}")
    if partner_uniprot:
        keys.append(f"partner_uniprot={partner_uniprot}")
    if site_position is not None:
        keys.append(f"site={site_position}")

    total = len(rows) + len(extra)
    examples: list[str] = []
    for r in (rows + extra)[:6]:
        site = f"{r.get('aa') or ''}{r.get('site') or ''}".strip() or "?"
        note = (
            f"{r.get('gene') or '?'} {site}-{r.get('ptm') or 'PTM'} "
            f"{r.get('effect') or 'regulates'} {r.get('int_gene') or r.get('int_uniprot') or '?'}"
            + (f" via {r.get('method')}" if r.get("method") else "")
            + (f"; {r.get('disease')}" if r.get("disease") and r.get("disease") != "None" else "")
            + (f" (PMID {r.get('pmid')})" if r.get("pmid") else "")
        )
        examples.append(note)

    summary = (
        f"PTMint: {total} PTM–PPI association(s) for {', '.join(keys)} "
        f"(Enhance≈{enhance}, Inhibit≈{inhibit}; "
        f"as_substrate={len(rows)}, as_partner={len(extra)})."
    )
    if examples:
        summary += " Examples: " + " ".join(examples)
    elif total == 0:
        summary += " No curated experimental hits."

    def _annotate(recs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out = []
        for r in recs:
            item = _pick(r)
            site = f"{item.get('aa') or ''}{item.get('site') or ''}".strip()
            item["note"] = (
                f"{item.get('gene')} {site}-{item.get('ptm')} "
                f"{item.get('effect')} {item.get('int_gene')}"
                + (f" (PMID {item.get('pmid')})" if item.get("pmid") else "")
            )
            out.append(item)
        return out

    manifest = get_catalog().get("ptmint")
    return {
        "summary": summary,
        "gene": gene,
        "uniprot_ac": uniprot_ac,
        "partner_gene": partner_gene,
        "partner_uniprot": partner_uniprot,
        "site_position": site_position,
        "total": total,
        "as_substrate": _annotate(rows),
        "as_partner": _annotate(extra),
        "source": "PTMint",
        "evidence": "experimental",
        "access": "local",
        "homepage": manifest.homepage if manifest else "https://ptmint.sjtu.edu.cn/",
        "pmid": manifest.pmid if manifest else "36548389",
        "doi": manifest.doi if manifest else "10.1093/bioinformatics/btac823",
    }


def register_ptmint_tools() -> None:
    registry.register(
        name="ptmint_ppi",
        description=(
            "Query PTMint curated experimental evidence that a PTM enhances or "
            "inhibits a protein–protein interaction. Returns substrate site, "
            "interactor, effect (Enhance/Inhibit), method, disease, and PMID. "
            "Distinct from iPTMnet iptmnet_ptm_ppi."
        ),
        parameters={
            "type": "object",
            "properties": {
                "gene": {"type": "string", "description": "Substrate gene symbol"},
                "uniprot_ac": {"type": "string", "description": "Substrate UniProt AC"},
                "partner_gene": {"type": "string", "description": "Interactor gene symbol"},
                "partner_uniprot": {
                    "type": "string",
                    "description": "Interactor UniProt accession",
                },
                "site_position": {
                    "type": "integer",
                    "description": "PTM site residue position",
                },
                "effect": {
                    "type": "string",
                    "enum": ["Enhance", "Inhibit", "all"],
                    "description": "PPI affinity effect filter",
                },
                "ptm_type": {
                    "type": "string",
                    "description": "PTM type filter (e.g. Phos, Acetyl)",
                },
            },
            "required": [],
        },
        handler=_ptmint_ppi,
    )
