"""Prepare PathBank working table from SMPDB protein–pathway CSV dump.

PathBank (pathbank.org) has no public REST API. We use the downloadable
SMPDB protein CSVs (Wishart lab; PathBank family / human predecessor):

  https://smpdb.ca/downloads/smpdb_proteins.csv.zip

Usage:
  python -m app.sources.prepare_pathbank
  python -m app.sources.prepare_pathbank --zip /path/to/smpdb_proteins.csv.zip
"""

from __future__ import annotations

import argparse
import csv
import logging
import tempfile
import zipfile
from pathlib import Path

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_SMPDB_ZIP = "https://smpdb.ca/downloads/smpdb_proteins.csv.zip"


def _root() -> Path:
    return Path(settings.data_root) / "pathways" / "PathBank"


def consolidate(csv_dir: Path, out: Path) -> int:
    cols = [
        "uniprot", "gene", "protein_name",
        "pathway_id", "pathway_name", "pathway_subject", "source",
    ]
    seen: set[tuple[str, str]] = set()
    n_out = 0
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as w:
        writer = csv.DictWriter(w, fieldnames=cols, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for f in sorted(csv_dir.glob("*_proteins.csv")):
            with f.open(encoding="utf-8", errors="replace", newline="") as fh:
                for row in csv.DictReader(fh):
                    uid = (row.get("Uniprot ID") or "").strip()
                    pid = (row.get("SMPDB ID") or "").strip()
                    if not uid or not pid:
                        continue
                    key = (uid, pid)
                    if key in seen:
                        continue
                    seen.add(key)
                    writer.writerow({
                        "uniprot": uid,
                        "gene": (row.get("Gene Name") or "").strip(),
                        "protein_name": (row.get("Protein Name") or "").strip(),
                        "pathway_id": pid,
                        "pathway_name": (row.get("Pathway Name") or "").strip(),
                        "pathway_subject": (row.get("Pathway Subject") or "").strip(),
                        "source": "SMPDB/PathBank",
                    })
                    n_out += 1
    return n_out


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zip", type=Path, default=None, help="Local smpdb_proteins.csv.zip")
    args = parser.parse_args()

    base = _root()
    out = base / "tables" / "protein_pathways.tsv"
    zip_path = args.zip

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        if zip_path is None:
            zip_path = tmp_path / "smpdb_proteins.csv.zip"
            logger.info("Downloading %s", _SMPDB_ZIP)
            with httpx.Client(timeout=120, follow_redirects=True) as client:
                resp = client.get(_SMPDB_ZIP)
                resp.raise_for_status()
                zip_path.write_bytes(resp.content)
        extract = tmp_path / "csv"
        extract.mkdir()
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(extract)
        # zip may contain nested folder
        csv_dirs = [extract] + [p for p in extract.rglob("*") if p.is_dir()]
        csv_dir = next(
            (d for d in csv_dirs if any(d.glob("*_proteins.csv"))),
            extract,
        )
        n = consolidate(csv_dir, out)
    logger.info("Wrote %d unique protein–pathway rows → %s", n, out)
    print(out)


if __name__ == "__main__":
    main()
