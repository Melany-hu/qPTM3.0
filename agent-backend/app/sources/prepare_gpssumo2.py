"""Prepare GPS-SUMO 2.0 curated training/test tables from supplementary xlsx.

Source: GPS-SUMO2.xlsx (Tables S2A/S2B/S2C from NAR 2024, PMID 38709873).
These are experimentally curated SUMOylation sites and SIMs used to train
GPS-SUMO 2.0 — real literature/database-backed data, not predictor output.

Keeps qPTM organisms: human, mouse, rat, yeast.

Usage:
  python -m app.sources.prepare_gpssumo2
  python -m app.sources.build_index gpssumo2
"""

from __future__ import annotations

import argparse
import logging
import re
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)

_PMID_RE = re.compile(r"^\d{5,9}$")
_RANGE_RE = re.compile(r"^(\d+)\s*[-–]\s*(\d+)$")

KEEP_SPECIES = {
    "Homo sapiens": "human",
    "Mus musculus": "mouse",
    "Rattus norvegicus": "rat",
    "Rattus norvegicus (Rat)": "rat",
    "Saccharomyces cerevisiae": "yeast",
}


def _root() -> Path:
    return Path(settings.data_root) / "enzymes" / "GPS-SUMO2"


def _uniprot_base(ac: str) -> str:
    ac = (ac or "").strip().upper()
    return ac.split("-")[0] if ac else ""


def _parse_source(raw: str) -> tuple[str, str]:
    """Split 'CPLM 4.0;11581165;19837819' → (source_dbs, pmids)."""
    dbs: list[str] = []
    pmids: list[str] = []
    for part in str(raw or "").replace(",", ";").split(";"):
        part = part.strip()
        if not part:
            continue
        if _PMID_RE.match(part):
            if part not in pmids:
                pmids.append(part)
        else:
            if part not in dbs:
                dbs.append(part)
    return ";".join(dbs), ";".join(pmids)


def _iter_sheet(xlsx: Path, sheet: str, skip_title_rows: int = 3):
    import openpyxl

    wb = openpyxl.load_workbook(str(xlsx), read_only=True, data_only=True)
    try:
        ws = wb[sheet]
        for i, row in enumerate(ws.iter_rows(values_only=True)):
            if i < skip_title_rows:
                continue
            if not row or row[0] is None or not str(row[0]).strip():
                continue
            # Skip accidental header repeats
            if str(row[0]).strip().lower() == "uniprot":
                continue
            yield [("" if c is None else str(c).strip()) for c in row]
    finally:
        wb.close()


def prepare_sumoylation(xlsx: Path, out: Path) -> int:
    cols = [
        "uniprot", "uniprot_base", "position", "residue", "peptide",
        "organism", "species", "source_dbs", "pmids", "dataset_split",
    ]
    seen: set[tuple[str, str]] = set()
    n = 0
    out.parent.mkdir(parents=True, exist_ok=True)

    with out.open("w", encoding="utf-8") as w:
        w.write("\t".join(cols) + "\n")
        for sheet, split in (("Table S2A", "train"), ("Table S2B", "test")):
            for cells in _iter_sheet(xlsx, sheet):
                if len(cells) < 5:
                    continue
                uni, pos, peptide, species, source = cells[:5]
                org = KEEP_SPECIES.get(species.strip())
                if not org:
                    continue
                base = _uniprot_base(uni)
                pos = pos.strip()
                if not base or not pos.isdigit():
                    continue
                key = (base, pos)
                if key in seen:
                    continue
                seen.add(key)
                dbs, pmids = _parse_source(source)
                row = [
                    uni.strip().upper(),
                    base,
                    pos,
                    "K",  # SUMOylation occurs on lysine
                    peptide,
                    org,
                    species.strip(),
                    dbs,
                    pmids,
                    split,
                ]
                w.write("\t".join(row) + "\n")
                n += 1
    return n


def prepare_sims(xlsx: Path, out: Path) -> int:
    cols = [
        "uniprot", "uniprot_base", "position_start", "position_end",
        "position", "peptide", "organism", "species", "source_dbs", "pmids",
    ]
    n = 0
    out.parent.mkdir(parents=True, exist_ok=True)

    with out.open("w", encoding="utf-8") as w:
        w.write("\t".join(cols) + "\n")
        for cells in _iter_sheet(xlsx, "Table S2C"):
            if len(cells) < 5:
                continue
            uni, pos_raw, peptide, species, resource = cells[:5]
            org = KEEP_SPECIES.get(species.strip())
            if not org:
                continue
            base = _uniprot_base(uni)
            m = _RANGE_RE.match(pos_raw.replace(" ", ""))
            if not base or not m:
                continue
            start, end = m.group(1), m.group(2)
            dbs, pmids = _parse_source(resource)
            # SIM Resource column is often PMID-only
            if not pmids and _PMID_RE.match(resource.strip()):
                pmids = resource.strip()
            row = [
                uni.strip().upper(),
                base,
                start,
                end,
                f"{start}-{end}",
                peptide,
                org,
                species.strip(),
                dbs,
                pmids,
            ]
            w.write("\t".join(row) + "\n")
            n += 1
    return n


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = argparse.ArgumentParser(description="Prepare GPS-SUMO 2.0 curated tables")
    parser.add_argument(
        "--xlsx",
        default=None,
        help="Path to GPS-SUMO2.xlsx (default: data/enzymes/GPS-SUMO2/GPS-SUMO2.xlsx)",
    )
    args = parser.parse_args(argv)

    root = _root()
    xlsx = Path(args.xlsx) if args.xlsx else root / "GPS-SUMO2.xlsx"
    if not xlsx.exists():
        raise FileNotFoundError(xlsx)

    sites = root / "tables" / "sumoylation_sites.tsv"
    sims = root / "tables" / "sims.tsv"
    n_sites = prepare_sumoylation(xlsx, sites)
    n_sims = prepare_sims(xlsx, sims)
    logger.info("Wrote %s (%d rows)", sites, n_sites)
    logger.info("Wrote %s (%d rows)", sims, n_sims)
    logger.info("Next: python -m app.sources.build_index gpssumo2")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
