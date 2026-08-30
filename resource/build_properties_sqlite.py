#!/usr/bin/env python3
"""Convert resource/properties/{species}.parquet into a lookup SQLite DB."""

import argparse
import os
import sqlite3
import time
from pathlib import Path

import pyarrow.parquet as pq

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_PROPERTIES_DIR = SCRIPT_DIR / "properties"
DEFAULT_DB = DEFAULT_PROPERTIES_DIR / "properties.sqlite"
SPECIES = ("human", "mouse", "rat", "yeast")


def fmt_list(values):
    if values is None:
        return ""
    if not isinstance(values, list):
        return str(values)
    parts = []
    for value in values:
        if isinstance(value, float):
            text = ("%.4f" % value).rstrip("0").rstrip(".")
            parts.append(text if text else "0")
        else:
            parts.append(str(value))
    return ",".join(parts)


def ensure_schema(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS protein_properties (
            uniprot_id TEXT PRIMARY KEY,
            species TEXT NOT NULL,
            sequence TEXT,
            length INTEGER,
            Disorder TEXT,
            ExposeBuried TEXT,
            SurfaceAccessbility TEXT,
            Second TEXT,
            Hydropathy TEXT,
            Polar TEXT,
            Charge TEXT
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_protein_properties_species "
        "ON protein_properties(species)"
    )


def convert_parquet(parquet_path, conn, batch_size=300):
    pf = pq.ParquetFile(parquet_path)
    species = parquet_path.stem.lower()
    cols = [
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
    ]
    rows = []
    total = 0
    t0 = time.time()
    for batch in pf.iter_batches(batch_size=batch_size, columns=cols):
        data = batch.to_pydict()
        for i in range(batch.num_rows):
            rows.append(
                (
                    data["uniprot_id"][i],
                    (data["species"][i] or species).lower(),
                    data["sequence"][i] or "",
                    int(data["length"][i] or 0),
                    fmt_list(data["disorder"][i]),
                    fmt_list(data["expose_buried"][i]),
                    fmt_list(data["surface_accessibility"][i]),
                    fmt_list(data["second_structure"][i]),
                    fmt_list(data["hydropathy"][i]),
                    fmt_list(data["polar"][i]),
                    fmt_list(data["charge"][i]),
                )
            )
            total += 1
        if len(rows) >= batch_size * 2:
            conn.executemany(
                "INSERT OR REPLACE INTO protein_properties VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                rows,
            )
            conn.commit()
            rows = []
            print(
                "  %s: %s/%s (%.1fs)"
                % (species, total, pf.metadata.num_rows, time.time() - t0),
                flush=True,
            )
    if rows:
        conn.executemany(
            "INSERT OR REPLACE INTO protein_properties VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            rows,
        )
        conn.commit()
    print("  %s: done %s rows in %.1fs" % (species, total, time.time() - t0), flush=True)
    return total


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--properties-dir",
        type=Path,
        default=DEFAULT_PROPERTIES_DIR,
        help="Directory containing {species}.parquet files",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB,
        help="Output SQLite path",
    )
    parser.add_argument(
        "--species",
        nargs="*",
        default=list(SPECIES),
        help="Species parquet stems to import",
    )
    args = parser.parse_args()

    args.db.parent.mkdir(parents=True, exist_ok=True)
    if args.db.exists():
        args.db.unlink()

    conn = sqlite3.connect(str(args.db))
    conn.execute("PRAGMA journal_mode=OFF")
    conn.execute("PRAGMA synchronous=OFF")
    conn.execute("PRAGMA temp_store=MEMORY")
    ensure_schema(conn)

    total = 0
    for species in args.species:
        parquet_path = args.properties_dir / ("%s.parquet" % species.lower())
        if not parquet_path.is_file():
            print("Skip missing %s" % parquet_path, flush=True)
            continue
        print("Importing %s ..." % parquet_path, flush=True)
        total += convert_parquet(parquet_path, conn)

    conn.close()
    size_mb = os.path.getsize(args.db) / 1e6
    print("Wrote %s (%s proteins, %.1f MB)" % (args.db, total, size_mb), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
