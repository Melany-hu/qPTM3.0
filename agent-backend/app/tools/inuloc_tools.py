"""iNuLoC + NLSdb tools — nuclear localization (PTM context).

Stage 3 (localization) tools:
  - inuloc_nls_nes — NLS/NES motifs (NLSdb) + DNL regions (iNuLoC)
  - inuloc_nuclear_prob — nuclear localization probability (iNuLoC)

Data:
  - NLS/NES motifs: data/localization/NLSdb/  (PMID 29106588)
  - DNL + nuclear_prob: data/localization/iNuLoC/  (PMID 40087285)

Note: shuttling-attacking mutation (SAM) tables are intentionally not included.
"""

from __future__ import annotations

import logging
from typing import Any

from app.sources.catalog import get_catalog
from app.sources.query import index_exists, query_records
from app.tools.registry import registry

logger = logging.getLogger(__name__)


def _meta(source_id: str) -> dict[str, str]:
    m = get_catalog().get(source_id)
    defaults = {
        "nlsdb": {
            "homepage": "https://rostlab.org/services/nlsdb/",
            "pmid": "29106588",
            "doi": "10.1093/nar/gkx1021",
        },
        "inuloc": {
            "homepage": "http://inuloc.omicsbio.info/",
            "pmid": "40087285",
            "doi": "10.1038/s41467-025-57858-8",
        },
    }
    base = defaults.get(source_id, {})
    return {
        "homepage": m.homepage if m else base.get("homepage", ""),
        "pmid": m.pmid if m else base.get("pmid", ""),
        "doi": m.doi if m else base.get("doi", ""),
    }


def _keys(gene, uniprot_ac, **extra) -> list[str]:
    keys = []
    if gene:
        keys.append(f"gene={gene}")
    if uniprot_ac:
        keys.append(f"uniprot={uniprot_ac}")
    for k, v in extra.items():
        if v is not None and v != "":
            keys.append(f"{k}={v}")
    return keys


def _lookup(
    source_id: str,
    file_id: str,
    gene,
    uniprot_ac,
    *,
    equals_ci=None,
    equals=None,
    limit=40,
):
    label = "NLSdb" if source_id == "nlsdb" else "iNuLoC"
    if not index_exists(source_id, file_id):
        raise FileNotFoundError(
            f"{label} {file_id} index missing. "
            f"Run: python -m app.sources.build_index {source_id}"
        )
    eq_ci = dict(equals_ci or {})
    if uniprot_ac:
        eq_ci["uniprot"] = uniprot_ac
    elif gene:
        eq_ci["gene"] = gene
    return query_records(
        source_id,
        file_id,
        equals=equals,
        equals_ci=eq_ci or None,
        limit=limit,
    )


def _inuloc_nls_nes(
    gene: str | None = None,
    uniprot_ac: str | None = None,
    signal: str = "all",
    include_predicted: bool = True,
    limit: int = 40,
) -> dict[str, Any]:
    """Query NLS/NES motifs (NLSdb) and DNL regions (iNuLoC)."""
    if not gene and not uniprot_ac:
        return {"error": "Provide gene or uniprot_ac", "summary": "Missing key for NLS/NES query"}

    sig = (signal or "all").strip().upper()
    equals_ci = {}
    if sig in ("NLS", "NES"):
        equals_ci["signal"] = sig

    try:
        exp = _lookup("nlsdb", "motifs_experimental", gene, uniprot_ac, equals_ci=equals_ci, limit=limit)
        pred = []
        dnls = []
        if include_predicted:
            pred = _lookup("nlsdb", "motifs_predicted", gene, uniprot_ac, equals_ci=equals_ci, limit=limit)
            if sig == "all":
                dnls = _lookup("inuloc", "dnl", gene, uniprot_ac, limit=min(limit, 20))
    except FileNotFoundError as e:
        return {"error": str(e), "summary": str(e)}

    total = len(exp) + len(pred) + len(dnls)
    summary = (
        f"NLS/NES/DNL: {total} hit(s) for {', '.join(_keys(gene, uniprot_ac, signal=sig))} "
        f"(NLSdb experimental={len(exp)}, NLSdb predicted={len(pred)}, iNuLoC DNL={len(dnls)})."
    )
    if total == 0:
        summary += " No NLS/NES/DNL annotations found."

    return {
        "summary": summary,
        "gene": gene,
        "uniprot_ac": uniprot_ac,
        "total": total,
        "experimental": exp[:limit],
        "predicted": pred[:limit],
        "dnl": dnls[:20],
        "sources": ["NLSdb", "iNuLoC"],
        "access": "local",
        **_meta("nlsdb"),
        "inuloc_homepage": _meta("inuloc")["homepage"],
        "inuloc_pmid": _meta("inuloc")["pmid"],
        "inuloc_doi": _meta("inuloc")["doi"],
    }


def _inuloc_nuclear_prob(
    gene: str | None = None,
    uniprot_ac: str | None = None,
    organism: str = "human",
    limit: int = 20,
) -> dict[str, Any]:
    """Query nuclear localization probability (iNuLoC)."""
    if not gene and not uniprot_ac:
        return {"error": "Provide gene or uniprot_ac", "summary": "Missing key for nuclear_prob"}

    org = (organism or "human").strip().lower()
    equals_ci = {"organism": org} if org not in ("all", "") else {}
    try:
        rows = _lookup(
            "inuloc", "nuclear_prob", gene, uniprot_ac, equals_ci=equals_ci, limit=limit,
        )
        if not rows and equals_ci:
            rows = _lookup("inuloc", "nuclear_prob", gene, uniprot_ac, limit=limit)
    except FileNotFoundError as e:
        return {"error": str(e), "summary": str(e)}

    summary = (
        f"iNuLoC nuclear probability: {len(rows)} record(s) for "
        f"{', '.join(_keys(gene, uniprot_ac, organism=org))}."
    )
    if not rows:
        summary += " No probability entry."

    return {
        "summary": summary,
        "gene": gene,
        "uniprot_ac": uniprot_ac,
        "organism": org,
        "total": len(rows),
        "probabilities": rows,
        "source": "iNuLoC",
        "access": "local",
        **_meta("inuloc"),
    }


def register_inuloc_tools() -> None:
    registry.register(
        name="inuloc_nls_nes",
        description=(
            "Query NLSdb for experimentally validated and predicted NLS/NES motifs, "
            "and iNuLoC for DNL (determinants of nuclear localization) regions. "
            "Useful for PTM questions about where a modified protein may localize."
        ),
        parameters={
            "type": "object",
            "properties": {
                "gene": {"type": "string"},
                "uniprot_ac": {"type": "string"},
                "signal": {"type": "string", "enum": ["NLS", "NES", "all"]},
                "include_predicted": {"type": "boolean"},
            },
            "required": [],
        },
        handler=_inuloc_nls_nes,
    )
    registry.register(
        name="inuloc_nuclear_prob",
        description=(
            "Query iNuLoC nuclear localization probability for a protein "
            "(organisms: human/mouse/rat/yeast/fly)."
        ),
        parameters={
            "type": "object",
            "properties": {
                "gene": {"type": "string"},
                "uniprot_ac": {"type": "string"},
                "organism": {
                    "type": "string",
                    "enum": ["human", "mouse", "rat", "yeast", "fly", "all"],
                },
            },
            "required": [],
        },
        handler=_inuloc_nuclear_prob,
    )
