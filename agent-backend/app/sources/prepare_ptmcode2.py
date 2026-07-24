"""Prepare lean working tables from PTMcode2 raw dumps.

Keeps associations for qPTM organisms with strong evidence flags:
  Species: Homo sapiens, Mus musculus, Rattus norvegicus, Saccharomyces cerevisiae
  within:  manual OR structure_distance OR same_residue(competition)
  between: manual OR structure_distance

Discards other species and coevolution-only noise
(~35M raw rows → curated unique pairs).

Usage:
  python -m app.sources.prepare_ptmcode2
"""

from __future__ import annotations

import argparse
import gzip
import logging
import re
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)

_RES = re.compile(r"^([A-Za-z])?(\d+)")

# Align with qPTM agent organisms
KEEP_SPECIES = frozenset({
    "Homo sapiens",
    "Mus musculus",
    "Rattus norvegicus",
    "Saccharomyces cerevisiae",
})

SPECIES_TO_ORG = {
    "Homo sapiens": "human",
    "Mus musculus": "mouse",
    "Rattus norvegicus": "rat",
    "Saccharomyces cerevisiae": "yeast",
}


def _pos(res: str) -> str:
    m = _RES.match((res or "").strip())
    return m.group(2) if m else ""


def _root() -> Path:
    return Path(settings.data_root) / "interactions" / "PTMcode2"


def extract_within(base: Path) -> Path:
    src = base / "PTMcode2_associations_within_proteins.txt.gz"
    out_dir = base / "tables"
    out_dir.mkdir(exist_ok=True)
    out = out_dir / "within.tsv"
    if not src.exists():
        raise FileNotFoundError(src)

    cols = [
        "organism", "species", "gene",
        "ptm1", "residue1", "position1", "propagated1", "rrcs1",
        "ptm2", "residue2", "position2", "propagated2", "rrcs2",
        "coevolution", "same_residue", "manual", "structure",
    ]
    seen: set[tuple] = set()
    n_in = n_out = 0

    with gzip.open(src, "rt", encoding="utf-8", errors="replace") as f, out.open(
        "w", encoding="utf-8"
    ) as w:
        w.write("\t".join(cols) + "\n")
        header = None
        for line in f:
            if line.startswith("## Protein\t"):
                header = [c.strip() for c in line[2:].strip().split("\t")]
                continue
            if line.startswith("#") or not line.strip() or header is None:
                continue
            row = dict(zip(header, line.rstrip("\n").split("\t")))
            sp = row.get("Species", "")
            if sp not in KEEP_SPECIES:
                continue
            n_in += 1
            man = row.get("Manual_evidence", "0") == "1"
            struct = row.get("Structure_distance_evidence", "0") == "1"
            same = row.get("same_residue(competition)_evidence", "0") == "1"
            if not (man or struct or same):
                continue

            a = (row["PTM1"], row["Residue1"])
            b = (row["PTM2"], row["Residue2"])
            if a > b:
                p1, r1, pr1, rr1 = row["PTM2"], row["Residue2"], row["Propagated2"], row["rRCS2"]
                p2, r2, pr2, rr2 = row["PTM1"], row["Residue1"], row["Propagated1"], row["rRCS1"]
            else:
                p1, r1, pr1, rr1 = row["PTM1"], row["Residue1"], row["Propagated1"], row["rRCS1"]
                p2, r2, pr2, rr2 = row["PTM2"], row["Residue2"], row["Propagated2"], row["rRCS2"]

            gene = row["Protein"].strip()
            key = (sp, gene, p1, r1, p2, r2)
            if key in seen:
                continue
            seen.add(key)
            w.write(
                "\t".join([
                    SPECIES_TO_ORG[sp], sp, gene,
                    p1, r1, _pos(r1), pr1, rr1,
                    p2, r2, _pos(r2), pr2, rr2,
                    row.get("Coevolution_evidence", "0"),
                    "1" if same else "0",
                    "1" if man else "0",
                    "1" if struct else "0",
                ]) + "\n"
            )
            n_out += 1

    logger.info("within: kept_species_rows=%d unique=%d → %s", n_in, n_out, out)
    # Remove legacy filename if present
    legacy = out_dir / "within_human.tsv"
    if legacy.exists():
        legacy.unlink()
    return out


def extract_between(base: Path) -> Path:
    src = base / "PTMcode2_associations_between_proteins.txt.gz"
    out = base / "tables" / "between.tsv"
    out.parent.mkdir(exist_ok=True)
    if not src.exists():
        raise FileNotFoundError(src)

    cols = [
        "organism", "species", "gene1", "gene2",
        "ptm1", "residue1", "position1", "propagated1", "rrcs1",
        "ptm2", "residue2", "position2", "propagated2", "rrcs2",
        "coevolution", "manual", "structure",
    ]
    seen: set[tuple] = set()
    n_in = n_out = 0

    with gzip.open(src, "rt", encoding="utf-8", errors="replace") as f, out.open(
        "w", encoding="utf-8"
    ) as w:
        w.write("\t".join(cols) + "\n")
        header = None
        for line in f:
            if line.startswith("## Protein1\t"):
                header = [c.strip() for c in line[2:].strip().split("\t")]
                continue
            if line.startswith("#") or not line.strip() or header is None:
                continue
            row = dict(zip(header, line.rstrip("\n").split("\t")))
            sp = row.get("Species", "")
            if sp not in KEEP_SPECIES:
                continue
            n_in += 1
            man = row.get("Manual_evidence", "0") == "1"
            struct = row.get("Structure_distance_evidence", "0") == "1"
            if not (man or struct):
                continue

            a = (row["Protein1"], row["PTM1"], row["Residue1"])
            b = (row["Protein2"], row["PTM2"], row["Residue2"])
            if a > b:
                g1, p1, r1 = b
                g2, p2, r2 = a
                pr1, rr1 = row["Propagated2"], row["rRCS2"]
                pr2, rr2 = row["Propagated1"], row["rRCS1"]
            else:
                g1, p1, r1 = a
                g2, p2, r2 = b
                pr1, rr1 = row["Propagated1"], row["rRCS1"]
                pr2, rr2 = row["Propagated2"], row["rRCS2"]

            key = (sp, g1, p1, r1, g2, p2, r2)
            if key in seen:
                continue
            seen.add(key)
            w.write(
                "\t".join([
                    SPECIES_TO_ORG[sp], sp, g1, g2,
                    p1, r1, _pos(r1), pr1, rr1,
                    p2, r2, _pos(r2), pr2, rr2,
                    row.get("Coevolution_evidence", "0"),
                    "1" if man else "0",
                    "1" if struct else "0",
                ]) + "\n"
            )
            n_out += 1

    logger.info("between: kept_species_rows=%d unique=%d → %s", n_in, n_out, out)
    legacy = out.parent / "between_human.tsv"
    if legacy.exists():
        legacy.unlink()
    return out


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Prepare PTMcode2 curated tables")
    parser.parse_args(argv)
    base = _root()
    extract_within(base)
    extract_between(base)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
