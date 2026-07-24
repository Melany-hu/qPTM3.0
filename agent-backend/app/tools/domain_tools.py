"""Domain / family tools — InterPro + Pfam via InterPro REST API.

Stage 3 WHERE (protein architecture context):
  interpro_domains — InterPro families / domains / sites on a protein
  pfam_domains     — Pfam signatures (queried through the same InterPro API)

Returns more than IDs: human-readable names, coordinates, functional
descriptions, GO terms and key literature PMIDs (fetched from entry detail).

Citations:
  InterPro  Mitchell et al. 2019  PMID 30398656  DOI 10.1093/nar/gky1100
  Pfam      El-Gebali et al. 2019 PMID 30357350  DOI 10.1093/nar/gky995
"""

from __future__ import annotations

import logging
import re
from html import unescape
from typing import Any
from urllib.parse import urljoin

import httpx

from app.config import settings
from app.sources.catalog import get_catalog
from app.sources.uniprot_id import resolve_identity
from app.tools.registry import registry

logger = logging.getLogger(__name__)

_INTERPRO_DEFAULTS = {
    "name": "InterPro",
    "homepage": "https://www.ebi.ac.uk/interpro/",
    "pmid": "30398656",
    "doi": "10.1093/nar/gky1100",
}
_PFAM_DEFAULTS = {
    "name": "Pfam",
    "homepage": "https://www.ebi.ac.uk/interpro/entry/pfam/",
    "pmid": "30357350",
    "doi": "10.1093/nar/gky995",
}

# Prefer domain-level annotations over broad family/superfamily when ranking.
_TYPE_RANK = {
    "domain": 0,
    "conserved_site": 1,
    "active_site": 1,
    "binding_site": 1,
    "ptm": 1,
    "repeat": 2,
    "family": 3,
    "homologous_superfamily": 4,
}


def _meta(source_id: str, defaults: dict[str, str]) -> dict[str, Any]:
    m = get_catalog().get(source_id)
    return {
        "source": defaults["name"],
        "access": "api",
        "homepage": (m.homepage if m else None) or defaults["homepage"],
        "pmid": (m.pmid if m else None) or defaults["pmid"],
        "doi": (m.doi if m else None) or defaults["doi"],
        "api_docs": "https://www.ebi.ac.uk/interpro/api/",
    }


def _base() -> str:
    return (settings.interpro_api_base_url or "https://www.ebi.ac.uk/interpro/api").rstrip("/")


def _client() -> httpx.Client:
    return httpx.Client(
        timeout=settings.http_timeout_seconds,
        follow_redirects=True,
        headers={
            "Accept": "application/json",
            "User-Agent": "qPTM_agent/1.0 (academic research)",
        },
    )


def _prefer_gene(gene: str | None, uniprot_ac: str | None):
    g = (gene or "").strip() or None
    ac = (uniprot_ac or "").strip().upper() or None
    identity = None
    if g or ac:
        identity = resolve_identity(uniprot_ac=ac, gene=g)
        if identity:
            g = identity.get("gene") or g
            ac = (identity.get("uniprot_ac") or ac or "").upper() or None
    return g, ac, identity


def _strip_html(text: str) -> str:
    """Remove InterPro markup tags / HTML and collapse whitespace."""
    if not text:
        return ""
    t = unescape(str(text))
    # Nested cite/xref forms: [[cite:PUB1], [cite:PUB2]] or [[cite:PUB1]]
    t = re.sub(r"\[\[cite:[^\]]*\](?:,\s*\[[^\]]*\])*\]", "", t)
    t = re.sub(r"\[\[cite:[^\]]+\]\]", "", t)
    t = re.sub(r"\[interpro:[^\]]+\]", "", t)
    t = re.sub(r"\[(?:cite|pubmed|doi):[^\]]+\]", "", t)
    t = re.sub(r"<[^>]+>", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    t = re.sub(r"\s+([,.;:])", r"\1", t)
    return t


def _entry_name(raw: Any) -> tuple[str, str]:
    """Return (display_name, short_name) from list or detail payload."""
    if isinstance(raw, dict):
        return str(raw.get("name") or "").strip(), str(raw.get("short") or "").strip()
    return str(raw or "").strip(), ""


def _parse_go(go_terms: Any) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    if not isinstance(go_terms, list):
        return out
    for g in go_terms:
        if not isinstance(g, dict) or not g.get("identifier"):
            continue
        cat = g.get("category")
        cat_name = cat.get("name") if isinstance(cat, dict) else cat
        out.append({
            "id": str(g["identifier"]),
            "name": str(g.get("name") or ""),
            "category": str(cat_name or ""),
        })
    return out[:10]


def _parse_members(members: Any) -> list[str]:
    member_ids: list[str] = []
    if not isinstance(members, dict):
        return member_ids
    for db, mapping in members.items():
        if isinstance(mapping, dict):
            for mid, mname in mapping.items():
                label = f"{db}:{mid}"
                if mname:
                    label += f" ({mname})"
                member_ids.append(label)
    return member_ids[:12]


def _parse_description(desc: Any) -> tuple[str, str]:
    """Return (short_blurb, longer_text) from InterPro description list."""
    if not isinstance(desc, list) or not desc:
        return "", ""
    texts: list[str] = []
    for block in desc:
        if isinstance(block, dict):
            texts.append(_strip_html(str(block.get("text") or "")))
        elif isinstance(block, str):
            texts.append(_strip_html(block))
    texts = [t for t in texts if t]
    if not texts:
        return "", ""
    # Prefer the most specific (usually first) blurb for summaries
    short = texts[0]
    if len(short) > 420:
        short = short[:417].rsplit(" ", 1)[0] + "…"
    long = " ".join(texts)
    if len(long) > 1200:
        long = long[:1197].rsplit(" ", 1)[0] + "…"
    return short, long


def _parse_literature(lit: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not isinstance(lit, dict):
        return out
    for _key, item in lit.items():
        if not isinstance(item, dict):
            continue
        pmid = item.get("PMID") or item.get("pmid")
        if not pmid:
            continue
        out.append({
            "pmid": str(pmid),
            "title": str(item.get("title") or "")[:200],
            "year": item.get("year"),
        })
    out.sort(key=lambda x: (-(int(x["year"]) if str(x.get("year") or "").isdigit() else 0), x["pmid"]))
    return out[:5]


def _entry_url(source_database: str | None, accession: str) -> str:
    db = (source_database or "interpro").strip().lower()
    path_db = "InterPro" if db == "interpro" else db
    return f"https://www.ebi.ac.uk/interpro/entry/{path_db}/{accession}/"


def _fetch_entry_matches(member_db: str, uniprot_ac: str, page_size: int = 50) -> list[dict[str, Any]]:
    url = f"{_base()}/entry/{member_db}/protein/uniprot/{uniprot_ac}"
    params = {"page_size": min(max(page_size, 1), 100)}
    rows: list[dict[str, Any]] = []
    pages = 0
    with _client() as client:
        while url and pages < 5:
            pages += 1
            try:
                resp = client.get(url, params=params if pages == 1 else None)
                if resp.status_code == 404:
                    return rows
                resp.raise_for_status()
                data = resp.json()
            except httpx.HTTPError as e:
                logger.warning("InterPro API error (%s/%s): %s", member_db, uniprot_ac, e)
                break
            except Exception as e:
                logger.error("InterPro request failed (%s/%s): %s", member_db, uniprot_ac, e)
                break

            results = data.get("results") if isinstance(data, dict) else None
            if isinstance(results, list):
                rows.extend(r for r in results if isinstance(r, dict))

            nxt = data.get("next") if isinstance(data, dict) else None
            if not nxt or len(rows) >= 200:
                break
            url = urljoin(_base() + "/", nxt) if isinstance(nxt, str) else None
            params = None
    return rows


def _fetch_entry_details(member_db: str, accessions: list[str]) -> dict[str, dict[str, Any]]:
    """Fetch /entry/{db}/{acc} for functional text / GO / literature."""
    details: dict[str, dict[str, Any]] = {}
    if not accessions:
        return details
    with _client() as client:
        for acc in accessions:
            try:
                resp = client.get(f"{_base()}/entry/{member_db}/{acc}")
                if resp.status_code == 404:
                    continue
                resp.raise_for_status()
                payload = resp.json()
                meta = payload.get("metadata") if isinstance(payload, dict) else None
                if isinstance(meta, dict):
                    details[acc] = meta
            except Exception as e:
                logger.warning("InterPro entry detail failed for %s: %s", acc, e)
    return details


def _locations_from_row(row: dict[str, Any], uniprot_ac: str) -> list[dict[str, Any]]:
    locs: list[dict[str, Any]] = []
    for prot in row.get("proteins") or []:
        if not isinstance(prot, dict):
            continue
        pac = str(prot.get("accession") or "").upper()
        if pac and pac != uniprot_ac.upper():
            continue
        for loc in prot.get("entry_protein_locations") or []:
            if not isinstance(loc, dict):
                continue
            fragments = []
            for fr in loc.get("fragments") or []:
                if not isinstance(fr, dict):
                    continue
                start, end = fr.get("start"), fr.get("end")
                if start is None or end is None:
                    continue
                fragments.append({
                    "start": int(start),
                    "end": int(end),
                    "status": fr.get("dc-status") or fr.get("dc_status"),
                })
            if not fragments:
                continue
            locs.append({
                "fragments": fragments,
                "score": loc.get("score"),
                "model": loc.get("model"),
                "start": fragments[0]["start"],
                "end": fragments[-1]["end"],
            })
    return locs


def _covers_position(locs: list[dict[str, Any]], position: int | None) -> bool:
    if position is None:
        return True
    for loc in locs:
        for fr in loc.get("fragments") or []:
            if fr["start"] <= position <= fr["end"]:
                return True
    return False


def _span_label(start: int | None, end: int | None) -> str:
    if start is None or end is None:
        return ""
    return f"aa {start}–{end}"


def _normalize_entries(
    rows: list[dict[str, Any]],
    uniprot_ac: str,
    position: int | None,
    entry_type: str | None,
) -> list[dict[str, Any]]:
    type_filter = (entry_type or "").strip().lower() or None
    entries: list[dict[str, Any]] = []
    for row in rows:
        meta = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        etype = str(meta.get("type") or "").strip()
        if type_filter and type_filter not in etype.lower():
            continue
        locs = _locations_from_row(row, uniprot_ac)
        if position is not None and not _covers_position(locs, position):
            continue
        accession = str(meta.get("accession") or "")
        name, short = _entry_name(meta.get("name"))
        entries.append({
            "accession": accession,
            "name": name,
            "short_name": short,
            "type": etype,
            "integrated": meta.get("integrated"),
            "source_database": meta.get("source_database"),
            "locations": locs[:8],
            "start": locs[0]["start"] if locs else None,
            "end": locs[0]["end"] if locs else None,
            "score": locs[0].get("score") if locs else None,
            "go_terms": _parse_go(meta.get("go_terms")),
            "member_signatures": _parse_members(meta.get("member_databases")),
            "description": "",
            "description_full": "",
            "literature": [],
            "url": _entry_url(meta.get("source_database"), accession) if accession else None,
            "covers_site": position is not None,
            "site_note": (
                f"Residue {position} lies within this {etype or 'entry'} "
                f"({_span_label(locs[0]['start'], locs[0]['end']) if locs else 'coordinates unknown'})."
                if position is not None and locs
                else None
            ),
        })

    entries.sort(key=lambda e: (
        _TYPE_RANK.get(str(e.get("type") or "").lower(), 9),
        (e.get("end") or 10**9) - (e.get("start") or 0),  # tighter domains first
        e.get("start") or 10**9,
        e.get("accession") or "",
    ))
    return entries


def _enrich_entries(member_db: str, entries: list[dict[str, Any]], max_detail: int = 12) -> None:
    """Attach functional descriptions / GO / literature from entry detail API."""
    to_fetch = [e["accession"] for e in entries[:max_detail] if e.get("accession")]
    details = _fetch_entry_details(member_db, to_fetch)
    for e in entries:
        detail = details.get(e.get("accession") or "")
        if not detail:
            continue
        name, short = _entry_name(detail.get("name"))
        if name:
            e["name"] = name
        if short:
            e["short_name"] = short
        if detail.get("type"):
            e["type"] = detail.get("type")
        if detail.get("integrated") is not None:
            e["integrated"] = detail.get("integrated")
        short_desc, long_desc = _parse_description(detail.get("description"))
        e["description"] = short_desc
        e["description_full"] = long_desc
        go = _parse_go(detail.get("go_terms"))
        if go:
            e["go_terms"] = go
        members = _parse_members(detail.get("member_databases"))
        if members:
            e["member_signatures"] = members
        lit = _parse_literature(detail.get("literature"))
        if lit:
            e["literature"] = lit


def _build_summary(
    source_name: str,
    ac: str,
    gene: str | None,
    position: int | None,
    domains: list[dict[str, Any]],
    total: int,
) -> str:
    target = f"{ac}" + (f" ({gene})" if gene else "")
    if not domains:
        if position is not None:
            return (
                f"No {source_name} domain/family covers residue {position} on {target}. "
                f"(Protein has other {source_name} annotations; none overlap this site.)"
            )
        return f"No {source_name} matches found for {target}."

    parts: list[str] = []
    if position is not None:
        parts.append(
            f"Residue {position} on {target} falls within {total} {source_name} "
            f"annotation(s):"
        )
    else:
        parts.append(f"{source_name} architecture for {target} ({total} entries):")

    for d in domains[:5]:
        span = _span_label(d.get("start"), d.get("end"))
        label = d.get("name") or d.get("accession")
        line = f"{label} ({d.get('accession')}"
        if d.get("type"):
            line += f", {d['type']}"
        if span:
            line += f", {span}"
        line += ")"
        if d.get("description"):
            line += f" — {d['description']}"
        elif d.get("go_terms"):
            go_names = ", ".join(
                g["name"] for g in d["go_terms"][:3] if g.get("name")
            )
            if go_names:
                line += f" — GO: {go_names}"
        parts.append(line)

    if total > 5:
        parts.append(f"…and {total - 5} more (see domains list).")
    return " ".join(parts)


def _query_member_db(
    *,
    source_id: str,
    defaults: dict[str, str],
    member_db: str,
    gene: str | None,
    uniprot_ac: str | None,
    position: int | None,
    entry_type: str | None,
    limit: int,
) -> dict[str, Any]:
    meta = _meta(source_id, defaults)
    g, ac, identity = _prefer_gene(gene, uniprot_ac)
    if not ac:
        return {
            **meta,
            "summary": f"Provide uniprot_ac or gene to query {defaults['name']}.",
            "gene": g,
            "uniprot_ac": None,
            "domains": [],
            "total": 0,
            "error": "missing_identifier",
        }

    lim = max(1, min(int(limit or 40), 80))
    rows = _fetch_entry_matches(member_db, ac)
    all_matching = _normalize_entries(rows, ac, position, entry_type)
    domains = all_matching[:lim]

    # Always enrich returned hits so the agent can explain biology, not just IDs.
    # When filtering by site, enrich all returned (usually few); otherwise top 12.
    enrich_n = len(domains) if position is not None else min(12, len(domains))
    _enrich_entries(member_db, domains, max_detail=enrich_n)

    summary = _build_summary(defaults["name"], ac, g or (identity or {}).get("gene"), position, domains, len(all_matching))

    return {
        **meta,
        "summary": summary,
        "gene": g or (identity or {}).get("gene"),
        "uniprot_ac": ac,
        "position": position,
        "entry_type": entry_type,
        "total": len(all_matching),
        "domains": domains,
        "uniprot_identity": identity,
    }


def _interpro_domains(
    uniprot_ac: str | None = None,
    gene: str | None = None,
    position: int | None = None,
    entry_type: str | None = None,
    limit: int = 40,
) -> dict[str, Any]:
    return _query_member_db(
        source_id="interpro",
        defaults=_INTERPRO_DEFAULTS,
        member_db="interpro",
        gene=gene,
        uniprot_ac=uniprot_ac,
        position=position,
        entry_type=entry_type,
        limit=limit,
    )


def _pfam_domains(
    uniprot_ac: str | None = None,
    gene: str | None = None,
    position: int | None = None,
    entry_type: str | None = None,
    limit: int = 40,
) -> dict[str, Any]:
    return _query_member_db(
        source_id="pfam",
        defaults=_PFAM_DEFAULTS,
        member_db="pfam",
        gene=gene,
        uniprot_ac=uniprot_ac,
        position=position,
        entry_type=entry_type,
        limit=limit,
    )


def register_domain_tools() -> None:
    registry.register(
        name="interpro_domains",
        description=(
            "Query InterPro for protein families/domains on a UniProt protein. "
            "Returns names, residue spans, functional descriptions, GO terms and "
            "key literature — not just InterPro IDs. Optional position filter places "
            "a PTM site inside its domain. Use for Stage 3 WHERE architecture context. "
            "Citation: Mitchell et al. NAR 2019 (PMID 30398656)."
        ),
        parameters={
            "type": "object",
            "properties": {
                "uniprot_ac": {
                    "type": "string",
                    "description": "UniProt accession (e.g. P04637)",
                },
                "gene": {
                    "type": "string",
                    "description": "Gene symbol; resolved to UniProt via local identity",
                },
                "position": {
                    "type": "integer",
                    "description": "Optional: only entries whose coordinates cover this residue",
                },
                "entry_type": {
                    "type": "string",
                    "description": "Optional type filter: domain, family, homologous_superfamily, etc.",
                },
                "limit": {"type": "integer", "description": "Max entries to return (default 40)"},
            },
            "required": [],
        },
        handler=_interpro_domains,
    )

    registry.register(
        name="pfam_domains",
        description=(
            "Query Pfam signatures for a UniProt protein via the InterPro API. "
            "Returns family/domain names, coordinates, scores, descriptions and "
            "integrated InterPro IDs — suitable for explaining site-in-domain biology. "
            "Citation: El-Gebali et al. NAR 2019 (PMID 30357350)."
        ),
        parameters={
            "type": "object",
            "properties": {
                "uniprot_ac": {
                    "type": "string",
                    "description": "UniProt accession (e.g. P04637)",
                },
                "gene": {
                    "type": "string",
                    "description": "Gene symbol; resolved to UniProt via local identity",
                },
                "position": {
                    "type": "integer",
                    "description": "Optional: only Pfam matches covering this residue",
                },
                "entry_type": {
                    "type": "string",
                    "description": "Optional type filter: domain, family, conserved_site, etc.",
                },
                "limit": {"type": "integer", "description": "Max entries to return (default 40)"},
            },
            "required": [],
        },
        handler=_pfam_domains,
    )
