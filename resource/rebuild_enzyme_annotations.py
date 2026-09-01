#!/usr/bin/env python3
"""Rebuild enzyme annotation tables for qPTM detail panels.

Outputs (under resource/data/):
  phosenztable_enriched.csv   → MySQL phosenztable (up,pos,exp,igps,gps)
  ubienztable.csv             → MySQL ubienztable (up,pos,e3)
  sumoenztable.csv            → MySQL sumoenztable (up,pos,evidence)

Encoding:
  Exp chunk:  GENE@Source@detail#DrugBankIDs
              Source=PhosphoSitePlus detail=vivo|vitro|vivo+vitro
              Source=eKPI detail=PMID[;PMID...]
  GPS chunk:  hierarchy#GENE@score#DrugBankIDs
  Ub e3:      E3GENE@class@pmid[;pmid]#
  SUMO:       pmid[;pmid]@source_dbs
"""

from __future__ import annotations

import argparse
import csv
import gzip
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "resource" / "data"
AGENT = ROOT / "agent-backend" / "data" / "enzymes"
DRUGBANK = ROOT / "agent-backend" / "data" / "drug" / "DrugBank" / "indexes" / "targets.sqlite"
EKPI_RESULT = Path("/var/www/html/ekpi/final_result")

PHOS_IN = DATA / "7_phosenztable.csv"
PHOS_OUT = DATA / "phosenztable_enriched.csv"
UB_OUT = DATA / "ubienztable.csv"
SUMO_OUT = DATA / "sumoenztable.csv"


def _open_csv(path: Path):
    # utf-8-sig strips BOM on first header field
    return path.open("r", encoding="utf-8-sig", newline="")


def build_gene_drug_map() -> dict[str, str]:
    gene2up: dict[str, set[str]] = defaultdict(set)
    psp = AGENT / "PhosphoSitePlus" / "indexes" / "kinase_substrate.sqlite"
    if psp.exists():
        con = sqlite3.connect(psp)
        for kinase, ku in con.execute(
            'SELECT kinase, kin_uniprot FROM records WHERE kin_uniprot IS NOT NULL AND kin_uniprot != ""'
        ):
            gene2up[str(kinase).upper()].add(str(ku).split("-")[0])
        con.close()
    kaka = AGENT / "KAKA" / "indexes" / "events.sqlite"
    if kaka.exists():
        con = sqlite3.connect(kaka)
        for gene, up in con.execute(
            'SELECT gene, uniprot_base FROM records WHERE gene IS NOT NULL AND uniprot_base IS NOT NULL'
        ):
            gene2up[str(gene).upper()].add(str(up))
        con.close()

    up2drugs: dict[str, list[str]] = defaultdict(list)
    if DRUGBANK.exists():
        con = sqlite3.connect(DRUGBANK)
        for up, dbid, groups in con.execute("SELECT uniprot, db_id, groups FROM records"):
            g = (groups or "").lower()
            # Prefer clinically relevant entries first
            rank = 0
            if "approved" in g:
                rank = 0
            elif "investigational" in g:
                rank = 1
            elif "experimental" in g:
                rank = 2
            else:
                rank = 3
            up2drugs[up].append((rank, dbid))
        con.close()

    out: dict[str, str] = {}
    for gene, ups in gene2up.items():
        ranked: list[tuple[int, str]] = []
        seen = set()
        for up in ups:
            for item in up2drugs.get(up, []):
                if item[1] in seen:
                    continue
                seen.add(item[1])
                ranked.append(item)
        ranked.sort(key=lambda x: (x[0], x[1]))
        drugs = [d for _, d in ranked[:8]]
        if drugs:
            out[gene] = ",".join(drugs)
    return out


def drugs_for(gene: str, gene_drugs: dict[str, str]) -> str:
    return gene_drugs.get((gene or "").upper(), "")


def load_psp_ks() -> dict[tuple[str, str], list[tuple[str, str]]]:
    """(sub_uniprot_base, position) -> [(kinase_gene, vivo|vitro|vivo+vitro), ...]"""
    path = AGENT / "PhosphoSitePlus" / "indexes" / "kinase_substrate.sqlite"
    out: dict[tuple[str, str], list[tuple[str, str]]] = defaultdict(list)
    if not path.exists():
        return out
    con = sqlite3.connect(path)
    for kinase, sub_up, pos, vivo, vitro, org in con.execute(
        "SELECT kinase, sub_uniprot, position, in_vivo_rxn, in_vitro_rxn, sub_organism FROM records"
    ):
        org_l = (org or "").lower()
        if "human" not in org_l:
            continue
        up = (sub_up or "").split("-")[0].strip()
        pos_s = str(pos or "").strip()
        gene = (kinase or "").strip()
        if not up or not pos_s or not gene:
            continue
        v_in = bool((vivo or "").strip()) and (vivo or "").strip() not in ("", " ")
        v_out = bool((vitro or "").strip()) and (vitro or "").strip() not in ("", " ")
        if v_in and v_out:
            detail = "vivo+vitro"
        elif v_in:
            detail = "vivo"
        elif v_out:
            detail = "vitro"
        else:
            detail = "reported"
        out[(up, pos_s)].append((gene, detail))
    con.close()
    return out


def load_gps_scores() -> dict[tuple[str, str], list[tuple[str, str, str]]]:
    """(up, pos) -> [(hierarchy, gene, score), ...] sorted by score desc."""
    path = AGENT / "GPS6.0" / "GPS_Human.csv"
    out: dict[tuple[str, str], list[tuple[str, str, str]]] = {}
    if not path.exists():
        return out
    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            up = (row.get("UniProtID") or "").strip()
            pos = str(row.get("Position") or "").strip()
            gps = (row.get("GPS") or "").strip()
            scores = (row.get("GPS_Score") or "").strip()
            if not up or not pos or not gps:
                continue
            chunks = gps.split("|")
            score_parts = scores.split("|") if scores else []
            items: list[tuple[str, str, str, float]] = []
            for i, chunk in enumerate(chunks):
                chunk = chunk.strip()
                if not chunk or "#" not in chunk:
                    continue
                hier, gene = chunk.split("#", 1)
                hier = hier.strip()
                gene = gene.strip()
                if not gene:
                    continue
                score_s = score_parts[i].strip() if i < len(score_parts) else ""
                try:
                    score_f = float(score_s)
                except ValueError:
                    score_f = -1.0
                    score_s = ""
                items.append((hier, gene, score_s, score_f))
            items.sort(key=lambda x: x[3], reverse=True)
            out[(up, pos)] = [(h, g, s) for h, g, s, _ in items]
    return out


def load_ekpi_file_keys(sites: set[tuple[str, str]]) -> dict[tuple[str, str], str]:
    path = AGENT / "eKPI" / "indexes" / "sites.sqlite"
    out: dict[tuple[str, str], str] = {}
    if not path.exists() or not sites:
        return out
    con = sqlite3.connect(path)
    # Index lookup per site (indexed on uniprot_base + position)
    for up, pos in sites:
        row = con.execute(
            "SELECT file_key FROM records WHERE uniprot_base = ? AND position = ? LIMIT 1",
            (up, pos),
        ).fetchone()
        if row and row[0]:
            out[(up, pos)] = row[0]
    con.close()
    return out


def harvest_ekpi_experiments(
    file_keys: dict[tuple[str, str], str],
) -> dict[tuple[str, str], list[tuple[str, str]]]:
    """(up,pos) -> [(kinase_gene, pmid_joined), ...] from Experiment column."""
    out: dict[tuple[str, str], list[tuple[str, str]]] = defaultdict(list)
    if not EKPI_RESULT.is_dir():
        print("WARN: eKPI final_result missing; skip Exp from eKPI", file=sys.stderr)
        return out
    n = 0
    hit = 0
    for (up, pos), key in file_keys.items():
        n += 1
        path = EKPI_RESULT / f"{key}.csv.gz"
        if not path.exists():
            continue
        try:
            with gzip.open(path, "rt", encoding="utf-8", errors="replace") as fh:
                reader = csv.reader(fh)
                next(reader, None)
                for record in reader:
                    if len(record) < 2:
                        continue
                    kinase = (record[0] or "").strip()
                    exp_raw = (record[1] or "").strip()
                    if not kinase or not exp_raw or exp_raw == "NA":
                        continue
                    pmids: list[str] = []
                    for chunk in exp_raw.replace("; ", ";").split(";"):
                        chunk = chunk.strip()
                        if not chunk or chunk == "NA":
                            continue
                        if "#" in chunk:
                            _, pmid_part = chunk.split("#", 1)
                        else:
                            pmid_part = chunk
                        for p in pmid_part.replace(",", ";").split(";"):
                            p = p.strip()
                            if p.isdigit() and p not in pmids:
                                pmids.append(p)
                    if pmids:
                        out[(up, pos)].append((kinase, ";".join(pmids)))
                        hit += 1
        except OSError as exc:
            print(f"WARN: cannot read {path}: {exc}", file=sys.stderr)
        if n % 500 == 0:
            print(f"  eKPI Exp scanned {n}/{len(file_keys)} sites...", file=sys.stderr)
    print(f"eKPI Exp: scanned {n} sites, kinase hits {hit}", file=sys.stderr)
    return out


def build_phos(gene_drugs: dict[str, str], skip_ekpi_exp: bool = False) -> int:
    psp = load_psp_ks()
    gps_map = load_gps_scores()
    sites: list[tuple[str, str]] = []
    with _open_csv(PHOS_IN) as fh:
        for row in csv.DictReader(fh):
            up = (row.get("up") or "").strip()
            pos = str(row.get("pos") or "").strip()
            if up and pos:
                sites.append((up, pos))
    site_set = set(sites)
    print(f"Phos sites in skeleton: {len(sites)}", file=sys.stderr)

    file_keys = load_ekpi_file_keys(site_set)
    print(f"eKPI file_keys matched: {len(file_keys)}", file=sys.stderr)
    ekpi_exp: dict[tuple[str, str], list[tuple[str, str]]] = {}
    if not skip_ekpi_exp:
        ekpi_exp = harvest_ekpi_experiments(file_keys)

    written = 0
    with PHOS_OUT.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["up", "pos", "exp", "igps", "gps"])
        for up, pos in sites:
            # --- Exp ---
            exp_chunks: list[str] = []
            seen_genes: set[str] = set()
            for gene, detail in psp.get((up, pos), []):
                gu = gene.upper()
                if gu in seen_genes:
                    continue
                seen_genes.add(gu)
                drugs = drugs_for(gene, gene_drugs)
                exp_chunks.append(f"{gene}@PhosphoSitePlus@{detail}#{drugs}")
            for gene, pmids in ekpi_exp.get((up, pos), []):
                gu = gene.upper()
                if gu in seen_genes:
                    # Prefer keeping PSP entry; skip duplicate gene from eKPI
                    continue
                seen_genes.add(gu)
                drugs = drugs_for(gene, gene_drugs)
                exp_chunks.append(f"{gene}@eKPI@{pmids}#{drugs}")

            # --- GPS ---
            gps_chunks: list[str] = []
            gps_items = gps_map.get((up, pos))
            if gps_items is None:
                # fallback: parse skeleton gps without scores
                gps_items = []
            for hier, gene, score in gps_items:
                drugs = drugs_for(gene, gene_drugs)
                if score:
                    gps_chunks.append(f"{hier}#{gene}@{score}#{drugs}")
                else:
                    gps_chunks.append(f"{hier}#{gene}#{drugs}")

            if not gps_chunks:
                # last resort from input file row — handled by re-reading below if needed
                pass

            w.writerow([up, pos, "|".join(exp_chunks), "", "|".join(gps_chunks)])
            written += 1

    # Fill GPS from input CSV when GPS6 map missed a site
    if written:
        by_key: dict[tuple[str, str], list[str]] = {}
        with _open_csv(PHOS_IN) as fh:
            for row in csv.DictReader(fh):
                up = (row.get("up") or "").strip()
                pos = str(row.get("pos") or "").strip()
                gps_raw = (row.get("gps") or "").strip()
                if not gps_raw:
                    continue
                rebuilt = []
                for chunk in gps_raw.split("|"):
                    chunk = chunk.strip()
                    if not chunk or "#" not in chunk:
                        continue
                    hier, gene = chunk.split("#", 1)
                    gene = gene.strip()
                    drugs = drugs_for(gene, gene_drugs)
                    rebuilt.append(f"{hier}#{gene}#{drugs}")
                by_key[(up, pos)] = rebuilt
        rows = []
        with PHOS_OUT.open(encoding="utf-8", newline="") as fh:
            rows = list(csv.DictReader(fh))
        with PHOS_OUT.open("w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=["up", "pos", "exp", "igps", "gps"])
            w.writeheader()
            for row in rows:
                key = (row["up"], row["pos"])
                if not (row.get("gps") or "").strip() and key in by_key:
                    row["gps"] = "|".join(by_key[key])
                w.writerow(row)

    print(f"Wrote {PHOS_OUT} ({written} rows)", file=sys.stderr)
    return written


def build_ub() -> int:
    path = AGENT / "GPS-Uber" / "indexes" / "ssesr.sqlite"
    grouped: dict[tuple[str, str], list[str]] = defaultdict(list)
    if not path.exists():
        print("WARN: GPS-Uber index missing", file=sys.stderr)
    else:
        con = sqlite3.connect(path)
        for up, pos, e3, cls, pmids in con.execute(
            "SELECT substrate_uniprot_base, position, e3_gene, e3_class, pmids FROM records"
        ):
            up = (up or "").strip()
            pos = str(pos or "").strip()
            e3 = (e3 or "").strip()
            if not up or not pos or not e3:
                continue
            cls = (cls or "unclassified").replace("|", "/").replace("#", "/")
            pmid = ";".join(
                p.strip()
                for p in (pmids or "").replace(",", ";").split(";")
                if p.strip().isdigit()
            )
            grouped[(up, pos)].append(f"{e3}@{cls}@{pmid}#")
        con.close()

    with UB_OUT.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["up", "pos", "e3"])
        for (up, pos), chunks in sorted(grouped.items()):
            # dedupe by e3 gene keep first
            seen = set()
            uniq = []
            for c in chunks:
                gene = c.split("@", 1)[0]
                if gene in seen:
                    continue
                seen.add(gene)
                uniq.append(c)
            w.writerow([up, pos, "|".join(uniq)])
    print(f"Wrote {UB_OUT} ({len(grouped)} rows)", file=sys.stderr)
    return len(grouped)


def build_sumo() -> int:
    path = AGENT / "GPS-SUMO2" / "indexes" / "sumoylation_sites.sqlite"
    rows: list[tuple[str, str, str]] = []
    if not path.exists():
        print("WARN: GPS-SUMO2 index missing", file=sys.stderr)
    else:
        con = sqlite3.connect(path)
        for up, pos, pmids, src, org, species in con.execute(
            "SELECT uniprot_base, position, pmids, source_dbs, organism, species FROM records"
        ):
            org_l = f"{org or ''} {species or ''}".lower()
            if "human" not in org_l and (org or "").strip() != "":
                # keep human; also keep blank organism rows if pmids present
                if "homo sapiens" not in org_l:
                    continue
            up = (up or "").strip()
            pos = str(pos or "").strip()
            pmid = ";".join(
                p.strip()
                for p in (pmids or "").replace(",", ";").split(";")
                if p.strip().isdigit()
            )
            if not up or not pos or not pmid:
                continue
            src = (src or "").replace("|", ",").replace("#", "")
            rows.append((up, pos, f"{pmid}@{src}"))
        con.close()

    # dedupe by site merge pmids
    merged: dict[tuple[str, str], list[str]] = defaultdict(list)
    src_map: dict[tuple[str, str], str] = {}
    for up, pos, evidence in rows:
        pmid_part, _, src = evidence.partition("@")
        for p in pmid_part.split(";"):
            if p and p not in merged[(up, pos)]:
                merged[(up, pos)].append(p)
        if src and (up, pos) not in src_map:
            src_map[(up, pos)] = src

    with SUMO_OUT.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["up", "pos", "evidence"])
        for (up, pos), pmids in sorted(merged.items()):
            src = src_map.get((up, pos), "")
            w.writerow([up, pos, f"{';'.join(pmids)}@{src}"])
    print(f"Wrote {SUMO_OUT} ({len(merged)} rows)", file=sys.stderr)
    return len(merged)


def load_mysql(host: str, user: str, password: str, database: str) -> None:
    try:
        import MySQLdb  # type: ignore
    except ImportError:
        try:
            import pymysql as MySQLdb  # type: ignore
        except ImportError as exc:
            raise SystemExit("Need MySQLdb or pymysql to load MySQL") from exc

    con = MySQLdb.connect(host=host, user=user, passwd=password, db=database, charset="utf8mb4")
    cur = con.cursor()

    def load_csv(table: str, path: Path, columns: list[str]) -> None:
        if not path.exists():
            print(f"SKIP load {table}: missing {path}", file=sys.stderr)
            return
        cur.execute(f"TRUNCATE TABLE `{table}`")
        # Prefer LOAD DATA LOCAL — fall back to row inserts
        abs_path = str(path.resolve())
        cols = ",".join(f"`{c}`" for c in columns)
        try:
            cur.execute(
                f"LOAD DATA LOCAL INFILE %s INTO TABLE `{table}` "
                f"FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '\"' "
                f"IGNORE 1 LINES ({cols})",
                (abs_path,),
            )
            print(f"LOAD DATA {table}: {cur.rowcount} rows", file=sys.stderr)
        except Exception as exc:
            print(f"LOAD DATA failed ({exc}); inserting rows for {table}", file=sys.stderr)
            with path.open(encoding="utf-8", newline="") as fh:
                reader = csv.DictReader(fh)
                sql = f"INSERT INTO `{table}` ({cols}) VALUES ({','.join(['%s']*len(columns))})"
                batch = []
                for row in reader:
                    batch.append(tuple(row.get(c, "") for c in columns))
                    if len(batch) >= 1000:
                        cur.executemany(sql, batch)
                        batch = []
                if batch:
                    cur.executemany(sql, batch)
            print(f"Inserted into {table}", file=sys.stderr)

    # Ensure Ub/SUMO tables exist
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS ubienztable (
          up varchar(255) DEFAULT NULL,
          pos int(11) DEFAULT NULL,
          e3 mediumtext,
          KEY up (up),
          KEY pos (pos)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS sumoenztable (
          up varchar(255) DEFAULT NULL,
          pos int(11) DEFAULT NULL,
          evidence mediumtext,
          KEY up (up),
          KEY pos (pos)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )

    load_csv("phosenztable", PHOS_OUT, ["up", "pos", "exp", "igps", "gps"])
    load_csv("ubienztable", UB_OUT, ["up", "pos", "e3"])
    load_csv("sumoenztable", SUMO_OUT, ["up", "pos", "evidence"])
    con.commit()
    cur.close()
    con.close()
    print("MySQL load complete", file=sys.stderr)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-ekpi-exp", action="store_true", help="Skip reading eKPI gz for Exp PMIDs")
    ap.add_argument("--skip-phos", action="store_true")
    ap.add_argument("--skip-ub", action="store_true")
    ap.add_argument("--skip-sumo", action="store_true")
    ap.add_argument("--load-mysql", action="store_true")
    ap.add_argument("--mysql-host", default="localhost")
    ap.add_argument("--mysql-user", default="cancerbi_web")
    ap.add_argument("--mysql-pass", default="web4lzx!")
    ap.add_argument("--mysql-db", default="cancerbi_qptm2026")
    args = ap.parse_args()

    gene_drugs = build_gene_drug_map()
    print(f"Gene→DrugBank map: {len(gene_drugs)} genes", file=sys.stderr)

    if not args.skip_phos:
        build_phos(gene_drugs, skip_ekpi_exp=args.skip_ekpi_exp)
    if not args.skip_ub:
        build_ub()
    if not args.skip_sumo:
        build_sumo()
    if args.load_mysql:
        load_mysql(args.mysql_host, args.mysql_user, args.mysql_pass, args.mysql_db)


if __name__ == "__main__":
    main()
