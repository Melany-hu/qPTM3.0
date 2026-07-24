"""PhosphoSitePlus tools — four PSP aspects for the qPTM agent.

  Stage 1 WHO:
    psp_kinase_substrate — kinase→substrate site relationships
  Stage 4 WHY:
    psp_regulatory     — ON_FUNCTION / ON_PROCESS / interaction effects
    psp_disease_sites  — disease-correlated PTM sites
    psp_ptmvar         — mutations at/near PTM sites (Class I/II)

Data split by research aspect under data/{regulation,enzymes,disease}/Phospho*SitePlus/
Homepage: https://www.phosphosite.org
PMID: 30445427  DOI: 10.1093/nar/gky1159
"""

from __future__ import annotations

import logging
import re
from typing import Any

from app.sources.catalog import get_catalog
from app.sources.query import index_exists, query_records
from app.tools.registry import registry

logger = logging.getLogger(__name__)

_PSP_DOI = "10.1093/nar/gky1159"
_PSP_PMID = "30445427"
_PSP_HOME = "https://www.phosphosite.org"

_MOD_MAP = {
    "p": "phosphorylation",
    "ac": "acetylation",
    "ub": "ubiquitylation",
    "me": "methylation",
    "me1": "methylation",
    "me2": "methylation",
    "me3": "methylation",
    "sm": "sumoylation",
    "g": "glycosylation",
    "ga": "glycosylation",
    "gl": "glycosylation",
}


def _meta() -> dict[str, Any]:
    m = get_catalog().get("psp_regulation") or get_catalog().get("psp_enzymes")
    return {
        "homepage": (m.homepage if m else None) or _PSP_HOME,
        "doi": (m.doi if m else None) or _PSP_DOI,
        "pmid": (m.pmid if m else None) or _PSP_PMID,
        "source": "PhosphoSitePlus",
    }


def _parse_mod_rsd(mod_rsd: str) -> tuple[str, int, str] | None:
    """Parse S15-p, S15, or bare 15 into (residue|'', position, ptm_type|'')."""
    text = (mod_rsd or "").strip()
    match = re.match(r"^([A-Z])?(\d+)(?:-([a-z0-9]+))?$", text, re.I)
    if not match:
        return None
    residue, pos_str, mod_code = match.groups()
    ptm = _MOD_MAP.get((mod_code or "").lower(), (mod_code or "").lower()) if mod_code else ""
    return (residue.upper() if residue else ""), int(pos_str), ptm


def _split_list(val: Any) -> list[str]:
    if not val:
        return []
    text = str(val).strip()
    if not text:
        return []
    parts = re.split(r"[;|]", text)
    return [p.strip() for p in parts if p.strip()]


def _missing_index(source_id: str, file_id: str) -> dict[str, Any]:
    return {
        "error": (
            f"PhosphoSitePlus index missing ({source_id}/{file_id}). "
            f"Run: python -m app.sources.build_index {source_id}"
        ),
        "summary": f"PhosphoSitePlus {file_id} index not built",
        "found": False,
        **_meta(),
    }


# ── psp_regulatory ────────────────────────────────────────────────

def _psp_regulatory(
    uniprot_ac: str | None = None,
    position: int | None = None,
    gene: str | None = None,
    ptm_type: str = "phosphorylation",
    limit: int = 20,
) -> dict[str, Any]:
    """Look up PhosphoSitePlus regulatory annotations for a PTM site."""
    if not any([uniprot_ac, gene]):
        return {"error": "Provide uniprot_ac and/or gene", "summary": "Missing query key", "found": False}

    if not index_exists("psp_regulation", "regulatory"):
        return _missing_index("psp_regulation", "regulatory")

    equals_ci: dict[str, str] = {}
    equals: dict[str, str] = {}
    if uniprot_ac:
        equals_ci["uniprot"] = uniprot_ac
    elif gene:
        equals_ci["gene"] = gene
    if position is not None:
        equals["position"] = str(position)

    try:
        rows = query_records(
            "psp_regulation",
            "regulatory",
            equals=equals or None,
            equals_ci=equals_ci or None,
            limit=limit,
        )
    except Exception as e:
        logger.error("psp_regulatory failed: %s", e, exc_info=True)
        return {"error": str(e), "summary": f"PhosphoSitePlus regulatory query failed: {e}", "found": False}

    # Optional PTM type preference
    preferred = []
    others = []
    for r in rows:
        parsed = _parse_mod_rsd(str(r.get("mod_rsd") or ""))
        r_ptm = parsed[2] if parsed else ""
        item = {
            "gene": r.get("gene"),
            "protein": r.get("protein"),
            "uniprot": r.get("uniprot"),
            "mod_rsd": r.get("mod_rsd"),
            "position": r.get("position"),
            "ptm_type": r_ptm,
            "on_function": _split_list(r.get("on_function")),
            "on_process": _split_list(r.get("on_process")),
            "on_prot_interact": _split_list(r.get("on_prot_interact")),
            "on_other_interact": _split_list(r.get("on_other_interact")),
            "notes": r.get("notes") or "",
            "pmids": _split_list(r.get("pmids")),
            "domain": r.get("domain") or "",
            "organism": r.get("organism") or "",
        }
        if ptm_type and r_ptm == ptm_type:
            preferred.append(item)
        else:
            others.append(item)

    hits = preferred or others
    if not hits:
        target = f"{uniprot_ac or gene}"
        if position is not None:
            target += f" position {position}"
        return {
            "summary": f"No PhosphoSitePlus regulatory annotation found for {target}.",
            "found": False,
            "available": True,
            "total": 0,
            "hits": [],
            **_meta(),
        }

    top = hits[0]
    parts = []
    if top["on_function"]:
        parts.append(f"Function: {', '.join(top['on_function'])}")
    if top["on_process"]:
        parts.append(f"Process: {', '.join(top['on_process'])}")
    if top["on_prot_interact"]:
        parts.append(f"Protein interactions: {', '.join(top['on_prot_interact'])}")
    summary = (
        f"PhosphoSitePlus regulatory annotation for "
        f"{top.get('uniprot') or top.get('gene')} {top.get('mod_rsd')}: "
        + ("; ".join(parts) if parts else "entry found")
    )
    if len(hits) > 1:
        summary += f" (+{len(hits) - 1} more)"

    return {
        "summary": summary,
        "found": True,
        "available": True,
        "total": len(hits),
        "uniprot_ac": top.get("uniprot"),
        "position": int(top["position"]) if str(top.get("position") or "").isdigit() else position,
        "ptm_type": top.get("ptm_type") or ptm_type,
        "on_function": top["on_function"],
        "on_process": top["on_process"],
        "on_prot_interact": top["on_prot_interact"],
        "on_other_interact": top["on_other_interact"],
        "notes": top["notes"],
        "pmids": top["pmids"],
        "hits": hits,
        **_meta(),
    }


# ── psp_kinase_substrate ──────────────────────────────────────────

def _psp_kinase_substrate(
    gene: str | None = None,
    uniprot_ac: str | None = None,
    position: int | None = None,
    kinase: str | None = None,
    evidence: str = "any",
    limit: int = 40,
) -> dict[str, Any]:
    """Query PSP kinase→substrate relationships for a site or kinase."""
    if not any([gene, uniprot_ac, kinase]):
        return {
            "error": "Provide gene, uniprot_ac (substrate), and/or kinase",
            "summary": "Missing query key for PSP kinases",
        }

    if not index_exists("psp_enzymes", "kinase_substrate"):
        return _missing_index("psp_enzymes", "kinase_substrate")

    equals_ci: dict[str, str] = {}
    equals: dict[str, str] = {}
    if uniprot_ac:
        equals_ci["sub_uniprot"] = uniprot_ac
    elif gene:
        equals_ci["sub_gene"] = gene
    if kinase:
        equals_ci["kinase"] = kinase
        # also allow gene column (kinase gene symbol)
        if not gene and not uniprot_ac:
            equals_ci = {"gene": kinase}
            # Wait - if only kinase provided we should query kinase column.
            # Using kinase field is correct; GENE is also kinase gene.
            equals_ci = {"kinase": kinase}
    if position is not None:
        equals["position"] = str(position)

    try:
        rows = query_records(
            "psp_enzymes",
            "kinase_substrate",
            equals=equals or None,
            equals_ci=equals_ci or None,
            limit=max(limit * 2, limit),
        )
    except Exception as e:
        logger.error("psp_kinase_substrate failed: %s", e, exc_info=True)
        return {"error": str(e), "summary": f"PSP kinase query failed: {e}"}

    ev = (evidence or "any").strip().lower()
    hits = []
    for r in rows:
        in_vivo = bool(str(r.get("in_vivo_rxn") or "").strip())
        in_vitro = bool(str(r.get("in_vitro_rxn") or "").strip())
        if ev == "in_vivo" and not in_vivo:
            continue
        if ev == "in_vitro" and not in_vitro:
            continue
        parsed = _parse_mod_rsd(str(r.get("sub_mod_rsd") or ""))
        hits.append({
            "kinase": r.get("kinase") or r.get("gene"),
            "kinase_gene": r.get("gene"),
            "kin_uniprot": r.get("kin_uniprot"),
            "kin_organism": r.get("kin_organism"),
            "substrate": r.get("substrate"),
            "sub_gene": r.get("sub_gene"),
            "sub_uniprot": r.get("sub_uniprot"),
            "sub_organism": r.get("sub_organism"),
            "mod_rsd": r.get("sub_mod_rsd"),
            "position": r.get("position"),
            "ptm_type": parsed[2] if parsed else "",
            "site_flank": r.get("site_flank") or r.get("site_+/-7_aa") or "",
            "domain": r.get("domain") or "",
            "in_vivo": in_vivo,
            "in_vitro": in_vitro,
            "evidence": (
                "in_vivo+in_vitro" if in_vivo and in_vitro
                else ("in_vivo" if in_vivo else ("in_vitro" if in_vitro else "unspecified"))
            ),
        })
        if len(hits) >= limit:
            break

    keys = [x for x in [kinase, gene, uniprot_ac] if x]
    if position is not None:
        keys.append(f"pos {position}")
    summary = (
        f"PhosphoSitePlus: {len(hits)} kinase–substrate hit(s) for "
        f"{', '.join(keys) or 'query'}"
    )
    return {
        "summary": summary,
        "total": len(hits),
        "hits": hits,
        **_meta(),
    }


# ── psp_disease_sites ─────────────────────────────────────────────

def _psp_disease_sites(
    gene: str | None = None,
    uniprot_ac: str | None = None,
    position: int | None = None,
    disease: str | None = None,
    limit: int = 40,
) -> dict[str, Any]:
    """Query PSP disease-associated PTM sites."""
    if not any([gene, uniprot_ac, disease]):
        return {
            "error": "Provide gene, uniprot_ac, and/or disease",
            "summary": "Missing query key for PSP disease sites",
        }

    if not index_exists("psp_disease", "disease_sites"):
        return _missing_index("psp_disease", "disease_sites")

    equals_ci: dict[str, str] = {}
    equals: dict[str, str] = {}
    if uniprot_ac:
        equals_ci["uniprot"] = uniprot_ac
    elif gene:
        equals_ci["gene"] = gene
    if disease:
        equals_ci["disease"] = disease
    if position is not None:
        equals["position"] = str(position)

    try:
        rows = query_records(
            "psp_disease",
            "disease_sites",
            equals=equals or None,
            equals_ci=equals_ci or None,
            limit=limit,
        )
    except Exception as e:
        logger.error("psp_disease_sites failed: %s", e, exc_info=True)
        return {"error": str(e), "summary": f"PSP disease query failed: {e}"}

    # If disease was free-text and exact match failed, broaden by gene then filter
    if disease and not rows and (gene or uniprot_ac):
        equals_ci.pop("disease", None)
        rows = query_records(
            "psp_disease",
            "disease_sites",
            equals=equals or None,
            equals_ci=equals_ci or None,
            limit=max(limit * 5, limit),
        )
        dlow = disease.lower()
        rows = [r for r in rows if dlow in str(r.get("disease") or "").lower()][:limit]

    hits = []
    for r in rows:
        parsed = _parse_mod_rsd(str(r.get("mod_rsd") or ""))
        hits.append({
            "disease": r.get("disease"),
            "alteration": r.get("alteration"),
            "gene": r.get("gene"),
            "protein": r.get("protein"),
            "uniprot": r.get("uniprot"),
            "mod_rsd": r.get("mod_rsd"),
            "position": r.get("position"),
            "ptm_type": parsed[2] if parsed else "",
            "domain": r.get("domain") or "",
            "organism": r.get("organism") or "",
            "pmids": _split_list(r.get("pmids")),
            "notes": r.get("notes") or "",
        })

    keys = [x for x in [gene, uniprot_ac, disease] if x]
    if position is not None:
        keys.append(f"pos {position}")
    return {
        "summary": f"PhosphoSitePlus: {len(hits)} disease-associated site hit(s) for {', '.join(keys) or 'query'}",
        "total": len(hits),
        "hits": hits,
        **_meta(),
    }


# ── psp_ptmvar ────────────────────────────────────────────────────

def _psp_ptmvar(
    gene: str | None = None,
    uniprot_ac: str | None = None,
    position: int | None = None,
    disease: str | None = None,
    var_class: str = "any",
    limit: int = 40,
) -> dict[str, Any]:
    """Query PSP PTMVars — mutations at (Class I) or within ±5 aa (Class II) of PTMs."""
    if not any([gene, uniprot_ac]):
        return {
            "error": "Provide gene and/or uniprot_ac",
            "summary": "Missing query key for PSP PTMVar",
        }

    if not index_exists("psp_regulation", "ptmvar"):
        return _missing_index("psp_regulation", "ptmvar")

    equals_ci: dict[str, str] = {}
    equals: dict[str, str] = {}
    if uniprot_ac:
        equals_ci["uniprot"] = uniprot_ac
    elif gene:
        equals_ci["gene"] = gene
    if position is not None:
        equals["position"] = str(position)

    try:
        rows = query_records(
            "psp_regulation",
            "ptmvar",
            equals=equals or None,
            equals_ci=equals_ci or None,
            limit=max(limit * 3, limit),
        )
    except Exception as e:
        logger.error("psp_ptmvar failed: %s", e, exc_info=True)
        return {"error": str(e), "summary": f"PSP PTMVar query failed: {e}"}

    # If querying by site position, also fetch Class II (±5) by gene/uniprot then filter
    if position is not None and (gene or uniprot_ac):
        broad = query_records(
            "psp_regulation",
            "ptmvar",
            equals_ci={("uniprot" if uniprot_ac else "gene"): (uniprot_ac or gene or "")},
            limit=max(limit * 10, 100),
        )
        # merge unique
        seen = {id(r) for r in rows}
        for r in broad:
            if id(r) not in seen:
                rows.append(r)

    wanted = (var_class or "any").strip().lower()
    hits = []
    for r in rows:
        try:
            mut_pos = int(str(r.get("mut_position") or "").strip())
        except ValueError:
            continue
        try:
            mod_pos = int(str(r.get("position") or r.get("mod_rsd") or "").strip())
        except ValueError:
            parsed = _parse_mod_rsd(str(r.get("mod_rsd") or ""))
            mod_pos = parsed[1] if parsed else None
        if mod_pos is None:
            continue

        delta = abs(mut_pos - mod_pos)
        raw_klass = str(r.get("var_class") or "").strip().upper()
        if raw_klass in ("I", "II"):
            klass = raw_klass
        else:
            klass = "I" if delta == 0 else ("II" if delta <= 5 else None)
        if klass is None:
            continue
        if wanted in ("i", "class_i", "class1", "1") and klass != "I":
            continue
        if wanted in ("ii", "class_ii", "class2", "2") and klass != "II":
            continue

        diseases = str(r.get("diseases") or "")
        if disease and disease.lower() not in diseases.lower():
            continue

        if position is not None:
            # Keep variants whose PTM site or mutation falls in the queried neighborhood
            if mod_pos != position and abs(mod_pos - position) > 5 and abs(mut_pos - position) > 5:
                continue

        mod_aa = r.get("mod_aa") or ""
        hits.append({
            "gene": r.get("gene"),
            "uniprot": r.get("uniprot"),
            "mod_rsd": f"{mod_aa}{mod_pos}" if mod_aa else str(mod_pos),
            "mod_position": mod_pos,
            "mod_type": r.get("mod_type"),
            "mut_position": mut_pos,
            "aa_change": r.get("aa_change"),
            "wt_aa": r.get("wt_aa"),
            "var_aa": r.get("var_aa"),
            "var_type": r.get("var_type"),
            "var_class": klass,
            "distance": delta,
            "diseases": diseases if diseases not in ("", "-") else "",
            "mut_source": r.get("mut_source"),
            "dbsnp": r.get("dbsnp") if r.get("dbsnp") not in (None, "-", "") else "",
            "ftid": r.get("ftid") or "",
            "site_seq": r.get("mod-site_seq") or r.get("mod_site_seq") or "",
        })
        if len(hits) >= limit:
            break

    keys = [x for x in [gene, uniprot_ac] if x]
    if position is not None:
        keys.append(f"site {position}")
    return {
        "summary": (
            f"PhosphoSitePlus PTMVar: {len(hits)} variant(s) overlapping PTM sites "
            f"for {', '.join(keys) or 'query'} "
            f"(Class I = PTM residue; Class II = ±5 aa)"
        ),
        "total": len(hits),
        "class_i": sum(1 for h in hits if h["var_class"] == "I"),
        "class_ii": sum(1 for h in hits if h["var_class"] == "II"),
        "hits": hits,
        **_meta(),
    }


# ── Register ──────────────────────────────────────────────────────

def register_psp_tools() -> None:
    """Register all PhosphoSitePlus tools."""
    registry.register(
        name="psp_regulatory",
        description=(
            "Look up PhosphoSitePlus regulatory site annotations (ON_FUNCTION, "
            "ON_PROCESS, protein/other interactions). Use for Stage 4 WHY: what "
            "happens when this site is modified. Local Regulatory_sites index."
        ),
        parameters={
            "type": "object",
            "properties": {
                "uniprot_ac": {"type": "string", "description": "UniProt accession"},
                "gene": {"type": "string", "description": "Gene symbol"},
                "position": {"type": "integer", "description": "Residue position"},
                "ptm_type": {
                    "type": "string",
                    "description": "Preferred PTM type (default phosphorylation)",
                },
                "limit": {"type": "integer", "description": "Max hits (default 20)"},
            },
        },
        handler=_psp_regulatory,
    )

    registry.register(
        name="psp_kinase_substrate",
        description=(
            "Query PhosphoSitePlus Kinase_Substrate_Dataset for kinases that modify "
            "a substrate site (or substrates of a kinase). Evidence flags: in vivo / "
            "in vitro. Use for Stage 1 WHO."
        ),
        parameters={
            "type": "object",
            "properties": {
                "gene": {"type": "string", "description": "Substrate gene symbol"},
                "uniprot_ac": {"type": "string", "description": "Substrate UniProt accession"},
                "position": {"type": "integer", "description": "Substrate site position"},
                "kinase": {"type": "string", "description": "Kinase gene/name filter"},
                "evidence": {
                    "type": "string",
                    "enum": ["any", "in_vivo", "in_vitro"],
                    "description": "Evidence filter (default any)",
                },
                "limit": {"type": "integer", "description": "Max hits (default 40)"},
            },
        },
        handler=_psp_kinase_substrate,
    )

    registry.register(
        name="psp_disease_sites",
        description=(
            "Query PhosphoSitePlus Disease-associated_sites for PTM sites correlated "
            "with disease states (increased/decreased etc.). Use for Stage 4 WHY."
        ),
        parameters={
            "type": "object",
            "properties": {
                "gene": {"type": "string", "description": "Gene symbol"},
                "uniprot_ac": {"type": "string", "description": "UniProt accession"},
                "position": {"type": "integer", "description": "Site position"},
                "disease": {"type": "string", "description": "Disease name filter"},
                "limit": {"type": "integer", "description": "Max hits (default 40)"},
            },
        },
        handler=_psp_disease_sites,
    )

    registry.register(
        name="psp_ptmvar",
        description=(
            "Query PhosphoSitePlus PTMVars: missense variants that change a PTM residue "
            "(Class I) or fall within ±5 residues (Class II), with disease/cancer "
            "annotations. Use for Stage 4 WHY (mutation perturbation of PTMs)."
        ),
        parameters={
            "type": "object",
            "properties": {
                "gene": {"type": "string", "description": "Gene symbol"},
                "uniprot_ac": {"type": "string", "description": "UniProt accession"},
                "position": {
                    "type": "integer",
                    "description": "PTM site position (includes Class II neighborhood)",
                },
                "disease": {"type": "string", "description": "Disease name substring filter"},
                "var_class": {
                    "type": "string",
                    "enum": ["any", "I", "II"],
                    "description": "Class I (exact PTM residue) or II (±5 aa)",
                },
                "limit": {"type": "integer", "description": "Max hits (default 40)"},
            },
        },
        handler=_psp_ptmvar,
    )
