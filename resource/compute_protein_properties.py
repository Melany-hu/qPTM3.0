#!/usr/bin/env python3
"""
Compute per-residue physicochemical properties for protein sequences.

Uses IUPred3 (long) for disorder, NetSurfP-3.0 for exposure/surface/secondary
structure, and Kyte-Doolittle lookup tables for hydropathy, polar, and charge.

Output fields match dbSAM wildtype_info and qPTM2026 proinfo formats:
  Disorder, ExposeBuried, SurfaceAccessbility, SecondStructure,
  Hydropathy, Polar, Charge

Bulk storage: use --output-parquet with optional --species for Parquet files.
"""

import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_IUPRED3 = "/var/www/html/software/iupred3/iupred3.py"
DEFAULT_NETSURFP_ROOT = Path("/var/www/html/software/netsurfp-3.0/NetSurfP-3.0_standalone")
DEFAULT_NETSURFP_MODEL = DEFAULT_NETSURFP_ROOT / "models" / "nsp3.pth"
DEFAULT_PARQUET_DIR = SCRIPT_DIR / "data" / "properties"
IUPRED_SMOOTHING_MIN_LEN = 19

PROPERTY_FIELDS = (
    "Disorder",
    "ExposeBuried",
    "SurfaceAccessbility",
    "SecondStructure",
    "Hydropathy",
    "Polar",
    "Charge",
)

PARQUET_COLUMNS = (
    "uniprot_id",
    "species",
    "sequence",
    "length",
    "disorder",
    "expose_buried",
    "surface_accessibility",
    "second_structure",
    "hydropathy",
    "polar",
    "charge",
)

AMINO_HYDROPATHY = {
    "A": 1.8, "R": -4.5, "N": -3.5, "D": -3.5, "C": 2.5,
    "Q": -3.5, "E": -3.5, "G": -0.4, "H": -3.2, "I": 4.5,
    "L": 3.8, "K": -3.9, "M": 1.9, "F": 2.8, "P": -1.6,
    "S": -0.8, "T": -0.7, "W": -0.9, "Y": -1.3, "V": 4.2,
}
POLAR_AA = frozenset("GFNQSTYHKRDE")
POSITIVE_CHARGE_AA = frozenset("RHK")
NEGATIVE_CHARGE_AA = frozenset("DE")


def read_fasta(path: Path) -> List[Tuple[str, str]]:
    entries: List[Tuple[str, str]] = []
    seq_id = None
    seq_parts: List[str] = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            if line.startswith(">"):
                if seq_id is not None:
                    entries.append((seq_id, "".join(seq_parts)))
                seq_id = line[1:].split()[0]
                seq_parts = []
            else:
                seq_parts.append(line.upper())
    if seq_id is not None:
        entries.append((seq_id, "".join(seq_parts)))
    return entries


def normalize_sequence(sequence: str) -> str:
    sequence = sequence.upper()
    if "U" in sequence:
        sequence = sequence.replace("U", "A")
    if "X" in sequence:
        sequence = sequence.replace("X", "A")
    return sequence


def parse_disorder(disorder_path: Path) -> List[float]:
    scores: List[float] = []
    with open(disorder_path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "\t" in line:
                parts = line.split("\t")
            else:
                parts = re.split(r"\s+", line)
            scores.append(float(parts[-1]))
    return scores


def sanitize_worker_id(seq_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", seq_id)
    return (safe[:48] if safe else "job")


def parse_netsurfp(netsurfp_path: Path) -> Tuple[List[int], List[float], List[str]]:
    exposed_buried: List[int] = []
    rsa: List[float] = []
    secondary: List[str] = []
    with open(netsurfp_path, encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("#") or not line.strip():
                continue
            data = re.split(r"\s+", line.strip())
            while len(data) < 10:
                data.insert(0, "")
            rsa.append(float(data[4]))
            exposed_buried.append(1 if data[0] == "E" else 0)
            helix, sheet, coil = data[7], data[8], data[9]
            probs = [float(helix), float(sheet), float(coil)]
            max_idx = probs.index(max(probs))
            secondary.append("A" if max_idx == 0 else "B" if max_idx == 1 else "C")
    return exposed_buried, rsa, secondary


def hydropathy_charge_polar(sequence: str) -> Tuple[List[float], List[int], List[int]]:
    hydropathy: List[float] = []
    polar: List[int] = []
    charge: List[int] = []
    for aa in sequence:
        hydropathy.append(AMINO_HYDROPATHY.get(aa, 0.0))
        polar.append(1 if aa in POLAR_AA else 0)
        if aa in POSITIVE_CHARGE_AA:
            charge.append(1)
        elif aa in NEGATIVE_CHARGE_AA:
            charge.append(-1)
        else:
            charge.append(0)
    return hydropathy, polar, charge


def choose_iupred_smoothing(sequence_length: int) -> str:
    if sequence_length < IUPRED_SMOOTHING_MIN_LEN:
        return "no"
    return "medium"


def run_iupred3(
    fasta_path: Path,
    out_path: Path,
    iupred_script: str,
    sequence_length: int,
) -> None:
    smoothing = choose_iupred_smoothing(sequence_length)
    with open(out_path, "w", encoding="utf-8") as out_fh:
        subprocess.run(
            [
                sys.executable,
                iupred_script,
                str(fasta_path),
                "long",
                "-s",
                smoothing,
            ],
            check=True,
            stdout=out_fh,
            stderr=subprocess.PIPE,
            universal_newlines=True,
        )


def run_netsurfp3(
    fasta_path: Path,
    tmp_dir: Path,
    seq_id: str,
    netsurfp_root: Path,
    netsurfp_model: Path,
) -> Path:
    worker_id = sanitize_worker_id(seq_id)
    output_parent = tmp_dir / "nsp3_output"
    output_parent.mkdir(parents=True, exist_ok=True)
    nsp3_script = netsurfp_root / "nsp3.py"
    subprocess.run(
        [
            sys.executable,
            str(nsp3_script),
            "-m",
            str(netsurfp_model),
            "-i",
            str(fasta_path),
            "-o",
            str(output_parent),
            "-w",
            worker_id,
        ],
        check=True,
        cwd=str(netsurfp_root),
        stderr=subprocess.PIPE,
        universal_newlines=True,
    )
    netsurfp_file = output_parent / worker_id / f"{worker_id}.netsurfp.txt"
    if not netsurfp_file.is_file():
        raise FileNotFoundError(f"NetSurfP-3.0 output not found: {netsurfp_file}")
    return netsurfp_file


def arrays_to_string_properties(
    disorder: List[float],
    exposed_buried: List[int],
    rsa: List[float],
    secondary: List[str],
    hydropathy: List[float],
    polar: List[int],
    charge: List[int],
) -> Dict[str, str]:
    rsa_str = [str(v) for v in rsa]
    return {
        "Disorder": ",".join(str(v) for v in disorder),
        "ExposeBuried": ",".join(str(v) for v in exposed_buried),
        "SurfaceAccessbility": ",".join(rsa_str),
        "Surface": ",".join(rsa_str),
        "SecondStructure": ",".join(secondary),
        "Second": ",".join(secondary),
        "Hydropathy": ",".join(str(v) for v in hydropathy),
        "Polar": ",".join(str(v) for v in polar),
        "Charge": ",".join(str(v) for v in charge),
    }


def compute_property_arrays(
    sequence: str,
    tmp_dir: Path,
    seq_id: str,
    iupred_script: str,
    netsurfp_root: Path,
    netsurfp_model: Path,
    species: Optional[str] = None,
) -> Dict[str, object]:
    sequence = normalize_sequence(sequence)
    fasta_path = tmp_dir / f"{seq_id}.fasta"
    iupred_out = tmp_dir / f"{seq_id}.iupred.txt"

    with open(fasta_path, "w", encoding="utf-8") as fh:
        fh.write(f">{seq_id}\n{sequence}\n")

    run_iupred3(fasta_path, iupred_out, iupred_script, len(sequence))
    netsurfp_out = run_netsurfp3(
        fasta_path, tmp_dir, seq_id, netsurfp_root, netsurfp_model
    )

    disorder = parse_disorder(iupred_out)
    exposed_buried, rsa, secondary = parse_netsurfp(netsurfp_out)
    hydropathy, polar, charge = hydropathy_charge_polar(sequence)

    seq_len = len(sequence)
    if len(disorder) != seq_len or len(exposed_buried) != seq_len:
        raise ValueError(
            f"Length mismatch for {seq_id}: sequence={seq_len}, "
            f"disorder={len(disorder)}, netsurfp={len(exposed_buried)}"
        )

    return {
        "uniprot_id": seq_id,
        "species": species or "",
        "sequence": sequence,
        "length": seq_len,
        "disorder": disorder,
        "expose_buried": exposed_buried,
        "surface_accessibility": rsa,
        "second_structure": secondary,
        "hydropathy": hydropathy,
        "polar": polar,
        "charge": charge,
    }


def compute_properties(
    sequence: str,
    tmp_dir: Path,
    seq_id: str,
    iupred_script: str,
    netsurfp_root: Path,
    netsurfp_model: Path,
    species: Optional[str] = None,
) -> Dict[str, str]:
    arrays = compute_property_arrays(
        sequence,
        tmp_dir,
        seq_id,
        iupred_script,
        netsurfp_root,
        netsurfp_model,
        species,
    )
    return arrays_to_string_properties(
        arrays["disorder"],
        arrays["expose_buried"],
        arrays["surface_accessibility"],
        arrays["second_structure"],
        arrays["hydropathy"],
        arrays["polar"],
        arrays["charge"],
    )


def resolve_parquet_path(output_parquet: Path, species: Optional[str]) -> Path:
    if output_parquet.suffix.lower() == ".parquet":
        return output_parquet
    if species:
        return output_parquet / f"{species}.parquet"
    raise ValueError(
        "When --output-parquet points to a directory, --species is required "
        "to name the output file as {species}.parquet"
    )


def write_parquet(rows: List[Dict[str, object]], parquet_path: Path, append: bool = False) -> None:
    import pandas as pd

    parquet_path.parent.mkdir(parents=True, exist_ok=True)
    df_new = pd.DataFrame(rows, columns=list(PARQUET_COLUMNS))

    if append and parquet_path.is_file():
        df_old = pd.read_parquet(parquet_path)
        df = pd.concat([df_old, df_new], ignore_index=True)
    else:
        df = df_new

    df.to_parquet(parquet_path, index=False, compression="snappy")


def format_property_lines(properties: Dict[str, str], include_surface_alias: bool = True) -> List[str]:
    lines = [
        f"Disorder\t{properties['Disorder']}",
        f"ExposeBuried\t{properties['ExposeBuried']}",
        f"SurfaceAccessbility\t{properties['SurfaceAccessbility']}",
        f"SecondStructure\t{properties['SecondStructure']}",
        f"Hydropathy\t{properties['Hydropathy']}",
        f"Polar\t{properties['Polar']}",
        f"Charge\t{properties['Charge']}",
    ]
    if include_surface_alias:
        lines.insert(3, f"Surface\t{properties['Surface']}")
        lines.insert(4, f"Second\t{properties['Second']}")
    return lines


def update_proinfo_file(proinfo_path: Path, properties: Dict[str, str]) -> None:
    field_map = {
        "Disorder": properties["Disorder"],
        "ExposeBuried": properties["ExposeBuried"],
        "SurfaceAccessbility": properties["SurfaceAccessbility"],
        "Surface": properties["Surface"],
        "SecondStructure": properties["SecondStructure"],
        "Second": properties["Second"],
        "Hydropathy": properties["Hydropathy"],
        "Polar": properties["Polar"],
        "Charge": properties["Charge"],
    }

    if proinfo_path.is_file():
        lines: List[str] = []
        seen: set = set()
        with open(proinfo_path, encoding="utf-8") as fh:
            for line in fh:
                if "\t" in line:
                    key, _ = line.split("\t", 1)
                    key = key.strip()
                    if key in field_map:
                        lines.append(f"{key}\t{field_map[key]}\n")
                        seen.add(key)
                    else:
                        lines.append(line if line.endswith("\n") else line + "\n")
                else:
                    lines.append(line if line.endswith("\n") else line + "\n")
        for key in field_map:
            if key not in seen:
                lines.append(f"{key}\t{field_map[key]}\n")
        with open(proinfo_path, "w", encoding="utf-8") as fh:
            fh.writelines(lines)
    else:
        with open(proinfo_path, "w", encoding="utf-8") as fh:
            for key, value in field_map.items():
                fh.write(f"{key}\t{value}\n")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compute per-residue physicochemical properties for protein sequences."
    )
    parser.add_argument(
        "input",
        help="FASTA file, or UniProt ID when using --proinfo-dir / --update-proinfo",
    )
    parser.add_argument(
        "-o", "--output",
        help="Write property lines to this text file (default: stdout for FASTA input)",
    )
    parser.add_argument(
        "--output-parquet",
        type=Path,
        help=(
            "Write Parquet output (one row per protein, nested per-residue lists). "
            "Use a .parquet file path, or a directory with --species ({species}.parquet)."
        ),
    )
    parser.add_argument(
        "--species",
        help="Species label stored in Parquet (e.g. human, mouse). Required when --output-parquet is a directory.",
    )
    parser.add_argument(
        "--append-parquet",
        action="store_true",
        help="Append rows to an existing Parquet file instead of overwriting",
    )
    parser.add_argument(
        "--proinfo-dir",
        type=Path,
        default=SCRIPT_DIR / "proinfo",
        help="Update proinfo/{UniProtID}.txt (input must be UniProt ID)",
    )
    parser.add_argument(
        "--update-proinfo",
        action="store_true",
        help="Merge results into proinfo file instead of printing only",
    )
    parser.add_argument(
        "--iupred",
        default=DEFAULT_IUPRED3,
        help="Path to IUPred3 script (iupred3.py)",
    )
    parser.add_argument(
        "--netsurfp-root",
        type=Path,
        default=DEFAULT_NETSURFP_ROOT,
        help="NetSurfP-3.0 standalone directory (contains nsp3.py)",
    )
    parser.add_argument(
        "--netsurfp-model",
        type=Path,
        default=DEFAULT_NETSURFP_MODEL,
        help="NetSurfP-3.0 model weights (nsp3.pth)",
    )
    parser.add_argument(
        "--keep-tmp",
        action="store_true",
        help="Keep temporary predictor output files",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    entries: List[Tuple[str, str]] = []

    if args.update_proinfo:
        uniprot_id = args.input.strip()
        proinfo_path = args.proinfo_dir / f"{uniprot_id}.txt"
        sequence = None
        if proinfo_path.is_file():
            with open(proinfo_path, encoding="utf-8") as fh:
                for line in fh:
                    if line.startswith("Sequence\t"):
                        sequence = line.split("\t", 1)[1].strip()
                        break
        if not sequence and input_path.is_file():
            entries = read_fasta(input_path)
            if entries:
                uniprot_id = entries[0][0]
                sequence = entries[0][1]
        if not sequence:
            print(f"Error: no sequence found for {uniprot_id}", file=sys.stderr)
            return 1
        entries = [(uniprot_id, sequence)]
    elif input_path.is_file():
        entries = read_fasta(input_path)
        if not entries:
            print(f"Error: no sequences in {input_path}", file=sys.stderr)
            return 1
    else:
        print(f"Error: input file not found: {input_path}", file=sys.stderr)
        return 1

    if args.output_parquet:
        try:
            parquet_path = resolve_parquet_path(args.output_parquet, args.species)
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
    else:
        parquet_path = None

    tmp_ctx = tempfile.TemporaryDirectory(prefix="protein_props_")
    tmp_dir = Path(tmp_ctx.name)
    parquet_rows: List[Dict[str, object]] = []

    try:
        for seq_id, sequence in entries:
            arrays = compute_property_arrays(
                sequence,
                tmp_dir,
                seq_id,
                args.iupred,
                args.netsurfp_root,
                args.netsurfp_model,
                args.species,
            )
            properties = arrays_to_string_properties(
                arrays["disorder"],
                arrays["expose_buried"],
                arrays["surface_accessibility"],
                arrays["second_structure"],
                arrays["hydropathy"],
                arrays["polar"],
                arrays["charge"],
            )

            if parquet_path is not None:
                parquet_rows.append(arrays)

            if args.update_proinfo:
                proinfo_path = args.proinfo_dir / f"{seq_id}.txt"
                update_proinfo_file(proinfo_path, properties)
                print(f"Updated {proinfo_path}")
            elif args.output:
                out_path = Path(args.output)
                mode = "a" if out_path.exists() and out_path.stat().st_size > 0 else "w"
                with open(out_path, mode, encoding="utf-8") as fh:
                    if mode == "a":
                        fh.write("\n")
                    fh.write(f"# {seq_id} length={len(sequence)}\n")
                    fh.write("\n".join(format_property_lines(properties)) + "\n")
                if mode == "w":
                    print(f"Wrote {out_path}")
            elif parquet_path is None:
                print(f"# {seq_id} length={len(sequence)}")
                print("\n".join(format_property_lines(properties)))

        if parquet_path is not None and parquet_rows:
            write_parquet(parquet_rows, parquet_path, append=args.append_parquet)
            print(
                f"Wrote Parquet {parquet_path} ({len(parquet_rows)} proteins, "
                f"species={args.species or 'n/a'})"
            )

        if args.keep_tmp:
            print(f"Temporary files kept in {tmp_dir}", file=sys.stderr)
            tmp_ctx.cleanup = lambda: None  # type: ignore[method-assign]
    finally:
        if not args.keep_tmp:
            tmp_ctx.cleanup()

    return 0


if __name__ == "__main__":
    sys.exit(main())
