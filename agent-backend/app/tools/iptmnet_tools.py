"""iPTMnet tools — query the iPTMnet REST API for kinase-substrate and PPI data.

Stage 2 tools:
  4. iptmnet_enzymes — get PTM enzymes (kinases, acetyltransferases, E3 ligases)
  5. iptmnet_ptm_ppi — get PTM-dependent protein-protein interactions

iPTMnet API base: https://research.bioinformatics.udel.edu/iptmnet/api
No authentication required.

Endpoints used:
  - /{uniprot}/info        — protein info (gene, organism, etc.)
  - /{uniprot}/proteoforms — PTM proteoforms with sites and associated enzymes
    Returns a list of proteoform objects, each with:
      - pro_id: PRO identifier
      - label: proteoform label (e.g., "hTP53/iso:1/Phos:4")
      - sites: list of site strings (e.g., "pT55", "acK120", "ubK386")
      - ptm_enzyme: {pro_id, label} — the enzyme that catalyzed the modification
      - source: {name} — data source
"""

import logging
import re
from typing import Any

import httpx

from app.config import settings
from app.tools.registry import registry

logger = logging.getLogger(__name__)


def _iptmnet_get(path: str) -> dict[str, Any] | list[Any] | None:
    """Make a GET request to the iPTMnet API."""
    url = f"{settings.iptmnet_api_base_url}/{path.lstrip('/')}"
    try:
        with httpx.Client(timeout=settings.http_timeout_seconds) as client:
            resp = client.get(url, headers={"Accept": "application/json"})
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPError as e:
        logger.warning(f"iPTMnet API error for {path}: {e}")
        return None
    except Exception as e:
        logger.error(f"iPTMnet request failed for {path}: {e}")
        return None


def _parse_site(site_str: str) -> dict[str, Any]:
    """Parse an iPTMnet site string like 'pT55', 'acK120', 'ubK386'.

    Returns dict with: residue, position, ptm_type
    """
    # Patterns: pS15, pT18, acK120, ubK386, meK372, smK386, gN120
    match = re.match(r'^([a-z]+)([A-Z])(\d+)$', site_str.strip())
    if not match:
        return {"raw": site_str, "residue": None, "position": None, "ptm_type": None}

    mod_code, residue, pos_str = match.groups()
    position = int(pos_str)

    mod_map = {
        'p': 'phosphorylation',
        'ac': 'acetylation',
        'ub': 'ubiquitylation',
        'me': 'methylation',
        'me1': 'methylation',
        'me2': 'methylation',
        'me3': 'methylation',
        'sm': 'sumoylation',
        'g': 'glycosylation',
        'ga': 'glycosylation',
        'gl': 'glycosylation',
    }
    ptm_type = mod_map.get(mod_code, mod_code)

    return {
        "raw": site_str,
        "residue": residue,
        "position": position,
        "ptm_type": ptm_type,
    }


def _parse_enzyme_label(label: str) -> dict[str, str]:
    """Parse an iPTMnet enzyme label like 'hTAF1' or 'hKAT8'.

    Returns dict with gene name and organism prefix.
    """
    if not label:
        return {"gene": "", "organism_prefix": ""}
    # Labels typically start with organism prefix: h=human, m=mouse, r=rat, y=yeast
    match = re.match(r'^([hmry])(.+)$', label)
    if match:
        prefix, gene = match.groups()
        return {"gene": gene, "organism_prefix": prefix}
    return {"gene": label, "organism_prefix": ""}


# ── Tool 4: iptmnet_enzymes ───────────────────────────────────────

def _iptmnet_enzymes(
    uniprot_ac: str,
    position: int | None = None,
) -> dict[str, Any]:
    """Query iPTMnet for PTM enzymes (kinases, acetyltransferases, E3 ligases).

    Uses the /proteoforms endpoint which contains PTM site → enzyme associations.
    """
    data = _iptmnet_get(f"{uniprot_ac}/proteoforms")
    if data is None:
        # Fallback: try /info to at least confirm the protein exists
        info = _iptmnet_get(f"{uniprot_ac}/info")
        if info is None:
            return {
                "summary": f"No data found in iPTMnet for {uniprot_ac}.",
                "uniprot_ac": uniprot_ac,
                "enzymes": [],
            }
        else:
            return {
                "summary": f"Protein {uniprot_ac} found in iPTMnet but no proteoform/enzyme data available.",
                "uniprot_ac": uniprot_ac,
                "enzymes": [],
            }

    proteoforms = data if isinstance(data, list) else []

    # Extract enzyme-site associations from proteoforms
    enzymes: list[dict[str, Any]] = []
    seen_enzymes: set[str] = set()

    for pf in proteoforms:
        if not isinstance(pf, dict):
            continue

        ptm_enzyme = pf.get("ptm_enzyme", {})
        if not isinstance(ptm_enzyme, dict) or not ptm_enzyme.get("label"):
            continue

        enzyme_label = ptm_enzyme["label"]
        enzyme_pro_id = ptm_enzyme.get("pro_id", "")

        # Parse sites for this proteoform
        sites = pf.get("sites", [])
        parsed_sites = [_parse_site(s) for s in sites if isinstance(s, str)]

        # Filter by position if specified
        if position:
            site_match = [s for s in parsed_sites if s.get("position") == position]
            if not site_match:
                continue

        # Parse enzyme gene name
        enzyme_info = _parse_enzyme_label(enzyme_label)
        gene = enzyme_info["gene"]

        # Determine enzyme type from PTM type
        ptm_types = set(s.get("ptm_type", "") for s in parsed_sites if s.get("ptm_type"))
        enzyme_type = "kinase"
        if ptm_types:
            primary_ptm = list(ptm_types)[0]
            type_map = {
                "phosphorylation": "kinase",
                "acetylation": "acetyltransferase",
                "ubiquitylation": "E3 ligase",
                "methylation": "methyltransferase",
                "sumoylation": "SUMO E3 ligase",
                "glycosylation": "glycosyltransferase",
            }
            enzyme_type = type_map.get(primary_ptm, "enzyme")

        # Extract UniProt accession from PRO ID if available
        enzyme_uniprot = ""
        if enzyme_pro_id and enzyme_pro_id.startswith("PR:"):
            # PRO IDs for human proteins often use UniProt accessions
            enzyme_uniprot = enzyme_pro_id.replace("PR:", "")

        # Deduplicate by enzyme gene + position
        dedup_key = f"{gene}_{position or 'all'}"
        if dedup_key in seen_enzymes:
            continue
        seen_enzymes.add(dedup_key)

        enzymes.append({
            "enzyme_gene": gene,
            "enzyme_label": enzyme_label,
            "enzyme_uniprot": enzyme_uniprot,
            "enzyme_type": enzyme_type,
            "substrate_position": position or (parsed_sites[0].get("position") if parsed_sites else None),
            "ptm_type": ", ".join(sorted(ptm_types)) if ptm_types else "",
            "evidence": "experimental",
            "source": pf.get("source", {}).get("name", "iPTMnet"),
        })

    # Build summary
    summary = f"Found {len(enzymes)} enzyme(s) in iPTMnet for {uniprot_ac}"
    if position:
        summary += f" at position {position}"
    summary += ". "
    if enzymes:
        names = [e["enzyme_gene"] for e in enzymes if e["enzyme_gene"]]
        if names:
            summary += f"Enzymes: {', '.join(names[:10])}."
    else:
        summary += "No enzyme data available in iPTMnet for this protein/site."

    return {
        "summary": summary,
        "uniprot_ac": uniprot_ac,
        "position": position,
        "total": len(enzymes),
        "enzymes": enzymes[:20],
    }


# ── Tool 5: iptmnet_ptm_ppi ───────────────────────────────────────

def _iptmnet_ptm_ppi(
    uniprot_ac: str,
    position: int | None = None,
) -> dict[str, Any]:
    """Get PTM-dependent protein-protein interactions from iPTMnet.

    Uses the /proteoforms endpoint. Proteoforms represent specific PTM states
    of a protein, and the associated enzyme/subunit information reveals
    PTM-dependent interactions.
    """
    data = _iptmnet_get(f"{uniprot_ac}/proteoforms")
    if data is None:
        return {
            "summary": f"No PTM-dependent PPI data found in iPTMnet for {uniprot_ac}.",
            "uniprot_ac": uniprot_ac,
            "interactions": [],
        }

    proteoforms = data if isinstance(data, list) else []

    # Extract interaction information from proteoforms
    interactions: list[dict[str, Any]] = []

    for pf in proteoforms:
        if not isinstance(pf, dict):
            continue

        sites = pf.get("sites", [])
        parsed_sites = [_parse_site(s) for s in sites if isinstance(s, str)]

        # Filter by position if specified
        if position:
            site_match = [s for s in parsed_sites if s.get("position") == position]
            if not site_match:
                continue

        # The proteoform label indicates the PTM state
        label = pf.get("label", "")
        pro_id = pf.get("pro_id", "")

        # PTM enzyme represents an interaction (enzyme-substrate)
        ptm_enzyme = pf.get("ptm_enzyme", {})
        if isinstance(ptm_enzyme, dict) and ptm_enzyme.get("label"):
            enzyme_info = _parse_enzyme_label(ptm_enzyme["label"])
            interactions.append({
                "interactor_a": uniprot_ac,
                "interactor_b": enzyme_info["gene"],
                "ptm_site": ", ".join(s.get("raw", "") for s in parsed_sites),
                "interaction_type": "enzyme-substrate",
                "effect": "catalyzes modification",
                "evidence": "experimental",
                "proteoform": label,
            })

        # Check for other interaction fields in the proteoform
        # iPTMnet proteoforms may have additional interaction data
        for key in ("interactions", "ppis", "binding_partners"):
            field_val = pf.get(key, [])
            if isinstance(field_val, list):
                for item in field_val:
                    if isinstance(item, dict):
                        partner = item.get("label") or item.get("protein") or item.get("interactor", "")
                        if partner:
                            interactions.append({
                                "interactor_a": uniprot_ac,
                                "interactor_b": partner,
                                "ptm_site": ", ".join(s.get("raw", "") for s in parsed_sites),
                                "interaction_type": item.get("type", "PTM-dependent"),
                                "effect": item.get("effect", ""),
                                "evidence": item.get("evidence", "experimental"),
                                "proteoform": label,
                            })

    # Deduplicate
    seen: set[str] = set()
    unique_interactions: list[dict[str, Any]] = []
    for inter in interactions:
        key = f"{inter['interactor_b']}_{inter['ptm_site']}_{inter['interaction_type']}"
        if key not in seen:
            seen.add(key)
            unique_interactions.append(inter)

    # Build summary
    summary = f"Found {len(unique_interactions)} PTM-dependent interaction(s) in iPTMnet for {uniprot_ac}"
    if position:
        summary += f" at position {position}"
    summary += ". "
    if unique_interactions:
        partners = set(i["interactor_b"] for i in unique_interactions if i["interactor_b"])
        if partners:
            summary += f"Interaction partners: {', '.join(sorted(partners)[:10])}."
    else:
        summary += "No PTM-dependent interaction data available."

    return {
        "summary": summary,
        "uniprot_ac": uniprot_ac,
        "position": position,
        "total": len(unique_interactions),
        "interactions": unique_interactions[:15],
    }


# ── Register tools ────────────────────────────────────────────────

def register_iptmnet_tools() -> None:
    """Register all iPTMnet tools with the global registry."""
    registry.register(
        name="iptmnet_enzymes",
        description=(
            "Query the iPTMnet database for PTM enzymes (kinases, acetyltransferases, E3 ligases, "
            "deubiquitinases, etc.) associated with a protein or specific modification site. "
            "iPTMnet integrates data from PhosphoSitePlus, UniProt, and literature text mining. "
            "Returns enzyme gene names, enzyme types, and associated PTM sites. "
            "Use this for Stage 2: identifying the enzyme responsible for a modification, "
            "especially when qPTM's internal kinase data is incomplete."
        ),
        parameters={
            "type": "object",
            "properties": {
                "uniprot_ac": {
                    "type": "string",
                    "description": "UniProt accession of the substrate protein (e.g., P04637)",
                },
                "position": {
                    "type": "integer",
                    "description": "Optional: residue position to filter enzymes for a specific site",
                },
            },
            "required": ["uniprot_ac"],
        },
        handler=_iptmnet_enzymes,
    )

    registry.register(
        name="iptmnet_ptm_ppi",
        description=(
            "Get PTM-dependent protein-protein interactions from iPTMnet. Shows how a modification "
            "at a specific site affects interactions with other proteins (enzyme-substrate relationships, "
            "binding partners). This reveals the functional impact of a PTM on the protein's "
            "interaction network. Use this for Stage 2/3: understanding how modification affects "
            "binding partners."
        ),
        parameters={
            "type": "object",
            "properties": {
                "uniprot_ac": {
                    "type": "string",
                    "description": "UniProt accession of the protein (e.g., P04637)",
                },
                "position": {
                    "type": "integer",
                    "description": "Optional: filter to interactions dependent on a specific site",
                },
            },
            "required": ["uniprot_ac"],
        },
        handler=_iptmnet_ptm_ppi,
    )
