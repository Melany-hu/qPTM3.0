"""Pathway tools — Reactome / KEGG / PathBank (Stage 3–4 signaling context).

  reactome_pathways  — Reactome Content Service (API)
  kegg_pathways      — KEGG REST link gene→pathway (API)
  pathbank_pathways  — PathBank-family protein–pathway map (local; SMPDB dump)

Returns readable pathway names plus short functional descriptions (Reactome
summation / KEGG DESCRIPTION) — not ID-only lists.

Citations:
  Reactome  Fabregat et al. 2018  PMID 29145629  DOI 10.1093/nar/gkx1132
  KEGG      Kanehisa et al. 2019  PMID 30321428  DOI 10.1093/nar/gky962
  PathBank  Wishart et al. 2020   PMID 31602469  DOI 10.1093/nar/gkz861
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any

import httpx

from app.config import settings
from app.sources.catalog import get_catalog
from app.sources.query import index_exists, query_records
from app.sources.uniprot_id import resolve_identity
from app.tools.registry import registry

logger = logging.getLogger(__name__)

_ORG_TAXON = {
    "human": 9606,
    "mouse": 10090,
    "rat": 10116,
    "yeast": 559292,
}
_ORG_KEGG = {
    "human": "hsa",
    "mouse": "mmu",
    "rat": "rno",
    "yeast": "sce",
}
_ORG_REACTOME = {
    "human": "Homo sapiens",
    "mouse": "Mus musculus",
    "rat": "Rattus norvegicus",
    "yeast": "Saccharomyces cerevisiae",
}

_pathway_name_cache: dict[str, dict[str, str]] = {}
_last_kegg_call = 0.0
_ENRICH_TOP = 8  # fetch descriptions for top hits shown to the agent/user


def _meta(source_id: str, defaults: dict[str, str]) -> dict[str, Any]:
    m = get_catalog().get(source_id)
    return {
        "source": defaults["name"],
        "access": defaults.get("access", "api"),
        "homepage": (m.homepage if m else None) or defaults["homepage"],
        "pmid": (m.pmid if m else None) or defaults["pmid"],
        "doi": (m.doi if m else None) or defaults["doi"],
    }


def _client() -> httpx.Client:
    return httpx.Client(
        timeout=settings.http_timeout_seconds,
        follow_redirects=True,
        headers={"User-Agent": "qPTM_agent/1.0 (academic research)"},
    )


def _prefer_gene(gene: str | None, uniprot_ac: str | None, organism: str | None):
    g = (gene or "").strip() or None
    ac = (uniprot_ac or "").strip().upper() or None
    identity = None
    if g or ac:
        taxon = _ORG_TAXON.get((organism or "human").lower(), 9606)
        identity = resolve_identity(uniprot_ac=ac, gene=g, organism_id=taxon)
        if identity:
            g = identity.get("gene") or g
            ac = identity.get("uniprot_ac") or ac
    return g, ac, identity


def _kegg_throttle() -> None:
    """KEGG asks ≤3 requests/second for academic use."""
    global _last_kegg_call
    elapsed = time.monotonic() - _last_kegg_call
    if elapsed < 0.35:
        time.sleep(0.35 - elapsed)
    _last_kegg_call = time.monotonic()


def _clip(text: str | None, n: int = 420) -> str:
    t = re.sub(r"\s+", " ", (text or "").strip())
    if len(t) <= n:
        return t
    return t[: n - 1].rsplit(" ", 1)[0] + "…"


def _display_name(raw: Any) -> str | None:
    if isinstance(raw, list) and raw:
        return str(raw[0])
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return None


def _pathway_summary(
    source: str,
    target: str,
    pathways: list[dict[str, Any]],
    total: int,
) -> str:
    if not pathways:
        return f"{source}: no pathways found for {target}."
    parts = [f"{source}: {total} pathway(s) for {target}:"]
    for p in pathways[:6]:
        name = p.get("pathway_name") or p.get("pathway_id") or "unnamed"
        line = name
        extra = []
        if p.get("pathway_subject"):
            extra.append(str(p["pathway_subject"]))
        if p.get("pathway_class"):
            extra.append(str(p["pathway_class"]))
        if p.get("is_disease") is True:
            extra.append("disease")
        if extra:
            line += f" [{'; '.join(extra)}]"
        if p.get("description"):
            line += f" — {p['description']}"
        parts.append(line)
    if total > 6:
        parts.append(f"…and {total - 6} more (see pathways list).")
    return " ".join(parts)


# ── Reactome enrichment ───────────────────────────────────────────

def _enrich_reactome(pathways: list[dict[str, Any]], n: int = _ENRICH_TOP) -> None:
    base = settings.reactome_api_base_url.rstrip("/")
    with _client() as client:
        for p in pathways[:n]:
            st_id = p.get("pathway_id")
            if not st_id:
                continue
            try:
                resp = client.get(
                    f"{base}/data/query/{st_id}",
                    headers={"Accept": "application/json"},
                )
                if resp.status_code != 200:
                    continue
                data = resp.json()
            except Exception as e:
                logger.warning("Reactome detail failed for %s: %s", st_id, e)
                continue

            name = data.get("displayName") or _display_name(data.get("name"))
            if name:
                p["pathway_name"] = name
            if data.get("isInDisease") is not None:
                p["is_disease"] = data.get("isInDisease")

            summ = data.get("summation") or []
            texts = []
            if isinstance(summ, list):
                for s in summ:
                    if isinstance(s, dict) and s.get("text"):
                        texts.append(str(s["text"]))
                    elif isinstance(s, str):
                        texts.append(s)
            if texts:
                p["description"] = _clip(" ".join(texts), 450)
                p["description_full"] = _clip(" ".join(texts), 1200)

            go = data.get("goBiologicalProcess")
            if isinstance(go, dict):
                p["go_process"] = {
                    "id": go.get("accession") or go.get("databaseName"),
                    "name": go.get("displayName") or go.get("name"),
                }
            elif isinstance(go, list) and go:
                g0 = go[0] if isinstance(go[0], dict) else {}
                p["go_process"] = {
                    "id": g0.get("accession"),
                    "name": g0.get("displayName") or g0.get("name"),
                }

            lit = data.get("literatureReference") or []
            pmids = []
            if isinstance(lit, list):
                for ref in lit:
                    if not isinstance(ref, dict):
                        continue
                    pmid = ref.get("pubMedIdentifier") or ref.get("pubmed")
                    if pmid:
                        pmids.append(str(pmid))
            if pmids:
                p["pmids"] = pmids[:5]


# ── KEGG enrichment ───────────────────────────────────────────────

def _parse_kegg_entry(text: str) -> dict[str, str]:
    """Parse flat KEGG /get record for NAME / DESCRIPTION / CLASS."""
    fields: dict[str, list[str]] = {}
    cur = None
    for line in text.splitlines():
        if not line.strip():
            continue
        if line[:12].strip() and not line.startswith(" "):
            # FIELD_NAME + value
            m = re.match(r"^(\S+)\s+(.*)$", line)
            if not m:
                continue
            cur, val = m.group(1), m.group(2).strip()
            fields.setdefault(cur, []).append(val)
        elif cur and line.startswith(" "):
            fields.setdefault(cur, []).append(line.strip())
    out: dict[str, str] = {}
    if "NAME" in fields:
        out["name"] = " ".join(fields["NAME"])
    if "DESCRIPTION" in fields:
        out["description"] = " ".join(fields["DESCRIPTION"])
    if "CLASS" in fields:
        out["pathway_class"] = " ".join(fields["CLASS"])
    return out


def _enrich_kegg(pathways: list[dict[str, Any]], n: int = _ENRICH_TOP) -> None:
    base = settings.kegg_api_base_url.rstrip("/")
    with _client() as client:
        for p in pathways[:n]:
            pid = p.get("pathway_id")
            if not pid:
                continue
            _kegg_throttle()
            try:
                resp = client.get(f"{base}/get/{pid}")
                if resp.status_code != 200 or not resp.text.strip():
                    continue
                parsed = _parse_kegg_entry(resp.text)
            except Exception as e:
                logger.warning("KEGG detail failed for %s: %s", pid, e)
                continue
            if parsed.get("name"):
                # Prefer organism-stripped short name when possible
                p["pathway_name"] = parsed["name"]
            if parsed.get("description"):
                p["description"] = _clip(parsed["description"], 450)
                p["description_full"] = _clip(parsed["description"], 1200)
            if parsed.get("pathway_class"):
                p["pathway_class"] = parsed["pathway_class"]


# ── Reactome ──────────────────────────────────────────────────────

def _reactome_pathways(
    gene: str | None = None,
    uniprot_ac: str | None = None,
    organism: str = "human",
    limit: int = 40,
) -> dict[str, Any]:
    g, ac, identity = _prefer_gene(gene, uniprot_ac, organism)
    if not ac:
        return {
            "error": "Reactome mapping needs UniProt (provide uniprot_ac or resolvable gene)",
            "summary": "Missing UniProt for Reactome",
        }

    lim = max(1, min(int(limit or 40), 80))
    base = settings.reactome_api_base_url.rstrip("/")
    url = f"{base}/data/mapping/UniProt/{ac}/pathways"
    try:
        with _client() as client:
            resp = client.get(url, headers={"Accept": "application/json"})
            if resp.status_code == 404:
                rows = []
            else:
                resp.raise_for_status()
                rows = resp.json() if resp.content else []
    except Exception as e:
        logger.error("Reactome query failed: %s", e, exc_info=True)
        return {"error": str(e), "summary": f"Reactome API failed: {e}"}

    if not isinstance(rows, list):
        rows = []

    species = _ORG_REACTOME.get((organism or "human").lower(), "Homo sapiens")
    pathways: list[dict[str, Any]] = []
    for r in rows:
        if species and r.get("speciesName") and r["speciesName"] != species:
            continue
        st_id = r.get("stId") or ""
        name = r.get("displayName") or _display_name(r.get("name"))
        pathways.append({
            "pathway_id": st_id,
            "pathway_name": name,
            "species": r.get("speciesName"),
            "is_disease": r.get("isInDisease"),
            "description": None,
            "go_process": None,
            "pmids": [],
            "url": f"https://reactome.org/content/detail/{st_id}" if st_id else None,
            "source_db": "Reactome",
        })
        if len(pathways) >= lim:
            break

    # Prefer non-disease pathways first for enrichment priority
    pathways.sort(key=lambda p: (1 if p.get("is_disease") else 0, p.get("pathway_name") or ""))
    _enrich_reactome(pathways, n=min(_ENRICH_TOP, len(pathways)))

    target = ac + (f" ({g})" if g else "")
    return {
        "summary": _pathway_summary("Reactome", target, pathways, len(pathways)),
        "gene": g,
        "uniprot_ac": ac,
        "uniprot_identity": identity,
        "organism": organism,
        "total": len(pathways),
        "pathways": pathways,
        **_meta("reactome", {
            "name": "Reactome",
            "homepage": "https://reactome.org",
            "pmid": "29145629",
            "doi": "10.1093/nar/gkx1132",
        }),
    }


# ── KEGG ──────────────────────────────────────────────────────────

def _kegg_pathway_names(org_code: str) -> dict[str, str]:
    if org_code in _pathway_name_cache:
        return _pathway_name_cache[org_code]
    base = settings.kegg_api_base_url.rstrip("/")
    _kegg_throttle()
    try:
        with _client() as client:
            resp = client.get(f"{base}/list/pathway/{org_code}")
            resp.raise_for_status()
            mapping = {}
            for line in resp.text.splitlines():
                if not line.strip() or "\t" not in line:
                    continue
                pid, name = line.split("\t", 1)
                mapping[pid.replace("path:", "")] = name.strip()
            _pathway_name_cache[org_code] = mapping
            return mapping
    except Exception as e:
        logger.warning("KEGG pathway list failed: %s", e)
        _pathway_name_cache[org_code] = {}
        return {}


def _kegg_pathways(
    gene: str | None = None,
    uniprot_ac: str | None = None,
    organism: str = "human",
    limit: int = 40,
) -> dict[str, Any]:
    g, ac, identity = _prefer_gene(gene, uniprot_ac, organism)
    if not ac and not g:
        return {"error": "Provide gene or uniprot_ac", "summary": "Missing query for KEGG"}

    org = _ORG_KEGG.get((organism or "human").lower(), "hsa")
    base = settings.kegg_api_base_url.rstrip("/")
    kegg_gene = None

    try:
        with _client() as client:
            if ac:
                _kegg_throttle()
                resp = client.get(f"{base}/conv/genes/uniprot:{ac}")
                if resp.status_code == 200 and resp.text.strip():
                    for line in resp.text.splitlines():
                        parts = line.split("\t")
                        if len(parts) >= 2 and parts[1].startswith(f"{org}:"):
                            kegg_gene = parts[1]
                            break
            if not kegg_gene and g:
                _kegg_throttle()
                resp = client.get(f"{base}/find/{org}/{g}")
                if resp.status_code == 200:
                    for line in resp.text.splitlines():
                        left, _, right = line.partition("\t")
                        symbols = right.split(";")[0]
                        if g.upper() in {
                            s.strip().upper() for s in symbols.split(",")
                        } or symbols.split(",")[0].strip().upper() == g.upper():
                            kegg_gene = left.strip()
                            break
                    if not kegg_gene:
                        for line in resp.text.splitlines():
                            if g.upper() in line.upper():
                                kegg_gene = line.split("\t", 1)[0].strip()
                                break

            if not kegg_gene:
                return {
                    "summary": f"KEGG: no gene mapping for {ac or g} ({org})",
                    "gene": g,
                    "uniprot_ac": ac,
                    "total": 0,
                    "pathways": [],
                    **_meta("kegg", {
                        "name": "KEGG",
                        "homepage": "https://www.kegg.jp",
                        "pmid": "30321428",
                        "doi": "10.1093/nar/gky962",
                    }),
                }

            _kegg_throttle()
            resp = client.get(f"{base}/link/pathway/{kegg_gene}")
            if resp.status_code == 404 or not resp.text.strip():
                path_ids: list[str] = []
            else:
                resp.raise_for_status()
                path_ids = []
                for line in resp.text.splitlines():
                    parts = line.split("\t")
                    if len(parts) >= 2:
                        path_ids.append(parts[1].replace("path:", ""))
    except Exception as e:
        logger.error("KEGG query failed: %s", e, exc_info=True)
        return {"error": str(e), "summary": f"KEGG API failed: {e}"}

    names = _kegg_pathway_names(org)
    lim = max(1, min(int(limit or 40), 80))
    pathways = []
    for pid in path_ids[:lim]:
        pathways.append({
            "pathway_id": pid,
            "pathway_name": names.get(pid) or pid,
            "kegg_gene": kegg_gene,
            "description": None,
            "pathway_class": None,
            "url": f"https://www.kegg.jp/pathway/{pid}",
            "source_db": "KEGG",
        })

    _enrich_kegg(pathways, n=min(_ENRICH_TOP, len(pathways)))

    target = (kegg_gene or ac or g or "") + (f" / {ac}" if ac and kegg_gene else "")
    return {
        "summary": _pathway_summary("KEGG", target, pathways, len(pathways)),
        "gene": g,
        "uniprot_ac": ac,
        "uniprot_identity": identity,
        "kegg_gene": kegg_gene,
        "organism": organism,
        "total": len(pathways),
        "pathways": pathways,
        **_meta("kegg", {
            "name": "KEGG",
            "homepage": "https://www.kegg.jp",
            "pmid": "30321428",
            "doi": "10.1093/nar/gky962",
        }),
    }


# ── PathBank (local SMPDB family index) ───────────────────────────

def _pathbank_pathways(
    gene: str | None = None,
    uniprot_ac: str | None = None,
    organism: str = "human",
    pathway_subject: str | None = None,
    limit: int = 40,
) -> dict[str, Any]:
    g, ac, identity = _prefer_gene(gene, uniprot_ac, organism)
    if not ac and not g:
        return {"error": "Provide gene or uniprot_ac", "summary": "Missing query for PathBank"}

    if not index_exists("pathbank", "protein_pathways"):
        return {
            "error": (
                "PathBank index missing. Run: "
                "python -m app.sources.prepare_pathbank && "
                "python -m app.sources.build_index pathbank"
            ),
            "summary": "PathBank index not built",
        }

    equals_ci: dict[str, str] = {}
    if ac:
        equals_ci["uniprot"] = ac
    elif g:
        equals_ci["gene"] = g
    if pathway_subject and pathway_subject.lower() not in ("all", ""):
        equals_ci["pathway_subject"] = pathway_subject

    lim = max(1, min(int(limit or 40), 80))
    try:
        rows = query_records(
            "pathbank",
            "protein_pathways",
            equals_ci=equals_ci,
            limit=lim,
        )
    except Exception as e:
        return {"error": str(e), "summary": f"PathBank query failed: {e}"}

    pathways = []
    for r in rows:
        pid = r.get("pathway_id") or ""
        subject = r.get("pathway_subject") or ""
        name = r.get("pathway_name") or pid
        # Local index has no long abstract; build a readable one-liner from fields.
        desc_bits = []
        if subject:
            desc_bits.append(f"{subject} pathway")
        if r.get("protein_name"):
            desc_bits.append(f"involving {r['protein_name']}")
        elif r.get("gene") or g:
            desc_bits.append(f"involving {r.get('gene') or g}")
        pathways.append({
            "pathway_id": pid,
            "pathway_name": name,
            "pathway_subject": subject or None,
            "gene": r.get("gene") or g,
            "uniprot": r.get("uniprot") or ac,
            "protein_name": r.get("protein_name"),
            "description": _clip("; ".join(desc_bits), 240) if desc_bits else None,
            "url": f"https://smpdb.ca/view/{pid}" if pid.startswith("SMP") else (
                f"https://pathbank.org/view/{pid}" if pid else None
            ),
            "source_db": "PathBank",
        })

    note = (
        "PathBank has no public REST API; results from local SMPDB/PathBank-family "
        "protein–pathway index (human). Descriptions are subject/protein labels "
        "(no remote abstracts)."
    )
    target = ac or g or ""
    return {
        "summary": _pathway_summary("PathBank", target, pathways, len(pathways)),
        "gene": g,
        "uniprot_ac": ac,
        "uniprot_identity": identity,
        "organism": organism,
        "total": len(pathways),
        "pathways": pathways,
        "note": note,
        **_meta("pathbank", {
            "name": "PathBank",
            "homepage": "https://pathbank.org",
            "pmid": "31602469",
            "doi": "10.1093/nar/gkz861",
            "access": "local",
        }),
    }


def register_pathway_tools() -> None:
    registry.register(
        name="reactome_pathways",
        description=(
            "Query Reactome for curated pathways containing a protein (UniProt). "
            "Returns pathway names, short summations, GO process and literature — "
            "not ID-only lists. Use for signaling / metabolism / DNA processes."
        ),
        parameters={
            "type": "object",
            "properties": {
                "gene": {"type": "string"},
                "uniprot_ac": {"type": "string"},
                "organism": {
                    "type": "string",
                    "enum": ["human", "mouse", "rat", "yeast"],
                },
                "limit": {"type": "integer"},
            },
            "required": [],
        },
        handler=_reactome_pathways,
    )
    registry.register(
        name="kegg_pathways",
        description=(
            "Query KEGG for organism-specific pathways linked to a gene/protein. "
            "Returns pathway names, CLASS and DESCRIPTION text for top hits."
        ),
        parameters={
            "type": "object",
            "properties": {
                "gene": {"type": "string"},
                "uniprot_ac": {"type": "string"},
                "organism": {
                    "type": "string",
                    "enum": ["human", "mouse", "rat", "yeast"],
                },
                "limit": {"type": "integer"},
            },
            "required": [],
        },
        handler=_kegg_pathways,
    )
    registry.register(
        name="pathbank_pathways",
        description=(
            "Query PathBank-family pathways (local SMPDB protein–pathway index) "
            "for metabolic, disease, drug-action and signaling pathways. Returns "
            "pathway names and subject categories."
        ),
        parameters={
            "type": "object",
            "properties": {
                "gene": {"type": "string"},
                "uniprot_ac": {"type": "string"},
                "organism": {
                    "type": "string",
                    "enum": ["human", "mouse", "rat", "yeast"],
                },
                "pathway_subject": {
                    "type": "string",
                    "description": "Optional filter: Metabolic, Disease, Signaling, Drug Action, …",
                },
                "limit": {"type": "integer"},
            },
            "required": [],
        },
        handler=_pathbank_pathways,
    )
