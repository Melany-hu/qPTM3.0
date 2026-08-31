"""Extract standardized source citations from tool results.

Each tool returns heterogeneous data; this module normalizes source metadata
so the LLM synthesis step can attribute findings to specific databases.

Public API:
  attach_citations(tool, database, raw_result) -> ToolResult
"""

from __future__ import annotations

from typing import Any

from app.models.schemas import (
    Citation,
    EvidenceLevel,
    SourceType,
    ToolResult,
)
from app.workflow.planner import DATABASE_CATALOG

QPTM_URL = DATABASE_CATALOG["qPTM"]["url"]
IPTMNET_URL = DATABASE_CATALOG["iPTMnet"]["url"]
UNIPROT_URL = DATABASE_CATALOG["UniProt"]["url"]
INTERPRO_URL = DATABASE_CATALOG["InterPro"]["url"]
PFAM_URL = DATABASE_CATALOG["Pfam"]["url"]
PSP_URL = DATABASE_CATALOG["PhosphoSitePlus"]["url"]
WERAM_URL = DATABASE_CATALOG["WERAM"]["url"]
UBIBROWSER_URL = DATABASE_CATALOG["UbiBrowser"]["url"]
GPSUBER_URL = DATABASE_CATALOG["GPS-Uber"]["url"]
GPS6_URL = DATABASE_CATALOG["GPS 6.0"]["url"]
GPSSUMO2_URL = DATABASE_CATALOG["GPS-SUMO 2.0"]["url"]
KAKA_URL = DATABASE_CATALOG["KAKA"]["url"]
EKPI_URL = DATABASE_CATALOG["eKPI"]["url"]
DBPTM_URL = DATABASE_CATALOG["dbPTM"]["url"]
ACTIVEDRIVER_URL = DATABASE_CATALOG["ActiveDriverDB"]["url"]
PMADS_URL = DATABASE_CATALOG["PMADS"]["url"]
DRUGBANK_URL = DATABASE_CATALOG["DrugBank"]["url"]
DECRYPTM_URL = DATABASE_CATALOG["decryptM"]["url"]
PTMPHASE_URL = DATABASE_CATALOG["PTMPhaSe"]["url"]
DSCOP_URL = DATABASE_CATALOG["dSCOPE"]["url"]
PTMD_URL = DATABASE_CATALOG["PTMD"]["url"]
CANCERPROTEOME_URL = DATABASE_CATALOG["CancerProteome"]["url"]
PTMINT_URL = DATABASE_CATALOG["PTMint"]["url"]
STRING_URL = DATABASE_CATALOG["STRING"]["url"]
BIOGRID_URL = DATABASE_CATALOG["BioGRID"]["url"]
INTACT_URL = DATABASE_CATALOG["IntAct"]["url"]
REACTOME_URL = DATABASE_CATALOG["Reactome"]["url"]
KEGG_URL = DATABASE_CATALOG["KEGG"]["url"]
PATHBANK_URL = DATABASE_CATALOG["PathBank"]["url"]
PTMCODE_URL = DATABASE_CATALOG["PTMcode2"]["url"]
NLSDB_URL = DATABASE_CATALOG["NLSdb"]["url"]
INULOC_URL = DATABASE_CATALOG["iNuLoC"]["url"]
COMPARTMENTS_URL = DATABASE_CATALOG["COMPARTMENTS"]["url"]
SUBCELL_URL = DATABASE_CATALOG["SubCELL"]["url"]
FUNCSCORE_URL = DATABASE_CATALOG["Funcscore"]["url"]
STABILITY_PMC = "PMC9839724"
STABILITY_DOI = "10.1038/s41467-023-35795-8"
PUBTATOR_URL = DATABASE_CATALOG["PubTator3"]["url"]


def _db_meta(database: str) -> dict[str, str]:
    info = DATABASE_CATALOG.get(database, {})
    return {
        "source_db": info.get("name", database),
        "url": info.get("url", ""),
        "source_type": info.get("type", "database"),
    }


def _as_source_type(value: str | SourceType) -> SourceType:
    if isinstance(value, SourceType):
        return value
    try:
        return SourceType(value)
    except ValueError:
        return SourceType.database


def _as_evidence_level(value: str | EvidenceLevel) -> EvidenceLevel:
    if isinstance(value, EvidenceLevel):
        return value
    try:
        return EvidenceLevel(value)
    except ValueError:
        return EvidenceLevel.unknown


def _cite(
    citations: list[dict[str, Any]],
    *,
    source_db: str,
    label: str,
    source_type: str | SourceType = SourceType.database,
    evidence_level: str | EvidenceLevel = EvidenceLevel.experimental,
    pmid: str | None = None,
    doi: str | None = None,
    url: str | None = None,
    detail: str | None = None,
) -> str:
    """Append a citation and return its id (S1, S2, ...)."""
    cid = f"S{len(citations) + 1}"
    entry: dict[str, Any] = {
        "id": cid,
        "source_db": source_db,
        "label": label,
        "source_type": _as_source_type(source_type).value,
        "evidence_level": _as_evidence_level(evidence_level).value,
    }
    if pmid:
        entry["pmid"] = pmid
        entry["url"] = url or f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
    elif url:
        entry["url"] = url
    if doi:
        entry["doi"] = doi
    if detail:
        entry["detail"] = detail
    citations.append(entry)
    return cid


def extract_citations(
    tool_name: str,
    database: str,
    result: dict[str, Any],
) -> list[dict[str, Any]]:
    """Build citation list for a single tool result."""
    if "error" in result:
        return []

    citations: list[dict[str, Any]] = []
    meta = _db_meta(database)

    if tool_name == "qptm_search":
        _cite(
            citations,
            source_db="qPTM",
            label="qPTM quantitative PTM event search (experimental MS)",
            url=QPTM_URL,
            evidence_level=EvidenceLevel.experimental,
            detail=f"{result.get('total', 0)} events matched",
        )
        pmids: set[str] = set()
        for event in result.get("events", [])[:20]:
            pmid = event.get("pmid")
            if pmid and str(pmid).strip():
                pmids.add(str(pmid).strip())
        for pmid in sorted(pmids)[:8]:
            _cite(
                citations,
                source_db="qPTM",
                label=f"qPTM literature reference PMID {pmid}",
                source_type=SourceType.literature,
                pmid=pmid,
                evidence_level=EvidenceLevel.experimental,
            )

    elif tool_name == "qptm_site_conditions":
        _cite(
            citations,
            source_db="qPTM",
            label="qPTM site-specific condition quantification (experimental MS)",
            url=QPTM_URL,
            evidence_level=EvidenceLevel.experimental,
            detail=(
                f"{result.get('uniprot_ac', '')} "
                f"pos {result.get('position', '')}: "
                f"{result.get('total_conditions', 0)} conditions"
            ),
        )

    elif tool_name == "qptm_kinases":
        seen_sources: set[str] = set()
        for kinase in result.get("kinases", [])[:15]:
            src = kinase.get("source_db") or "qPTM"
            evidence = (kinase.get("evidence_type") or "unknown").lower()
            key = f"{src}:{evidence}"
            if key in seen_sources:
                continue
            seen_sources.add(key)
            if evidence == "experimental":
                level = EvidenceLevel.experimental
            elif evidence == "predicted":
                level = EvidenceLevel.predicted
            else:
                level = EvidenceLevel.unknown
            _cite(
                citations,
                source_db=f"qPTM ({src})",
                label=f"qPTM kinase data via {src} ({evidence})",
                source_type=(
                    SourceType.prediction
                    if level == EvidenceLevel.predicted
                    else SourceType.database
                ),
                evidence_level=level,
                url=QPTM_URL,
            )
        if not seen_sources:
            _cite(
                citations,
                source_db="qPTM",
                label="qPTM integrated kinase-substrate data (no hits)",
                url=QPTM_URL,
                evidence_level=EvidenceLevel.unknown,
            )

    elif tool_name == "iptmnet_enzymes":
        _cite(
            citations,
            source_db="iPTMnet",
            label="iPTMnet enzyme–substrate relationships",
            url=result.get("homepage") or IPTMNET_URL,
            doi=result.get("doi") or "10.1093/nar/gkx1104",
            pmid=str(result.get("pmid") or "29145615"),
            evidence_level=EvidenceLevel.curated,
            detail=f"{result.get('total', len(result.get('enzymes', [])))} enzyme–site hits",
        )
        pmids = {
            str(p).strip()
            for e in (result.get("enzymes") or [])[:20]
            for p in (e.get("pmids") or [])
            if str(p).strip().isdigit()
        }
        for pmid in sorted(pmids)[:6]:
            _cite(
                citations,
                source_db="iPTMnet",
                label=f"iPTMnet literature PMID {pmid}",
                source_type=SourceType.literature,
                pmid=pmid,
                evidence_level=EvidenceLevel.experimental,
            )

    elif tool_name == "iptmnet_ptm_ppi":
        _cite(
            citations,
            source_db="iPTMnet",
            label="iPTMnet PTM-dependent protein interactions",
            url=result.get("homepage") or IPTMNET_URL,
            doi=result.get("doi") or "10.1093/nar/gkx1104",
            pmid=str(result.get("pmid") or "29145615"),
            evidence_level=EvidenceLevel.curated,
            detail=f"{result.get('total', len(result.get('interactions', [])))} interactions",
        )
        pmids = {
            str(i.get("pmid")).strip()
            for i in (result.get("interactions") or [])
            if i.get("pmid") and str(i.get("pmid")).strip().isdigit()
        }
        for pmid in sorted(pmids)[:6]:
            _cite(
                citations,
                source_db="iPTMnet",
                label=f"iPTMnet PPI literature PMID {pmid}",
                source_type=SourceType.literature,
                pmid=pmid,
                evidence_level=EvidenceLevel.experimental,
            )

    elif tool_name == "psp_regulatory":
        _cite(
            citations,
            source_db="PhosphoSitePlus",
            label="PhosphoSitePlus regulatory site annotation",
            url=result.get("homepage") or PSP_URL,
            doi=result.get("doi") or "10.1093/nar/gky1159",
            pmid=str(result.get("pmid") or "30445427"),
            evidence_level=EvidenceLevel.curated,
            detail=f"found={result.get('found')}, hits={result.get('total', 0)}",
        )
        for pmid in (result.get("pmids") or [])[:6]:
            if str(pmid).isdigit():
                _cite(
                    citations,
                    source_db="PhosphoSitePlus",
                    label=f"PhosphoSitePlus literature PMID {pmid}",
                    source_type=SourceType.literature,
                    pmid=str(pmid),
                    evidence_level=EvidenceLevel.curated,
                )

    elif tool_name == "psp_kinase_substrate":
        _cite(
            citations,
            source_db="PhosphoSitePlus",
            label="PhosphoSitePlus kinase–substrate dataset",
            url=result.get("homepage") or PSP_URL,
            doi=result.get("doi") or "10.1093/nar/gky1159",
            pmid=str(result.get("pmid") or "30445427"),
            evidence_level=EvidenceLevel.curated,
            detail=f"{result.get('total', 0)} kinase–substrate hits",
        )

    elif tool_name == "weram_regulators":
        level = EvidenceLevel.curated
        if str(result.get("evidence") or "").lower() == "predicted":
            level = EvidenceLevel.predicted
        _cite(
            citations,
            source_db="WERAM",
            label="WERAM histone acetylation/methylation writers, erasers and readers",
            url=result.get("homepage") or WERAM_URL,
            doi=result.get("doi") or "10.1093/nar/gkw1011",
            pmid=str(result.get("pmid") or "27789692"),
            evidence_level=level,
            detail=f"{result.get('total', 0)} regulator records",
        )

    elif tool_name == "ubibrowser_interactions":
        known_n = int(result.get("known_total") or 0)
        pred_n = int(result.get("predicted_total") or 0)
        if known_n > 0 or (known_n == 0 and pred_n == 0):
            _cite(
                citations,
                source_db="UbiBrowser",
                label="UbiBrowser known/literature E3/DUB–substrate interactions",
                url=result.get("homepage") or UBIBROWSER_URL,
                doi=result.get("doi") or "10.1093/nar/gkab962",
                pmid=str(result.get("pmid") or "34634807"),
                evidence_level=EvidenceLevel.experimental,
                detail=f"known={known_n}",
            )
        if pred_n > 0:
            _cite(
                citations,
                source_db="UbiBrowser",
                label="UbiBrowser predicted E3/DUB–substrate interactions",
                source_type=SourceType.prediction,
                url=result.get("homepage") or UBIBROWSER_URL,
                doi=result.get("doi") or "10.1093/nar/gkab962",
                pmid=str(result.get("pmid") or "34634807"),
                evidence_level=EvidenceLevel.predicted,
                detail=f"predicted={pred_n}",
            )
        pmids = {
            str(i.get("pmid")).strip()
            for i in (result.get("interactions") or [])[:30]
            if i.get("pmid") and str(i.get("pmid")).strip().isdigit()
        }
        for pmid in sorted(pmids)[:6]:
            _cite(
                citations,
                source_db="UbiBrowser",
                label=f"UbiBrowser literature PMID {pmid}",
                source_type=SourceType.literature,
                pmid=pmid,
                evidence_level=EvidenceLevel.experimental,
            )

    elif tool_name == "gpsuber_e3_sites":
        _cite(
            citations,
            source_db="GPS-Uber",
            label="GPS-Uber site-specific E3–substrate relations (ssESRs)",
            url=result.get("homepage") or GPSUBER_URL,
            doi=result.get("doi") or "10.1093/bib/bbab574",
            pmid=str(result.get("pmid") or "35037020"),
            evidence_level=EvidenceLevel.curated,
            detail=f"{result.get('total', 0)} ssESR hits",
        )
        pmids = {
            str(p).strip()
            for i in (result.get("relations") or [])[:30]
            for p in (i.get("pmids") or [])
            if str(p).strip().isdigit()
        }
        for pmid in sorted(pmids)[:6]:
            _cite(
                citations,
                source_db="GPS-Uber",
                label=f"GPS-Uber literature PMID {pmid}",
                source_type=SourceType.literature,
                pmid=pmid,
                evidence_level=EvidenceLevel.experimental,
            )

    elif tool_name == "gps6_kinases":
        _cite(
            citations,
            source_db="GPS 6.0",
            label="GPS 6.0 kinase-specific phosphorylation sites",
            url=result.get("homepage") or GPS6_URL,
            doi=result.get("doi") or "10.1093/nar/gkad383",
            pmid=str(result.get("pmid") or "37158278"),
            evidence_level=EvidenceLevel.experimental,
            detail=f"{result.get('total', 0)} hits (min_score={result.get('min_score')})",
        )

    elif tool_name == "gpssumo2_sites":
        _cite(
            citations,
            source_db="GPS-SUMO 2.0",
            label="GPS-SUMO 2.0 curated SUMOylation sites / SIMs (training & test sets)",
            url=result.get("homepage") or GPSSUMO2_URL,
            doi=result.get("doi") or "10.1093/nar/gkae346",
            pmid=str(result.get("pmid") or "38709873"),
            evidence_level=EvidenceLevel.curated,
            detail=(
                f"sites={result.get('site_total', 0)}, "
                f"SIMs={result.get('sim_total', 0)}"
            ),
        )
        pmids = {
            str(p).strip()
            for row in (result.get("sites") or [])[:30] + (result.get("sims") or [])[:20]
            for p in (row.get("pmids") or [])
            if str(p).strip().isdigit()
        }
        for pmid in sorted(pmids)[:6]:
            _cite(
                citations,
                source_db="GPS-SUMO 2.0",
                label=f"GPS-SUMO 2.0 literature PMID {pmid}",
                source_type=SourceType.literature,
                pmid=pmid,
                evidence_level=EvidenceLevel.experimental,
            )

    elif tool_name == "kaka_kinase_mutations":
        _cite(
            citations,
            source_db="KAKA",
            label="KAKA kinase activity–related key alterations",
            url=result.get("homepage") or KAKA_URL,
            doi=result.get("doi") or "10.1016/j.jgg.2026.03.010",
            pmid=str(result.get("pmid") or "41839313"),
            evidence_level=EvidenceLevel.curated,
            detail=f"{result.get('total', 0)} curated alteration(s)",
        )
        pmids = {
            str(p).strip()
            for row in (result.get("alterations") or [])[:30]
            for p in (row.get("pmids") or [])
            if str(p).strip().isdigit()
        }
        for pmid in sorted(pmids)[:6]:
            _cite(
                citations,
                source_db="KAKA",
                label=f"KAKA literature PMID {pmid}",
                source_type=SourceType.literature,
                pmid=pmid,
                evidence_level=EvidenceLevel.experimental,
            )

    elif tool_name == "ekpi_kinases":
        n_exp = len(result.get("experimental_kinases") or [])
        n_pred = len(result.get("predicted_only_kinases") or [])
        _cite(
            citations,
            source_db="eKPI",
            label="eKPI kinase–phosphosite evidence (experimental + predicted)",
            url=result.get("homepage") or EKPI_URL,
            doi=result.get("doi") or "10.1093/bib/bbaf143",
            pmid=str(result.get("pmid") or "40194556"),
            evidence_level=(
                EvidenceLevel.curated if n_exp else EvidenceLevel.predicted
            ),
            detail=(
                f"{result.get('total', 0)} kinase(s) for "
                f"{result.get('site') or result.get('position') or ''} "
                f"(experimental×{n_exp}, predicted-only×{n_pred})"
            ),
        )
        pmids = {
            str(p).strip()
            for row in (result.get("kinases") or [])[:30]
            for p in (row.get("experimental_pmids") or [])
            if str(p).strip().isdigit()
        }
        for pmid in sorted(pmids)[:6]:
            _cite(
                citations,
                source_db="eKPI",
                label=f"eKPI experimental KPI PMID {pmid}",
                source_type=SourceType.literature,
                pmid=pmid,
                evidence_level=EvidenceLevel.experimental,
            )

    elif tool_name == "ekpi_quantitative":
        _cite(
            citations,
            source_db="eKPI",
            label="eKPI Quantitative kinase–phosphosite correlations",
            url=result.get("homepage") or EKPI_URL,
            doi=result.get("doi") or "10.1093/bib/bbaf143",
            pmid=str(result.get("pmid") or "40194556"),
            evidence_level=EvidenceLevel.predicted,
            detail=(
                f"{result.get('total', 0)} correlation(s) for "
                f"{result.get('site') or result.get('position') or ''} "
                f"(cohort={result.get('cohort')})"
            ),
        )
        pmids = {
            str(p).strip()
            for row in (result.get("correlations") or [])[:30]
            for p in [row.get("pmid")]
            if p and str(p).strip().isdigit()
        }
        for pmid in sorted(pmids)[:6]:
            _cite(
                citations,
                source_db="eKPI",
                label=f"eKPI cohort dataset PMID {pmid}",
                source_type=SourceType.literature,
                pmid=pmid,
                evidence_level=EvidenceLevel.experimental,
            )

    elif tool_name == "psp_disease_sites":
        _cite(
            citations,
            source_db="PhosphoSitePlus",
            label="PhosphoSitePlus disease-associated sites",
            url=result.get("homepage") or PSP_URL,
            doi=result.get("doi") or "10.1093/nar/gky1159",
            pmid=str(result.get("pmid") or "30445427"),
            evidence_level=EvidenceLevel.curated,
            detail=f"{result.get('total', 0)} disease–site hits",
        )

    elif tool_name == "psp_ptmvar":
        _cite(
            citations,
            source_db="PhosphoSitePlus",
            label="PhosphoSitePlus PTMVars (mutation–PTM overlap)",
            url=result.get("homepage") or PSP_URL,
            doi=result.get("doi") or "10.1093/nar/gky1159",
            pmid=str(result.get("pmid") or "30445427"),
            evidence_level=EvidenceLevel.curated,
            detail=(
                f"{result.get('total', 0)} variants "
                f"(Class I={result.get('class_i', 0)}, Class II={result.get('class_ii', 0)})"
            ),
        )

    elif tool_name == "uniprot_annotation":
        _cite(
            citations,
            source_db="UniProt",
            label=f"UniProt annotation for {result.get('uniprot_ac', '')}",
            url=UNIPROT_URL,
            evidence_level=EvidenceLevel.curated,
        )

    elif tool_name == "interpro_domains":
        _cite(
            citations,
            source_db="InterPro",
            label="InterPro protein domains / families",
            url=result.get("homepage") or INTERPRO_URL,
            doi=result.get("doi") or "10.1093/nar/gky1100",
            pmid=str(result.get("pmid") or "30398656"),
            evidence_level=EvidenceLevel.curated,
            detail=f"{result.get('total', 0)} match(es)",
        )

    elif tool_name == "pfam_domains":
        _cite(
            citations,
            source_db="Pfam",
            label="Pfam protein family signatures",
            url=result.get("homepage") or PFAM_URL,
            doi=result.get("doi") or "10.1093/nar/gky995",
            pmid=str(result.get("pmid") or "30357350"),
            evidence_level=EvidenceLevel.curated,
            detail=f"{result.get('total', 0)} match(es)",
        )

    elif tool_name == "dbptm_functional":
        _cite(
            citations,
            source_db="dbPTM",
            label="dbPTM nsSNP–disease associations",
            url=DBPTM_URL,
        )

    elif tool_name == "ptm_stability":
        _cite(
            citations,
            source_db="PTM-stability",
            label="PTM-stability curated table (compiled from Batista et al., 2023)",
            source_type=SourceType.curated_dataset,
            evidence_level=EvidenceLevel.curated,
            pmid=None,
            doi=STABILITY_DOI,
            url=f"https://www.ncbi.nlm.nih.gov/pmc/articles/{STABILITY_PMC}/",
            detail="Curation provenance: Nature Communications review PMC9839724",
        )
        seen_pmid: set[str] = set()
        for entry in result.get("entries", [])[:12]:
            for part in (entry.get("source") or "").replace(",", "|").split("|"):
                pmid = part.strip()
                if not pmid.isdigit() or pmid in seen_pmid:
                    continue
                seen_pmid.add(pmid)
                _cite(
                    citations,
                    source_db="PTM-stability",
                    label=(
                        f"Primary literature for "
                        f"{entry.get('gene', '')} "
                        f"{entry.get('ptm_type', '')} "
                        f"{entry.get('effect_direction', '')}".strip()
                    ),
                    source_type=SourceType.literature,
                    evidence_level=EvidenceLevel.experimental,
                    pmid=pmid,
                    url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                    detail=(entry.get("mechanism") or "")[:120] or None,
                )
                if len(seen_pmid) >= 5:
                    break
            if len(seen_pmid) >= 5:
                break

    elif tool_name == "activedriver_mutations":
        _cite(
            citations,
            source_db="ActiveDriverDB",
            label=(
                f"ActiveDriverDB mutations affecting PTM sites "
                f"({', '.join(result.get('datasets', [])) or 'local tables'})"
            ),
            url=result.get("homepage") or ACTIVEDRIVER_URL,
            detail=f"{result.get('total', 0)} hits for {result.get('gene', '')}",
        )

    elif tool_name == "activedriver_kinase_network":
        _cite(
            citations,
            source_db="ActiveDriverDB",
            label="ActiveDriverDB site-specific kinase–target network",
            url=ACTIVEDRIVER_URL,
            detail=f"{result.get('total', 0)} edges for {result.get('gene', '')}",
        )

    elif tool_name == "pmads_drug_ptm":
        _cite(
            citations,
            source_db="PMADS",
            label="PMADS drug–PTM–disease associations",
            url=result.get("homepage") or PMADS_URL,
            doi=result.get("doi") or "10.1093/nar/gkaf1033",
            pmid=str(result.get("pmid") or "41099621"),
            evidence_level=EvidenceLevel.curated,
            detail=(
                f"{result.get('total', 0)} hits "
                f"(filter={result.get('status_filter', '')})"
            ),
        )
        pmids: set[str] = set()
        for row in (result.get("associations") or [])[:20]:
            pmid = row.get("pmid")
            if pmid and str(pmid).strip().isdigit():
                pmids.add(str(pmid).strip())
        for pmid in sorted(pmids)[:6]:
            _cite(
                citations,
                source_db="PMADS",
                label=f"PMADS literature PMID {pmid}",
                source_type=SourceType.literature,
                pmid=pmid,
                evidence_level=EvidenceLevel.curated,
            )

    elif tool_name == "drugbank_targets":
        _cite(
            citations,
            source_db="DrugBank",
            label="DrugBank drug–target associations",
            url=result.get("homepage") or DRUGBANK_URL,
            doi=result.get("doi") or "10.1093/nar/gkad976",
            pmid=str(result.get("pmid") or "37953279"),
            evidence_level=EvidenceLevel.curated,
            detail=f"{result.get('total', 0)} hits",
        )
        pmids = set()
        for row in (result.get("associations") or [])[:20]:
            raw = str(row.get("pmids") or "")
            for part in raw.replace(";", ",").split(","):
                p = part.strip()
                if p.isdigit():
                    pmids.add(p)
        for pmid in sorted(pmids)[:6]:
            _cite(
                citations,
                source_db="DrugBank",
                label=f"DrugBank literature PMID {pmid}",
                source_type=SourceType.literature,
                pmid=pmid,
                evidence_level=EvidenceLevel.curated,
            )

    elif tool_name == "decryptm_drug_ptm":
        identity = result.get("uniprot_identity") or {}
        if identity.get("uniprot_ac"):
            _cite(
                citations,
                source_db="UniProt",
                label=(
                    f"UniProt identity {identity.get('gene') or ''} "
                    f"({identity.get('uniprot_ac')})"
                ).strip(),
                source_type=SourceType.database,
                url=identity.get("url") or UNIPROT_URL,
                evidence_level=EvidenceLevel.curated,
                detail=identity.get("protein_name") or identity.get("entry_name"),
            )
        _cite(
            citations,
            source_db="decryptM",
            label="decryptM drug–PTM dose-response (ProteomicsDB)",
            source_type=SourceType.database,
            url=result.get("explore_url") or result.get("homepage") or DECRYPTM_URL,
            doi=result.get("doi") or "10.1126/science.ade3925",
            pmid=str(result.get("pmid") or "36926954"),
            evidence_level=EvidenceLevel.experimental,
            detail=(
                f"{result.get('total', 0)} curves "
                f"(local={result.get('local_count', 0)}, "
                f"api={result.get('api_count', 0)})"
            ),
        )

    elif tool_name == "ptmphase_llps":
        _cite(
            citations,
            source_db="PTMPhaSe",
            label="PTMPhaSe curated PTM–LLPS experimental evidence",
            url=result.get("homepage") or PTMPHASE_URL,
            doi=result.get("doi") or "10.1038/s42004-025-01773-y",
            pmid=str(result.get("pmid") or "41360972"),
            evidence_level=EvidenceLevel.experimental,
            detail=f"{result.get('total', 0)} associations",
        )
        pmids = {
            str(r.get("pmid")).strip()
            for r in (result.get("associations") or [])
            if r.get("pmid") and str(r.get("pmid")).strip().isdigit()
        }
        for pmid in sorted(pmids)[:6]:
            _cite(
                citations,
                source_db="PTMPhaSe",
                label=f"PTMPhaSe literature PMID {pmid}",
                source_type=SourceType.literature,
                pmid=pmid,
                evidence_level=EvidenceLevel.experimental,
            )

    elif tool_name == "ptmphase_phosllps":
        _cite(
            citations,
            source_db="PTMPhaSe/PhosLLPS",
            label="PhosLLPS predicted functional phosphorylation sites (LLPS)",
            source_type=SourceType.prediction,
            url=result.get("homepage") or "https://ptmphase.sjtu.edu.cn/Predictor",
            doi=result.get("doi") or "10.1038/s42004-025-01773-y",
            pmid=str(result.get("pmid") or "41360972"),
            evidence_level=EvidenceLevel.predicted,
            detail=f"{result.get('total', 0)} predictions",
        )

    elif tool_name == "dscope_literature":
        _cite(
            citations,
            source_db="dSCOPE",
            label="dSCOPE literature-curated LLPS-driving segments",
            url=result.get("homepage") or DSCOP_URL,
            doi=result.get("doi") or "10.1093/bib/bbac550",
            pmid=str(result.get("pmid") or "36528388"),
            evidence_level=EvidenceLevel.experimental,
            detail=f"{result.get('total', 0)} segments",
        )
        pmids = set()
        for r in result.get("segments") or []:
            for part in str(r.get("pmid") or "").replace(";", " ").split():
                part = part.strip()
                if part.isdigit():
                    pmids.add(part)
        for pmid in sorted(pmids)[:6]:
            _cite(
                citations,
                source_db="dSCOPE",
                label=f"dSCOPE literature PMID {pmid}",
                source_type=SourceType.literature,
                pmid=pmid,
                evidence_level=EvidenceLevel.experimental,
            )

    elif tool_name == "dscope_predictions":
        _cite(
            citations,
            source_db="dSCOPE",
            label="dSCOPE predicted PS-driving regions (human proteome)",
            source_type=SourceType.prediction,
            url=result.get("homepage") or DSCOP_URL,
            doi=result.get("doi") or "10.1093/bib/bbac550",
            pmid=str(result.get("pmid") or "36528388"),
            evidence_level=EvidenceLevel.predicted,
            detail=f"{result.get('total', 0)} regions",
        )

    elif tool_name == "ptmd_disease":
        _cite(
            citations,
            source_db="PTMD",
            label="PTMD disease-associated PTM associations (PDAs)",
            url=result.get("homepage") or PTMD_URL,
            doi=result.get("doi") or "10.1093/nar/gkae850",
            pmid=str(result.get("pmid") or "39329270"),
            evidence_level=EvidenceLevel.curated,
            detail=(
                f"{result.get('total', 0)} PDAs "
                f"(lit={len(result.get('literature') or [])}, "
                f"public={len(result.get('public') or [])})"
            ),
        )
        pmids = {
            str(r.get("pmid")).strip()
            for r in (result.get("literature") or [])[:20]
            if r.get("pmid") and str(r.get("pmid")).strip().isdigit()
        }
        for pmid in sorted(pmids)[:6]:
            _cite(
                citations,
                source_db="PTMD",
                label=f"PTMD literature PMID {pmid}",
                source_type=SourceType.literature,
                pmid=pmid,
                evidence_level=EvidenceLevel.curated,
            )

    elif tool_name == "cancerproteome_disease":
        _cite(
            citations,
            source_db="CancerProteome",
            label="CancerProteome tumor vs control PTM/protein quantification",
            url=result.get("homepage") or CANCERPROTEOME_URL,
            doi=result.get("doi") or "10.1093/nar/gkad824",
            pmid=str(result.get("pmid") or "37823596"),
            evidence_level=EvidenceLevel.experimental,
            detail=(
                f"PTM hits={result.get('ptm_total', 0)}, "
                f"protein hits={result.get('protein_total', 0)}"
            ),
        )

    elif tool_name == "ptmint_ppi":
        _cite(
            citations,
            source_db="PTMint",
            label="PTMint curated PTM–PPI regulation evidence",
            url=result.get("homepage") or PTMINT_URL,
            doi=result.get("doi") or "10.1093/bioinformatics/btac823",
            pmid=str(result.get("pmid") or "36548389"),
            evidence_level=EvidenceLevel.experimental,
            detail=f"{result.get('total', 0)} associations",
        )
        pmids = {
            str(r.get("pmid")).strip()
            for r in (result.get("as_substrate") or []) + (result.get("as_partner") or [])
            if r.get("pmid") and str(r.get("pmid")).strip().isdigit()
        }
        for pmid in sorted(pmids)[:6]:
            _cite(
                citations,
                source_db="PTMint",
                label=f"PTMint literature PMID {pmid}",
                source_type=SourceType.literature,
                pmid=pmid,
                evidence_level=EvidenceLevel.experimental,
            )

    elif tool_name == "string_ppi":
        _cite(
            citations,
            source_db="STRING",
            label="STRING protein association network",
            url=result.get("homepage") or STRING_URL,
            doi=result.get("doi") or "10.1093/nar/gkae1113",
            pmid=str(result.get("pmid") or "39558183"),
            evidence_level=EvidenceLevel.curated,
            detail=(
                f"{result.get('total', 0)} partners "
                f"(type={result.get('network_type', '')}, "
                f"score≥{result.get('required_score', '')})"
            ),
        )

    elif tool_name == "biogrid_interactions":
        _cite(
            citations,
            source_db="BioGRID",
            label="BioGRID curated interactions",
            url=result.get("homepage") or BIOGRID_URL,
            doi=result.get("doi") or "10.1002/pro.3978",
            pmid=str(result.get("pmid") or "33070389"),
            evidence_level=EvidenceLevel.experimental,
            detail=f"{result.get('total', 0)} interactions",
        )
        pmids = set()
        for row in result.get("interactions") or []:
            for p in row.get("pmids") or []:
                if str(p).isdigit():
                    pmids.add(str(p))
        for pmid in sorted(pmids)[:6]:
            _cite(
                citations,
                source_db="BioGRID",
                label=f"BioGRID literature PMID {pmid}",
                source_type=SourceType.literature,
                pmid=pmid,
                evidence_level=EvidenceLevel.experimental,
            )

    elif tool_name == "intact_interactions":
        _cite(
            citations,
            source_db="IntAct",
            label="IntAct molecular interactions",
            url=result.get("homepage") or INTACT_URL,
            doi=result.get("doi") or "10.1093/nar/gkab1006",
            pmid=str(result.get("pmid") or "34761267"),
            evidence_level=EvidenceLevel.experimental,
            detail=f"{result.get('total', 0)} interactions",
        )
        pmids = set()
        for row in result.get("interactions") or []:
            for p in row.get("pmids") or []:
                if str(p).isdigit():
                    pmids.add(str(p))
        for pmid in sorted(pmids)[:6]:
            _cite(
                citations,
                source_db="IntAct",
                label=f"IntAct literature PMID {pmid}",
                source_type=SourceType.literature,
                pmid=pmid,
                evidence_level=EvidenceLevel.experimental,
            )

    elif tool_name == "reactome_pathways":
        _cite(
            citations,
            source_db="Reactome",
            label="Reactome pathways",
            url=result.get("homepage") or REACTOME_URL,
            doi=result.get("doi") or "10.1093/nar/gkx1132",
            pmid=str(result.get("pmid") or "29145629"),
            evidence_level=EvidenceLevel.curated,
            detail=f"{result.get('total', 0)} pathways",
        )

    elif tool_name == "kegg_pathways":
        _cite(
            citations,
            source_db="KEGG",
            label="KEGG pathways",
            url=result.get("homepage") or KEGG_URL,
            doi=result.get("doi") or "10.1093/nar/gky962",
            pmid=str(result.get("pmid") or "30321428"),
            evidence_level=EvidenceLevel.curated,
            detail=f"{result.get('total', 0)} pathways",
        )

    elif tool_name == "pathbank_pathways":
        _cite(
            citations,
            source_db="PathBank",
            label="PathBank/SMPDB protein–pathway associations",
            url=result.get("homepage") or PATHBANK_URL,
            doi=result.get("doi") or "10.1093/nar/gkz861",
            pmid=str(result.get("pmid") or "31602469"),
            evidence_level=EvidenceLevel.curated,
            detail=f"{result.get('total', 0)} pathways",
        )

    elif tool_name == "ptmcode_associations":
        _cite(
            citations,
            source_db="PTMcode2",
            label="PTMcode2 PTM–PTM functional associations (human/mouse/rat/yeast curated subset)",
            url=result.get("homepage") or PTMCODE_URL,
            doi=result.get("doi") or "10.1093/nar/gku1081",
            pmid=str(result.get("pmid") or "25361965"),
            evidence_level=EvidenceLevel.predicted,
            detail=(
                f"within={result.get('within_total', 0)}, "
                f"between={result.get('between_total', 0)}"
            ),
        )

    elif tool_name == "inuloc_nls_nes":
        exp_n = len(result.get("experimental") or [])
        pred_n = len(result.get("predicted") or [])
        dnl_n = len(result.get("dnl") or [])
        if exp_n > 0 or (exp_n == 0 and pred_n == 0 and dnl_n == 0):
            _cite(
                citations,
                source_db="NLSdb",
                label="NLSdb experimental NLS/NES motifs",
                source_type=SourceType.database,
                url=result.get("homepage") or NLSDB_URL,
                doi=result.get("doi") or "10.1093/nar/gkx1021",
                pmid=str(result.get("pmid") or "29106588"),
                evidence_level=EvidenceLevel.experimental,
                detail=f"experimental={exp_n}",
            )
        if pred_n > 0:
            _cite(
                citations,
                source_db="NLSdb",
                label="NLSdb predicted/in silico NLS/NES motifs",
                source_type=SourceType.prediction,
                url=result.get("homepage") or NLSDB_URL,
                doi=result.get("doi") or "10.1093/nar/gkx1021",
                pmid=str(result.get("pmid") or "29106588"),
                evidence_level=EvidenceLevel.predicted,
                detail=f"predicted={pred_n}",
            )
        if dnl_n:
            _cite(
                citations,
                source_db="iNuLoC",
                label="iNuLoC DNL (determinants of nuclear localization)",
                source_type=SourceType.prediction,
                url=result.get("inuloc_homepage") or INULOC_URL,
                doi=result.get("inuloc_doi") or "10.1038/s41467-025-57858-8",
                pmid=str(result.get("inuloc_pmid") or "40087285"),
                evidence_level=EvidenceLevel.predicted,
                detail=f"{dnl_n} DNL region(s)",
            )

    elif tool_name == "inuloc_nuclear_prob":
        _cite(
            citations,
            source_db="iNuLoC",
            label="iNuLoC nuclear localization probability",
            source_type=SourceType.prediction,
            url=result.get("homepage") or INULOC_URL,
            doi=result.get("doi") or "10.1038/s41467-025-57858-8",
            pmid=str(result.get("pmid") or "40087285"),
            evidence_level=EvidenceLevel.predicted,
            detail=f"{result.get('total', 0)} records",
        )

    elif tool_name == "compartments_localization":
        identity = result.get("uniprot_identity") or {}
        if identity.get("uniprot_ac"):
            _cite(
                citations,
                source_db="UniProt",
                label=(
                    f"UniProt identity {identity.get('gene') or ''} "
                    f"({identity.get('uniprot_ac')})"
                ).strip(),
                source_type=SourceType.database,
                url=identity.get("url") or UNIPROT_URL,
                evidence_level=EvidenceLevel.curated,
                detail=identity.get("protein_name") or identity.get("entry_name"),
            )
        _cite(
            citations,
            source_db="COMPARTMENTS",
            label="COMPARTMENTS subcellular localization evidence",
            source_type=SourceType.database,
            url=result.get("homepage") or COMPARTMENTS_URL,
            doi=result.get("doi") or "10.1093/database/bau012",
            pmid=str(result.get("pmid") or "24573882"),
            evidence_level=EvidenceLevel.curated,
            detail=f"{result.get('total', 0)} localization(s)",
        )

    elif tool_name == "subcell_scsi":
        _cite(
            citations,
            source_db="SubCELL",
            label="SubCELL compartment-specific molecular interactions",
            url=result.get("homepage") or SUBCELL_URL,
            doi=result.get("doi") or "10.1093/nar/gkae863",
            pmid=str(result.get("pmid") or "39373488"),
            evidence_level=EvidenceLevel.curated,
            detail=(
                f"{result.get('total', 0)} SCSI(s), "
                f"{len(result.get('locations') or [])} location(s)"
            ),
        )

    elif tool_name == "funcscore_phosphosite":
        _cite(
            citations,
            source_db="Funcscore",
            label="Ochoa et al. phosphosite functional score",
            source_type=SourceType.prediction,
            url=result.get("homepage") or FUNCSCORE_URL,
            doi=result.get("doi") or "10.1038/s41587-019-0344-3",
            pmid=str(result.get("pmid") or "31819260"),
            evidence_level=EvidenceLevel.predicted,
            detail=f"{result.get('total', 0)} scored site(s)",
        )

    elif tool_name == "pubtator_literature_search":
        _cite(
            citations,
            source_db="PubTator3",
            label="PubTator3 biomedical literature search",
            source_type=SourceType.literature,
            url=result.get("homepage") or PUBTATOR_URL,
            doi=result.get("doi") or "10.1093/nar/gkae263",
            pmid=str(result.get("pmid") or "38460829"),
            evidence_level=EvidenceLevel.curated,
            detail=(
                f"query='{result.get('query', '')}', "
                f"{result.get('total', 0)} hit(s), "
                f"{len(result.get('papers') or [])} recommended"
            ),
        )
        for paper in (result.get("papers") or [])[:8]:
            pmid = str(paper.get("pmid") or "").strip()
            if not pmid.isdigit():
                continue
            title = (paper.get("title") or "")[:120]
            _cite(
                citations,
                source_db="PubTator3",
                label=f"Recommended literature: {title}",
                source_type=SourceType.literature,
                pmid=pmid,
                doi=paper.get("doi") or None,
                evidence_level=EvidenceLevel.experimental,
                detail=(
                    f"{paper.get('journal', '')} "
                    f"({paper.get('year', '')})"
                ).strip(),
            )

    elif tool_name == "pubmed_fetch_abstracts":
        _cite(
            citations,
            source_db="PubMed",
            label="PubMed abstract fetch (NCBI eutils)",
            source_type=SourceType.literature,
            url=result.get("homepage") or "https://pubmed.ncbi.nlm.nih.gov/",
            evidence_level=EvidenceLevel.experimental,
            detail=f"{len(result.get('abstracts') or [])} abstract(s) fetched",
        )
        for row in (result.get("abstracts") or [])[:10]:
            pmid = str(row.get("pmid") or "").strip()
            if not pmid.isdigit():
                continue
            title = (row.get("title") or "")[:120]
            _cite(
                citations,
                source_db="PubMed",
                label=f"Literature: {title}",
                source_type=SourceType.literature,
                pmid=pmid,
                evidence_level=EvidenceLevel.experimental,
                detail=(row.get("abstract") or "")[:200],
            )

    else:
        _cite(
            citations,
            source_db=meta["source_db"],
            label=f"{tool_name} result",
            source_type=_as_source_type(meta.get("source_type", "database")),
            url=meta.get("url") or None,
        )

    return citations


def attach_citations(
    tool: str,
    database: str,
    raw_result: dict[str, Any],
    *,
    include_raw: bool = False,
) -> ToolResult:
    """Wrap a bare tool dict into a ToolResult with citations and compact data.

    Call site: main.py Phase 2 after each step (preferred), or registry exit.
    """
    success = "error" not in raw_result
    summary = raw_result.get("summary") or raw_result.get("error") or ""

    if not success:
        return ToolResult(
            tool=tool,
            database=database,
            success=False,
            summary=str(summary),
            data={},
            citations=[],
        )

    cite_dicts = extract_citations(tool, database, raw_result)
    citations = [Citation.model_validate(c) for c in cite_dicts]

    return ToolResult(
        tool=tool,
        database=database,
        success=True,
        summary=str(summary),
        data=compact_tool_data(tool, raw_result),
        raw=raw_result if include_raw else {},
        citations=citations,
    )


def compact_tool_data(tool_name: str, result: dict[str, Any]) -> dict[str, Any]:
    """Extract structured evidence for LLM context (token-limited)."""
    if "error" in result:
        return {"error": result["error"]}

    compact: dict[str, Any] = {"summary": result.get("summary", "")}

    if tool_name == "qptm_search":
        compact["events"] = [
            {
                "gene": e.get("gene"),
                "uniprot_ac": e.get("uniprot_ac"),
                "position": e.get("position"),
                "ptm_type": e.get("ptm_type"),
                "condition": e.get("condition"),
                "sample": e.get("sample"),
                "log2_ratio": e.get("log2_ratio"),
                "pmid": e.get("pmid"),
            }
            for e in result.get("events", [])[:12]
        ]
        compact["total"] = result.get("total", 0)

    elif tool_name == "qptm_site_conditions":
        compact["site"] = {
            "uniprot_ac": result.get("uniprot_ac"),
            "position": result.get("position"),
        }
        compact["conditions"] = [
            {
                "condition_name": c.get("condition_name"),
                "log2_range": c.get("log2_range"),
                "event_count": c.get("event_count"),
            }
            for c in result.get("conditions", [])[:12]
        ]

    elif tool_name == "qptm_kinases":
        compact["kinases"] = [
            {
                "kinase_gene": k.get("kinase_gene"),
                "evidence_type": k.get("evidence_type"),
                "source_db": k.get("source_db"),
                "inhibitor": k.get("inhibitor"),
            }
            for k in result.get("kinases", [])[:15]
        ]

    elif tool_name == "iptmnet_enzymes":
        compact["total"] = result.get("total", 0)
        compact["gene"] = result.get("gene")
        compact["uniprot_ac"] = result.get("uniprot_ac")
        compact["enzymes"] = [
            {
                "enzyme_gene": e.get("enzyme_gene"),
                "enzyme_uniprot": e.get("enzyme_uniprot"),
                "enzyme_type": e.get("enzyme_type"),
                "substrate_site": e.get("substrate_site"),
                "ptm_type": e.get("ptm_type"),
                "score": e.get("score"),
                "pmids": (e.get("pmids") or [])[:3],
                "evidence": e.get("evidence"),
            }
            for e in result.get("enzymes", [])[:12]
        ]

    elif tool_name == "iptmnet_ptm_ppi":
        compact["total"] = result.get("total", 0)
        compact["gene"] = result.get("gene")
        compact["uniprot_ac"] = result.get("uniprot_ac")
        compact["interactions"] = [
            {
                "interactor_a": i.get("interactor_a"),
                "interactor_b": i.get("interactor_b"),
                "ptm_site": i.get("ptm_site"),
                "ptm_type": i.get("ptm_type"),
                "association_type": i.get("association_type"),
                "effect": i.get("effect"),
                "pmid": i.get("pmid"),
                "source": i.get("source"),
                "note": i.get("note"),
            }
            for i in (result.get("interactions") or [])[:10]
        ]

    elif tool_name == "psp_regulatory":
        compact.update({
            "found": result.get("found"),
            "total": result.get("total", 0),
            "on_function": result.get("on_function", [])[:8],
            "on_process": result.get("on_process", [])[:8],
            "on_prot_interact": result.get("on_prot_interact", [])[:8],
            "pmids": result.get("pmids", [])[:10],
            "notes": result.get("notes"),
            "hits": (result.get("hits") or [])[:8],
        })

    elif tool_name == "psp_kinase_substrate":
        compact["total"] = result.get("total", 0)
        compact["hits"] = (result.get("hits") or [])[:15]

    elif tool_name == "weram_regulators":
        compact["total"] = result.get("total", 0)
        compact["gene"] = result.get("gene")
        compact["uniprot_ac"] = result.get("uniprot_ac")
        compact["roles_found"] = result.get("roles_found")
        compact["modifications_found"] = result.get("modifications_found")
        compact["note"] = result.get("note")
        compact["regulators"] = (result.get("regulators") or [])[:15]

    elif tool_name == "ubibrowser_interactions":
        compact["total"] = result.get("total", 0)
        compact["known_total"] = result.get("known_total", 0)
        compact["predicted_total"] = result.get("predicted_total", 0)
        compact["gene"] = result.get("gene")
        compact["uniprot_ac"] = result.get("uniprot_ac")
        compact["note"] = result.get("note")
        compact["interactions"] = (result.get("interactions") or [])[:15]

    elif tool_name == "gpsuber_e3_sites":
        compact["total"] = result.get("total", 0)
        compact["gene"] = result.get("gene")
        compact["uniprot_ac"] = result.get("uniprot_ac")
        compact["position"] = result.get("position")
        compact["e3s_found"] = result.get("e3s_found")
        compact["e3_classes_found"] = result.get("e3_classes_found")
        compact["note"] = result.get("note")
        compact["relations"] = (result.get("relations") or [])[:15]

    elif tool_name == "gps6_kinases":
        compact["total"] = result.get("total", 0)
        compact["gene"] = result.get("gene")
        compact["uniprot_ac"] = result.get("uniprot_ac")
        compact["position"] = result.get("position")
        compact["min_score"] = result.get("min_score")
        compact["kinases_found"] = result.get("kinases_found")
        compact["sites_found"] = result.get("sites_found")
        compact["note"] = result.get("note")
        compact["predictions"] = (result.get("predictions") or [])[:15]

    elif tool_name == "gpssumo2_sites":
        compact["total"] = result.get("total", 0)
        compact["site_total"] = result.get("site_total", 0)
        compact["sim_total"] = result.get("sim_total", 0)
        compact["gene"] = result.get("gene")
        compact["uniprot_ac"] = result.get("uniprot_ac")
        compact["position"] = result.get("position")
        compact["organism"] = result.get("organism")
        compact["note"] = result.get("note")
        compact["sites"] = (result.get("sites") or [])[:15]
        compact["sims"] = (result.get("sims") or [])[:10]

    elif tool_name == "kaka_kinase_mutations":
        compact["total"] = result.get("total", 0)
        compact["gene"] = result.get("gene")
        compact["uniprot_ac"] = result.get("uniprot_ac")
        compact["mutation"] = result.get("mutation")
        compact["position"] = result.get("position")
        compact["enzyme_activity"] = result.get("enzyme_activity")
        compact["organism"] = result.get("organism")
        compact["activity_counts"] = result.get("activity_counts")
        compact["note"] = result.get("note")
        compact["alterations"] = [
            {
                "gene": a.get("gene"),
                "uniprot": a.get("uniprot"),
                "mutation": a.get("mutation"),
                "position": a.get("position"),
                "enzyme_activity": a.get("enzyme_activity"),
                "organism": a.get("organism"),
                "pmids": a.get("pmids"),
                "description": (a.get("description") or "")[:350],
            }
            for a in (result.get("alterations") or [])[:15]
        ]

    elif tool_name == "ekpi_kinases":
        compact["total"] = result.get("total", 0)
        compact["gene"] = result.get("gene")
        compact["uniprot_ac"] = result.get("uniprot_ac")
        compact["position"] = result.get("position")
        compact["site"] = result.get("site")
        compact["evidence_type"] = result.get("evidence_type")
        compact["experimental_kinases"] = result.get("experimental_kinases")
        compact["predicted_only_kinases"] = (result.get("predicted_only_kinases") or [])[:20]
        compact["note"] = result.get("note")
        compact["kinases"] = [
            {
                "kinase_gene": k.get("kinase_gene"),
                "evidence_levels": k.get("evidence_levels"),
                "experimental_pmids": k.get("experimental_pmids"),
                "prediction_tools": k.get("prediction_tools"),
                "best_correlation": k.get("best_correlation"),
            }
            for k in (result.get("kinases") or [])[:20]
        ]

    elif tool_name == "ekpi_quantitative":
        compact["total"] = result.get("total", 0)
        compact["gene"] = result.get("gene")
        compact["uniprot_ac"] = result.get("uniprot_ac")
        compact["position"] = result.get("position")
        compact["site"] = result.get("site")
        compact["cohort"] = result.get("cohort")
        compact["kinases_found"] = result.get("kinases_found")
        compact["positive_rho"] = result.get("positive_rho")
        compact["negative_rho"] = result.get("negative_rho")
        compact["note"] = result.get("note")
        compact["correlations"] = [
            {
                "kinase_gene": c.get("kinase_gene"),
                "kinase_feature": c.get("kinase_feature"),
                "feature_type": c.get("feature_type"),
                "rho": c.get("rho"),
                "pvalue": c.get("pvalue"),
                "n": c.get("n"),
                "pmid": c.get("pmid"),
                "cancer_type": c.get("cancer_type"),
                "cohort": c.get("cohort"),
            }
            for c in (result.get("correlations") or [])[:15]
        ]

    elif tool_name == "psp_disease_sites":
        compact["total"] = result.get("total", 0)
        compact["hits"] = (result.get("hits") or [])[:15]

    elif tool_name == "psp_ptmvar":
        compact["total"] = result.get("total", 0)
        compact["class_i"] = result.get("class_i", 0)
        compact["class_ii"] = result.get("class_ii", 0)
        compact["hits"] = (result.get("hits") or [])[:15]

    elif tool_name == "uniprot_annotation":
        compact.update({
            "gene": result.get("gene"),
            "protein_name": result.get("protein_name"),
            "function": (result.get("function") or "")[:500],
            "ptm_description": (result.get("ptm_description") or "")[:400],
            "domains": result.get("domains", [])[:8],
            "disease_associations": result.get("disease_associations", [])[:8],
        })

    elif tool_name in ("interpro_domains", "pfam_domains"):
        compact["total"] = result.get("total", 0)
        compact["gene"] = result.get("gene")
        compact["uniprot_ac"] = result.get("uniprot_ac")
        compact["position"] = result.get("position")
        compact["domains"] = [
            {
                "accession": d.get("accession"),
                "name": d.get("name"),
                "short_name": d.get("short_name"),
                "type": d.get("type"),
                "start": d.get("start"),
                "end": d.get("end"),
                "integrated": d.get("integrated"),
                "score": d.get("score"),
                "site_note": d.get("site_note"),
                "description": (d.get("description") or "")[:350],
                "go_terms": [
                    {"id": g.get("id"), "name": g.get("name")}
                    for g in (d.get("go_terms") or [])[:5]
                ],
                "literature_pmids": [
                    lit.get("pmid") for lit in (d.get("literature") or [])[:3]
                ],
                "url": d.get("url"),
            }
            for d in (result.get("domains") or [])[:10]
        ]

    elif tool_name == "dbptm_functional":
        compact["disease_associations"] = result.get("disease_associations", [])[:8]
        compact["functional_sites"] = result.get("functional_sites", [])[:8]

    elif tool_name == "ptm_stability":
        compact["entries"] = [
            {
                "ptm_type": e.get("ptm_type"),
                "position": e.get("position"),
                "effect_direction": e.get("effect_direction"),
                "mechanism": e.get("mechanism"),
                "writer": e.get("writer"),
                "eraser": e.get("eraser"),
                "reader": e.get("reader"),
                "evidence": e.get("evidence"),
                "source": e.get("source"),
                "curated_from": e.get("curated_from"),
            }
            for e in result.get("entries", [])[:8]
        ]
        compact["primary_pmids"] = result.get("primary_pmids", [])[:10]
        compact["curated_from"] = result.get("curated_from")

    elif tool_name == "activedriver_mutations":
        compact["gene"] = result.get("gene")
        compact["site_position"] = result.get("site_position")
        compact["total"] = result.get("total", 0)
        by_ds = result.get("mutations_by_dataset") or {}
        compact["mutations_by_dataset"] = {
            ds: [
                {
                    "mutation_position": r.get("mutation_position"),
                    "mutation_alt": r.get("mutation_alt"),
                    "mutation_summary": r.get("mutation_summary"),
                    "site_position": r.get("site_position"),
                    "site_residue": r.get("site_residue"),
                }
                for r in rows[:8]
            ]
            for ds, rows in by_ds.items()
        }

    elif tool_name == "activedriver_kinase_network":
        compact["gene"] = result.get("gene")
        compact["as_substrate"] = [
            {
                "kinase_symbol": r.get("kinase_symbol"),
                "target_sequence_position": r.get("target_sequence_position"),
                "target_amino_acid": r.get("target_amino_acid"),
            }
            for r in (result.get("as_substrate") or [])[:12]
        ]
        compact["as_kinase"] = [
            {
                "target_symbol": r.get("target_symbol"),
                "target_sequence_position": r.get("target_sequence_position"),
            }
            for r in (result.get("as_kinase") or [])[:8]
        ]

    elif tool_name == "pmads_drug_ptm":
        compact["total"] = result.get("total", 0)
        compact["status_filter"] = result.get("status_filter")
        compact["associations"] = (result.get("associations") or [])[:12]

    elif tool_name == "drugbank_targets":
        compact["total"] = result.get("total", 0)
        compact["uniprot_ac"] = result.get("uniprot_ac")
        compact["associations"] = (result.get("associations") or [])[:12]

    elif tool_name == "decryptm_drug_ptm":
        compact["total"] = result.get("total", 0)
        compact["access"] = result.get("access")
        compact["local_count"] = result.get("local_count")
        compact["api_count"] = result.get("api_count")
        compact["gene"] = result.get("gene")
        compact["uniprot_ac"] = result.get("uniprot_ac")
        compact["protein_name"] = result.get("protein_name")
        compact["drug"] = result.get("drug")
        compact["query_mode"] = result.get("query_mode")
        compact["notes"] = result.get("notes")
        compact["curves"] = (result.get("curves") or [])[:15]

    elif tool_name == "ptmphase_llps":
        compact["total"] = result.get("total", 0)
        compact["associations"] = (result.get("associations") or [])[:12]

    elif tool_name == "ptmphase_phosllps":
        compact["total"] = result.get("total", 0)
        compact["min_prob"] = result.get("min_prob")
        compact["predictions"] = (result.get("predictions") or [])[:12]

    elif tool_name == "dscope_literature":
        compact["total"] = result.get("total", 0)
        compact["segments"] = (result.get("segments") or [])[:12]

    elif tool_name == "dscope_predictions":
        compact["total"] = result.get("total", 0)
        compact["min_score"] = result.get("min_score")
        compact["proteins"] = (result.get("proteins") or [])[:8]

    elif tool_name == "ptmd_disease":
        compact["total"] = result.get("total", 0)
        compact["state_legend"] = result.get("state_legend")
        compact["literature"] = (result.get("literature") or [])[:10]
        compact["public"] = (result.get("public") or [])[:10]

    elif tool_name == "cancerproteome_disease":
        compact["total"] = result.get("total", 0)
        compact["ptm_total"] = result.get("ptm_total", 0)
        compact["protein_total"] = result.get("protein_total", 0)
        compact["cancer_filter"] = result.get("cancer_filter")
        compact["note"] = result.get("note")
        compact["ptm_hits"] = (result.get("ptm_hits") or [])[:12]
        compact["protein_hits"] = (result.get("protein_hits") or [])[:12]

    elif tool_name == "ptmint_ppi":
        compact["total"] = result.get("total", 0)
        compact["as_substrate"] = [
            {
                "gene": r.get("gene"),
                "site": f"{r.get('aa') or ''}{r.get('site') or ''}",
                "ptm": r.get("ptm"),
                "int_gene": r.get("int_gene"),
                "effect": r.get("effect"),
                "method": r.get("method"),
                "disease": r.get("disease"),
                "pmid": r.get("pmid"),
                "note": r.get("note"),
            }
            for r in (result.get("as_substrate") or [])[:10]
        ]
        compact["as_partner"] = [
            {
                "gene": r.get("gene"),
                "site": f"{r.get('aa') or ''}{r.get('site') or ''}",
                "ptm": r.get("ptm"),
                "int_gene": r.get("int_gene"),
                "effect": r.get("effect"),
                "method": r.get("method"),
                "pmid": r.get("pmid"),
                "note": r.get("note"),
            }
            for r in (result.get("as_partner") or [])[:8]
        ]

    elif tool_name in ("string_ppi", "biogrid_interactions", "intact_interactions"):
        compact["total"] = result.get("total", 0)
        compact["gene"] = result.get("gene")
        compact["uniprot_ac"] = result.get("uniprot_ac")
        compact["interactions"] = [
            {
                "interactor_a": i.get("interactor_a"),
                "interactor_b": i.get("interactor_b"),
                "partner": i.get("partner"),
                "partner_annotation": (i.get("partner_annotation") or "")[:160],
                "score": i.get("score"),
                "detection_method": i.get("detection_method"),
                "interaction_type": i.get("interaction_type") or i.get("evidence_type"),
                "pmids": (i.get("pmids") or [])[:3],
                "note": i.get("note"),
                "url": i.get("url"),
            }
            for i in (result.get("interactions") or [])[:12]
        ]

    elif tool_name in ("reactome_pathways", "kegg_pathways", "pathbank_pathways"):
        compact["total"] = result.get("total", 0)
        compact["gene"] = result.get("gene")
        compact["uniprot_ac"] = result.get("uniprot_ac")
        compact["pathways"] = [
            {
                "pathway_id": p.get("pathway_id"),
                "pathway_name": p.get("pathway_name"),
                "pathway_subject": p.get("pathway_subject"),
                "pathway_class": p.get("pathway_class"),
                "is_disease": p.get("is_disease"),
                "description": (p.get("description") or "")[:320],
                "go_process": p.get("go_process"),
                "pmids": (p.get("pmids") or [])[:3],
                "url": p.get("url"),
            }
            for p in (result.get("pathways") or [])[:12]
        ]
        if result.get("note"):
            compact["note"] = result.get("note")

    elif tool_name == "ptmcode_associations":
        compact["total"] = result.get("total", 0)
        compact["within_total"] = result.get("within_total", 0)
        compact["between_total"] = result.get("between_total", 0)
        compact["note"] = result.get("note")
        compact["within"] = [
            {
                "gene": r.get("gene"),
                "site1": r.get("site1"),
                "site2": r.get("site2"),
                "evidence": r.get("evidence"),
            }
            for r in (result.get("within") or [])[:10]
        ]
        compact["between"] = [
            {
                "gene1": r.get("gene1") or r.get("gene"),
                "gene2": r.get("gene2") or r.get("partner_gene"),
                "site1": r.get("site1"),
                "site2": r.get("site2"),
                "evidence": r.get("evidence"),
            }
            for r in (result.get("between") or [])[:10]
        ]

    elif tool_name == "subcell_scsi":
        compact["total"] = result.get("total", 0)
        compact["gene"] = result.get("gene")
        compact["uniprot_ac"] = result.get("uniprot_ac")
        compact["interactions"] = [
            {
                "query_gene": i.get("query_gene"),
                "partner_gene": i.get("partner_gene"),
                "partner_protein": i.get("partner_protein"),
                "compartment": i.get("compartment"),
                "scsi_type": i.get("scsi_type"),
                "note": i.get("note"),
            }
            for i in (result.get("interactions") or [])[:12]
        ]
        compact["locations"] = [
            {
                "gene": loc.get("gene"),
                "compartment": loc.get("compartment"),
            }
            for loc in (result.get("locations") or [])[:10]
        ]

    elif tool_name == "inuloc_nls_nes":
        compact["total"] = result.get("total", 0)
        compact["experimental"] = (result.get("experimental") or [])[:10]
        compact["predicted"] = (result.get("predicted") or [])[:10]
        compact["dnl"] = (result.get("dnl") or [])[:8]

    elif tool_name == "inuloc_nuclear_prob":
        compact["total"] = result.get("total", 0)
        compact["probabilities"] = (result.get("probabilities") or [])[:10]

    elif tool_name == "compartments_localization":
        compact["total"] = result.get("total", 0)
        compact["gene"] = result.get("gene")
        compact["uniprot_ac"] = result.get("uniprot_ac")
        compact["min_confidence"] = result.get("min_confidence")
        compact["localizations"] = (result.get("localizations") or [])[:15]

    elif tool_name == "funcscore_phosphosite":
        compact["total"] = result.get("total", 0)
        compact["min_score"] = result.get("min_score")
        compact["sites"] = (result.get("sites") or [])[:15]

    elif tool_name == "pubtator_literature_search":
        compact["query"] = result.get("query", "")
        compact["total"] = result.get("total", 0)
        compact["papers"] = [
            {
                "pmid": p.get("pmid"),
                "title": p.get("title"),
                "journal": p.get("journal"),
                "year": p.get("year"),
                "authors": p.get("authors"),
                "doi": p.get("doi"),
                "url": p.get("url"),
                "highlight": p.get("highlight"),
            }
            for p in (result.get("papers") or [])[:8]
        ]

    elif tool_name == "pubmed_fetch_abstracts":
        compact["pmids"] = result.get("pmids") or []
        compact["abstracts"] = [
            {
                "pmid": a.get("pmid"),
                "title": a.get("title"),
                "abstract": (a.get("abstract") or "")[:700],
                "journal": a.get("journal"),
                "year": a.get("year"),
                "url": a.get("url"),
            }
            for a in (result.get("abstracts") or [])[:5]
        ]

    return compact
