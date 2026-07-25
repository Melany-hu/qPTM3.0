"""KAKA tools — kinase activity–related key alterations (mutations → activity).

Stage 1 WHO / mutation-precision tool:
  kaka_kinase_mutations — literature-curated effects of kinase mutations on
  enzyme activity (increase / decrease / kinase-dead / no-effect)

Data: data/enzymes/KAKA/ (PMID 41839313)
Homepage: https://kaka.omicsbio.info/
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from typing import Any

from app.sources.catalog import get_catalog
from app.sources.query import index_exists, query_records
from app.sources.uniprot_id import resolve_identity
from app.tools.registry import registry

logger = logging.getLogger(__name__)

_DEFAULTS = {
    "name": "KAKA",
    "homepage": "https://kaka.omicsbio.info/",
    "pmid": "41839313",
    "doi": "10.1016/j.jgg.2026.03.010",
}

_MUT_RE = re.compile(r"^([A-Za-z\*])(\d+)([A-Za-z\*]+)?$")
_ACTIVITY_ALIASES = {
    "no-effect": "no effect",
    "noeffect": "no effect",
    "kinase dead": "kinase-dead",
    "kinasedead": "kinase-dead",
    "increased": "increase",
    "decreased": "decrease",
}


def _meta() -> dict[str, Any]:
    m = get_catalog().get("kaka")
    return {
        "source": _DEFAULTS["name"],
        "access": "local",
        "homepage": (m.homepage if m else None) or _DEFAULTS["homepage"],
        "pmid": (m.pmid if m else None) or _DEFAULTS["pmid"],
        "doi": (m.doi if m else None) or _DEFAULTS["doi"],
    }


def _split_pmids(raw: Any) -> list[str]:
    text = str(raw or "").strip()
    if not text:
        return []
    parts: list[str] = []
    for p in text.replace(";", "|").replace(",", "|").split("|"):
        p = p.strip()
        if p.isdigit():
            parts.append(p)
    return parts


def _norm_activity(raw: str | None) -> str | None:
    if raw is None:
        return None
    text = " ".join(str(raw).strip().lower().split())
    if not text or text in ("any", "all"):
        return None
    return _ACTIVITY_ALIASES.get(text, text)


def _norm_mutation(raw: str | None) -> str | None:
    if not raw:
        return None
    mut = str(raw).strip().upper().replace(" ", "").replace("P.", "")
    return mut or None


def _compact(row: dict[str, Any]) -> dict[str, Any]:
    pmids = _split_pmids(row.get("pmids"))
    pos = row.get("position")
    out = {
        "gene": row.get("gene"),
        "protein_name": row.get("protein_name"),
        "uniprot": row.get("uniprot"),
        "mutation": row.get("mutation"),
        "aa_from": row.get("aa_from"),
        "aa_to": row.get("aa_to"),
        "position": int(pos) if str(pos or "").isdigit() else pos,
        "enzyme_activity": row.get("enzyme_activity"),
        "organism": row.get("organism"),
        "species": row.get("species"),
        "review": row.get("review"),
        "pmids": pmids,
        "description": (row.get("description") or "")[:600],
        "evidence": "literature",
    }
    return {k: v for k, v in out.items() if v not in (None, "", [])}


def _summarize(hits: list[dict[str, Any]], keys: list[str]) -> str:
    if not hits:
        return f"KAKA: no kinase activity–related mutations for {', '.join(keys)}."
    acts = Counter(h.get("enzyme_activity") or "?" for h in hits)
    genes = sorted({h.get("gene") or "?" for h in hits})
    examples = []
    for h in hits[:4]:
        bit = (
            f"{h.get('gene') or h.get('uniprot')} {h.get('mutation')} → "
            f"{h.get('enzyme_activity')}"
        )
        if h.get("pmids"):
            bit += f" (PMID {','.join(h['pmids'][:2])})"
        examples.append(bit)
    return (
        f"KAKA: {len(hits)} curated kinase activity alteration(s) "
        f"for {', '.join(keys)} "
        f"({len(genes)} gene(s); "
        f"effects: {', '.join(f'{k}×{v}' for k, v in acts.most_common())}). "
        f"Examples: " + "; ".join(examples)
    )


def _kaka_kinase_mutations(
    gene: str | None = None,
    uniprot_ac: str | None = None,
    mutation: str | None = None,
    position: int | None = None,
    enzyme_activity: str | None = None,
    organism: str | None = None,
    limit: int = 40,
) -> dict[str, Any]:
    """Query KAKA curated kinase mutations and their effects on enzyme activity."""
    mut = _norm_mutation(mutation)
    activity = _norm_activity(enzyme_activity)
    org = (organism or "").strip().lower() or None
    if org in ("any", "all", ""):
        org = None

    if not any([gene, uniprot_ac, mut]):
        return {
            "error": "Provide gene, uniprot_ac, and/or mutation (e.g. D177A)",
            "summary": "Missing query key for KAKA",
            "found": False,
            **_meta(),
        }

    if not index_exists("kaka", "events"):
        return {
            "error": "KAKA index missing. Run: python -m app.sources.build_index kaka",
            "summary": "KAKA index not built yet",
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

    # Infer position from mutation label when not given
    if position is None and mut:
        m = _MUT_RE.match(mut)
        if m:
            position = int(m.group(2))

    equals_ci: dict[str, str] = {}
    equals: dict[str, str] = {}

    if resolved_ac:
        equals_ci["uniprot_base"] = resolved_ac.split("-")[0]
    elif resolved_gene:
        equals_ci["gene"] = resolved_gene

    if mut:
        equals_ci["mutation"] = mut
    if position is not None and not mut:
        equals["position"] = str(int(position))
    if activity:
        equals_ci["enzyme_activity"] = activity
    if org:
        equals_ci["organism"] = org

    if not equals_ci and not equals:
        return {
            "error": "No usable filters after identity resolution",
            "summary": "KAKA: empty query",
            "found": False,
            **_meta(),
        }

    try:
        rows = query_records(
            "kaka",
            "events",
            equals=equals or None,
            equals_ci=equals_ci or None,
            limit=min(max(limit * 3, limit), 200),
        )
    except Exception as e:
        logger.error("KAKA query failed: %s", e, exc_info=True)
        return {
            "error": str(e),
            "summary": f"KAKA query failed: {e}",
            "found": False,
            **_meta(),
        }

    # Prefer exact isoform accession when provided
    if resolved_ac and "-" in resolved_ac:
        exact = [r for r in rows if (r.get("uniprot") or "").upper() == resolved_ac]
        if exact:
            rows = exact

    # If mutation+position both set, tighten after fetch
    if mut and position is not None:
        tightened = [
            r for r in rows
            if str(r.get("position") or "") == str(position)
            or (r.get("mutation") or "").upper() == mut
        ]
        if tightened:
            rows = tightened

    hits = [_compact(r) for r in rows[: min(limit, 80)]]
    keys: list[str] = []
    if resolved_gene:
        keys.append(f"gene={resolved_gene}")
    if resolved_ac:
        keys.append(f"uniprot={resolved_ac}")
    if mut:
        keys.append(f"mutation={mut}")
    elif position is not None:
        keys.append(f"pos={position}")
    if activity:
        keys.append(f"activity={activity}")
    if org:
        keys.append(f"organism={org}")

    activity_counts = dict(Counter(h.get("enzyme_activity") or "?" for h in hits))
    genes_found = sorted({h.get("gene") for h in hits if h.get("gene")})

    return {
        "summary": _summarize(hits, keys or ["query"]),
        "found": bool(hits),
        "gene": resolved_gene,
        "uniprot_ac": resolved_ac,
        "uniprot_identity": identity,
        "mutation": mut,
        "position": position,
        "enzyme_activity": activity,
        "organism": org,
        "genes_found": genes_found,
        "activity_counts": activity_counts,
        "total": len(hits),
        "alterations": hits,
        "note": (
            "KAKA curated kinase activity–related key alterations from literature "
            "(increase / decrease / kinase-dead / no-effect). Distinct from "
            "ActiveDriverDB / PSP PTMVar (mutation–PTM site overlap): these records "
            "report experimental effects on kinase catalytic activity."
        ),
        **_meta(),
    }


def register_kaka_tools() -> None:
    registry.register(
        name="kaka_kinase_mutations",
        description=(
            "Query KAKA for literature-curated kinase mutations and their "
            "experimentally validated effects on enzyme activity (increase, "
            "decrease, kinase-dead, or no-effect). Use for kinase-dead / "
            "gain-of-function / loss-of-function mutation questions and "
            "mutation-precision workflows. PMID 41839313."
        ),
        parameters={
            "type": "object",
            "properties": {
                "gene": {"type": "string", "description": "Kinase gene symbol (e.g. SGK1)"},
                "uniprot_ac": {
                    "type": "string",
                    "description": "Kinase UniProt accession (e.g. O00141)",
                },
                "mutation": {
                    "type": "string",
                    "description": "Missense allele (e.g. D177A, K127N)",
                },
                "position": {
                    "type": "integer",
                    "description": "Residue position filter when mutation label absent",
                },
                "enzyme_activity": {
                    "type": "string",
                    "description": (
                        "Optional activity class filter: increase, decrease, "
                        "kinase-dead, no-effect"
                    ),
                },
                "organism": {
                    "type": "string",
                    "description": (
                        "Optional organism short name "
                        "(human, mouse, rat, yeast, arabidopsis, ...)"
                    ),
                },
                "limit": {"type": "integer", "description": "Max hits (default 40)"},
            },
            "required": [],
        },
        handler=_kaka_kinase_mutations,
    )
