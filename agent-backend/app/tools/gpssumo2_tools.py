"""GPS-SUMO 2.0 tools — curated experimental SUMOylation sites and SIMs.

Stage 1 WHO tool:
  gpssumo2_sites — literature/database-curated SUMOylation lysines + SIMs
                   from the GPS-SUMO 2.0 training/test sets (real data)

Data: data/enzymes/GPS-SUMO2/ (Wang et al. NAR 2024, PMID 38709873)
Homepage: https://sumo.biocuckoo.cn/
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
    "name": "GPS-SUMO 2.0",
    "homepage": "https://sumo.biocuckoo.cn/",
    "pmid": "38709873",
    "doi": "10.1093/nar/gkae346",
}

_ORG_ALIAS = {
    "human": "human",
    "homo sapiens": "human",
    "mouse": "mouse",
    "mus musculus": "mouse",
    "rat": "rat",
    "rattus norvegicus": "rat",
    "yeast": "yeast",
    "saccharomyces cerevisiae": "yeast",
}


def _meta() -> dict[str, Any]:
    m = get_catalog().get("gpssumo2")
    return {
        "source": _DEFAULTS["name"],
        "access": "local",
        "homepage": (m.homepage if m else None) or _DEFAULTS["homepage"],
        "pmid": (m.pmid if m else None) or _DEFAULTS["pmid"],
        "doi": (m.doi if m else None) or _DEFAULTS["doi"],
    }


def _norm_org(organism: str | None) -> str | None:
    if organism is None or str(organism).strip() == "":
        return "human"
    key = str(organism).strip().lower()
    if key in ("any", "all", "*"):
        return None
    return _ORG_ALIAS.get(key, key)


def _split_pmids(raw: Any) -> list[str]:
    text = str(raw or "").strip()
    if not text:
        return []
    out: list[str] = []
    for p in text.replace(",", ";").split(";"):
        p = p.strip()
        if p.isdigit() and p not in out:
            out.append(p)
    return out


def _compact_site(row: dict[str, Any], gene: str | None = None) -> dict[str, Any]:
    pos = row.get("position")
    out = {
        "gene": gene,
        "uniprot": row.get("uniprot") or row.get("uniprot_base"),
        "position": int(pos) if str(pos or "").isdigit() else pos,
        "residue": row.get("residue") or "K",
        "site": f"K{pos}" if pos else None,
        "peptide": row.get("peptide"),
        "organism": row.get("organism"),
        "source_dbs": row.get("source_dbs") or None,
        "pmids": _split_pmids(row.get("pmids")),
        "dataset_split": row.get("dataset_split"),
        "evidence": "curated",
        "record_type": "sumoylation_site",
    }
    return {k: v for k, v in out.items() if v not in (None, "", [])}


def _compact_sim(row: dict[str, Any], gene: str | None = None) -> dict[str, Any]:
    start = row.get("position_start")
    end = row.get("position_end")
    out = {
        "gene": gene,
        "uniprot": row.get("uniprot") or row.get("uniprot_base"),
        "position_start": int(start) if str(start or "").isdigit() else start,
        "position_end": int(end) if str(end or "").isdigit() else end,
        "position": row.get("position") or (
            f"{start}-{end}" if start and end else None
        ),
        "peptide": row.get("peptide"),
        "organism": row.get("organism"),
        "source_dbs": row.get("source_dbs") or None,
        "pmids": _split_pmids(row.get("pmids")),
        "evidence": "curated",
        "record_type": "sim",
    }
    return {k: v for k, v in out.items() if v not in (None, "", [])}


def _summarize(
    sites: list[dict[str, Any]],
    sims: list[dict[str, Any]],
    keys: list[str],
) -> str:
    if not sites and not sims:
        return f"GPS-SUMO 2.0: no curated SUMOylation sites or SIMs for {', '.join(keys)}."
    parts = []
    if sites:
        examples = []
        for h in sites[:3]:
            examples.append(
                f"{h.get('gene') or h.get('uniprot')} {h.get('site')}"
                + (f" (PMID {','.join(h.get('pmids') or [])})" if h.get("pmids") else "")
            )
        parts.append(
            f"{len(sites)} curated SUMOylation site(s)"
            + (f" e.g. " + "; ".join(examples) if examples else "")
        )
    if sims:
        examples = []
        for h in sims[:3]:
            examples.append(
                f"{h.get('gene') or h.get('uniprot')} SIM {h.get('position')}"
            )
        parts.append(
            f"{len(sims)} curated SIM(s)"
            + (f" e.g. " + "; ".join(examples) if examples else "")
        )
    return f"GPS-SUMO 2.0: " + "; ".join(parts) + f" for {', '.join(keys)}."


def _gpssumo2_sites(
    gene: str | None = None,
    uniprot_ac: str | None = None,
    position: int | None = None,
    organism: str | None = "human",
    include_sims: bool = True,
    limit: int = 40,
) -> dict[str, Any]:
    """Query curated GPS-SUMO 2.0 SUMOylation sites and optional SIMs."""
    if not (gene or uniprot_ac):
        return {
            "error": "Provide gene or uniprot_ac",
            "summary": "Missing query key for GPS-SUMO 2.0",
            "found": False,
            **_meta(),
        }

    if not index_exists("gpssumo2", "sumoylation_sites"):
        return {
            "error": (
                "GPS-SUMO 2.0 index missing. Run: "
                "python -m app.sources.prepare_gpssumo2 && "
                "python -m app.sources.build_index gpssumo2"
            ),
            "summary": "GPS-SUMO 2.0 index not built yet",
            "found": False,
            **_meta(),
        }

    identity = None
    g = (gene or "").strip() or None
    ac = (uniprot_ac or "").strip().upper() or None
    if g or ac:
        try:
            identity = resolve_identity(gene=g, uniprot_ac=ac)
        except Exception as e:
            logger.warning("UniProt resolve failed: %s", e)
            identity = None
        if identity:
            if identity.get("gene"):
                g = identity["gene"]
            if identity.get("uniprot_ac"):
                ac = identity["uniprot_ac"]

    org = _norm_org(organism)
    keys = [x for x in (g, ac, f"K{position}" if position else None, org) if x]

    equals: dict[str, str] = {}
    equals_ci: dict[str, str] = {}
    if ac:
        equals_ci["uniprot_base"] = ac.split("-")[0]
    if position is not None:
        equals["position"] = str(int(position))
    if org:
        equals["organism"] = org

    if not equals_ci.get("uniprot_base"):
        return {
            "error": "Could not resolve UniProt accession for the query",
            "summary": "GPS-SUMO 2.0: unresolved identity",
            "found": False,
            "gene": g,
            "uniprot_ac": ac,
            **_meta(),
        }

    try:
        raw_sites = query_records(
            "gpssumo2",
            "sumoylation_sites",
            equals=equals or None,
            equals_ci=equals_ci or None,
            limit=max(int(limit), 1),
        )
    except Exception as e:
        logger.error("GPS-SUMO 2.0 site query failed: %s", e, exc_info=True)
        return {
            "error": str(e),
            "summary": f"GPS-SUMO 2.0 query failed: {e}",
            "found": False,
            **_meta(),
        }

    sites = [_compact_site(r, gene=g) for r in raw_sites]

    sims: list[dict[str, Any]] = []
    if include_sims and index_exists("gpssumo2", "sims") and ac:
        sim_equals: dict[str, str] = {}
        sim_equals_ci: dict[str, str] = {"uniprot_base": ac.split("-")[0]}
        if org:
            sim_equals["organism"] = org
        try:
            raw_sims = query_records(
                "gpssumo2",
                "sims",
                equals=sim_equals or None,
                equals_ci=sim_equals_ci,
                limit=max(int(limit), 1),
            )
        except Exception as e:
            logger.warning("GPS-SUMO 2.0 SIM query failed: %s", e)
            raw_sims = []

        for r in raw_sims:
            item = _compact_sim(r, gene=g)
            if position is not None:
                try:
                    s = int(item.get("position_start") or 0)
                    epos = int(item.get("position_end") or 0)
                    if not (s <= int(position) <= epos):
                        continue
                except (TypeError, ValueError):
                    pass
            sims.append(item)
            if len(sims) >= limit:
                break

    found = bool(sites or sims)
    return {
        "summary": _summarize(sites, sims, keys or ["query"]),
        "found": found,
        "total": len(sites) + len(sims),
        "site_total": len(sites),
        "sim_total": len(sims),
        "gene": g,
        "uniprot_ac": ac,
        "position": position,
        "organism": org or "any",
        "uniprot_identity": identity,
        "sites": sites[:limit],
        "sims": sims[:limit],
        "note": (
            "Curated experimental SUMOylation sites / SIMs from the GPS-SUMO 2.0 "
            "training and independent test sets (not online predictor scores)."
        ),
        **_meta(),
    }


def register_gpssumo2_tools() -> None:
    registry.register(
        name="gpssumo2_sites",
        description=(
            "Query curated experimental SUMOylation sites and SUMO-interacting "
            "motifs (SIMs) from the GPS-SUMO 2.0 training/test sets "
            "(Wang et al. NAR 2024; PMID 38709873). These are real "
            "literature/database-backed sites used for model training — not "
            "computational predictions. Query by gene or UniProt (± lysine "
            "position); optional organism filter."
        ),
        parameters={
            "type": "object",
            "properties": {
                "gene": {
                    "type": "string",
                    "description": "Substrate gene symbol (e.g. TP53, PML)",
                },
                "uniprot_ac": {
                    "type": "string",
                    "description": "UniProt accession (e.g. P04637)",
                },
                "position": {
                    "type": "integer",
                    "description": "Lysine position (SUMO site or within a SIM)",
                },
                "organism": {
                    "type": "string",
                    "description": "human|mouse|rat|yeast|any (default human)",
                    "default": "human",
                },
                "include_sims": {
                    "type": "boolean",
                    "description": "Also return curated SIMs (default true)",
                    "default": True,
                },
                "limit": {
                    "type": "integer",
                    "description": "Max sites/SIMs to return (default 40)",
                    "default": 40,
                },
            },
            "required": [],
        },
        handler=_gpssumo2_sites,
    )
