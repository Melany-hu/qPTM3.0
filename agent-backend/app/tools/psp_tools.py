"""PhosphoSitePlus tools — query local PSP regulatory site annotations.

Stage 3 tool:
  7. psp_regulatory — look up functional effects of a PTM site

PhosphoSitePlus does not have a public API. Users download the
'Regulatory_sites' file from phosphosite.org (free account required)
and place it in data/psp/. The file is loaded into an in-memory index
on first access.

The Regulatory_sites file is a tab-delimited text file with columns:
  GENE, PROTEIN, ACC_ID (UniProt), MOD_RSD (e.g., S15-p),
  ORG, MOD_TYPE, ON_FUNCTION, ON_PROCESS, ON_PROT_INTERACT,
  ON_OTHER_INTERACT, NOTES, PMIDS

The key fields for functional consequences:
  ON_FUNCTION — molecular function effects (e.g., "activity, induced")
  ON_PROCESS — cellular process effects (e.g., "cell cycle progression")
  ON_PROT_INTERACT — protein interactions induced/disrupted
  ON_OTHER_INTERACT — other interactions (DNA, RNA, etc.)
"""

import logging
import os
import re
from pathlib import Path
from typing import Any

from app.config import settings
from app.tools.registry import registry

logger = logging.getLogger(__name__)

# In-memory index: (uniprot_ac, position, ptm_type) → annotation dict
_psp_index: dict[tuple[str, int, str], dict[str, Any]] | None = None
_psp_loaded = False


def _parse_mod_rsd(mod_rsd: str) -> tuple[str, int, str] | None:
    """Parse a MOD_RSD string like 'S15-p' or 'K120-u' into (residue, position, ptm_type).

    Returns (residue_letter, position, ptm_type) or None if unparseable.
    """
    # Patterns: S15-p, K120-ac, K120-ub, K120-me, K120-sm, N120-g
    match = re.match(r'^([A-Z])(\d+)-([a-z]+)$', mod_rsd.strip())
    if not match:
        return None
    residue, pos_str, mod_code = match.groups()
    position = int(pos_str)

    # Map PSP modification codes to our PTM types
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
    return residue, position, ptm_type


def _load_psp_data() -> dict[tuple[str, int, str], dict[str, Any]]:
    """Load the PhosphoSitePlus Regulatory_sites file into an in-memory index."""
    global _psp_index, _psp_loaded

    if _psp_loaded:
        return _psp_index or {}

    psp_dir = Path(settings.psp_data_dir)
    # Try common filenames
    candidates = [
        psp_dir / "Regulatory_sites",
        psp_dir / "Regulatory_sites.txt",
        psp_dir / "regulatory_sites.tsv",
    ]

    filepath = None
    for c in candidates:
        if c.exists():
            filepath = c
            break

    if filepath is None:
        logger.info("PhosphoSitePlus Regulatory_sites file not found in %s. "
                    "psp_regulatory tool will return empty results. "
                    "Download from phosphosite.org (free account) and place in data/psp/", psp_dir)
        _psp_loaded = True
        _psp_index = {}
        return _psp_index

    logger.info(f"Loading PhosphoSitePlus data from {filepath}...")
    index: dict[tuple[str, int, str], dict[str, Any]] = {}

    try:
        with open(filepath, encoding="iso-8859-1") as f:
            # PSP files have header lines starting with #, then column headers
            header_line = None
            for line in f:
                if line.startswith("#"):
                    continue
                header_line = line.strip()
                break

            if not header_line:
                logger.warning("PSP file appears empty or has no header")
                _psp_loaded = True
                _psp_index = {}
                return _psp_index

            headers = header_line.split("\t")

            # Find column indices
            col_map = {h: i for i, h in enumerate(headers)}
            acc_idx = col_map.get("ACC_ID", col_map.get("ACC_ID ", -1))
            mod_idx = col_map.get("MOD_RSD", -1)
            func_idx = col_map.get("ON_FUNCTION", -1)
            proc_idx = col_map.get("ON_PROCESS", -1)
            ppi_idx = col_map.get("ON_PROT_INTERACT", -1)
            other_idx = col_map.get("ON_OTHER_INTERACT", -1)
            notes_idx = col_map.get("NOTES", -1)
            pmid_idx = col_map.get("PMIDS", -1)

            if acc_idx < 0 or mod_idx < 0:
                logger.warning("PSP file missing required columns (ACC_ID, MOD_RSD)")
                _psp_loaded = True
                _psp_index = {}
                return _psp_index

            for line in f:
                parts = line.strip().split("\t")
                if len(parts) <= max(acc_idx, mod_idx):
                    continue

                acc_id = parts[acc_idx].strip()
                mod_rsd = parts[mod_idx].strip()
                parsed = _parse_mod_rsd(mod_rsd)
                if not parsed:
                    continue

                _, position, ptm_type = parsed

                def safe_get(idx: int) -> list[str]:
                    if idx < 0 or idx >= len(parts):
                        return []
                    val = parts[idx].strip()
                    if not val:
                        return []
                    return [v.strip() for v in val.split(";") if v.strip()]

                entry = {
                    "uniprot_ac": acc_id,
                    "position": position,
                    "ptm_type": ptm_type,
                    "on_function": safe_get(func_idx),
                    "on_process": safe_get(proc_idx),
                    "on_prot_interact": safe_get(ppi_idx),
                    "on_other_interact": safe_get(other_idx),
                    "notes": parts[notes_idx].strip() if notes_idx >= 0 and notes_idx < len(parts) else None,
                    "pmids": safe_get(pmid_idx),
                }
                index[(acc_id, position, ptm_type)] = entry

        logger.info(f"Loaded {len(index)} PSP regulatory site annotations")
    except Exception as e:
        logger.error(f"Failed to load PSP data: {e}", exc_info=True)
        index = {}

    _psp_loaded = True
    _psp_index = index
    return _psp_index


# ── Tool 7: psp_regulatory ────────────────────────────────────────

def _psp_regulatory(
    uniprot_ac: str,
    position: int,
    ptm_type: str = "phosphorylation",
) -> dict[str, Any]:
    """Look up PhosphoSitePlus regulatory annotations for a PTM site."""
    index = _load_psp_data()

    if not index:
        return {
            "summary": (
                "PhosphoSitePlus data not loaded. To enable functional consequence analysis, "
                "download the 'Regulatory_sites' file from phosphosite.org (free account) "
                "and place it in the data/psp/ directory."
            ),
            "uniprot_ac": uniprot_ac,
            "position": position,
            "available": False,
        }

    # Try exact match
    key = (uniprot_ac, position, ptm_type)
    entry = index.get(key)

    # If no exact match, try without ptm_type (search all PTM types for this site)
    if not entry:
        for (acc, pos, ptype), e in index.items():
            if acc == uniprot_ac and pos == position:
                entry = e
                break

    if not entry:
        return {
            "summary": f"No PhosphoSitePlus regulatory annotation found for {uniprot_ac} position {position}.",
            "uniprot_ac": uniprot_ac,
            "position": position,
            "available": True,
            "found": False,
        }

    # Build summary
    parts = []
    if entry["on_function"]:
        parts.append(f"Function: {', '.join(entry['on_function'])}")
    if entry["on_process"]:
        parts.append(f"Process: {', '.join(entry['on_process'])}")
    if entry["on_prot_interact"]:
        parts.append(f"Protein interactions: {', '.join(entry['on_prot_interact'])}")
    if entry["on_other_interact"]:
        parts.append(f"Other interactions: {', '.join(entry['on_other_interact'])}")
    if entry["notes"]:
        parts.append(f"Notes: {entry['notes']}")

    summary = f"PhosphoSitePlus regulatory annotation for {uniprot_ac} {position}: " + \
              "; ".join(parts) if parts else f"Entry found but no functional annotations."

    return {
        "summary": summary,
        "uniprot_ac": uniprot_ac,
        "position": position,
        "ptm_type": entry["ptm_type"],
        "available": True,
        "found": True,
        "on_function": entry["on_function"],
        "on_process": entry["on_process"],
        "on_prot_interact": entry["on_prot_interact"],
        "on_other_interact": entry["on_other_interact"],
        "notes": entry["notes"],
        "pmids": entry["pmids"],
    }


# ── Register tool ─────────────────────────────────────────────────

def register_psp_tools() -> None:
    """Register PhosphoSitePlus tools with the global registry."""
    registry.register(
        name="psp_regulatory",
        description=(
            "Look up PhosphoSitePlus regulatory site annotations for a PTM site. "
            "Returns functional effects (ON_FUNCTION: enzyme activity, stability, etc.), "
            "cellular process effects (ON_PROCESS: cell cycle, apoptosis, etc.), "
            "protein interaction changes (ON_PROT_INTERACT: induces/disrupts binding), "
            "and literature references (PMIDs). "
            "This is the PRIMARY data source for Stage 3: understanding what happens to "
            "protein function after modification. Requires the Regulatory_sites file "
            "downloaded from phosphosite.org."
        ),
        parameters={
            "type": "object",
            "properties": {
                "uniprot_ac": {
                    "type": "string",
                    "description": "UniProt accession of the modified protein",
                },
                "position": {
                    "type": "integer",
                    "description": "Residue position of the modification site",
                },
                "ptm_type": {
                    "type": "string",
                    "enum": ["phosphorylation", "acetylation", "ubiquitylation",
                             "methylation", "glycosylation", "sumoylation"],
                    "description": "PTM type (default: phosphorylation)",
                },
            },
            "required": ["uniprot_ac", "position"],
        },
        handler=_psp_regulatory,
    )
