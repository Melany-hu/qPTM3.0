"""dbPTM tools — query local dbPTM data for functional annotations and disease associations.

Stage 3 tool:
  8. dbptm_functional — look up functional annotations, disease associations,
     and regulatory network context for a PTM site

dbPTM (https://biomics.lab.nycu.edu.tw/dbPTM/) does not provide a public REST API.
Users download bulk data files from the dbPTM download page and place them in
data/dbptm/. The tool loads these into an in-memory index on first access.

Supported data files (tab-delimited, from dbPTM download page):
  1. experimental_ptm_sites — UniProt ID, position, PTM type, sequence window
     (the main experimental sites file, categorized by modified amino acid)
  2. disease_associated_ptms — disease associations based on nsSNP annotation
  3. drug_binding_ptms — drug binding-associated PTM sites

The tool also provides a web-scraping fallback: if no local data is available,
it attempts to query the dbPTM search page by UniProt accession. This fallback
is best-effort since dbPTM renders pages dynamically.
"""

import logging
import re
from pathlib import Path
from typing import Any

import httpx

from app.config import settings
from app.tools.registry import registry

logger = logging.getLogger(__name__)

# In-memory indices (loaded lazily)
_ptm_sites_index: dict[str, list[dict[str, Any]]] | None = None  # keyed by uniprot_ac
_disease_index: dict[str, list[dict[str, Any]]] | None = None    # keyed by uniprot_ac
_drug_index: dict[str, list[dict[str, Any]]] | None = None       # keyed by uniprot_ac
_dbptm_loaded = False

# dbPTM web base URL for fallback queries
_DBPTM_WEB_BASE = "https://biomics.lab.nycu.edu.tw/dbPTM"


def _parse_ptm_type(raw_type: str) -> str:
    """Normalize dbPTM PTM type strings to our standard types."""
    raw = raw_type.strip().lower()
    type_map = {
        "phosphorylation": "phosphorylation",
        "phosphoryl": "phosphorylation",
        "acetylation": "acetylation",
        "ubiquitination": "ubiquitylation",
        "ubiquitylation": "ubiquitylation",
        "methylation": "methylation",
        "glycosylation": "glycosylation",
        "n-linked glycosylation": "glycosylation",
        "o-linked glycosylation": "glycosylation",
        "c-linked glycosylation": "glycosylation",
        "sumoylation": "sumoylation",
        "sumolation": "sumoylation",
    }
    for key, val in type_map.items():
        if key in raw:
            return val
    return raw_type.strip()


def _load_dbptm_data() -> None:
    """Load dbPTM bulk data files into in-memory indices."""
    global _ptm_sites_index, _disease_index, _drug_index, _dbptm_loaded

    if _dbptm_loaded:
        return

    dbptm_dir = Path(settings.dbptm_data_dir)
    _ptm_sites_index = {}
    _disease_index = {}
    _drug_index = {}

    # ── Load experimental PTM sites ──
    # dbPTM provides files categorized by modified amino acid / PTM type.
    # Users may place individual files or a combined file.
    site_candidates = [
        dbptm_dir / "experimental_ptm_sites",
        dbptm_dir / "experimental_ptm_sites.txt",
        dbptm_dir / "experimental_ptm_sites.tsv",
        dbptm_dir / "all_experimental_sites.tsv",
    ]
    # Also check for per-type files in subdirectories
    if dbptm_dir.exists():
        for f in dbptm_dir.glob("*.txt"):
            if f.name not in [c.name for c in site_candidates]:
                site_candidates.append(f)
        for f in dbptm_dir.glob("*.tsv"):
            if f.name not in [c.name for c in site_candidates]:
                site_candidates.append(f)

    sites_loaded = 0
    for filepath in site_candidates:
        if not filepath.exists():
            continue
        try:
            with open(filepath, encoding="utf-8", errors="replace") as f:
                header = None
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    parts = line.split("\t")
                    if header is None:
                        # First non-comment line is the header
                        header = [h.strip().lower() for h in parts]
                        continue

                    # Expected columns: UniProt ID/AC, position, PTM type, sequence window
                    # Be flexible with column names
                    col_map = {h: i for i, h in enumerate(header)}
                    acc = (
                        parts[col_map["uniprot_ac"]]
                        if "uniprot_ac" in col_map and col_map["uniprot_ac"] < len(parts)
                        else parts[col_map.get("uniprot id", col_map.get("protein_id", 0))]
                        if col_map.get("uniprot id", col_map.get("protein_id", 0)) < len(parts)
                        else parts[0]
                    )
                    acc = acc.strip()

                    pos_idx = col_map.get("position", col_map.get("modified position", 1))
                    position = int(parts[pos_idx]) if pos_idx < len(parts) and parts[pos_idx].isdigit() else None

                    type_idx = col_map.get("ptm type", col_map.get("modification", 2))
                    ptm_type = _parse_ptm_type(parts[type_idx]) if type_idx < len(parts) else ""

                    seq_idx = col_map.get("sequence", col_map.get("sequence window", 3))
                    sequence_window = parts[seq_idx].strip() if seq_idx < len(parts) else None

                    if position is None:
                        continue

                    entry = {
                        "uniprot_ac": acc,
                        "position": position,
                        "ptm_type": ptm_type,
                        "sequence_window": sequence_window,
                        "source": "dbPTM",
                    }
                    _ptm_sites_index.setdefault(acc, []).append(entry)
                    sites_loaded += 1

            logger.info(f"Loaded dbPTM sites from {filepath}: {sites_loaded} total entries so far")
        except Exception as e:
            logger.warning(f"Failed to load dbPTM file {filepath}: {e}")

    # ── Load disease-associated PTMs ──
    disease_candidates = [
        dbptm_dir / "disease_associated_ptms",
        dbptm_dir / "disease_associated_ptms.txt",
        dbptm_dir / "disease_associated_ptms.tsv",
    ]
    for filepath in disease_candidates:
        if not filepath.exists():
            continue
        try:
            with open(filepath, encoding="utf-8", errors="replace") as f:
                header = None
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    parts = line.split("\t")
                    if header is None:
                        header = [h.strip().lower() for h in parts]
                        continue
                    col_map = {h: i for i, h in enumerate(header)}
                    acc = parts[col_map.get("uniprot_ac", col_map.get("uniprot id", 0))].strip()
                    entry = {
                        "uniprot_ac": acc,
                        "position": int(parts[col_map.get("position", 1)]) if col_map.get("position", 1) < len(parts) and parts[col_map.get("position", 1)].isdigit() else None,
                        "ptm_type": _parse_ptm_type(parts[col_map.get("ptm type", 2)]) if col_map.get("ptm type", 2) < len(parts) else "",
                        "disease": parts[col_map.get("disease", col_map.get("disease name", 3))].strip() if col_map.get("disease", col_map.get("disease name", 3)) < len(parts) else "",
                        "snp": parts[col_map.get("snp", col_map.get("rs_id", 4))].strip() if col_map.get("snp", col_map.get("rs_id", 4)) < len(parts) else None,
                    }
                    _disease_index.setdefault(acc, []).append(entry)
            logger.info(f"Loaded dbPTM disease associations from {filepath}")
        except Exception as e:
            logger.warning(f"Failed to load dbPTM disease file {filepath}: {e}")

    # ── Load drug-binding PTMs ──
    drug_candidates = [
        dbptm_dir / "drug_binding_ptms",
        dbptm_dir / "drug_binding_ptms.txt",
        dbptm_dir / "drug_binding_ptms.tsv",
    ]
    for filepath in drug_candidates:
        if not filepath.exists():
            continue
        try:
            with open(filepath, encoding="utf-8", errors="replace") as f:
                header = None
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    parts = line.split("\t")
                    if header is None:
                        header = [h.strip().lower() for h in parts]
                        continue
                    col_map = {h: i for i, h in enumerate(header)}
                    acc = parts[col_map.get("uniprot_ac", col_map.get("uniprot id", 0))].strip()
                    entry = {
                        "uniprot_ac": acc,
                        "position": int(parts[col_map.get("position", 1)]) if col_map.get("position", 1) < len(parts) and parts[col_map.get("position", 1)].isdigit() else None,
                        "ptm_type": _parse_ptm_type(parts[col_map.get("ptm type", 2)]) if col_map.get("ptm type", 2) < len(parts) else "",
                        "drug": parts[col_map.get("drug", col_map.get("drug name", 3))].strip() if col_map.get("drug", col_map.get("drug name", 3)) < len(parts) else "",
                        "binding_type": parts[col_map.get("binding type", 4)].strip() if col_map.get("binding type", 4) < len(parts) else None,
                    }
                    _drug_index.setdefault(acc, []).append(entry)
            logger.info(f"Loaded dbPTM drug-binding data from {filepath}")
        except Exception as e:
            logger.warning(f"Failed to load dbPTM drug file {filepath}: {e}")

    _dbptm_loaded = True

    total_sites = sum(len(v) for v in _ptm_sites_index.values())
    total_disease = sum(len(v) for v in _disease_index.values())
    total_drug = sum(len(v) for v in _drug_index.values())
    if total_sites == 0 and total_disease == 0 and total_drug == 0:
        logger.info(
            "No dbPTM data files found in %s. dbptm_functional tool will use web fallback. "
            "Download experimental PTM sites from "
            "https://biomics.lab.nycu.edu.tw/dbPTM/download.php and place in data/dbptm/",
            dbptm_dir,
        )
    else:
        logger.info(
            "dbPTM data loaded: %d PTM sites, %d disease associations, %d drug-binding sites",
            total_sites, total_disease, total_drug,
        )


def _web_fallback_search(uniprot_ac: str) -> dict[str, Any] | None:
    """Best-effort web query to dbPTM search page by UniProt accession.

    dbPTM renders results dynamically, so this may not always work.
    Returns parsed data or None.
    """
    try:
        with httpx.Client(timeout=settings.http_timeout_seconds) as client:
            # Try the search by UniProt AC
            resp = client.get(
                f"{_DBPTM_WEB_BASE}/search.php",
                params={"search_type": "uniprot_ac", "keyword": uniprot_ac},
                headers={"Accept": "text/html"},
            )
            if resp.status_code != 200:
                return None

            # Parse the HTML for PTM site information
            # dbPTM search results contain tables with PTM site data
            text = resp.text
            # Look for protein info and PTM site tables
            # This is a best-effort parse; dbPTM uses PHP-rendered tables
            sites = []
            # Pattern: rows in PTM site tables typically have position, type, sequence
            # Match table rows with PTM data
            row_pattern = re.findall(
                r'<tr[^>]*>.*?(\d+).*?(Phosphorylation|Acetylation|Ubiquitination|Methylation|Glycosylation|Sumoylation).*?</tr>',
                text, re.IGNORECASE | re.DOTALL,
            )
            for pos_str, ptype in row_pattern:
                sites.append({
                    "position": int(pos_str),
                    "ptm_type": _parse_ptm_type(ptype),
                    "source": "dbPTM web",
                })

            if not sites:
                return None

            return {
                "uniprot_ac": uniprot_ac,
                "sites": sites[:20],
                "source": "dbPTM web (best-effort)",
            }
    except Exception as e:
        logger.debug(f"dbPTM web fallback failed for {uniprot_ac}: {e}")
        return None


# ── Tool 8: dbptm_functional ──────────────────────────────────────

def _dbptm_functional(
    uniprot_ac: str,
    position: int | None = None,
    ptm_type: str = "all",
) -> dict[str, Any]:
    """Query dbPTM for functional annotations, disease associations, and drug-binding data."""
    _load_dbptm_data()

    has_local_data = (
        (_ptm_sites_index and len(_ptm_sites_index) > 0)
        or (_disease_index and len(_disease_index) > 0)
        or (_drug_index and len(_drug_index) > 0)
    )

    # ── If no local data, try web fallback ──
    if not has_local_data:
        web_result = _web_fallback_search(uniprot_ac)
        if web_result:
            sites = web_result["sites"]
            if position:
                sites = [s for s in sites if s["position"] == position]
            summary = (
                f"dbPTM web query found {len(sites)} PTM site(s) for {uniprot_ac}"
                + (f" at position {position}" if position else "")
                + ". Note: This is a best-effort web query. For complete data, "
                "download dbPTM bulk files from biomics.lab.nycu.edu.tw/dbPTM/download.php"
            )
            return {
                "summary": summary,
                "uniprot_ac": uniprot_ac,
                "position": position,
                "source": "dbPTM web (best-effort)",
                "sites": sites[:15],
                "disease_associations": [],
                "drug_binding_sites": [],
            }
        else:
            return {
                "summary": (
                    f"No dbPTM data available for {uniprot_ac}. "
                    "dbPTM bulk data files not loaded and web query returned no results. "
                    "To enable dbPTM integration, download experimental PTM sites from "
                    "https://biomics.lab.nycu.edu.tw/dbPTM/download.php and place in data/dbptm/."
                ),
                "uniprot_ac": uniprot_ac,
                "position": position,
                "available": False,
            }

    # ── Query local indices ──
    # PTM sites
    all_sites = _ptm_sites_index.get(uniprot_ac, []) if _ptm_sites_index else []
    if position:
        sites = [s for s in all_sites if s["position"] == position]
    elif ptm_type != "all":
        sites = [s for s in all_sites if s["ptm_type"] == ptm_type]
    else:
        sites = all_sites

    # Disease associations
    all_disease = _disease_index.get(uniprot_ac, []) if _disease_index else []
    if position:
        disease = [d for d in all_disease if d.get("position") == position]
    else:
        disease = all_disease

    # Drug-binding sites
    all_drug = _drug_index.get(uniprot_ac, []) if _drug_index else []
    if position:
        drug_sites = [d for d in all_drug if d.get("position") == position]
    else:
        drug_sites = all_drug

    # Build summary
    parts = []
    if sites:
        site_types = set(s["ptm_type"] for s in sites)
        parts.append(f"{len(sites)} PTM site(s) in dbPTM ({', '.join(sorted(site_types))})")
    if disease:
        disease_names = set(d["disease"] for d in disease if d["disease"])
        parts.append(f"{len(disease)} disease association(s): {', '.join(sorted(disease_names)[:5])}")
    if drug_sites:
        drug_names = set(d["drug"] for d in drug_sites if d["drug"])
        parts.append(f"{len(drug_sites)} drug-binding PTM site(s): {', '.join(sorted(drug_names)[:5])}")

    if not parts:
        summary = f"No dbPTM annotations found for {uniprot_ac}"
        if position:
            summary += f" at position {position}"
        summary += "."
    else:
        summary = f"dbPTM data for {uniprot_ac}: " + "; ".join(parts) + "."

    return {
        "summary": summary,
        "uniprot_ac": uniprot_ac,
        "position": position,
        "available": True,
        "sites": sites[:20],
        "disease_associations": disease[:15],
        "drug_binding_sites": drug_sites[:15],
        "total_sites": len(all_sites),
        "total_disease": len(all_disease),
        "total_drug": len(all_drug),
    }


# ── Register tool ─────────────────────────────────────────────────

def register_dbptm_tools() -> None:
    """Register dbPTM tools with the global registry."""
    registry.register(
        name="dbptm_functional",
        description=(
            "Query the dbPTM database for functional annotations, disease associations, "
            "and drug-binding PTM sites. dbPTM integrates 2.79M PTM sites from 48 databases "
            "and 80K+ research articles, with disease associations based on nsSNP annotation "
            "and drug-binding site data. Use this for Stage 3: understanding disease relevance "
            "and therapeutic potential of a PTM site. If local bulk data files are not loaded, "
            "the tool falls back to a best-effort web query."
        ),
        parameters={
            "type": "object",
            "properties": {
                "uniprot_ac": {
                    "type": "string",
                    "description": "UniProt accession of the protein (e.g., P04637 for TP53)",
                },
                "position": {
                    "type": "integer",
                    "description": "Optional: filter to a specific residue position",
                },
                "ptm_type": {
                    "type": "string",
                    "enum": ["all", "phosphorylation", "acetylation", "ubiquitylation",
                             "methylation", "glycosylation", "sumoylation"],
                    "description": "Filter by PTM type (default: all)",
                },
            },
            "required": ["uniprot_ac"],
        },
        handler=_dbptm_functional,
    )
