"""qPTM MCP tool implementations."""

from __future__ import annotations

import json
import re
from typing import Any

from app.tools.registry import registry
from app.workflow.planner import infer_tool_arguments, parse_query_entities

_ENTITY_TOOL_MAP: dict[str, list[str]] = {
    "site": ["qptm_search", "qptm_site_conditions", "uniprot_annotation"],
    "kinase": ["qptm_kinases", "iptmnet_enzymes", "psp_kinase_substrate", "gps6_kinases"],
    "condition": ["qptm_site_conditions", "qptm_search", "ekpi_quantitative"],
    "disease": ["ptmd_disease", "psp_disease_sites", "activedriver_mutations", "cancerproteome_disease"],
    "drug": ["pmads_drug_ptm", "drugbank_targets", "decryptm_drug_ptm"],
    "localization": ["compartments_localization", "inuloc_nls_nes", "interpro_domains"],
    "function": ["psp_regulatory", "ptm_stability", "funcscore_phosphosite", "ptmcode_associations"],
    "pathway": ["reactome_pathways", "kegg_pathways", "pathbank_pathways"],
    "ppi": ["string_ppi", "iptmnet_ptm_ppi", "ptmint_ppi"],
    "llps": ["ptmphase_llps", "dscope_predictions"],
    "literature": ["pubtator_literature_search", "pubmed_fetch_abstracts"],
}

_TOOL_DEFAULT_ARGS: dict[str, dict[str, Any]] = {
    "qptm_search": {"query": "", "field": "any"},
    "qptm_site_conditions": {"gene": "", "position": 0},
    "qptm_kinases": {"gene": "", "position": 0},
    "uniprot_annotation": {"uniprot_ac": ""},
    "pubtator_literature_search": {"query": ""},
}


def _infer_gene_position(query: str, gene: str | None, position: int | None) -> tuple[str | None, int | None]:
    g = gene
    p = position
    if not g:
        m = re.search(r"\b([A-Z][A-Z0-9]{1,9})\b", query or "")
        if m:
            g = m.group(1)
    if not p:
        m = re.search(r"\b[STYKR](\d{2,5})\b", query or "", re.I)
        if m:
            p = int(m.group(1))
    return g, p


def qptm_search(
    entity: str,
    query: str,
    gene: str = "",
    position: int = 0,
    uniprot_ac: str = "",
) -> str:
    entity = (entity or "site").lower().strip()
    tools = _ENTITY_TOOL_MAP.get(entity, _ENTITY_TOOL_MAP["site"])
    g, p = _infer_gene_position(query, gene or None, position or None)
    outputs: list[dict[str, Any]] = []

    for tool_name in tools[:3]:
        entities = parse_query_entities(query or "")
        if gene:
            entities["gene"] = gene
        if position:
            entities["position"] = position
        if uniprot_ac:
            entities["uniprot_ac"] = uniprot_ac
        args = infer_tool_arguments(tool_name, entities, query)
        try:
            result = registry.execute(tool_name, args)
            outputs.append({"tool": tool_name, "result": result})
        except Exception as exc:
            outputs.append({"tool": tool_name, "error": str(exc)})

    summary_parts = []
    for o in outputs:
        r = o.get("result") or {}
        if isinstance(r, dict) and r.get("summary"):
            summary_parts.append(f"[{o['tool']}] {r['summary']}")
    return json.dumps(
        {
            "success": True,
            "summary": " | ".join(summary_parts)[:800] or "Search completed",
            "data": outputs,
        },
        ensure_ascii=False,
        default=str,
    )


def qptm_get(entity: str, id: str, section: str = "") -> str:
    id = (id or "").strip()
    entity = (entity or "").lower().strip()

    if id.startswith("pmid:") or entity == "literature":
        pmid = id.replace("pmid:", "").strip()
        result = registry.execute("pubmed_fetch_abstracts", {"pmids": [pmid]})
        return json.dumps(result, ensure_ascii=False, default=str)[:12000]

    if ":" in id:
        left, right = id.split(":", 1)
        if re.match(r"^\d+$", right):
            gene, pos = left, int(right)
            tool = "qptm_site_conditions" if entity in ("condition", "site") else "qptm_kinases"
            result = registry.execute(tool, {"gene": gene, "position": pos})
            return json.dumps(result, ensure_ascii=False, default=str)[:12000]
        if re.match(r"^[OPQ][0-9]", left, re.I):
            result = registry.execute(
                "qptm_site_conditions",
                {"uniprot_ac": left, "position": int(right)},
            )
            return json.dumps(result, ensure_ascii=False, default=str)[:12000]

    if id in registry.tool_names:
        args = dict(_TOOL_DEFAULT_ARGS.get(id, {}))
        if section:
            args["query"] = section
        result = registry.execute(id, args)
        return json.dumps(result, ensure_ascii=False, default=str)[:12000]

    return json.dumps({"success": False, "summary": f"Unknown id: {id}", "data": None})


def qptm_invoke(tool_name: str, arguments_json: str = "{}") -> str:
    try:
        args = json.loads(arguments_json or "{}")
    except json.JSONDecodeError:
        args = {}
    if not isinstance(args, dict):
        args = {}
    if not args.get("query") and args.get("gene"):
        entities = parse_query_entities(str(args.get("gene")))
        entities.update({k: v for k, v in args.items() if v})
        args = infer_tool_arguments(tool_name, entities, str(args.get("query") or args.get("gene") or ""))
    result = registry.execute(tool_name, args)
    return json.dumps(result, ensure_ascii=False, default=str)[:12000]
