"""Prepare SubCELL working tables from official full-data downloads.

Downloads (https://subcell.idrblab.cn/download):
  1.1-SCSIs-PPI.txt
  2.1-subcellularCompartmentAnnotation-Protein.txt
  3.1-molecularGeneralInfo-Protein.txt

Keeps human / mouse / rat / yeast proteins and their SCSIs.

Usage:
  python -m app.sources.prepare_subcell
  python -m app.sources.prepare_subcell --skip-download
"""

from __future__ import annotations

import argparse
import csv
import logging
from pathlib import Path

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_BASE = "https://subcell.idrblab.cn/files/full-data-download"
_FILES = (
    "1.1-SCSIs-PPI.txt",
    "2.1-subcellularCompartmentAnnotation-Protein.txt",
    "3.1-molecularGeneralInfo-Protein.txt",
)
KEEP_ORG = {"9606", "10090", "10116", "559292"}
ORG_LABEL = {"9606": "human", "10090": "mouse", "10116": "rat", "559292": "yeast"}


def _root() -> Path:
    return Path(settings.data_root) / "localization" / "SubCELL"


def download_raw(raw: Path) -> None:
    raw.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=300, follow_redirects=True, headers={"User-Agent": "qPTM_agent/1.0"}) as client:
        for name in _FILES:
            dest = raw / name
            if dest.exists() and dest.stat().st_size > 1000:
                logger.info("reuse %s", dest)
                continue
            url = f"{_BASE}/{name}"
            logger.info("download %s", url)
            resp = client.get(url)
            resp.raise_for_status()
            dest.write_bytes(resp.content)


def load_compartments() -> dict[str, dict[str, str]]:
    with httpx.Client(timeout=60, follow_redirects=True) as client:
        tree = client.get(
            "https://subcell.idrblab.cn/api/the_biomarker/getOrganismLocationTree"
        ).json()["result"]
    compartments: dict[str, dict[str, str]] = {}

    def walk(node: dict, parent: str | None = None) -> None:
        cid = node.get("id") or node.get("value")
        label = node.get("label") or ""
        if cid:
            compartments[cid] = {
                "compartment_id": cid,
                "compartment_name": label,
                "parent_id": parent or "",
            }
        for ch in node.get("children") or []:
            walk(ch, cid)

    for node in tree.values():
        walk(node)
    return compartments


def prepare(raw: Path, tables: Path) -> None:
    tables.mkdir(parents=True, exist_ok=True)
    compartments = load_compartments()
    with (tables / "compartments.tsv").open("w", encoding="utf-8", newline="") as w:
        cols = ["compartment_id", "compartment_name", "parent_id"]
        wr = csv.DictWriter(w, fieldnames=cols, delimiter="\t", lineterminator="\n")
        wr.writeheader()
        for cid in sorted(compartments):
            wr.writerow(compartments[cid])

    proteins: dict[str, dict[str, str]] = {}
    with (raw / "3.1-molecularGeneralInfo-Protein.txt").open(
        encoding="utf-8", errors="replace", newline=""
    ) as f:
        for row in csv.DictReader(f, delimiter="\t"):
            org = (row.get("Organism ID") or "").strip()
            if org not in KEEP_ORG:
                continue
            mid = (row.get("Molecule ID") or "").strip()
            ac = (row.get("AlphaFoldDB") or "").strip()
            if ac in (".", ""):
                ac = ""
            proteins[mid] = {
                "molecule_id": mid,
                "uniprot_ac": ac,
                "uniprot_entry": (row.get("Uniprot ID") or "").strip(),
                "gene": (row.get("Gene name (primary)") or "").strip(),
                "protein_name": (row.get("Molecule name") or "").strip(),
                "organism_id": org,
                "organism": ORG_LABEL.get(org, org),
            }

    with (tables / "proteins.tsv").open("w", encoding="utf-8", newline="") as w:
        cols = [
            "molecule_id", "uniprot_ac", "uniprot_entry", "gene",
            "protein_name", "organism_id", "organism",
        ]
        wr = csv.DictWriter(w, fieldnames=cols, delimiter="\t", lineterminator="\n")
        wr.writeheader()
        for mid in sorted(proteins):
            wr.writerow(proteins[mid])
    logger.info("proteins=%d", len(proteins))

    n_out = 0
    with (raw / "1.1-SCSIs-PPI.txt").open(encoding="utf-8", errors="replace", newline="") as f, (
        tables / "interactions.tsv"
    ).open("w", encoding="utf-8", newline="") as w:
        reader = csv.DictReader(f, delimiter="\t")
        keys = reader.fieldnames or []
        ka = next(k for k in keys if "MoleculeA" in k)
        kb = next(k for k in keys if "MoleculeB" in k)
        kc = next(k for k in keys if "Compartment" in k)
        kt = next(k for k in keys if "SCSI" in k)
        cols = [
            "molecule_a", "molecule_b", "compartment_id", "scsi_type",
            "gene_a", "gene_b", "uniprot_a", "uniprot_b",
            "protein_a", "protein_b", "organism_a", "organism_b", "compartment_name",
        ]
        wr = csv.DictWriter(w, fieldnames=cols, delimiter="\t", lineterminator="\n")
        wr.writeheader()
        for row in reader:
            a = (row.get(ka) or "").strip()
            b = (row.get(kb) or "").strip()
            pa, pb = proteins.get(a), proteins.get(b)
            if not pa and not pb:
                continue
            cid = (row.get(kc) or "").strip()
            wr.writerow({
                "molecule_a": a,
                "molecule_b": b,
                "compartment_id": cid,
                "scsi_type": (row.get(kt) or "").strip(),
                "gene_a": (pa or {}).get("gene", ""),
                "gene_b": (pb or {}).get("gene", ""),
                "uniprot_a": (pa or {}).get("uniprot_ac", ""),
                "uniprot_b": (pb or {}).get("uniprot_ac", ""),
                "protein_a": (pa or {}).get("protein_name", ""),
                "protein_b": (pb or {}).get("protein_name", ""),
                "organism_a": (pa or {}).get("organism", ""),
                "organism_b": (pb or {}).get("organism", ""),
                "compartment_name": compartments.get(cid, {}).get("compartment_name", ""),
            })
            n_out += 1
    logger.info("interactions=%d", n_out)

    n_loc = 0
    with (raw / "2.1-subcellularCompartmentAnnotation-Protein.txt").open(
        encoding="utf-8", errors="replace", newline=""
    ) as f, (tables / "locations.tsv").open("w", encoding="utf-8", newline="") as w:
        cols = [
            "molecule_id", "gene", "uniprot_ac",
            "compartment_id", "compartment_name", "organism",
        ]
        wr = csv.DictWriter(w, fieldnames=cols, delimiter="\t", lineterminator="\n")
        wr.writeheader()
        for row in csv.DictReader(f, delimiter="\t"):
            mid = (row.get("Molecule ID") or "").strip()
            if mid not in proteins:
                continue
            cid = (row.get("Compartment ID") or "").strip()
            p = proteins[mid]
            wr.writerow({
                "molecule_id": mid,
                "gene": p["gene"],
                "uniprot_ac": p["uniprot_ac"],
                "compartment_id": cid,
                "compartment_name": compartments.get(cid, {}).get("compartment_name", ""),
                "organism": p["organism"],
            })
            n_loc += 1
    logger.info("locations=%d", n_loc)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-download", action="store_true")
    args = parser.parse_args()
    root = _root()
    raw, tables = root / "raw", root / "tables"
    if not args.skip_download:
        download_raw(raw)
    prepare(raw, tables)
    print(tables)


if __name__ == "__main__":
    main()
