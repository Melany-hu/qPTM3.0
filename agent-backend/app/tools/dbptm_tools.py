"""dbPTM tools — query local dbPTM data for functional annotations and disease associations.

Stage 3 tool:
  8. dbptm_functional — look up functional annotations, disease associations,
     and regulatory network context for a PTM site

dbPTM (https://biomics.lab.nycu.edu.tw/dbPTM/) does not provide a public REST API.
Prepare local tables with:

  python -m app.sources.prepare_dbptm

Files (tab-delimited) under data/disease/dbptm/ or data/disease/dbptm/tables/:
  1. disease_associated_ptms — nsSNP / disease-associated PTM sites (primary)
  2. experimental_ptm_sites — optional site inventory (not required)

The tool also provides a web-scraping fallback: if no local data is available,
it attempts to query the dbPTM search page by UniProt accession. This fallback
is best-effort since dbPTM renders pages dynamically.
"""

from __future__ import annotations

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


def _candidate_files(dbptm_dir: Path, stem: str) -> list[Path]:
    """Prefer tables/ then data-dir root (loader picks first existing)."""
    names = [f"{stem}.tsv", f"{stem}.txt", stem]
    out: list[Path] = []
    for name in names:
        out.append(dbptm_dir / "tables" / name)
    for name in names:
        out.append(dbptm_dir / name)
    return out


def _col(col_map: dict[str, int], *names: str, default: int | None = None) -> int | None:
    for name in names:
        if name in col_map:
            return col_map[name]
    return default


def _cell(parts: list[str], idx: int | None, default: str = "") -> str:
    if idx is None or idx < 0 or idx >= len(parts):
        return default
    return parts[idx].strip()


def _index_put(index: dict[str, list[dict[str, Any]]], *keys: str, entry: dict[str, Any]) -> None:
    seen: set[str] = set()
    for key in keys:
        k = (key or "").strip()
        if not k or k in seen:
            continue
        seen.add(k)
        index.setdefault(k, []).append(entry)


def _first_existing(candidates: list[Path]) -> Path | None:
    seen: set[Path] = set()
    for path in candidates:
        if not path.exists():
            continue
        resolved = path.resolve()
        if resolved in seen:
            continue
        return resolved
    return None


def _load_dbptm_data() -> None:
    """Load dbPTM bulk data files into in-memory indices."""
    global _ptm_sites_index, _disease_index, _dbptm_loaded

    if _dbptm_loaded:
        return

    dbptm_dir = Path(settings.dbptm_data_dir)
    _ptm_sites_index = {}
    _disease_index = {}

    # ── Load experimental PTM sites (optional) ──
    site_candidates = _candidate_files(dbptm_dir, "experimental_ptm_sites")
    site_candidates.append(dbptm_dir / "all_experimental_sites.tsv")
    site_candidates.append(dbptm_dir / "tables" / "all_experimental_sites.tsv")
    skip_names = {
        "disease_associated_ptms", "disease_associated_ptms.txt", "disease_associated_ptms.tsv",
    }
    if dbptm_dir.exists():
        for f in list(dbptm_dir.glob("*.txt")) + list(dbptm_dir.glob("*.tsv")):
            if f.name in skip_names:
                continue
            if f not in site_candidates:
                site_candidates.append(f)

    sites_loaded = 0
    seen_site_files: set[Path] = set()
    for filepath in site_candidates:
        if not filepath.exists():
            continue
        resolved = filepath.resolve()
        if resolved in seen_site_files:
            continue
        seen_site_files.add(resolved)
        try:
            with open(resolved, encoding="utf-8", errors="replace") as f:
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
                    acc = _cell(
                        parts,
                        _col(col_map, "uniprot_ac", "uniprot id", "uniprot_id", "protein_id", default=0),
                    )
                    pos_raw = _cell(
                        parts,
                        _col(col_map, "position", "modified position", "modified_location", default=1),
                    )
                    position = int(pos_raw) if pos_raw.isdigit() else None
                    ptm_type = _parse_ptm_type(
                        _cell(parts, _col(col_map, "ptm type", "ptm_type", "modification", default=2))
                    )
                    sequence_window = _cell(
                        parts,
                        _col(col_map, "sequence", "sequence window", "sequence_window", default=3),
                    ) or None

                    if position is None or not acc:
                        continue

                    entry = {
                        "uniprot_ac": acc,
                        "position": position,
                        "ptm_type": ptm_type,
                        "sequence_window": sequence_window,
                        "source": "dbPTM",
                    }
                    _index_put(_ptm_sites_index, acc, entry=entry)
                    sites_loaded += 1

            logger.info("Loaded dbPTM sites from %s: %d total entries so far", resolved, sites_loaded)
        except Exception as e:
            logger.warning("Failed to load dbPTM file %s: %s", resolved, e)

    # ── Load disease-associated PTMs (prefer tables/, single file) ──
    disease_path = _first_existing(_candidate_files(dbptm_dir, "disease_associated_ptms"))
    if disease_path is not None:
        try:
            with open(disease_path, encoding="utf-8", errors="replace") as f:
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
                    acc = _cell(parts, _col(col_map, "uniprot_ac", "uniprot id", "uniprot_id", default=0))
                    entry_name = _cell(parts, _col(col_map, "uniprot_id", "entry_name", "id"))
                    pos_raw = _cell(
                        parts,
                        _col(col_map, "position", "modified_location", "modified location", default=1),
                    )
                    entry = {
                        "uniprot_ac": acc,
                        "uniprot_id": entry_name or None,
                        "position": int(pos_raw) if pos_raw.isdigit() else None,
                        "ptm_type": _parse_ptm_type(
                            _cell(parts, _col(col_map, "ptm type", "ptm_type", default=2))
                        ),
                        "disease": _cell(
                            parts,
                            _col(col_map, "disease", "disease name", "related_disease", default=3),
                        ),
                        "snp": _cell(parts, _col(col_map, "snp", "rs_id", "snp_id", default=4)) or None,
                        "sap_position": _cell(parts, _col(col_map, "sap_position", "sap position")) or None,
                        "pmid": _cell(parts, _col(col_map, "pmid", "reference")) or None,
                        "source": "dbPTM",
                    }
                    _index_put(_disease_index, acc, entry_name, entry=entry)
            logger.info("Loaded dbPTM disease associations from %s", disease_path)
        except Exception as e:
            logger.warning("Failed to load dbPTM disease file %s: %s", disease_path, e)

    _dbptm_loaded = True

    total_sites = sum(len(v) for v in _ptm_sites_index.values())
    total_disease = sum(len(v) for v in _disease_index.values())
    if total_sites == 0 and total_disease == 0:
        logger.info(
            "No dbPTM data files found in %s. dbptm_functional tool will use web fallback. "
            "Run: python -m app.sources.prepare_dbptm",
            dbptm_dir,
        )
    else:
        logger.info(
            "dbPTM data loaded: %d PTM sites, %d disease associations",
            total_sites, total_disease,
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
    """Query dbPTM for nsSNP-linked disease associations (and optional site inventory)."""
    _load_dbptm_data()

    has_local_data = (
        (_ptm_sites_index and len(_ptm_sites_index) > 0)
        or (_disease_index and len(_disease_index) > 0)
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
                "run: python -m app.sources.prepare_dbptm"
            )
            return {
                "summary": summary,
                "uniprot_ac": uniprot_ac,
                "position": position,
                "source": "dbPTM web (best-effort)",
                "sites": sites[:15],
                "disease_associations": [],
            }
        else:
            return {
                "summary": (
                    f"No dbPTM data available for {uniprot_ac}. "
                    "dbPTM bulk data files not loaded and web query returned no results. "
                    "To enable dbPTM integration, run: python -m app.sources.prepare_dbptm"
                ),
                "uniprot_ac": uniprot_ac,
                "position": position,
                "available": False,
            }

    # ── Query local indices ──
    all_sites = _ptm_sites_index.get(uniprot_ac, []) if _ptm_sites_index else []
    if position:
        sites = [s for s in all_sites if s["position"] == position]
    elif ptm_type != "all":
        sites = [s for s in all_sites if s["ptm_type"] == ptm_type]
    else:
        sites = all_sites

    all_disease = _disease_index.get(uniprot_ac, []) if _disease_index else []
    if position:
        disease = [d for d in all_disease if d.get("position") == position]
    else:
        disease = all_disease

    parts = []
    if sites:
        site_types = set(s["ptm_type"] for s in sites)
        parts.append(f"{len(sites)} PTM site(s) in dbPTM ({', '.join(sorted(site_types))})")
    if disease:
        disease_names = set(d["disease"] for d in disease if d["disease"])
        parts.append(f"{len(disease)} disease association(s): {', '.join(sorted(disease_names)[:5])}")

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
        "total_sites": len(all_sites),
        "total_disease": len(all_disease),
    }


# ── Register tool ─────────────────────────────────────────────────

def register_dbptm_tools() -> None:
    """Register dbPTM tools with the global registry."""
    registry.register(
        name="dbptm_functional",
        description=(
            "Query dbPTM for disease associations based on nsSNP / GWAS proximity to PTM sites. "
            "Distinct from PTMD (literature PDAs) and DrugBank (use drugbank_targets / PMADS for drugs). "
            "If local bulk data files are not loaded, falls back to a best-effort web query."
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
