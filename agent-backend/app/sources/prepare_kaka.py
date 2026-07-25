"""Prepare KAKA kinase activity–related key alteration tables from qevent.xlsx.

Source: https://kaka.omicsbio.info/
  Literature-curated mutations that alter protein kinase activity
  (increase / decrease / kinase-dead / no-effect).
  PMID 41839313; DOI 10.1016/j.jgg.2026.03.010

Usage:
  python -m app.sources.prepare_kaka
  python -m app.sources.build_index kaka
"""

from __future__ import annotations

import argparse
import logging
import re
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)

_MUT_RE = re.compile(
    r"^([A-Za-z\*]|[A-Z]{3})(\d+)([A-Za-z\*]+|[A-Z]{3})?$",
)
_PMID_RE = re.compile(r"\d{5,9}")

SPECIES_MAP = {
    "Homo sapiens": "human",
    "Mus musculus": "mouse",
    "Rattus norvegicus": "rat",
    "Saccharomyces cerevisiae": "yeast",
    "Schizosaccharomyces pombe": "fission_yeast",
    "Arabidopsis thaliana": "arabidopsis",
    "Drosophila melanogaster": "fly",
    "Caenorhabditis elegans": "worm",
}

_AA3_TO_1 = {
    "ALA": "A", "ARG": "R", "ASN": "N", "ASP": "D", "CYS": "C",
    "GLN": "Q", "GLU": "E", "GLY": "G", "HIS": "H", "ILE": "I",
    "LEU": "L", "LYS": "K", "MET": "M", "PHE": "F", "PRO": "P",
    "SER": "S", "THR": "T", "TRP": "W", "TYR": "Y", "VAL": "V",
    "TER": "*", "STOP": "*", "DEL": "del", "INS": "ins",
}


def _root() -> Path:
    return Path(settings.data_root) / "enzymes" / "KAKA"


def _uniprot_base(ac: str) -> str:
    ac = (ac or "").strip().upper()
    return ac.split("-")[0] if ac else ""


def _aa1(token: str) -> str:
    t = (token or "").strip()
    if not t:
        return ""
    u = t.upper()
    if len(u) == 1 or u in ("*", "DEL", "INS"):
        return _AA3_TO_1.get(u, u if len(u) == 1 or u == "*" else t)
    if u in _AA3_TO_1:
        return _AA3_TO_1[u]
    return t


def _parse_mutation(raw: str) -> tuple[str, str, str, str]:
    """Return (mutation, aa_from, position, aa_to)."""
    mut = (raw or "").strip().upper().replace(" ", "")
    if not mut:
        return "", "", "", ""
    m = _MUT_RE.match(mut)
    if not m:
        return mut, "", "", ""
    aa_from = _aa1(m.group(1))
    pos = m.group(2)
    aa_to = _aa1(m.group(3) or "")
    # Canonical 1-letter form when both ends are single letters
    if len(aa_from) == 1 and aa_to and len(aa_to) == 1:
        mut = f"{aa_from}{pos}{aa_to}"
    elif len(aa_from) == 1 and not aa_to:
        mut = f"{aa_from}{pos}"
    return mut, aa_from, pos, aa_to


def _normalize_activity(raw: str) -> str:
    text = " ".join(str(raw or "").strip().lower().split())
    aliases = {
        "no-effect": "no effect",
        "noeffect": "no effect",
        "kinase dead": "kinase-dead",
        "kinasedead": "kinase-dead",
        "increased": "increase",
        "decreased": "decrease",
    }
    return aliases.get(text, text)


def _parse_pmids(raw: object) -> str:
    text = str(raw if raw is not None else "").strip()
    if not text or text.lower() in ("none", "nan", "null"):
        return ""
    seen: list[str] = []
    for m in _PMID_RE.findall(text):
        if m not in seen:
            seen.append(m)
    return ";".join(seen)


def _clean_cell(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    # Flatten newlines in literature descriptions for TSV
    return " ".join(text.split())


def prepare_events(xlsx: Path, out: Path) -> int:
    import openpyxl

    cols = [
        "gene", "protein_name", "uniprot", "uniprot_base", "review",
        "mutation", "aa_from", "aa_to", "position",
        "enzyme_activity", "organism", "species",
        "pmids", "description",
    ]
    out.parent.mkdir(parents=True, exist_ok=True)
    n = 0

    wb = openpyxl.load_workbook(str(xlsx), read_only=True, data_only=True)
    try:
        ws = wb.active
        with out.open("w", encoding="utf-8") as w:
            w.write("\t".join(cols) + "\n")
            for i, row in enumerate(ws.iter_rows(values_only=True)):
                if i == 0:
                    continue
                if not row or all(c is None or str(c).strip() == "" for c in row):
                    continue
                cells = ["" if c is None else c for c in row]
                if len(cells) < 9:
                    cells.extend([""] * (9 - len(cells)))

                gene = _clean_cell(cells[0])
                protein = _clean_cell(cells[1])
                uniprot = _clean_cell(cells[2]).upper()
                review = _clean_cell(cells[3]).lower()
                mut_raw = _clean_cell(cells[4])
                activity = _normalize_activity(cells[5])
                species = _clean_cell(cells[6])
                pmids = _parse_pmids(cells[7])
                desc = _clean_cell(cells[8])

                if not gene and not uniprot:
                    continue
                mutation, aa_from, position, aa_to = _parse_mutation(mut_raw)
                organism = SPECIES_MAP.get(species, species.lower().replace(" ", "_"))
                base = _uniprot_base(uniprot)

                values = [
                    gene,
                    protein,
                    uniprot,
                    base,
                    review,
                    mutation or mut_raw.upper().replace(" ", ""),
                    aa_from,
                    aa_to,
                    position,
                    activity,
                    organism,
                    species,
                    pmids,
                    desc,
                ]
                w.write("\t".join(values) + "\n")
                n += 1
    finally:
        wb.close()
    return n


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = argparse.ArgumentParser(
        description="Prepare KAKA kinase activity alteration tables",
    )
    parser.add_argument(
        "--xlsx",
        default=None,
        help="Path to qevent.xlsx (default: data/enzymes/KAKA/qevent.xlsx)",
    )
    args = parser.parse_args(argv)

    root = _root()
    xlsx = Path(args.xlsx) if args.xlsx else root / "qevent.xlsx"
    if not xlsx.exists():
        raise FileNotFoundError(xlsx)

    out = root / "tables" / "events.tsv"
    n = prepare_events(xlsx, out)
    logger.info("Wrote %s (%d rows)", out, n)
    logger.info("Next: python -m app.sources.build_index kaka")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
