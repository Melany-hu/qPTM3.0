"""DrugBank tools — drug–target associations (local index).

Stage 1 (WHO) tool:
  drugbank_targets — drugs targeting a protein (UniProt / gene / drug name)

Data: data/drug/DrugBank/ (NAR 2024, PMID 37953279, doi:10.1093/nar/gkad976)
Homepage: https://go.drugbank.com
"""

from __future__ import annotations

import logging
from typing import Any

from app.sources.catalog import get_catalog
from app.sources.query import index_exists, query_records
from app.sources.uniprot_id import resolve_identity
from app.tools.registry import registry

logger = logging.getLogger(__name__)

_COMPACT = (
    "uniprot", "db_id", "drug_name", "drug_type", "groups", "know_action", "pmids",
)


def _meta() -> dict[str, Any]:
    m = get_catalog().get("drugbank")
    return {
        "source": "DrugBank",
        "access": "local",
        "homepage": (m.homepage if m else None) or "https://go.drugbank.com",
        "pmid": (m.pmid if m else None) or "37953279",
        "doi": (m.doi if m else None) or "10.1093/nar/gkad976",
    }


def _compact_row(row: dict[str, Any]) -> dict[str, Any]:
    out = {k: row.get(k) for k in _COMPACT if row.get(k) not in (None, "")}
    db_id = out.get("db_id")
    if db_id:
        out["url"] = f"https://go.drugbank.com/drugs/{db_id}"
    return out


def _drugbank_targets(
    gene: str | None = None,
    uniprot_ac: str | None = None,
    drug: str | None = None,
    db_id: str | None = None,
    know_action: str | None = None,
    approved_only: bool = False,
    limit: int = 40,
) -> dict[str, Any]:
    """Query DrugBank drug–target links for a protein or drug."""
    if not any([gene, uniprot_ac, drug, db_id]):
        return {
            "error": "Provide at least one of: gene, uniprot_ac, drug, db_id",
            "summary": "Missing query key for DrugBank",
        }

    if not index_exists("drugbank", "targets"):
        return {
            "error": "DrugBank index missing. Run: python -m app.sources.build_index drugbank",
            "summary": "DrugBank index not built yet",
        }

    identity = None
    resolved_ac = (uniprot_ac or "").strip().upper() or None
    if gene and not resolved_ac:
        identity = resolve_identity(gene=gene)
        if identity and identity.get("uniprot_ac"):
            resolved_ac = identity["uniprot_ac"]
    elif resolved_ac:
        identity = resolve_identity(uniprot_ac=resolved_ac, gene=gene)

    equals_ci: dict[str, str] = {}
    equals: dict[str, str] = {}

    if resolved_ac:
        equals_ci["uniprot"] = resolved_ac
    if db_id:
        equals_ci["db_id"] = db_id.strip().upper()
    elif drug:
        equals_ci["drug_name"] = drug
    if know_action and know_action.strip().lower() not in ("all", "any", "", "na"):
        equals_ci["know_action"] = know_action

    if not equals_ci and not equals:
        return {
            "error": (
                f"Could not resolve UniProt for gene={gene}; "
                "provide uniprot_ac or a drug name"
            ),
            "summary": "DrugBank: protein identity unresolved",
        }

    fetch_limit = min(max(limit * 3, limit), 200) if approved_only else min(limit, 80)
    try:
        rows = query_records(
            "drugbank",
            "targets",
            equals=equals or None,
            equals_ci=equals_ci or None,
            limit=fetch_limit,
        )
    except Exception as e:
        logger.error("DrugBank query failed: %s", e, exc_info=True)
        return {"error": str(e), "summary": f"DrugBank query failed: {e}"}

    if approved_only:
        rows = [
            r for r in rows
            if "approved" in str(r.get("groups") or "").lower()
        ]

    rows = rows[: min(limit, 80)]
    compact = [_compact_row(r) for r in rows]

    keys = []
    if gene:
        keys.append(f"gene={gene}")
    if resolved_ac:
        keys.append(f"uniprot={resolved_ac}")
    if drug:
        keys.append(f"drug={drug}")
    if db_id:
        keys.append(f"db_id={db_id}")
    if know_action:
        keys.append(f"action={know_action}")
    if approved_only:
        keys.append("approved_only")

    summary = f"DrugBank: {len(compact)} drug–target link(s) for {', '.join(keys)}"
    if not compact:
        summary += ". No matching entries in local DrugBank table."

    return {
        "summary": summary,
        "gene": (identity or {}).get("gene") or gene,
        "uniprot_ac": resolved_ac,
        "uniprot_identity": identity,
        "drug": drug,
        "db_id": db_id,
        "know_action": know_action,
        "approved_only": approved_only,
        "total": len(compact),
        "associations": compact,
        **_meta(),
    }


def register_drugbank_tools() -> None:
    registry.register(
        name="drugbank_targets",
        description=(
            "Query DrugBank for drugs that target a protein (or proteins targeted "
            "by a drug). Returns DrugBank ID, drug name/type, approval groups, "
            "known pharmacological action, and literature PMIDs. Use in Stage 1 "
            "WHO for upstream drug context (complementary to PMADS/decryptM)."
        ),
        parameters={
            "type": "object",
            "properties": {
                "gene": {"type": "string", "description": "Gene symbol (resolved via UniProt)"},
                "uniprot_ac": {"type": "string", "description": "UniProt accession"},
                "drug": {"type": "string", "description": "Drug name (e.g. Gefitinib)"},
                "db_id": {"type": "string", "description": "DrugBank ID (e.g. DB00317)"},
                "know_action": {
                    "type": "string",
                    "description": "Optional action filter (inhibitor, agonist, substrate, …)",
                },
                "approved_only": {
                    "type": "boolean",
                    "description": "If true, keep only groups containing 'approved'",
                },
                "limit": {"type": "integer", "description": "Max hits (default 40)"},
            },
            "required": [],
        },
        handler=_drugbank_targets,
    )
