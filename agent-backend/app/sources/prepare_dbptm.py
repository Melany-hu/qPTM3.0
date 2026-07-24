"""Prepare dbPTM disease (nsSNP) table for dbptm_functional.

Source (no public REST API):
  Disease (nsSNP): https://biomics.lab.nycu.edu.tw/dbPTM/export_snpptm_sequence.php

Drug-binding PTMs are intentionally not ingested (overlap with DrugBank / PMADS).

Writes loader-aligned TSV (tab-delimited, header names match dbptm_tools.py):
  tables/disease_associated_ptms.tsv
and mirrors it to the dbPTM data-dir root for the existing loader.

Usage:
  python -m app.sources.prepare_dbptm
  python -m app.sources.prepare_dbptm --skip-download   # reuse raw/
"""

from __future__ import annotations

import argparse
import csv
import logging
import re
import time
from pathlib import Path
from typing import Iterable

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_DBPTM = "https://biomics.lab.nycu.edu.tw/dbPTM"
_UA = {"User-Agent": "qPTM-agent/1.0 (dbPTM data prepare; research use)"}


def _root() -> Path:
    return Path(settings.dbptm_data_dir)


def _ensure_dirs(base: Path) -> tuple[Path, Path]:
    raw = base / "raw"
    tables = base / "tables"
    raw.mkdir(parents=True, exist_ok=True)
    tables.mkdir(parents=True, exist_ok=True)
    return raw, tables


def download_disease_csv(raw: Path, *, force: bool = False) -> Path:
    out = raw / "snpptm_with_sequence.csv"
    legacy = raw / "export_snpptm_sequence.bin"
    if out.exists() and not force:
        logger.info("Reuse disease CSV: %s", out)
        return out
    if legacy.exists() and not force:
        legacy.rename(out)
        logger.info("Renamed legacy disease dump → %s", out)
        return out

    url = f"{_DBPTM}/export_snpptm_sequence.php"
    logger.info("Downloading disease CSV from %s", url)
    with httpx.Client(timeout=120.0, follow_redirects=True, headers=_UA) as client:
        resp = client.get(url)
        resp.raise_for_status()
        out.write_bytes(resp.content)
    logger.info("Wrote %s (%d bytes)", out, out.stat().st_size)
    return out


def map_entry_names_to_ac(entry_names: Iterable[str]) -> dict[str, str]:
    """Map UniProt entry names (e.g. TP53_HUMAN) → primary accessions via ID mapping."""
    names = sorted({n.strip() for n in entry_names if n and n.strip()})
    if not names:
        return {}

    mapping: dict[str, str] = {}
    batch_size = 500
    base = "https://rest.uniprot.org/idmapping"

    with httpx.Client(timeout=120.0, follow_redirects=True, headers=_UA) as client:
        for i in range(0, len(names), batch_size):
            batch = names[i : i + batch_size]
            logger.info("UniProt idmapping batch %d–%d / %d", i + 1, i + len(batch), len(names))
            submit = client.post(
                f"{base}/run",
                data={
                    "from": "UniProtKB_AC-ID",
                    "to": "UniProtKB",
                    "ids": ",".join(batch),
                },
            )
            submit.raise_for_status()
            job_id = submit.json()["jobId"]

            for _ in range(60):
                st = client.get(f"{base}/status/{job_id}")
                st.raise_for_status()
                body = st.json()
                if body.get("jobStatus") == "FINISHED" or "results" in body:
                    break
                if body.get("jobStatus") in {"FAILED", "ERROR"}:
                    raise RuntimeError(f"UniProt idmapping failed: {body}")
                time.sleep(1.5)
            else:
                raise TimeoutError(f"UniProt idmapping job {job_id} timed out")

            results = client.get(
                f"{base}/uniprotkb/results/{job_id}",
                params={"size": 500, "format": "json"},
            )
            results.raise_for_status()
            data = results.json()
            for item in data.get("results") or []:
                frm = str(item.get("from") or "").strip()
                to = item.get("to") or {}
                ac = ""
                if isinstance(to, dict):
                    ac = str(to.get("primaryAccession") or "").strip()
                elif isinstance(to, str):
                    ac = to.strip()
                if frm and ac:
                    mapping[frm] = ac

            tsv = client.get(
                f"{base}/stream/{job_id}",
                params={"format": "tsv"},
            )
            if tsv.status_code == 200:
                lines = tsv.text.splitlines()
                for line in lines[1:]:
                    parts = line.split("\t")
                    if len(parts) >= 2 and parts[0] and parts[1]:
                        mapping.setdefault(parts[0].strip(), parts[1].strip())

    logger.info("Mapped %d / %d entry names to accessions", len(mapping), len(names))
    missing = [n for n in names if n not in mapping]
    if missing:
        logger.warning("Unmapped entry names (%d): %s", len(missing), ", ".join(missing[:20]))
    return mapping


def write_disease_table(csv_path: Path, tables: Path, id_map: dict[str, str]) -> Path:
    out = tables / "disease_associated_ptms.tsv"
    fieldnames = [
        "uniprot_ac",
        "position",
        "ptm type",
        "disease",
        "snp",
        "uniprot_id",
        "sap_position",
        "pmid",
        "sequence_window",
    ]
    seen: set[tuple[str, ...]] = set()
    n_in = n_out = n_skip = 0
    _ac_re = re.compile(
        r"^[OPQ][0-9][A-Z0-9]{3}[0-9]$|^[A-NR-Z][0-9]([A-Z][A-Z0-9]{2}[0-9]){1,2}$"
    )

    with csv_path.open(newline="", encoding="utf-8", errors="replace") as fin, out.open(
        "w", encoding="utf-8", newline=""
    ) as fout:
        reader = csv.DictReader(fin)
        writer = csv.DictWriter(fout, fieldnames=fieldnames, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for row in reader:
            n_in += 1
            entry = (row.get("ID") or "").strip()
            ac = id_map.get(entry, "")
            if not ac:
                if _ac_re.match(entry):
                    ac = entry
                else:
                    n_skip += 1
                    continue
            pos = (row.get("Modified_Location") or "").strip()
            if not pos.isdigit():
                n_skip += 1
                continue
            rec = {
                "uniprot_ac": ac,
                "position": pos,
                "ptm type": (row.get("PTM_Type") or "").strip(),
                "disease": (row.get("Related_Disease") or "").strip(),
                "snp": (row.get("SNP_ID") or "").strip(),
                "uniprot_id": entry,
                "sap_position": (row.get("SAP_Position") or "").strip(),
                "pmid": (row.get("Reference") or "").strip(),
                "sequence_window": (row.get("Sequence") or "").strip(),
            }
            key = (
                rec["uniprot_ac"],
                rec["position"],
                rec["ptm type"],
                rec["disease"],
                rec["snp"],
                rec["pmid"],
            )
            if key in seen:
                continue
            seen.add(key)
            writer.writerow(rec)
            n_out += 1

    logger.info(
        "Disease table %s: %d unique / %d raw (%d skipped unmapped)",
        out,
        n_out,
        n_in,
        n_skip,
    )
    return out


def mirror_to_loader_root(base: Path, tables: Path) -> None:
    src = tables / "disease_associated_ptms.tsv"
    if src.exists():
        dst = base / "disease_associated_ptms.tsv"
        dst.write_bytes(src.read_bytes())
        logger.info("Mirrored %s → %s", src.name, dst)


def prepare(*, skip_download: bool = False, force: bool = False) -> None:
    base = _root()
    raw, tables = _ensure_dirs(base)

    disease_csv = (
        download_disease_csv(raw, force=force)
        if not skip_download
        else (raw / "snpptm_with_sequence.csv")
    )
    if not disease_csv.exists():
        raise FileNotFoundError(disease_csv)

    entries: set[str] = set()
    with disease_csv.open(newline="", encoding="utf-8", errors="replace") as f:
        for row in csv.DictReader(f):
            if row.get("ID"):
                entries.add(row["ID"].strip())

    id_map = map_entry_names_to_ac(entries)
    write_disease_table(disease_csv, tables, id_map)
    mirror_to_loader_root(base, tables)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--skip-download", action="store_true", help="Reuse files already in raw/")
    ap.add_argument("--force", action="store_true", help="Re-download even if raw exists")
    args = ap.parse_args()
    prepare(skip_download=args.skip_download, force=args.force)


if __name__ == "__main__":
    main()
