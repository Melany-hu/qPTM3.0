"""eKPI tools — kinase–phosphosite evidence (experimental + predicted + quantitative).

Stage 1 WHO / Stage 2 WHEN tools:
  ekpi_kinases — experimental + tool-predicted kinases for a phosphosite
  ekpi_quantitative — Spearman correlations (cancer multi-omics Quantitative)

Per-site CSV columns:
  Kinase | Experiment | Concatenated(Prediction) | Qualitative | Quantification

Data:
  Site index: data/enzymes/eKPI/ (built from ekpi_all_phosphosite.txt)
  Matrices:   EKPI_FINAL_RESULT_DIR/{uniprot}#{gene}#{site}.csv.gz
Paper: Brief Bioinform 2025; PMID 40194556; DOI 10.1093/bib/bbaf143
Homepage: https://ekpi.omicsbio.info/
"""

from __future__ import annotations

import csv
import gzip
import logging
import re
from collections import Counter
from pathlib import Path
from typing import Any

from app.config import settings
from app.sources.catalog import get_catalog
from app.sources.query import index_exists, query_records
from app.sources.uniprot_id import resolve_identity
from app.tools.registry import registry

logger = logging.getLogger(__name__)

csv.field_size_limit(10**7)

_DEFAULTS = {
    "name": "eKPI",
    "homepage": "https://ekpi.omicsbio.info/",
    "pmid": "40194556",
    "doi": "10.1093/bib/bbaf143",
}

# Quantitative cohort PMIDs → cancer type (from eKPI front-end cancerType map)
_CANCER_TYPE_BY_PMID: dict[str, str] = {
    "34534465": "Pancreatic Ductal Adenocarcinoma",
    "33242424": "Pediatric Brain Cancer",
    "32649875": "Non-Smoking Lung Cancer",
    "30205044": "Medulloblastoma",
    "32888432": "Metastatic Colorectal Cancer",
    "32649874": "Lung Adenocarcinoma",
    "32649877": "Lung Adenocarcinoma",
    "34358469": "Lung Squamous Cell Carcinoma",
    "34971568": "Intrahepatic Cholangiocarcinoma",
    "27372738": "High-Grade Serous Ovarian Cancer",
    "31585088": "HBV-Related Hepatocellular Carcinoma",
    "33577785": "Glioblastoma",
    "30814741": "Early-Stage Hepatocellular Carcinoma",
    "34764241": "Esophageal Squamous Cell Carcinoma",
    "30645970": "Early-Onset Gastric Cancer",
    "32059776": "Endometrial Carcinoma",
    "34400640": "Esophageal Cancer",
    "31751824": "Diffuse-Type Gastric Cancer",
    "25043054": "CRC.Nat",
    "31031003": "Colon Cancer",
    "31675502": "Clear Cell Renal Cell Carcinoma",
    "27251275": "Breast Cancer",
    "33212010": "Treatment-Naive Primary Breast Cancers",
    "33417831": "HPV-Negative Head And Neck Squamous Cell Carcinoma",
    # Present in Quantitative matrices but not in the original front-end snippet
    "36001024": "Triple-Negative Breast Cancer",
}

_SITE_RE = re.compile(r"^([STY])(\d+)$", re.I)


def _cancer_type(pmid: str | None) -> str | None:
    if not pmid:
        return None
    return _CANCER_TYPE_BY_PMID.get(str(pmid).strip())


def _meta() -> dict[str, Any]:
    m = get_catalog().get("ekpi")
    return {
        "source": _DEFAULTS["name"],
        "access": "hybrid",
        "homepage": (m.homepage if m else None) or _DEFAULTS["homepage"],
        "pmid": (m.pmid if m else None) or _DEFAULTS["pmid"],
        "doi": (m.doi if m else None) or _DEFAULTS["doi"],
    }


def _final_result_dir() -> Path:
    return Path(settings.ekpi_final_result_dir)


def _feature_type(raw: str) -> str:
    t = (raw or "").strip()
    if t == "Pro":
        return "protein"
    if t in ("mRNA", "RNA"):
        return "mrna"
    if t.startswith("p") and len(t) >= 2 and t[1] in "STY":
        return "phospho"
    return "other"


def _parse_pmids(raw: str) -> list[str]:
    """Extract digit PMIDs from strings like '10446957;11875057;447490'."""
    seen: list[str] = []
    for part in re.split(r"[;\s,|/]+", raw or ""):
        p = part.strip()
        if p.isdigit() and p not in seen:
            seen.append(p)
    return seen


def _parse_experiment(raw: str, kinase_gene: str) -> dict[str, Any] | None:
    """Parse Experiment cell: 'ATM#10446957;11875057' → experimental evidence."""
    text = (raw or "").strip()
    if not text or text == "NA":
        return None
    pmids: list[str] = []
    # One or more 'GENE#pmid;pmid' chunks separated by '; ' (space) or plain ';'
    for chunk in re.split(r";\s+", text):
        chunk = chunk.strip()
        if not chunk or chunk == "NA":
            continue
        if "#" in chunk:
            _gene, pmid_part = chunk.split("#", 1)
            pmids.extend(_parse_pmids(pmid_part))
        else:
            pmids.extend(_parse_pmids(chunk))
    # Deduplicate preserving order
    uniq: list[str] = []
    for p in pmids:
        if p not in uniq:
            uniq.append(p)
    if not uniq and "#" not in text:
        return None
    return {
        "kinase_gene": kinase_gene,
        "evidence": "experimental",
        "pmids": uniq,
        "raw": text[:300],
    }


def _parse_predictions(raw: str) -> list[dict[str, Any]]:
    """Parse Concatenated prediction cell: 'Scansite: Medium; NetPhos: 0.5'."""
    text = (raw or "").strip()
    if not text or text == "NA":
        return []
    out: list[dict[str, Any]] = []
    for part in text.split(";"):
        part = part.strip()
        if not part or ":" not in part:
            continue
        tool, score = part.split(":", 1)
        tool = tool.strip()
        score = score.strip()
        if not tool:
            continue
        entry: dict[str, Any] = {"tool": tool, "score": score}
        try:
            entry["score_num"] = float(score)
        except ValueError:
            pass
        out.append(entry)
    return out


def _parse_quant_entries(raw: str) -> list[dict[str, Any]]:
    """Parse Quantification cell: feature#rho#p#n#pmid#cohort (; separated)."""
    out: list[dict[str, Any]] = []
    if not raw or raw == "NA":
        return out
    for entry in raw.split("; "):
        entry = entry.strip()
        if not entry or entry == "NA":
            continue
        parts = entry.split("#")
        if len(parts) < 6:
            continue
        feature, rho_s, p_s, n_s, pmid, cohort = parts[:6]
        try:
            rho = float(rho_s)
            pvalue = float(p_s)
            n = int(float(n_s))
        except (TypeError, ValueError):
            continue
        pmid_s = str(pmid).strip() if str(pmid).strip().isdigit() else None
        out.append({
            "kinase_feature": feature,
            "feature_type": _feature_type(feature),
            "rho": rho,
            "pvalue": pvalue,
            "n": n,
            "pmid": pmid_s,
            "cancer_type": _cancer_type(pmid_s),
            "cohort": cohort,
            "is_tumor": "tumor" in cohort.lower(),
            "is_normal": "normal" in cohort.lower(),
        })
    return out


def _read_site_csv(path: Path) -> list[dict[str, Any]]:
    """Read one final_result gzip CSV → kinase rows (any evidence type)."""
    rows: list[dict[str, Any]] = []
    with gzip.open(path, "rt", encoding="utf-8", errors="replace") as fh:
        reader = csv.reader(fh)
        header = next(reader, None)
        if not header:
            return rows
        for record in reader:
            if len(record) < 5:
                continue
            kinase = (record[0] or "").strip()
            if not kinase or kinase.lower() == "kinase":
                continue
            exp_raw = (record[1] or "").strip()
            pred_raw = (record[2] or "").strip()
            qual_raw = (record[3] or "").strip()
            quant = _parse_quant_entries(record[4])
            experiment = _parse_experiment(exp_raw, kinase)
            predictions = _parse_predictions(pred_raw)
            if not experiment and not predictions and not quant:
                continue
            rows.append({
                "kinase_gene": kinase,
                "experiment": experiment,
                "experiment_raw": exp_raw if exp_raw and exp_raw != "NA" else None,
                "predictions": predictions,
                "prediction_raw": pred_raw if pred_raw and pred_raw != "NA" else None,
                "qualitative": qual_raw if qual_raw and qual_raw != "NA" else None,
                "correlations": quant,
                "has_experimental": bool(experiment),
                "has_predicted": bool(predictions),
                "has_quantitative": bool(quant),
            })
    return rows


def _merge_kinase_evidence(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge duplicate kinase rows (same gene may appear multiple times)."""
    by_gene: dict[str, dict[str, Any]] = {}
    for row in rows:
        gene = (row.get("kinase_gene") or "").strip()
        if not gene:
            continue
        cur = by_gene.get(gene)
        if cur is None:
            by_gene[gene] = {
                "kinase_gene": gene,
                "experimental_pmids": list((row.get("experiment") or {}).get("pmids") or []),
                "predictions": list(row.get("predictions") or []),
                "prediction_tools": sorted({
                    p.get("tool") for p in (row.get("predictions") or []) if p.get("tool")
                }),
                "correlations": list(row.get("correlations") or []),
                "has_experimental": bool(row.get("has_experimental")),
                "has_predicted": bool(row.get("has_predicted")),
                "has_quantitative": bool(row.get("has_quantitative")),
            }
            continue
        for p in (row.get("experiment") or {}).get("pmids") or []:
            if p not in cur["experimental_pmids"]:
                cur["experimental_pmids"].append(p)
        # Merge predictions by tool (keep first score)
        seen_tools = {p.get("tool") for p in cur["predictions"]}
        for p in row.get("predictions") or []:
            if p.get("tool") and p["tool"] not in seen_tools:
                cur["predictions"].append(p)
                seen_tools.add(p["tool"])
        cur["prediction_tools"] = sorted(t for t in seen_tools if t)
        cur["correlations"].extend(row.get("correlations") or [])
        cur["has_experimental"] = cur["has_experimental"] or bool(row.get("has_experimental"))
        cur["has_predicted"] = cur["has_predicted"] or bool(row.get("has_predicted"))
        cur["has_quantitative"] = cur["has_quantitative"] or bool(row.get("has_quantitative"))
    # Evidence priority for sorting: experimental > predicted > quantitative-only
    merged = list(by_gene.values())

    def _rank(item: dict[str, Any]) -> tuple[int, int, str]:
        if item.get("has_experimental"):
            tier = 0
        elif item.get("has_predicted"):
            tier = 1
        else:
            tier = 2
        return (tier, -len(item.get("experimental_pmids") or []), item.get("kinase_gene") or "")

    merged.sort(key=_rank)
    return merged


def _lookup_sites(
    *,
    gene: str | None,
    uniprot_ac: str | None,
    position: int | None,
    site: str | None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    if not index_exists("ekpi", "sites"):
        return []
    equals: dict[str, str] = {}
    equals_ci: dict[str, str] = {}
    if uniprot_ac:
        equals_ci["uniprot_base"] = uniprot_ac.split("-")[0]
    elif gene:
        # eKPI gene column may be "TP53 P53"; prefer exact gene_token match
        equals_ci["gene_token"] = gene.strip().split()[0]
    if position is not None:
        equals["position"] = str(int(position))
    if site:
        equals_ci["site"] = site
    if not equals and not equals_ci:
        return []
    rows = query_records(
        "ekpi",
        "sites",
        equals=equals or None,
        equals_ci=equals_ci or None,
        limit=limit,
    )
    if rows or uniprot_ac or not gene:
        return rows
    # Fallback: partial match on full gene string
    equals_ci2 = {"gene": gene.strip()}
    if position is not None:
        return query_records(
            "ekpi",
            "sites",
            equals={"position": str(int(position))},
            equals_ci=equals_ci2,
            limit=limit,
        )
    return query_records(
        "ekpi",
        "sites",
        equals_ci=equals_ci2,
        limit=limit,
    )


def _resolve_gz_path(site_row: dict[str, Any]) -> Path | None:
    root = _final_result_dir()
    if not root.is_dir():
        return None
    key = (site_row.get("file_key") or "").strip()
    candidates: list[Path] = []
    if key:
        candidates.append(root / f"{key}.csv.gz")
    uni = (site_row.get("uniprot") or "").strip()
    gene = (site_row.get("gene_token") or site_row.get("gene") or "").strip().split()[0]
    residue = (site_row.get("residue") or "").strip()
    pos = site_row.get("position")
    if uni and gene and residue and pos is not None:
        candidates.append(root / f"{uni}#{gene}#{residue}{pos}.csv.gz")
        # isoform-stripped fallback
        base = uni.split("-")[0]
        if base != uni:
            candidates.append(root / f"{base}#{gene}#{residue}{pos}.csv.gz")
    for path in candidates:
        if path.exists():
            return path
    # Glob fallback for gene/position when UniProt isoform differs
    if gene and residue and pos is not None:
        pattern = f"*#{gene}#{residue}{pos}.csv.gz"
        hits = sorted(root.glob(pattern))
        if uni:
            prefer = [h for h in hits if h.name.startswith(uni.split("-")[0])]
            if prefer:
                return prefer[0]
        if hits:
            return hits[0]
    return None


def _filter_correlations(
    entries: list[dict[str, Any]],
    *,
    kinase: str | None,
    feature_type: str | None,
    cohort: str | None,
    max_pvalue: float | None,
    min_abs_rho: float | None,
) -> list[dict[str, Any]]:
    kin = (kinase or "").strip().upper() or None
    ft = (feature_type or "").strip().lower() or None
    if ft in ("pro", "protein", "prot"):
        ft = "protein"
    elif ft in ("mrna", "rna", "transcript"):
        ft = "mrna"
    elif ft in ("phospho", "phosphorylation", "psite", "p"):
        ft = "phospho"
    elif ft in ("any", "all", ""):
        ft = None

    co = (cohort or "").strip().lower() or None
    if co in ("tumor", "cancer", "cancer tumor", "t"):
        co = "tumor"
    elif co in ("normal", "adjacent", "cancer normal", "n"):
        co = "normal"
    elif co in ("any", "all", ""):
        co = None

    out: list[dict[str, Any]] = []
    for e in entries:
        if kin and (e.get("kinase_gene") or "").upper() != kin:
            continue
        for c in e.get("correlations") or []:
            if ft and c.get("feature_type") != ft:
                continue
            if co == "tumor" and not c.get("is_tumor"):
                continue
            if co == "normal" and not c.get("is_normal"):
                continue
            if max_pvalue is not None and c.get("pvalue", 1.0) > max_pvalue:
                continue
            if min_abs_rho is not None and abs(c.get("rho") or 0.0) < min_abs_rho:
                continue
            out.append({
                "kinase_gene": e.get("kinase_gene"),
                "kinase_feature": c.get("kinase_feature"),
                "feature_type": c.get("feature_type"),
                "rho": round(float(c["rho"]), 6),
                "pvalue": float(c["pvalue"]),
                "n": c.get("n"),
                "pmid": c.get("pmid"),
                "cancer_type": c.get("cancer_type") or _cancer_type(c.get("pmid")),
                "cohort": c.get("cohort"),
                "has_experimental": bool(e.get("has_experimental")),
            })
    out.sort(key=lambda x: (x.get("pvalue", 1.0), -abs(x.get("rho") or 0.0)))
    return out


def _load_site_matrix(
    *,
    gene: str | None,
    uniprot_ac: str | None,
    position: int | None,
    site: str | None,
) -> dict[str, Any]:
    """Shared resolve: identity → site row → gzip matrix path → kinase rows."""
    site_label = (site or "").strip().upper() or None
    if site_label:
        m = _SITE_RE.match(site_label)
        if m and position is None:
            position = int(m.group(2))

    if not any([gene, uniprot_ac]) or position is None:
        return {
            "error": "Provide gene or uniprot_ac, and position (or site like S15)",
            "summary": "Missing query key for eKPI",
            "found": False,
            **_meta(),
        }

    if not index_exists("ekpi", "sites"):
        return {
            "error": (
                "eKPI sites index missing. Run: "
                "python -m app.sources.prepare_ekpi && "
                "python -m app.sources.build_index ekpi"
            ),
            "summary": "eKPI sites index not built yet",
            "found": False,
            **_meta(),
        }

    final_dir = _final_result_dir()
    if not final_dir.is_dir():
        return {
            "error": (
                f"eKPI final_result directory missing: {final_dir}. "
                "Set EKPI_FINAL_RESULT_DIR."
            ),
            "summary": "eKPI matrices not available on this host",
            "found": False,
            **_meta(),
        }

    identity = None
    resolved_ac = (uniprot_ac or "").strip().upper() or None
    resolved_gene = (gene or "").strip() or None
    if resolved_gene or resolved_ac:
        identity = resolve_identity(uniprot_ac=resolved_ac, gene=resolved_gene)
        if identity:
            resolved_ac = (identity.get("uniprot_ac") or resolved_ac or "").upper() or None
            resolved_gene = identity.get("gene") or resolved_gene

    try:
        site_rows = _lookup_sites(
            gene=resolved_gene,
            uniprot_ac=resolved_ac,
            position=position,
            site=site_label,
            limit=10,
        )
    except Exception as e:
        logger.error("eKPI site lookup failed: %s", e, exc_info=True)
        return {
            "error": str(e),
            "summary": f"eKPI site lookup failed: {e}",
            "found": False,
            **_meta(),
        }

    if not site_rows:
        return {
            "summary": (
                f"eKPI: no phosphosite record for "
                f"{resolved_gene or resolved_ac or '?'} position {position}"
            ),
            "found": False,
            "gene": resolved_gene,
            "uniprot_ac": resolved_ac,
            "position": position,
            **_meta(),
        }

    if resolved_ac:
        exact = [r for r in site_rows if (r.get("uniprot") or "").upper() == resolved_ac]
        if exact:
            site_rows = exact

    site_row = site_rows[0]
    gz_path = _resolve_gz_path(site_row)
    if gz_path is None:
        return {
            "error": f"Matrix file not found for {site_row.get('file_key')}",
            "summary": (
                f"eKPI: site known ({site_row.get('gene')} {site_row.get('site')}) "
                "but matrix file missing"
            ),
            "found": False,
            "gene": site_row.get("gene_token") or resolved_gene,
            "uniprot_ac": site_row.get("uniprot") or resolved_ac,
            "position": position,
            "site": site_row.get("site"),
            **_meta(),
        }

    try:
        kinase_rows = _read_site_csv(gz_path)
    except Exception as e:
        logger.error("eKPI read %s failed: %s", gz_path, e, exc_info=True)
        return {
            "error": str(e),
            "summary": f"eKPI matrix read failed: {e}",
            "found": False,
            **_meta(),
        }

    gene_disp = (
        site_row.get("gene_token")
        or resolved_gene
        or (site_row.get("gene") or "").split()[0]
        or None
    )
    site_disp = site_row.get("site") or f"{site_row.get('residue') or ''}{position}"
    return {
        "ok": True,
        "identity": identity,
        "resolved_gene": resolved_gene,
        "resolved_ac": resolved_ac,
        "gene_disp": gene_disp,
        "site_disp": site_disp,
        "position": position,
        "site_row": site_row,
        "gz_path": gz_path,
        "kinase_rows": kinase_rows,
    }


def _summarize(
    hits: list[dict[str, Any]],
    keys: list[str],
    *,
    site_label: str,
) -> str:
    if not hits:
        return f"eKPI Quantitative: no kinase–{site_label} correlations for {', '.join(keys)}."
    kinases = sorted({h.get("kinase_gene") or "?" for h in hits})
    feats = Counter(h.get("feature_type") or "?" for h in hits)
    cohorts = Counter(h.get("cohort") or "?" for h in hits)
    cancers = Counter(h.get("cancer_type") or "unknown" for h in hits)
    examples = []
    for h in hits[:4]:
        cancer = h.get("cancer_type") or h.get("cohort") or "?"
        examples.append(
            f"{h.get('kinase_gene')}[{h.get('kinase_feature')}] ρ={h.get('rho')} "
            f"p={h.get('pvalue'):.3g} n={h.get('n')} "
            f"({cancer}; PMID {h.get('pmid') or '-'})"
        )
    return (
        f"eKPI Quantitative: {len(hits)} correlation(s) for {site_label} "
        f"({', '.join(keys)}; {len(kinases)} kinase(s); "
        f"features: {', '.join(f'{k}×{v}' for k, v in feats.most_common())}; "
        f"cancers: {', '.join(f'{k}×{v}' for k, v in cancers.most_common(4))}; "
        f"cohorts: {', '.join(f'{k}×{v}' for k, v in cohorts.most_common())}). "
        f"Top: " + "; ".join(examples)
    )


def _ekpi_kinases(
    gene: str | None = None,
    uniprot_ac: str | None = None,
    position: int | None = None,
    site: str | None = None,
    kinase: str | None = None,
    evidence_type: str = "any",
    include_quantitative_summary: bool = True,
    limit: int = 40,
) -> dict[str, Any]:
    """Query eKPI experimental + predicted kinases for a phosphosite."""
    loaded = _load_site_matrix(
        gene=gene, uniprot_ac=uniprot_ac, position=position, site=site,
    )
    if not loaded.get("ok"):
        loaded.setdefault("kinases", [])
        loaded.setdefault("total", 0)
        return loaded

    et = (evidence_type or "any").strip().lower()
    if et in ("exp", "experimental", "experiment"):
        et = "experimental"
    elif et in ("pred", "predicted", "prediction", "computational"):
        et = "predicted"
    elif et in ("quant", "quantitative", "correlation"):
        et = "quantitative"
    elif et in ("any", "all", ""):
        et = "any"

    kin_filter = (kinase or "").strip().upper() or None
    merged = _merge_kinase_evidence(loaded["kinase_rows"])
    if kin_filter:
        merged = [m for m in merged if (m.get("kinase_gene") or "").upper() == kin_filter]

    if et == "experimental":
        merged = [m for m in merged if m.get("has_experimental")]
    elif et == "predicted":
        merged = [m for m in merged if m.get("has_predicted")]
    elif et == "quantitative":
        merged = [m for m in merged if m.get("has_quantitative")]

    display_n = min(max(limit, 1), 80)
    kinases_out: list[dict[str, Any]] = []
    for m in merged[:display_n]:
        item: dict[str, Any] = {
            "kinase_gene": m.get("kinase_gene"),
            "has_experimental": bool(m.get("has_experimental")),
            "has_predicted": bool(m.get("has_predicted")),
            "has_quantitative": bool(m.get("has_quantitative")),
            "evidence_levels": [],
        }
        if m.get("has_experimental"):
            item["evidence_levels"].append("experimental")
            item["experimental_pmids"] = m.get("experimental_pmids") or []
        if m.get("has_predicted"):
            item["evidence_levels"].append("predicted")
            item["prediction_tools"] = m.get("prediction_tools") or []
            item["predictions"] = (m.get("predictions") or [])[:8]
        if m.get("has_quantitative") and include_quantitative_summary:
            item["evidence_levels"].append("quantitative")
            # Best tumor correlation if available
            corrs = sorted(
                m.get("correlations") or [],
                key=lambda c: (c.get("pvalue", 1.0), -abs(c.get("rho") or 0.0)),
            )
            tumor = [c for c in corrs if c.get("is_tumor")]
            best = (tumor or corrs)[:1]
            if best:
                b = best[0]
                item["best_correlation"] = {
                    "kinase_feature": b.get("kinase_feature"),
                    "feature_type": b.get("feature_type"),
                    "rho": round(float(b["rho"]), 6),
                    "pvalue": float(b["pvalue"]),
                    "n": b.get("n"),
                    "pmid": b.get("pmid"),
                    "cancer_type": b.get("cancer_type"),
                    "cohort": b.get("cohort"),
                }
        kinases_out.append(item)

    exp_kinases = [k["kinase_gene"] for k in kinases_out if k.get("has_experimental")]
    pred_kinases = [
        k["kinase_gene"] for k in kinases_out
        if k.get("has_predicted") and not k.get("has_experimental")
    ]
    gene_disp = loaded["gene_disp"]
    site_disp = loaded["site_disp"]
    site_row = loaded["site_row"]
    keys = [f"gene={gene_disp}", f"uniprot={site_row.get('uniprot')}", f"site={site_disp}"]
    if et != "any":
        keys.append(f"evidence={et}")

    examples = []
    for k in kinases_out[:4]:
        bits = [k["kinase_gene"]]
        if k.get("has_experimental"):
            pm = ",".join((k.get("experimental_pmids") or [])[:3])
            bits.append(f"exp PMID {pm or '-'}")
        if k.get("has_predicted"):
            bits.append("pred " + "/".join((k.get("prediction_tools") or [])[:3]))
        if k.get("best_correlation"):
            bc = k["best_correlation"]
            bits.append(
                f"ρ={bc.get('rho')} ({bc.get('cancer_type') or bc.get('cohort')})"
            )
        examples.append(" / ".join(bits))

    n_exp = sum(1 for k in kinases_out if k.get("has_experimental"))
    n_pred = sum(1 for k in kinases_out if k.get("has_predicted"))
    n_quant = sum(1 for k in kinases_out if k.get("has_quantitative"))
    summary = (
        f"eKPI: {len(kinases_out)} kinase(s) for {site_disp} "
        f"({', '.join(keys)}; experimental×{n_exp}, predicted×{n_pred}, "
        f"quantitative×{n_quant}). "
        + ("Examples: " + "; ".join(examples) if examples else "No kinase evidence.")
    )

    return {
        "summary": summary,
        "found": bool(kinases_out),
        "gene": gene_disp,
        "uniprot_ac": site_row.get("uniprot") or loaded.get("resolved_ac"),
        "uniprot_identity": loaded.get("identity"),
        "position": loaded["position"],
        "residue": site_row.get("residue"),
        "site": site_disp,
        "evidence_type": et,
        "experimental_kinases": exp_kinases,
        "predicted_only_kinases": pred_kinases,
        "kinases_found": [k["kinase_gene"] for k in kinases_out],
        "total": len(kinases_out),
        "total_merged": len(merged),
        "kinases": kinases_out,
        "matrix_file": loaded["gz_path"].name,
        "note": (
            "eKPI integrates three evidence layers for kinase–phosphosite links: "
            "(1) Experimental — literature-validated KPIs with PMIDs; "
            "(2) Predicted — NetPhos/NetworKIN/NetPhorest/GPS/PhosphoPICK/"
            "Scansite/MusiteDeep scores; "
            "(3) Quantitative — cancer multi-omics Spearman correlations. "
            "Use ekpi_quantitative for detailed correlation tables."
        ),
        **_meta(),
    }


def _ekpi_quantitative(
    gene: str | None = None,
    uniprot_ac: str | None = None,
    position: int | None = None,
    site: str | None = None,
    kinase: str | None = None,
    feature_type: str | None = None,
    cohort: str = "tumor",
    max_pvalue: float = 0.05,
    min_abs_rho: float = 0.0,
    limit: int = 40,
) -> dict[str, Any]:
    """Query eKPI Quantitative kinase–phosphosite Spearman correlations."""
    loaded = _load_site_matrix(
        gene=gene, uniprot_ac=uniprot_ac, position=position, site=site,
    )
    if not loaded.get("ok"):
        loaded.setdefault("correlations", [])
        loaded.setdefault("total", 0)
        return loaded

    kinase_rows = loaded["kinase_rows"]
    hits = _filter_correlations(
        kinase_rows,
        kinase=kinase,
        feature_type=feature_type,
        cohort=cohort,
        max_pvalue=None if max_pvalue is None or max_pvalue < 0 else float(max_pvalue),
        min_abs_rho=float(min_abs_rho or 0.0),
    )

    best_by_kinase: dict[str, dict[str, Any]] = {}
    for h in hits:
        k = h.get("kinase_gene") or ""
        prev = best_by_kinase.get(k)
        if prev is None or h["pvalue"] < prev["pvalue"] or (
            h["pvalue"] == prev["pvalue"] and abs(h["rho"]) > abs(prev["rho"])
        ):
            best_by_kinase[k] = h

    display = hits[: min(max(limit, 1), 80)]
    gene_disp = loaded["gene_disp"]
    site_disp = loaded["site_disp"]
    site_row = loaded["site_row"]
    keys = []
    if gene_disp:
        keys.append(f"gene={gene_disp}")
    if site_row.get("uniprot") or loaded.get("resolved_ac"):
        keys.append(f"uniprot={site_row.get('uniprot') or loaded.get('resolved_ac')}")
    keys.append(f"site={site_disp}")
    if kinase:
        keys.append(f"kinase={kinase}")
    if feature_type:
        keys.append(f"feature={feature_type}")
    if cohort:
        keys.append(f"cohort={cohort}")

    pos_n = sum(1 for h in display if (h.get("rho") or 0) > 0)
    neg_n = sum(1 for h in display if (h.get("rho") or 0) < 0)

    return {
        "summary": _summarize(display, keys, site_label=str(site_disp)),
        "found": bool(display),
        "gene": gene_disp,
        "uniprot_ac": site_row.get("uniprot") or loaded.get("resolved_ac"),
        "uniprot_identity": loaded.get("identity"),
        "position": loaded["position"],
        "residue": site_row.get("residue"),
        "site": site_disp,
        "kinase": kinase,
        "feature_type": feature_type,
        "cohort": cohort,
        "max_pvalue": max_pvalue,
        "min_abs_rho": min_abs_rho,
        "kinases_found": sorted(best_by_kinase.keys()),
        "kinase_best": list(best_by_kinase.values())[:20],
        "positive_rho": pos_n,
        "negative_rho": neg_n,
        "total": len(display),
        "total_unfiltered_matches": len(hits),
        "correlations": display,
        "matrix_file": loaded["gz_path"].name,
        "note": (
            "eKPI Quantitative: Spearman correlations between kinase levels "
            "(mRNA / protein / kinase phosphosites) and the substrate phosphosite "
            "across cancer multi-omics cohorts. For literature-validated and "
            "tool-predicted kinases, use ekpi_kinases."
        ),
        **_meta(),
    }


def register_ekpi_tools() -> None:
    registry.register(
        name="ekpi_kinases",
        description=(
            "Query eKPI kinase–phosphosite evidence: (1) experimental literature "
            "KPIs with PMIDs, (2) computational predictions from 7 tools "
            "(NetPhos, NetworKIN, NetPhorest, GPS, PhosphoPICK, Scansite, "
            "MusiteDeep), and optionally (3) a best quantitative correlation "
            "summary. Prefer this for Stage 1 WHO kinase identification. "
            "PMID 40194556."
        ),
        parameters={
            "type": "object",
            "properties": {
                "gene": {"type": "string", "description": "Substrate gene symbol (e.g. TP53)"},
                "uniprot_ac": {
                    "type": "string",
                    "description": "Substrate UniProt accession (e.g. P04637)",
                },
                "position": {
                    "type": "integer",
                    "description": "Phosphosite residue position (e.g. 15)",
                },
                "site": {
                    "type": "string",
                    "description": "Optional site label like S15 (sets position)",
                },
                "kinase": {
                    "type": "string",
                    "description": "Optional kinase gene filter (e.g. ATM)",
                },
                "evidence_type": {
                    "type": "string",
                    "description": (
                        "Filter: any (default) | experimental | predicted | quantitative"
                    ),
                },
                "include_quantitative_summary": {
                    "type": "boolean",
                    "description": "Attach best Spearman hit per kinase (default true)",
                },
                "limit": {"type": "integer", "description": "Max kinases to return (default 40)"},
            },
            "required": [],
        },
        handler=_ekpi_kinases,
    )
    registry.register(
        name="ekpi_quantitative",
        description=(
            "Query eKPI Quantitative kinase–phosphosite correlations: Spearman "
            "ρ between kinase mRNA/protein/phosphosite abundance and a substrate "
            "phosphosite across tumor and adjacent-normal multi-omics cohorts. "
            "Use for detailed cancer correlation tables; for experimental/"
            "predicted kinases prefer ekpi_kinases. PMID 40194556."
        ),
        parameters={
            "type": "object",
            "properties": {
                "gene": {"type": "string", "description": "Substrate gene symbol (e.g. TP53)"},
                "uniprot_ac": {
                    "type": "string",
                    "description": "Substrate UniProt accession (e.g. P04637)",
                },
                "position": {
                    "type": "integer",
                    "description": "Phosphosite residue position (e.g. 15)",
                },
                "site": {
                    "type": "string",
                    "description": "Optional site label like S15 (sets position)",
                },
                "kinase": {
                    "type": "string",
                    "description": "Optional kinase gene filter (e.g. ATM, CDK1)",
                },
                "feature_type": {
                    "type": "string",
                    "description": "Kinase feature: protein | mrna | phospho | any",
                },
                "cohort": {
                    "type": "string",
                    "description": "tumor (default) | normal | any",
                },
                "max_pvalue": {
                    "type": "number",
                    "description": "Max Spearman p-value (default 0.05; set <0 to disable)",
                },
                "min_abs_rho": {
                    "type": "number",
                    "description": "Min |Spearman ρ| (default 0)",
                },
                "limit": {"type": "integer", "description": "Max correlations to return (default 40)"},
            },
            "required": [],
        },
        handler=_ekpi_quantitative,
    )
