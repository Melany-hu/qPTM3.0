"""ActiveDriverDB tools — PTM-site mutations & kinase network (local index + API).

Stage 3 (disease_drug) tools:
  - activedriver_mutations — ClinVar / MC3 / PCAWG / population variants near PTM sites
  - activedriver_kinase_network — site-specific kinase→target edges

Primary access: local SQLite indexes under data/disease/ActiveDriverDB/indexes/
built via `python -m app.sources.build_index activedriverdb`.

Optional API (may be retired after 2026-05-01):
  https://activedriverdb.org/api/
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import settings
from app.sources.catalog import get_catalog
from app.sources.query import index_exists, query_by_gene
from app.tools.registry import registry

logger = logging.getLogger(__name__)

_MUTATION_DATASETS = ("clinvar", "mc3", "pcawg", "population")


def _api_get(path: str) -> Any | None:
    base = (settings.activedriver_api_base_url or "").rstrip("/")
    if not base:
        return None
    url = f"{base}/{path.lstrip('/')}"
    try:
        with httpx.Client(timeout=settings.http_timeout_seconds) as client:
            resp = client.get(url, headers={"Accept": "application/json"})
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        logger.warning("ActiveDriverDB API error for %s: %s", path, e)
        return None


def _activedriver_mutations(
    gene: str,
    site_position: int | None = None,
    datasets: str = "clinvar,mc3",
    limit_per_dataset: int = 25,
) -> dict[str, Any]:
    """Query mutations affecting PTM sites for a gene (local index preferred)."""
    gene = (gene or "").strip()
    if not gene:
        return {"error": "gene is required", "summary": "gene is required"}

    wanted = [d.strip().lower() for d in datasets.split(",") if d.strip()]
    if not wanted or wanted == ["all"]:
        wanted = list(_MUTATION_DATASETS)
    for d in wanted:
        if d not in _MUTATION_DATASETS:
            return {
                "error": f"Unknown dataset '{d}'. Choose from {_MUTATION_DATASETS}",
                "summary": f"Unknown dataset '{d}'",
            }

    missing = [d for d in wanted if not index_exists("activedriverdb", d)]
    if missing:
        return {
            "error": (
                "ActiveDriverDB indexes missing for: "
                + ", ".join(missing)
                + ". Run: python -m app.sources.build_index activedriverdb"
            ),
            "summary": "ActiveDriverDB indexes not built yet",
        }

    by_dataset: dict[str, list[dict[str, Any]]] = {}
    total = 0
    for ds in wanted:
        rows = query_by_gene(
            "activedriverdb",
            ds,
            gene,
            site_position=site_position,
            limit=min(limit_per_dataset, 50),
        )
        by_dataset[ds] = rows
        total += len(rows)

    site_bit = f" at PTM site position {site_position}" if site_position else ""
    summary = (
        f"ActiveDriverDB: {total} mutation–PTM site hit(s) for {gene}{site_bit} "
        f"across {', '.join(wanted)}."
    )
    if total == 0:
        summary += " No matching variants in local tables."

    manifest = get_catalog().get("activedriverdb")
    return {
        "summary": summary,
        "gene": gene,
        "site_position": site_position,
        "datasets": wanted,
        "total": total,
        "mutations_by_dataset": by_dataset,
        "source": "ActiveDriverDB",
        "access": "local",
        "homepage": manifest.homepage if manifest else "https://activedriverdb.org",
    }


def _activedriver_kinase_network(
    gene: str,
    site_position: int | None = None,
    limit: int = 40,
) -> dict[str, Any]:
    """Query site-specific kinase→target edges for a substrate gene."""
    gene = (gene or "").strip()
    if not gene:
        return {"error": "gene is required", "summary": "gene is required"}

    if not index_exists("activedriverdb", "kinase_network"):
        return {
            "error": (
                "ActiveDriverDB kinase_network index missing. "
                "Run: python -m app.sources.build_index activedriverdb"
            ),
            "summary": "ActiveDriverDB kinase network index not built",
        }

    rows = query_by_gene(
        "activedriverdb",
        "kinase_network",
        gene,
        site_position=site_position,
        limit=min(limit, 80),
    )
    # Also include edges where gene is the kinase
    as_kinase: list[dict[str, Any]] = []
    try:
        from app.sources.catalog import get_catalog as _gc
        from app.sources.query import open_index

        manifest = _gc().require("activedriverdb")
        meta = manifest.file_by_id("kinase_network")
        conn = open_index(manifest, meta) if meta else None
        if conn is not None:
            try:
                cur = conn.execute(
                    'SELECT * FROM records WHERE UPPER("kinase_symbol") = ? LIMIT ?',
                    (gene.upper(), min(limit, 80)),
                )
                as_kinase = [dict(r) for r in cur.fetchall()]
            finally:
                conn.close()
    except Exception as e:
        logger.warning("kinase-as-source lookup failed: %s", e)

    summary = (
        f"ActiveDriverDB network: {len(rows)} kinase→{gene} edge(s)"
        + (f" at site {site_position}" if site_position else "")
        + (f"; {len(as_kinase)} edge(s) where {gene} is the kinase." if as_kinase else ".")
    )
    return {
        "summary": summary,
        "gene": gene,
        "site_position": site_position,
        "as_substrate": rows,
        "as_kinase": as_kinase[:40],
        "total": len(rows) + len(as_kinase),
        "source": "ActiveDriverDB",
        "access": "local",
    }


def register_activedriver_tools() -> None:
    registry.register(
        name="activedriver_mutations",
        description=(
            "Query ActiveDriverDB for mutations (ClinVar, TCGA/MC3, PCAWG, population) "
            "that affect PTM sites of a gene. Use for disease / cancer / germline variant "
            "context around a modification site. Requires local indexes."
        ),
        parameters={
            "type": "object",
            "properties": {
                "gene": {
                    "type": "string",
                    "description": "Gene symbol (e.g. TP53)",
                },
                "site_position": {
                    "type": "integer",
                    "description": "Optional PTM site residue position to filter",
                },
                "datasets": {
                    "type": "string",
                    "description": (
                        "Comma-separated: clinvar,mc3,pcawg,population or 'all' "
                        "(default: clinvar,mc3)"
                    ),
                },
            },
            "required": ["gene"],
        },
        handler=_activedriver_mutations,
    )

    registry.register(
        name="activedriver_kinase_network",
        description=(
            "Query ActiveDriverDB site-specific kinase–substrate network for a gene. "
            "Returns edges where the gene is a substrate (and optionally a kinase)."
        ),
        parameters={
            "type": "object",
            "properties": {
                "gene": {
                    "type": "string",
                    "description": "Gene symbol (substrate or kinase)",
                },
                "site_position": {
                    "type": "integer",
                    "description": "Optional target site position filter",
                },
            },
            "required": ["gene"],
        },
        handler=_activedriver_kinase_network,
    )
