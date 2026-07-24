"""PTMD tools — disease-associated PTM associations (local index).

Stage 3 (disease) tool:
  ptmd_disease — PTM–disease associations (PDAs) from PTMD 2.0

Data: data/disease/PTMD/
Homepage: https://ptmd.biocuckoo.cn/
PMID: 39329270  DOI: 10.1093/nar/gkae850

PDA state codes:
  U/D — upregulation / downregulation of PTM levels
  A/P — absence / presence of PTMs
  C/N — creation / disruption of PTM sites
"""

from __future__ import annotations

import logging
from typing import Any

from app.sources.catalog import get_catalog
from app.sources.query import index_exists, query_records
from app.tools.registry import registry

logger = logging.getLogger(__name__)

_STATE_LABELS = {
    "U": "upregulation of PTM level",
    "D": "downregulation of PTM level",
    "A": "absence of PTM",
    "P": "presence of PTM",
    "C": "creation of PTM site",
    "N": "disruption of PTM site",
}

_LIT_FIELDS = (
    "uniprot", "position", "gene", "protein_name", "organism",
    "type", "state", "disease", "pmid", "sentence",
)
_PUB_FIELDS = (
    "pdas_id", "uniprot", "position", "gene", "type", "state", "disease",
    "residue", "mutation_site", "source", "enzyme", "is_experimental",
    "pmid", "sentence", "celltype",
)


def _pick(row: dict[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    out = {k: row.get(k) for k in fields if row.get(k) not in (None, "")}
    st = out.get("state")
    if st in _STATE_LABELS:
        out["state_label"] = _STATE_LABELS[st]
    sent = out.get("sentence")
    if isinstance(sent, str) and len(sent) > 280:
        out["sentence"] = sent[:277] + "..."
    return out


def _query_table(
    file_id: str,
    *,
    gene: str | None,
    uniprot_ac: str | None,
    position: int | None,
    disease: str | None,
    ptm_type: str | None,
    state: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    if not index_exists("ptmd", file_id):
        raise FileNotFoundError(
            f"PTMD {file_id} index missing. Run: python -m app.sources.build_index ptmd"
        )
    equals_ci: dict[str, str] = {}
    equals: dict[str, str] = {}
    if uniprot_ac:
        equals_ci["uniprot"] = uniprot_ac
    elif gene:
        equals_ci["gene"] = gene
    if position is not None:
        equals["position"] = str(position)
    if disease:
        equals_ci["disease"] = disease
    if ptm_type and ptm_type.lower() not in ("all", ""):
        equals_ci["type"] = ptm_type
    if state and state.lower() not in ("all", ""):
        equals_ci["state"] = state.upper() if len(state) == 1 else state

    return query_records(
        "ptmd",
        file_id,
        equals=equals or None,
        equals_ci=equals_ci or None,
        limit=limit,
    )


def _ptmd_disease(
    gene: str | None = None,
    uniprot_ac: str | None = None,
    position: int | None = None,
    disease: str | None = None,
    ptm_type: str | None = None,
    state: str | None = None,
    source: str = "both",
    limit: int = 40,
) -> dict[str, Any]:
    """Query PTMD PTM–disease associations (literature and/or public PDAs)."""
    if not any([gene, uniprot_ac, disease]):
        return {
            "error": "Provide at least one of: gene, uniprot_ac, disease",
            "summary": "Missing query key for PTMD",
        }

    src = (source or "both").strip().lower()
    if src not in ("both", "literature", "public"):
        return {
            "error": "source must be both|literature|public",
            "summary": f"Invalid PTMD source '{source}'",
        }

    per = min(limit, 80)
    lit_rows: list[dict[str, Any]] = []
    pub_rows: list[dict[str, Any]] = []
    try:
        if src in ("both", "literature"):
            lit_rows = _query_table(
                "literature",
                gene=gene,
                uniprot_ac=uniprot_ac,
                position=position,
                disease=disease,
                ptm_type=ptm_type,
                state=state,
                limit=per,
            )
        if src in ("both", "public"):
            # Prefer literature; fill remaining budget from public
            remain = per if src == "public" else max(per - len(lit_rows), min(15, per))
            if remain > 0:
                pub_rows = _query_table(
                    "public",
                    gene=gene,
                    uniprot_ac=uniprot_ac,
                    position=position,
                    disease=disease,
                    ptm_type=ptm_type,
                    state=state,
                    limit=remain,
                )
    except FileNotFoundError as e:
        return {"error": str(e), "summary": str(e)}
    except Exception as e:
        logger.error("PTMD query failed: %s", e)
        return {"error": str(e), "summary": f"PTMD query failed: {e}"}

    lit = [_pick(r, _LIT_FIELDS) for r in lit_rows]
    pub = [_pick(r, _PUB_FIELDS) for r in pub_rows]
    total = len(lit) + len(pub)

    keys = []
    if gene:
        keys.append(f"gene={gene}")
    if uniprot_ac:
        keys.append(f"uniprot={uniprot_ac}")
    if position is not None:
        keys.append(f"pos={position}")
    if disease:
        keys.append(f"disease={disease}")
    if state:
        keys.append(f"state={state}")

    summary = (
        f"PTMD: {total} PDA(s) for {', '.join(keys) or 'query'} "
        f"(literature={len(lit)}, public={len(pub)}; source={src})."
    )
    if total == 0:
        summary += " No matching PTM–disease associations."

    manifest = get_catalog().get("ptmd")
    return {
        "summary": summary,
        "gene": gene,
        "uniprot_ac": uniprot_ac,
        "position": position,
        "disease": disease,
        "ptm_type": ptm_type,
        "state": state,
        "source_filter": src,
        "total": total,
        "literature": lit,
        "public": pub,
        "state_legend": _STATE_LABELS,
        "source": "PTMD",
        "access": "local",
        "homepage": manifest.homepage if manifest else "https://ptmd.biocuckoo.cn/",
        "pmid": manifest.pmid if manifest else "39329270",
        "doi": manifest.doi if manifest else "10.1093/nar/gkae850",
    }


def register_ptmd_tools() -> None:
    registry.register(
        name="ptmd_disease",
        description=(
            "Query PTMD 2.0 for disease-associated PTMs (PDAs). Returns literature "
            "curated associations (with PMID) and/or integrated public PDAs. States: "
            "U/D (up/down PTM level), A/P (absence/presence), C/N (create/disrupt site). "
            "Distinct from dbPTM."
        ),
        parameters={
            "type": "object",
            "properties": {
                "gene": {"type": "string", "description": "Gene symbol"},
                "uniprot_ac": {"type": "string", "description": "UniProt accession"},
                "position": {
                    "type": "integer",
                    "description": "PTM site residue position",
                },
                "disease": {
                    "type": "string",
                    "description": "Disease name (e.g. Breast cancer)",
                },
                "ptm_type": {
                    "type": "string",
                    "description": "PTM type (e.g. Phosphorylation, Acetylation)",
                },
                "state": {
                    "type": "string",
                    "enum": ["U", "D", "A", "P", "C", "N", "all"],
                    "description": "PDA state code filter",
                },
                "source": {
                    "type": "string",
                    "enum": ["both", "literature", "public"],
                    "description": "Which PTMD table(s) to query (default both)",
                },
            },
            "required": [],
        },
        handler=_ptmd_disease,
    )
