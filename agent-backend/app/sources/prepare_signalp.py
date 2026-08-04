"""Prepare SignalP working table from SignalP.txt proteome predictions.

Source: data/localization/SignalP/SignalP.txt
  Columns: EntryID (UniProt), Prediction (SP/OTHER), scores, cleavage-site text.

Usage:
  python -m app.sources.prepare_signalp
  python -m app.sources.build_index signalp
"""

from __future__ import annotations

import argparse
import csv
import logging
import re
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)

_CS_RE = re.compile(
    r"CS\s+pos:\s*(\d+)\s*-\s*(\d+)\.\s*Pr:\s*([\d.]+)",
    re.I,
)


def _root() -> Path:
    return Path(settings.data_root) / "localization" / "SignalP"


def _parse_cs(raw: str) -> tuple[str, str, str, str]:
    text = (raw or "").strip()
    if not text:
        return "", "", "", ""
    m = _CS_RE.search(text)
    if not m:
        return "", "", "", text
    return m.group(1), m.group(2), m.group(3), text


def prepare_signalp() -> Path:
    root = _root()
    src = root / "SignalP.txt"
    tables = root / "tables"
    tables.mkdir(parents=True, exist_ok=True)
    out = tables / "predictions.tsv"

    if not src.exists():
        raise FileNotFoundError(f"SignalP source file not found: {src}")

    rows_written = 0
    sp_count = 0
    with src.open(encoding="utf-8") as fin, out.open("w", encoding="utf-8", newline="") as fout:
        reader = csv.DictReader(fin, delimiter="\t")
        fieldnames = [
            "uniprot",
            "prediction",
            "other_score",
            "sp_score",
            "cleavage_start",
            "cleavage_end",
            "cleavage_probability",
            "cs_position",
        ]
        writer = csv.DictWriter(fout, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        for row in reader:
            uniprot = (row.get("EntryID") or "").strip().upper()
            if not uniprot:
                continue
            prediction = (row.get("Prediction") or "").strip().upper()
            cs_start, cs_end, cs_prob, cs_raw = _parse_cs(row.get("CS Position") or "")
            if prediction == "SP":
                sp_count += 1
            writer.writerow({
                "uniprot": uniprot,
                "prediction": prediction or "OTHER",
                "other_score": (row.get("OTHER") or "").strip(),
                "sp_score": (row.get("SP(Sec/SPI)") or "").strip(),
                "cleavage_start": cs_start,
                "cleavage_end": cs_end,
                "cleavage_probability": cs_prob,
                "cs_position": cs_raw,
            })
            rows_written += 1

    logger.info(
        "Wrote %s rows (%s with SP prediction) to %s",
        rows_written, sp_count, out,
    )
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare SignalP predictions TSV")
    _ = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    prepare_signalp()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
