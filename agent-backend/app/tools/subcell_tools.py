"""SubCELL tools — compartment-specific protein interactions (local index).

Stage 3 WHERE / Stage 4 WHY tool:
  subcell_scsi — SCSIs (protein–protein) in a named subcellular compartment
                 plus protein location annotations

Data: data/localization/SubCELL/
Homepage: https://subcell.idrblab.cn/
PMID: 39373488  DOI: 10.1093/nar/gkae863
"""

from __future__ import annotations

import logging
from typing import Any

from app.sources.catalog import get_catalog
from app.sources.query import index_exists, open_index, query_records
from app.sources.uniprot_id import resolve_identity
from app.tools.registry import registry

logger = logging.getLogger(__name__)

_ORG_TAXON = {"human": 9606, "mouse": 10090, "rat": 10116, "yeast": 559292}


def _meta() -> dict[str, Any]:
    m = get_catalog().get("subcell")
    return {
        "source": "SubCELL",
        "access": "local",
        "homepage": (m.homepage if m else None) or "https://subcell.idrblab.cn/",
        "pmid": (m.pmid if m else None) or "39373488",
        "doi": (m.doi if m else None) or "10.1093/nar/gkae863",
    }


def _find_proteins(
    gene: str | None,
    uniprot_ac: str | None,
    organism: str | None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    if not index_exists("subcell", "proteins"):
        raise FileNotFoundError(
            "SubCELL proteins index missing. Run: "
            "python -m app.sources.prepare_subcell && python -m app.sources.build_index subcell"
        )
    equals_ci: dict[str, str] = {}
    if uniprot_ac:
        equals_ci["uniprot_ac"] = uniprot_ac
    elif gene:
        equals_ci["gene"] = gene
    else:
        return []
    if organism and organism.lower() in _ORG_TAXON:
        equals_ci["organism"] = organism.lower()
    return query_records("subcell", "proteins", equals_ci=equals_ci, limit=limit)


def _query_interactions_for_molecule(
    molecule_id: str,
    compartment: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    manifest = get_catalog().require("subcell")
    meta = manifest.file_by_id("interactions")
    assert meta is not None
    conn = open_index(manifest, meta)
    if conn is None:
        raise FileNotFoundError("SubCELL interactions index missing")
    try:
        where = ['("molecule_a" = ? OR "molecule_b" = ?)']
        params: list[Any] = [molecule_id, molecule_id]
        if compartment:
            where.append(
                '(LOWER("compartment_name") LIKE ? OR LOWER("compartment_id") = ?)'
            )
            params.extend([f"%{compartment.lower()}%", compartment.lower()])
        sql = f'SELECT * FROM records WHERE {" AND ".join(where)} LIMIT ?'
        params.append(limit)
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def _partner_fields(row: dict[str, Any], query_mid: str) -> dict[str, Any]:
    if row.get("molecule_a") == query_mid:
        return {
            "partner_molecule_id": row.get("molecule_b"),
            "partner_gene": row.get("gene_b"),
            "partner_uniprot": row.get("uniprot_b"),
            "partner_protein": row.get("protein_b"),
            "partner_organism": row.get("organism_b"),
        }
    return {
        "partner_molecule_id": row.get("molecule_a"),
        "partner_gene": row.get("gene_a"),
        "partner_uniprot": row.get("uniprot_a"),
        "partner_protein": row.get("protein_a"),
        "partner_organism": row.get("organism_a"),
    }


def _subcell_scsi(
    gene: str | None = None,
    uniprot_ac: str | None = None,
    organism: str = "human",
    compartment: str | None = None,
    include_locations: bool = True,
    limit: int = 40,
) -> dict[str, Any]:
    """Query SubCELL compartment-specific PPIs for a protein."""
    if not gene and not uniprot_ac:
        return {
            "error": "Provide gene or uniprot_ac",
            "summary": "Missing query for SubCELL",
        }

    identity = None
    g = (gene or "").strip() or None
    ac = (uniprot_ac or "").strip().upper() or None
    if g or ac:
        identity = resolve_identity(
            uniprot_ac=ac,
            gene=g,
            organism_id=_ORG_TAXON.get((organism or "human").lower(), 9606),
        )
        if identity:
            g = identity.get("gene") or g
            ac = identity.get("uniprot_ac") or ac

    try:
        proteins = _find_proteins(g, ac, organism)
        if not proteins and g and ac:
            proteins = _find_proteins(g, None, organism) or _find_proteins(None, ac, organism)
    except FileNotFoundError as e:
        return {"error": str(e), "summary": str(e)}

    if not proteins:
        return {
            "summary": f"SubCELL: no protein entry for {ac or g}",
            "gene": g,
            "uniprot_ac": ac,
            "total": 0,
            "interactions": [],
            "locations": [],
            **_meta(),
        }

    lim = max(1, min(int(limit or 40), 80))
    interactions: list[dict[str, Any]] = []
    seen: set[tuple] = set()
    for prot in proteins:
        mid = prot["molecule_id"]
        try:
            rows = _query_interactions_for_molecule(mid, compartment, lim * 2)
        except FileNotFoundError as e:
            return {"error": str(e), "summary": str(e)}
        for row in rows:
            partner = _partner_fields(row, mid)
            key = (
                partner.get("partner_molecule_id"),
                row.get("compartment_id"),
                row.get("scsi_type"),
            )
            if key in seen:
                continue
            seen.add(key)
            interactions.append({
                "query_molecule_id": mid,
                "query_gene": prot.get("gene"),
                "query_uniprot": prot.get("uniprot_ac"),
                "compartment_id": row.get("compartment_id"),
                "compartment": row.get("compartment_name"),
                "scsi_type": row.get("scsi_type"),
                "source_db": "SubCELL",
                **partner,
            })
            if len(interactions) >= lim:
                break
        if len(interactions) >= lim:
            break

    locations: list[dict[str, Any]] = []
    if include_locations and index_exists("subcell", "locations"):
        for prot in proteins[:3]:
            equals_ci: dict[str, str] = {"molecule_id": prot["molecule_id"]}
            if compartment:
                # post-filter by name
                locs = query_records(
                    "subcell", "locations", equals_ci=equals_ci, limit=50
                )
                locs = [
                    loc for loc in locs
                    if compartment.lower() in str(loc.get("compartment_name") or "").lower()
                    or compartment.lower() == str(loc.get("compartment_id") or "").lower()
                ]
            else:
                locs = query_records(
                    "subcell", "locations", equals_ci=equals_ci, limit=20
                )
            for loc in locs:
                locations.append({
                    "molecule_id": loc.get("molecule_id"),
                    "gene": loc.get("gene"),
                    "uniprot_ac": loc.get("uniprot_ac"),
                    "compartment_id": loc.get("compartment_id"),
                    "compartment": loc.get("compartment_name"),
                    "organism": loc.get("organism"),
                })

    keys = [x for x in (g, ac, organism, compartment) if x]
    examples: list[str] = []
    for i in interactions[:6]:
        partner = i.get("partner_gene") or i.get("partner_uniprot") or "?"
        pname = i.get("partner_protein")
        comp = i.get("compartment") or i.get("compartment_id") or "compartment"
        note = f"{i.get('query_gene') or g or '?'}–{partner}"
        if pname:
            note += f" ({pname})"
        note += f" in {comp}"
        if i.get("scsi_type"):
            note += f" [{i['scsi_type']}]"
        i["note"] = note
        examples.append(note)

    summary = (
        f"SubCELL: {len(interactions)} compartment-specific PPI(s)"
        + (f" + {len(locations)} location(s)" if locations else "")
        + f" for {', '.join(map(str, keys))}."
    )
    if examples:
        summary += " Examples: " + " ".join(examples)

    return {
        "summary": summary,
        "gene": g,
        "uniprot_ac": ac,
        "uniprot_identity": identity,
        "organism": organism,
        "compartment_filter": compartment,
        "proteins": proteins[:5],
        "total": len(interactions),
        "interactions": interactions,
        "locations": locations[:30],
        **_meta(),
    }


def register_subcell_tools() -> None:
    registry.register(
        name="subcell_scsi",
        description=(
            "Query SubCELL for subcellular compartment-specific protein–protein "
            "interactions (SCSIs) and protein location annotations. Use in Stage 3 "
            "WHERE when asking where a protein interacts (nucleus, mitochondrion, …)."
        ),
        parameters={
            "type": "object",
            "properties": {
                "gene": {"type": "string"},
                "uniprot_ac": {"type": "string"},
                "organism": {
                    "type": "string",
                    "enum": ["human", "mouse", "rat", "yeast"],
                },
                "compartment": {
                    "type": "string",
                    "description": "Optional compartment name filter (e.g. Nucleus, Mitochondrion)",
                },
                "include_locations": {
                    "type": "boolean",
                    "description": "Also return protein location annotations (default true)",
                },
                "limit": {"type": "integer"},
            },
            "required": [],
        },
        handler=_subcell_scsi,
    )
