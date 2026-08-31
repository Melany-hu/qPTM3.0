#!/usr/bin/env python3
"""Merge qratio protein annotation TSV + FASTA into resource/proinfo/*.txt.

- Update ProteinName / GeneName / Function / Localization / PTM_qPTM / PTMs_other_resource from TSV
- Drop EntrezID, GenbankProteinID, GenbankNucleotideID
- Drop Disorder, Surface, Second and other property fields (now in resource/properties)
- For new / incomplete proteins: fill Sequence / Organism / Taxonomy from FASTA
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Dict, Optional, Tuple

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT_DIR = SCRIPT_DIR.parent
DEFAULT_TSV = SCRIPT_DIR / "annotation" / "qratio_unique_proteins_annotation_20260830.tsv"
DEFAULT_PROINFO = SCRIPT_DIR / "proinfo"
DEFAULT_FASTA_DIR = ROOT_DIR / "fasta_file"

# Canonical display strings used by existing proinfo files
SPECIES_META = {
    "human": ("Homo sapiens (Human)", "9606"),
    "mouse": ("Mus musculus (Mouse)", "10090"),
    "rat": ("Rattus norvegicus (Rat)", "10116"),
    "yeast": (
        "Saccharomyces cerevisiae (strain ATCC 204508 / S288c) (Baker's yeast)",
        "559292",
    ),
}

DROP_KEYS = {
    "EntrezID",
    "GenbankProteinID",
    "GenbankNucleotideID",
    "Disorder",
    "Surface",
    "Second",
    "ExposeBuried",
    "SurfaceAccessbility",
    "Hydropathy",
    "Polar",
    "Charge",
}

# Preferred write order; remaining keys keep relative discovery order after these
FIELD_ORDER = [
    "UniProtID",
    "ProteinName",
    "GeneName",
    "Organism",
    "Taxonomy",
    "Function",
    "Localization",
    "Sequence",
    "PTM_qPTM",
    "PTMs_other_resource",
]


def parse_species_from_fasta_name(path: Path) -> str:
    stem = path.stem.lower()
    for species in SPECIES_META:
        if species in stem:
            return species
    raise ValueError(f"Cannot infer species from FASTA name: {path.name}")


def load_fasta_index(fasta_dir: Path) -> Dict[str, dict]:
    """Map UniProt accession -> {sequence, species, entry_name}."""
    index: Dict[str, dict] = {}
    fasta_files = sorted(fasta_dir.glob("*.fasta"))
    if not fasta_files:
        raise FileNotFoundError(f"No .fasta files under {fasta_dir}")

    for fasta_path in fasta_files:
        species = parse_species_from_fasta_name(fasta_path)
        acc: Optional[str] = None
        entry: str = ""
        seq_parts = []

        def flush():
            nonlocal acc, entry, seq_parts
            if acc:
                index[acc] = {
                    "sequence": "".join(seq_parts),
                    "species": species,
                    "entry_name": entry,
                }
            acc = None
            entry = ""
            seq_parts = []

        with fasta_path.open(encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.rstrip("\n")
                if line.startswith(">"):
                    flush()
                    # >sp|ACC|ENTRY ... or >tr|ACC|ENTRY ...
                    body = line[1:]
                    parts = body.split("|")
                    if len(parts) >= 3:
                        acc = parts[1].strip()
                        entry = parts[2].split()[0].strip()
                    else:
                        acc = body.split()[0].strip()
                        entry = ""
                elif acc is not None:
                    seq_parts.append(line.strip())
            flush()

    return index


def read_proinfo(path: Path) -> Dict[str, str]:
    data: Dict[str, str] = {}
    if not path.is_file():
        return data
    with path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line or "\t" not in line:
                continue
            key, value = line.split("\t", 1)
            data[key] = value
    return data


def tsv_ptm_value(row: dict) -> str:
    """Read PTM track from TSV (column may be qPTM_PTM or PTM_qPTM)."""
    return (row.get("qPTM_PTM") or row.get("PTM_qPTM") or "").strip()


def build_uniprot_id(row: dict, fasta_rec: Optional[dict], existing: str) -> str:
    if existing:
        return existing
    accs = (row.get("uniprotaccs") or row.get("primaryacc") or row.get("uniprot_id") or "").strip()
    accs = accs.replace(";", ",")
    entry = (fasta_rec or {}).get("entry_name") or ""
    if entry and entry not in accs.split(","):
        return f"{entry},{accs}" if accs else entry
    return accs


def ordered_items(data: Dict[str, str]) -> list[Tuple[str, str]]:
    seen = set()
    items = []
    for key in FIELD_ORDER:
        if key in data:
            items.append((key, data[key]))
            seen.add(key)
    for key, value in data.items():
        if key not in seen:
            items.append((key, value))
            seen.add(key)
    return items


def write_proinfo(path: Path, data: Dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{k}\t{v}" for k, v in ordered_items(data)]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def merge_one(
    row: dict,
    proinfo_dir: Path,
    fasta_index: Dict[str, dict],
    dry_run: bool,
) -> str:
    uid = row["uniprot_id"].strip()
    path = proinfo_dir / f"{uid}.txt"
    existed = path.is_file()
    data = read_proinfo(path)

    for key in DROP_KEYS:
        data.pop(key, None)

    fasta_rec = fasta_index.get(uid)
    if fasta_rec is None:
        # try primaryacc / first alt accession
        for alt in (row.get("primaryacc") or "").split(";") + (row.get("uniprotaccs") or "").replace(",", ";").split(";"):
            alt = alt.strip()
            if alt and alt in fasta_index:
                fasta_rec = fasta_index[alt]
                break

    data["UniProtID"] = build_uniprot_id(row, fasta_rec, data.get("UniProtID", ""))
    data["ProteinName"] = (row.get("proteinname") or "").strip()
    data["GeneName"] = (row.get("genename") or "").strip()
    data["Function"] = (row.get("function") or "").strip()
    data["Localization"] = (row.get("localization") or "").strip()
    data["PTM_qPTM"] = tsv_ptm_value(row)
    ptms_other = (row.get("PTMs_other_resource") or "").strip()
    if ptms_other:
        data["PTMs_other_resource"] = ptms_other
    else:
        data.pop("PTMs_other_resource", None)

    if not data.get("Sequence") and fasta_rec:
        data["Sequence"] = fasta_rec["sequence"]

    if not data.get("Organism") or not data.get("Taxonomy"):
        if fasta_rec:
            organism, taxonomy = SPECIES_META[fasta_rec["species"]]
            data["Organism"] = organism
            data["Taxonomy"] = taxonomy

    if not dry_run:
        write_proinfo(path, data)

    if existed:
        return "updated"
    return "created"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tsv", type=Path, default=DEFAULT_TSV)
    parser.add_argument("--proinfo-dir", type=Path, default=DEFAULT_PROINFO)
    parser.add_argument("--fasta-dir", type=Path, default=DEFAULT_FASTA_DIR)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not args.tsv.is_file():
        print(f"TSV not found: {args.tsv}", file=sys.stderr)
        return 1
    if not args.fasta_dir.is_dir():
        print(f"FASTA dir not found: {args.fasta_dir}", file=sys.stderr)
        return 1

    print(f"Loading FASTA index from {args.fasta_dir} ...")
    fasta_index = load_fasta_index(args.fasta_dir)
    print(f"  {len(fasta_index)} accessions")

    stats = {"updated": 0, "created": 0, "missing_fasta_seq": 0, "missing_organism": 0}
    with args.tsv.open(encoding="utf-8", errors="replace", newline="") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        required = {"uniprot_id", "genename", "proteinname", "function", "localization"}
        fieldnames = set(reader.fieldnames or [])
        missing_cols = required - fieldnames
        if missing_cols:
            print(f"TSV missing columns: {sorted(missing_cols)}", file=sys.stderr)
            return 1
        if "qPTM_PTM" not in fieldnames and "PTM_qPTM" not in fieldnames:
            print("TSV missing PTM column (qPTM_PTM or PTM_qPTM)", file=sys.stderr)
            return 1
        if "PTMs_other_resource" not in fieldnames:
            print("TSV missing column: PTMs_other_resource", file=sys.stderr)
            return 1

        for i, row in enumerate(reader, 1):
            status = merge_one(row, args.proinfo_dir, fasta_index, args.dry_run)
            stats[status] += 1

            uid = row["uniprot_id"].strip()
            path = args.proinfo_dir / f"{uid}.txt"
            data = read_proinfo(path) if not args.dry_run else None
            if args.dry_run:
                # approximate checks without write
                existing = read_proinfo(path)
                if not existing.get("Sequence") and uid not in fasta_index:
                    stats["missing_fasta_seq"] += 1
                if (not existing.get("Organism") or not existing.get("Taxonomy")) and uid not in fasta_index:
                    stats["missing_organism"] += 1
            else:
                if not data.get("Sequence"):
                    stats["missing_fasta_seq"] += 1
                if not data.get("Organism") or not data.get("Taxonomy"):
                    stats["missing_organism"] += 1

            if i % 5000 == 0:
                print(f"  processed {i} ...")

    mode = "DRY-RUN" if args.dry_run else "DONE"
    print(f"{mode}: updated={stats['updated']} created={stats['created']}")
    print(
        f"  missing Sequence after merge={stats['missing_fasta_seq']} "
        f"missing Organism/Taxonomy={stats['missing_organism']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
