"""qPTM database tools — call the qPTM PHP REST API.

Stage 1 tools:
  1. qptm_search — search PTM events by keyword
  2. qptm_site_conditions — get conditions for a specific site

Stage 2 tool:
  3. qptm_kinases — get kinases from qPTM's integrated data
"""

import logging
from typing import Any

import httpx

from app.config import settings
from app.tools.registry import registry

logger = logging.getLogger(__name__)

# Shared HTTP client (reused across calls)
_http_client: httpx.AsyncClient | None = None


def _sync_client() -> httpx.Client:
    """Get a synchronous httpx client for tool execution."""
    return httpx.Client(
        base_url=settings.qptm_api_base_url,
        timeout=settings.http_timeout_seconds,
        headers={"Accept": "application/json"},
    )


def _get(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Make a GET request to the qPTM API and return parsed JSON."""
    with _sync_client() as client:
        resp = client.get(path, params=params)
        resp.raise_for_status()
        return resp.json()


# ── Tool 1: qptm_search ───────────────────────────────────────────

def _qptm_search(
    query: str,
    field: str = "any",
    organism: str = "all",
    ptm_type: str = "all",
    page: int = 1,
    per_page: int = 20,
) -> dict[str, Any]:
    """Search qPTM for PTM events matching a keyword."""
    data = _get("/search", {
        "q": query,
        "field": field,
        "organism": organism,
        "ptm_type": ptm_type,
        "page": page,
        "per_page": min(per_page, 50),
    })
    events = data.get("events", [])
    # Summarize for the LLM (don't dump all events if too many)
    summary = (
        f"Found {data.get('total', 0)} PTM events (showing {len(events)}). "
    )
    if events:
        genes = set(e.get("gene", "") for e in events)
        ptm_types = set(e.get("ptm_type", "") for e in events)
        conditions = set(e.get("condition", "") for e in events if e.get("condition"))
        summary += f"Genes: {', '.join(sorted(genes)[:10])}. "
        summary += f"PTM types: {', '.join(sorted(ptm_types))}. "
        summary += f"Conditions: {', '.join(sorted(conditions)[:10])}."
    return {
        "summary": summary,
        "total": data.get("total", 0),
        "page": data.get("page", 1),
        "events": events[:20],  # Cap at 20 for context window
    }


# ── Tool 2: qptm_site_conditions ──────────────────────────────────

def _qptm_site_conditions(
    uniprot_ac: str,
    position: int,
    ptm_type: str = "all",
) -> dict[str, Any]:
    """Get all experimental conditions where a specific PTM site was quantified."""
    data = _get("/conditions", {
        "uniprot_ac": uniprot_ac,
        "position": str(position),
        "ptm_type": ptm_type,
    })
    conditions = data.get("conditions", [])
    summary = f"Site {uniprot_ac} position {position} was quantified under {len(conditions)} condition(s). "
    if conditions:
        top = conditions[:10]
        cond_names = [c.get("condition_name", "") for c in top]
        summary += f"Top conditions: {', '.join(cond_names)}. "
        # Highlight conditions with large fold changes
        significant = [
            c for c in conditions
            if c.get("log2_range", {}).get("max") is not None
            and abs(c["log2_range"]["max"]) > 1.0
        ]
        if significant:
            summary += f"{len(significant)} condition(s) show log2 ratio > 1 (significant change)."
    return {
        "summary": summary,
        "uniprot_ac": uniprot_ac,
        "position": position,
        "total_conditions": data.get("total_conditions", 0),
        "conditions": conditions[:15],
    }


# ── Tool 3: qptm_kinases ──────────────────────────────────────────

def _qptm_kinases(
    uniprot_ac: str,
    position: int,
) -> dict[str, Any]:
    """Get kinases/enzymes from qPTM's integrated kinase-substrate data."""
    data = _get(f"/kinases/{uniprot_ac}/{position}")
    kinases = data.get("kinases", [])
    summary = f"Found {len(kinases)} kinase(s)/enzyme(s) for {uniprot_ac} position {position}. "
    if kinases:
        exp_kinases = [k for k in kinases if k.get("evidence_type") == "experimental"]
        pred_kinases = [k for k in kinases if k.get("evidence_type") == "predicted"]
        if exp_kinases:
            names = [k.get("kinase_gene", "") for k in exp_kinases]
            summary += f"Experimentally validated: {', '.join(names)}. "
        if pred_kinases:
            names = [k.get("kinase_gene", "") for k in pred_kinases]
            summary += f"Predicted: {', '.join(names)}. "
        inhibitors = [k.get("inhibitor") for k in kinases if k.get("inhibitor")]
        if inhibitors:
            summary += f"Known inhibitors: {', '.join(set(inhibitors))}."
    else:
        summary += "No kinase information available in qPTM for this site."
    return {
        "summary": summary,
        "uniprot_ac": uniprot_ac,
        "position": position,
        "total": len(kinases),
        "kinases": kinases,
    }


# ── Register tools ────────────────────────────────────────────────

def register_qptm_tools() -> None:
    """Register all qPTM tools with the global registry."""
    registry.register(
        name="qptm_search",
        description=(
            "Search the qPTM database for PTM events by gene name, protein name, "
            "UniProt accession, sample, or condition. Returns matching quantitative PTM events "
            "with conditions, samples, log2 ratios, and p-values. Use this to find which proteins "
            "and sites have quantitative PTM data in qPTM."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search keyword (gene name, protein name, UniProt AC, sample, or condition)",
                },
                "field": {
                    "type": "string",
                    "enum": ["any", "gene", "uniprot", "protein", "function", "sample", "condition"],
                    "description": "Which field to search in (default: any)",
                },
                "organism": {
                    "type": "string",
                    "enum": ["all", "human", "mouse", "rat", "yeast"],
                    "description": "Filter by organism (default: all)",
                },
                "ptm_type": {
                    "type": "string",
                    "enum": ["all", "phosphorylation", "acetylation", "ubiquitylation",
                             "methylation", "glycosylation", "sumoylation"],
                    "description": "Filter by PTM type (default: all)",
                },
            },
            "required": ["query"],
        },
        handler=_qptm_search,
    )

    registry.register(
        name="qptm_site_conditions",
        description=(
            "Get all experimental conditions (cell types, treatments, stimuli, time points) "
            "where a specific PTM site was quantified. Requires UniProt accession and residue position. "
            "Returns condition names, sample types, event counts, and log2 ratio ranges. "
            "Use this for Stage 1: understanding when and where a site is modified."
        ),
        parameters={
            "type": "object",
            "properties": {
                "uniprot_ac": {
                    "type": "string",
                    "description": "UniProt accession (e.g., P04637 for TP53)",
                },
                "position": {
                    "type": "integer",
                    "description": "Residue position in the protein sequence (e.g., 15 for S15)",
                },
                "ptm_type": {
                    "type": "string",
                    "enum": ["all", "phosphorylation", "acetylation", "ubiquitylation",
                             "methylation", "glycosylation", "sumoylation"],
                    "description": "Filter by PTM type (default: all)",
                },
            },
            "required": ["uniprot_ac", "position"],
        },
        handler=_qptm_site_conditions,
    )

    registry.register(
        name="qptm_kinases",
        description=(
            "Get kinases and enzymes associated with a specific PTM site from qPTM's integrated "
            "kinase-substrate data. Includes experimentally validated and computationally predicted "
            "kinases, plus known inhibitors from DrugBank. Use this for Stage 2: identifying which "
            "kinase catalyzes the modification."
        ),
        parameters={
            "type": "object",
            "properties": {
                "uniprot_ac": {
                    "type": "string",
                    "description": "UniProt accession of the substrate protein",
                },
                "position": {
                    "type": "integer",
                    "description": "Residue position of the modification site",
                },
            },
            "required": ["uniprot_ac", "position"],
        },
        handler=_qptm_kinases,
    )
