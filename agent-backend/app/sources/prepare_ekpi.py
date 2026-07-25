"""Prepare eKPI phosphosite lookup table for Quantitative KPI queries.

Source site list: /var/www/html/ekpi/ekpi_all_phosphosite.txt
Quantitative matrices live in per-site gzip CSVs under final_result/
(not copied — queried on demand via EKPI_FINAL_RESULT_DIR).

Paper: Brief Bioinform 2025;26(2):bbaf143
  PMID 40194556; DOI 10.1093/bib/bbaf143
Homepage: https://ekpi.omicsbio.info/

Usage:
  python -m app.sources.prepare_ekpi
  python -m app.sources.build_index ekpi
"""

from __future__ import annotations

import argparse
import logging
import shutil
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)


def _root() -> Path:
    return Path(settings.data_root) / "enzymes" / "eKPI"


def _gene_token(name: str) -> str:
    """Match eKPI Result.go: first whitespace-delimited token of gene name."""
    return (name or "").strip().split()[0] if (name or "").strip() else ""


def _uniprot_base(ac: str) -> str:
    ac = (ac or "").strip().upper()
    return ac.split("-")[0] if ac else ""


def prepare_sites(src: Path, out: Path) -> int:
    cols = [
        "uniprot", "uniprot_base", "gene", "gene_token", "protein_name",
        "position", "residue", "site", "flank_n", "flank_c", "file_key",
    ]
    out.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with src.open("r", encoding="utf-8", errors="replace") as fin, out.open(
        "w", encoding="utf-8"
    ) as fout:
        header = fin.readline()
        if not header:
            raise ValueError(f"Empty source: {src}")
        fout.write("\t".join(cols) + "\n")
        for line in fin:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 7:
                continue
            uni, pos, gene, protein, fseq, obseq, eseq = parts[:7]
            uni = uni.strip()
            pos = pos.strip()
            if not uni or not pos.isdigit():
                continue
            residue = (obseq or "").strip().upper()[:1]
            gene = gene.strip()
            token = _gene_token(gene)
            site = f"{residue}{pos}" if residue else pos
            file_key = f"{uni}#{token}#{residue}{pos}" if token and residue else ""
            row = [
                uni.upper(),
                _uniprot_base(uni),
                gene,
                token,
                " ".join(protein.strip().split()),
                pos,
                residue,
                site,
                fseq.strip(),
                eseq.strip(),
                file_key,
            ]
            fout.write("\t".join(row) + "\n")
            n += 1
    return n


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = argparse.ArgumentParser(description="Prepare eKPI site lookup table")
    parser.add_argument(
        "--sites",
        default=None,
        help="Path to ekpi_all_phosphosite.txt "
        "(default: EKPI_DATA_DIR/ekpi_all_phosphosite.txt)",
    )
    args = parser.parse_args(argv)

    root = _root()
    root.mkdir(parents=True, exist_ok=True)

    src = Path(args.sites) if args.sites else Path(settings.ekpi_data_dir) / "ekpi_all_phosphosite.txt"
    if not src.exists():
        # Fall back to colocated copy if prepare was run after a manual copy
        alt = root / "ekpi_all_phosphosite.txt"
        if alt.exists():
            src = alt
        else:
            raise FileNotFoundError(
                f"eKPI sites file not found: {src}. "
                "Set EKPI_DATA_DIR or pass --sites."
            )

    # Keep a provenance copy under the aspect folder (28 MB)
    dest_raw = root / "ekpi_all_phosphosite.txt"
    if src.resolve() != dest_raw.resolve():
        shutil.copy2(src, dest_raw)
        logger.info("Copied %s → %s", src, dest_raw)

    out = root / "tables" / "sites.tsv"
    n = prepare_sites(dest_raw if dest_raw.exists() else src, out)
    logger.info("Wrote %s (%d rows)", out, n)
    logger.info(
        "Quantitative matrices: %s (on-demand; not copied)",
        settings.ekpi_final_result_dir,
    )
    logger.info("Next: python -m app.sources.build_index ekpi")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
