#!/usr/bin/env python3
"""
Batch compute physicochemical properties for a large multi-entry FASTA file.

Uses NetSurfP-3.0 in chunks (max 5000 sequences per run) and IUPred3 per sequence.
Results are appended to a Parquet file with resume support.
"""

import argparse
import glob
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from compute_protein_properties import (
    DEFAULT_NETSURFP_MODEL,
    DEFAULT_NETSURFP_ROOT,
    arrays_to_string_properties,
    choose_iupred_smoothing,
    hydropathy_charge_polar,
    normalize_sequence,
    parse_netsurfp,
    write_parquet,
)

IUPRED3_DIR = Path("/var/www/html/software/iupred3")
sys.path.insert(0, str(IUPRED3_DIR))
import iupred3_lib  # noqa: E402

NETSURFP_MAX_SEQUENCES = 5000
DEFAULT_OUTPUT_DIR = SCRIPT_DIR / "physicochemical_property"


def extract_uniprot_id(header: str) -> str:
    h = header.lstrip(">").strip()
    parts = h.split("|")
    if len(parts) >= 2 and parts[0] in ("sp", "tr", "ref"):
        return parts[1]
    return h.split()[0]


def read_fasta_entries(path: Path) -> List[Tuple[str, str]]:
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
                    entries.append((seq_id, normalize_sequence("".join(seq_parts))))
                seq_id = extract_uniprot_id(line[1:])
                seq_parts = []
            else:
                seq_parts.append(line)
    if seq_id is not None:
        entries.append((seq_id, normalize_sequence("".join(seq_parts))))
    return entries


def write_chunk_fasta(entries: List[Tuple[str, str]], path: Path) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        for uniprot_id, sequence in entries:
            fh.write(f">{uniprot_id}\n{sequence}\n")


def run_iupred3_sequence(sequence: str) -> List[float]:
    smoothing = choose_iupred_smoothing(len(sequence))
    scores = iupred3_lib.iupred(sequence, "long", smoothing=smoothing)[0]
    return [float(v) for v in scores]


def run_netsurfp_chunk(
    fasta_path: Path,
    tmp_dir: Path,
    worker_id: str,
    netsurfp_root: Path,
    netsurfp_model: Path,
) -> Path:
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
    )
    return output_parent / worker_id


def id_from_netsurfp_path(path: Path) -> str:
    stem = path.stem
    if "_" in stem:
        return stem.split("_", 1)[1]
    return stem


def collect_netsurfp_results(batch_dir: Path) -> Dict[str, Tuple[List[int], List[float], List[str]]]:
    results: Dict[str, Tuple[List[int], List[float], List[str]]] = {}
    pattern = str(batch_dir / "**" / "*.netsurfp.txt")
    for netsurfp_path in glob.glob(pattern, recursive=True):
        if netsurfp_path.endswith(f"{batch_dir.name}.netsurfp.txt"):
            continue
        uniprot_id = id_from_netsurfp_path(Path(netsurfp_path))
        results[uniprot_id] = parse_netsurfp(Path(netsurfp_path))
    return results


def load_completed_ids(parquet_path: Path) -> Set[str]:
    if not parquet_path.is_file():
        return set()
    import pandas as pd

    df = pd.read_parquet(parquet_path, columns=["uniprot_id"])
    return set(df["uniprot_id"].astype(str))


def save_property_txt(out_dir: Path, uniprot_id: str, properties: Dict[str, str]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{uniprot_id}.txt"
    with open(path, "w", encoding="utf-8") as fh:
        for key in (
            "Disorder",
            "ExposeBuried",
            "SurfaceAccessbility",
            "SecondStructure",
            "Hydropathy",
            "Polar",
            "Charge",
        ):
            fh.write(f"{key}\t{properties[key]}\n")


def process_chunk(
    chunk_entries: List[Tuple[str, str]],
    chunk_index: int,
    tmp_dir: Path,
    netsurfp_root: Path,
    netsurfp_model: Path,
    species: str,
    write_txt: bool,
    txt_dir: Path,
) -> List[Dict[str, object]]:
    chunk_name = f"batch_{chunk_index:04d}"
    chunk_fasta = tmp_dir / f"{chunk_name}.fasta"
    write_chunk_fasta(chunk_entries, chunk_fasta)

    print(f"[{chunk_name}] NetSurfP-3.0 on {len(chunk_entries)} sequences ...", flush=True)
    t0 = time.time()
    batch_dir = run_netsurfp_chunk(
        chunk_fasta, tmp_dir, chunk_name, netsurfp_root, netsurfp_model
    )
    netsurfp_map = collect_netsurfp_results(batch_dir)
    print(
        f"[{chunk_name}] NetSurfP finished in {time.time() - t0:.1f}s, "
        f"parsed {len(netsurfp_map)} outputs",
        flush=True,
    )

    rows: List[Dict[str, object]] = []
    for i, (uniprot_id, sequence) in enumerate(chunk_entries):
        if uniprot_id not in netsurfp_map:
            print(f"[{chunk_name}] WARNING: missing NetSurfP result for {uniprot_id}", flush=True)
            continue

        t1 = time.time()
        disorder = run_iupred3_sequence(sequence)
        exposed_buried, rsa, secondary = netsurfp_map[uniprot_id]
        hydropathy, polar, charge = hydropathy_charge_polar(sequence)

        seq_len = len(sequence)
        if len(disorder) != seq_len or len(exposed_buried) != seq_len:
            print(
                f"[{chunk_name}] WARNING: length mismatch for {uniprot_id}: "
                f"seq={seq_len}, disorder={len(disorder)}, netsurfp={len(exposed_buried)}",
                flush=True,
            )
            continue

        row = {
            "uniprot_id": uniprot_id,
            "species": species,
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
        rows.append(row)

        if write_txt:
            properties = arrays_to_string_properties(
                disorder, exposed_buried, rsa, secondary, hydropathy, polar, charge
            )
            save_property_txt(txt_dir, uniprot_id, properties)

        if (i + 1) % 100 == 0 or i + 1 == len(chunk_entries):
            print(
                f"[{chunk_name}] IUPred+merge {i + 1}/{len(chunk_entries)} "
                f"(last {time.time() - t1:.2f}s)",
                flush=True,
            )

    return rows


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Batch compute physicochemical properties for a large FASTA file."
    )
    parser.add_argument("input", type=Path, help="Input multi-entry FASTA file")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Output directory (default: resource/physicochemical_property)",
    )
    parser.add_argument("--species", default="human", help="Species label in Parquet")
    parser.add_argument(
        "--parquet-name",
        default=None,
        help="Parquet filename (default: {species}.parquet)",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=NETSURFP_MAX_SEQUENCES,
        help="Sequences per NetSurfP-3.0 batch (max 5000)",
    )
    parser.add_argument("--limit", type=int, default=0, help="Process only N sequences (testing)")
    parser.add_argument(
        "--write-txt",
        action="store_true",
        help="Also write per-protein txt files to output directory",
    )
    parser.add_argument(
        "--netsurfp-root",
        type=Path,
        default=DEFAULT_NETSURFP_ROOT,
    )
    parser.add_argument(
        "--netsurfp-model",
        type=Path,
        default=DEFAULT_NETSURFP_MODEL,
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Skip UniProt IDs already present in the Parquet file",
    )
    args = parser.parse_args()

    if args.chunk_size > NETSURFP_MAX_SEQUENCES:
        print(
            f"Error: chunk-size cannot exceed NetSurfP limit ({NETSURFP_MAX_SEQUENCES})",
            file=sys.stderr,
        )
        return 1

    if not args.input.is_file():
        print(f"Error: input not found: {args.input}", file=sys.stderr)
        return 1

    args.output_dir.mkdir(parents=True, exist_ok=True)
    parquet_name = args.parquet_name or f"{args.species}.parquet"
    parquet_path = args.output_dir / parquet_name
    progress_path = args.output_dir / f"{args.species}.progress.json"

    completed_ids: Set[str] = set()
    if args.resume:
        completed_ids = load_completed_ids(parquet_path)
        print(f"Resume: {len(completed_ids)} proteins already in {parquet_path}", flush=True)

    all_entries = read_fasta_entries(args.input)
    if args.limit > 0:
        all_entries = all_entries[:args.limit]

    pending = [(uid, seq) for uid, seq in all_entries if uid not in completed_ids]
    print(
        f"Total entries: {len(all_entries)}, pending: {len(pending)}, "
        f"chunk_size: {args.chunk_size}",
        flush=True,
    )

    if not pending:
        print("Nothing to do.", flush=True)
        return 0

    import tempfile

    tmp_ctx = tempfile.TemporaryDirectory(prefix="batch_props_")
    tmp_dir = Path(tmp_ctx.name)
    total_rows = 0
    start = time.time()

    try:
        for chunk_index, offset in enumerate(
            range(0, len(pending), args.chunk_size)
        ):
            chunk_entries = pending[offset:offset + args.chunk_size]
            rows = process_chunk(
                chunk_entries,
                chunk_index,
                tmp_dir,
                args.netsurfp_root,
                args.netsurfp_model,
                args.species,
                args.write_txt,
                args.output_dir,
            )
            if rows:
                append = parquet_path.is_file()
                write_parquet(rows, parquet_path, append=append)
                total_rows += len(rows)
                elapsed = time.time() - start
                progress = {
                    "species": args.species,
                    "parquet": str(parquet_path),
                    "completed_rows": len(completed_ids) + total_rows,
                    "pending_remaining": len(pending) - offset - len(chunk_entries),
                    "last_chunk": chunk_index,
                    "elapsed_seconds": elapsed,
                }
                with open(progress_path, "w", encoding="utf-8") as fh:
                    json.dump(progress, fh, indent=2)
                print(
                    f"Wrote {len(rows)} rows to {parquet_path} "
                    f"(cumulative new: {total_rows}, elapsed: {elapsed:.1f}s)",
                    flush=True,
                )
    finally:
        tmp_ctx.cleanup()

    print(
        f"Done. Added {total_rows} proteins to {parquet_path}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
