"""PTM stability tools — query curated PTM-protein stability relationships.

Direction 3 tool:
  ptm_stability — look up how a PTM affects protein stability (stabilize/destabilize)

Data source: A manually curated dataset compiled from the Nature Communications
review "Control of protein stability by post-translational modifications"
(Batista et al., 2023, doi:10.1038/s41467-023-35795-8, PMC9839724).

The dataset covers 7 PTM types (phosphorylation, methylation, acetylation,
ubiquitylation, SUMOylation, hydroxylation, glycosylation) and 34 substrate
proteins, with 78 curated relationships. Each entry records:
  - effect_direction: stabilize or destabilize
  - mechanism: molecular mechanism (degron type, E3 ligase, reader protein, etc.)
  - writer/eraser/reader: enzymes and recognition proteins
  - ubiquitin_sites: specific lysines targeted for ubiquitination
  - evidence: experimental
  - source: primary-literature PMID(s) supporting the claim (pipe-separated)
  - curated_from: PMC9839724 (review used as curation provenance)

The TSV file is loaded into an in-memory index on first access, keyed by
UniProt accession for fast per-protein lookup.
"""

from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Any

from app.config import settings
from app.tools.registry import registry

logger = logging.getLogger(__name__)

# In-memory index: uniprot_ac -> list of stability entry dicts
_stability_index: dict[str, list[dict[str, Any]]] | None = None
_stability_loaded = False


def _load_stability_data() -> dict[str, list[dict[str, Any]]]:
    """Load the curated PTM-stability TSV into an in-memory index."""
    global _stability_index, _stability_loaded

    if _stability_loaded:
        return _stability_index or {}

    stability_dir = Path(settings.stability_data_dir)
    filepath = stability_dir / "ptm_stability_curated.tsv"

    if not filepath.exists():
        logger.warning(
            "PTM-stability curated dataset not found at %s. "
            "ptm_stability tool will return empty results.",
            filepath,
        )
        _stability_loaded = True
        _stability_index = {}
        return _stability_index

    logger.info(f"Loading PTM-stability curated dataset from {filepath}...")
    index: dict[str, list[dict[str, Any]]] = {}

    try:
        with open(filepath, encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter="\t")
            for row in reader:
                acc = row.get("uniprot_ac", "").strip()
                if not acc:
                    continue

                # Parse position (may be "-" for unspecified)
                pos_str = row.get("position", "").strip()
                position: int | None = None
                if pos_str and pos_str != "-":
                    try:
                        position = int(pos_str)
                    except ValueError:
                        pass

                def _clean(val: str) -> str | None:
                    """Convert empty string or '-' placeholder to None."""
                    v = (val or "").strip()
                    return v if v and v != "-" else None

                entry = {
                    "uniprot_ac": acc,
                    "gene": row.get("gene", "").strip(),
                    "ptm_type": row.get("ptm_type", "").strip(),
                    "position": position,
                    "effect_direction": row.get("effect_direction", "").strip(),
                    "mechanism": row.get("mechanism", "").strip(),
                    "writer": _clean(row.get("writer", "")),
                    "eraser": _clean(row.get("eraser", "")),
                    "reader": _clean(row.get("reader", "")),
                    "ubiquitin_sites": _clean(row.get("ubiquitin_sites", "")),
                    "evidence": row.get("evidence", "").strip(),
                    "source": row.get("source", "").strip(),
                    "curated_from": row.get("curated_from", "").strip() or "PMC9839724",
                }
                index.setdefault(acc, []).append(entry)

        total = sum(len(v) for v in index.values())
        logger.info(f"Loaded {total} PTM-stability entries for {len(index)} proteins")

    except Exception as e:
        logger.error(f"Failed to load PTM-stability data: {e}", exc_info=True)
        index = {}

    _stability_loaded = True
    _stability_index = index
    return _stability_index


# ── Tool: ptm_stability ───────────────────────────────────────────

def _ptm_stability(
    uniprot_ac: str,
    position: int | None = None,
    ptm_type: str = "all",
) -> dict[str, Any]:
    """Query the curated PTM-stability dataset for a protein or specific site.

    Returns all known PTM-stability relationships for the given protein,
    optionally filtered by residue position and/or PTM type. Each entry
    indicates whether the modification stabilizes or destabilizes the protein,
    the molecular mechanism, and the writer/eraser/reader enzymes involved.
    """
    index = _load_stability_data()

    if not index:
        return {
            "summary": (
                "PTM-stability curated dataset not loaded. "
                "The dataset file (ptm_stability_curated.tsv) should be in "
                "the data/stability/curated/ directory."
            ),
            "uniprot_ac": uniprot_ac,
            "available": False,
        }

    all_entries = index.get(uniprot_ac, [])

    if not all_entries:
        return {
            "summary": (
                f"No PTM-stability data found for {uniprot_ac} in the curated dataset. "
                f"The dataset covers {len(index)} proteins from a review of "
                f"PTM-controlled protein stability (PMC9839724). "
                f"This protein may not be covered by that review."
            ),
            "uniprot_ac": uniprot_ac,
            "available": True,
            "found": False,
            "total_proteins_in_dataset": len(index),
        }

    # Filter by position
    entries = all_entries
    if position:
        # Match exact position OR entries with no specified position (general mechanism)
        entries = [
            e for e in all_entries
            if e["position"] == position or e["position"] is None
        ]

    # Filter by PTM type
    if ptm_type != "all":
        entries = [e for e in entries if e["ptm_type"] == ptm_type]

    if not entries:
        filter_desc = []
        if position:
            filter_desc.append(f"position {position}")
        if ptm_type != "all":
            filter_desc.append(ptm_type)
        filter_str = " and ".join(filter_desc) if filter_desc else "these filters"
        return {
            "summary": (
                f"No PTM-stability entries match {filter_str} for {uniprot_ac}. "
                f"The protein has {len(all_entries)} total entries in the dataset "
                f"but none match the specified filters."
            ),
            "uniprot_ac": uniprot_ac,
            "available": True,
            "found": False,
            "total_for_protein": len(all_entries),
        }

    # Build summary
    gene = entries[0]["gene"] if entries else uniprot_ac
    stabilize = [e for e in entries if e["effect_direction"] == "stabilize"]
    destabilize = [e for e in entries if e["effect_direction"] == "destabilize"]

    parts = []
    parts.append(f"Found {len(entries)} PTM-stability relationship(s) for {gene} ({uniprot_ac})")
    if position:
        parts.append(f"at position {position}")
    if ptm_type != "all":
        parts.append(f"for {ptm_type}")
    summary = " ".join(parts) + ". "

    if stabilize:
        stab_details = []
        for e in stabilize[:5]:
            detail = f"{e['ptm_type']}"
            if e["position"]:
                detail += f" at {e['position']}"
            if e["writer"] and e["writer"] != "-":
                detail += f" (writer: {e['writer']})"
            stab_details.append(detail)
        summary += f"Stabilizing: {', '.join(stab_details)}. "

    if destabilize:
        destab_details = []
        for e in destabilize[:5]:
            detail = f"{e['ptm_type']}"
            if e["position"]:
                detail += f" at {e['position']}"
            if e["writer"] and e["writer"] != "-":
                detail += f" (writer: {e['writer']})"
            destab_details.append(detail)
        summary += f"Destabilizing: {', '.join(destab_details)}. "

    primary_pmids: list[str] = []
    seen_pmid: set[str] = set()
    for e in entries:
        for part in (e.get("source") or "").replace(",", "|").split("|"):
            pmid = part.strip()
            if pmid.isdigit() and pmid not in seen_pmid:
                seen_pmid.add(pmid)
                primary_pmids.append(pmid)
    if primary_pmids:
        summary += f"Primary literature: PMID {', '.join(primary_pmids[:8])}"
        if len(primary_pmids) > 8:
            summary += f" (+{len(primary_pmids) - 8} more)"
        summary += ". "
    summary += "Curated from PMC9839724 (Nat Comms 2023)."

    return {
        "summary": summary,
        "uniprot_ac": uniprot_ac,
        "gene": gene,
        "available": True,
        "found": True,
        "total": len(entries),
        "stabilize_count": len(stabilize),
        "destabilize_count": len(destabilize),
        "entries": entries[:20],
        "primary_pmids": primary_pmids[:20],
        "curated_from": "PMC9839724",
        "total_for_protein": len(all_entries),
        "total_proteins_in_dataset": len(index),
    }


# ── Register tool ─────────────────────────────────────────────────

def register_stability_tools() -> None:
    """Register PTM stability tools with the global registry."""
    registry.register(
        name="ptm_stability",
        description=(
            "Query a curated dataset of PTM-protein stability relationships. "
            "Returns how a specific PTM (phosphorylation, methylation, acetylation, "
            "ubiquitylation, SUMOylation, hydroxylation, glycosylation) affects "
            "protein stability — whether it stabilizes or destabilizes the protein, "
            "the molecular mechanism (degron type, E3 ligase, reader protein), "
            "and the writer/eraser/reader enzymes involved. "
            "Entries cite primary literature PMIDs; the table was curated from a "
            "Nature Communications review of PTM-controlled protein stability "
            "(PMC9839724, 2023). Covers 34 substrate proteins and "
            "78 PTM-stability relationships. "
            "Use this for Direction 3: understanding how PTMs affect protein stability "
            "and degradation. Query by UniProt accession, optionally filtered by "
            "residue position and PTM type."
        ),
        parameters={
            "type": "object",
            "properties": {
                "uniprot_ac": {
                    "type": "string",
                    "description": "UniProt accession of the substrate protein (e.g., P04637 for TP53)",
                },
                "position": {
                    "type": "integer",
                    "description": "Optional: filter to a specific residue position (e.g., 15 for S15)",
                },
                "ptm_type": {
                    "type": "string",
                    "enum": ["all", "phosphorylation", "acetylation", "ubiquitylation",
                             "methylation", "glycosylation", "sumoylation", "hydroxylation"],
                    "description": "Filter by PTM type (default: all)",
                },
            },
            "required": ["uniprot_ac"],
        },
        handler=_ptm_stability,
    )
