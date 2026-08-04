"""Biomni-E1 complementary tools — public REST APIs (no Biomni conda env required).

Selected from Biomni-E1 coverage to complement qPTM's PTM-specialized stack
without duplicating UniProt, Reactome, STRING, KEGG, InterPro, etc.

  alphafold_structure   — AlphaFold DB structure summary + pLDDT
  ensembl_gene          — Ensembl gene coordinates / canonical transcript
  gnomad_variants       — Population variants (gnomAD GraphQL or Ensembl fallback)
  opentargets_disease   — Open Targets disease–target associations
  gwas_catalog_assoc    — GWAS Catalog SNP–trait associations for a gene
  jaspar_tf_motifs      — JASPAR transcription-factor binding profiles
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import settings
from app.sources.uniprot_id import lookup_by_gene, resolve_identity
from app.tools.registry import registry

logger = logging.getLogger(__name__)

_ORG_TAXON = {"human": 9606, "mouse": 10090, "rat": 10116, "yeast": 559292}
_ORG_ENSEMBL = {
    "human": "homo_sapiens",
    "mouse": "mus_musculus",
    "rat": "rattus_norvegicus",
    "yeast": "saccharomyces_cerevisiae",
}

_ALPHAFOLD_HOME = "https://alphafold.ebi.ac.uk"
_ALPHAFOLD_PMID = "36599774"
_ALPHAFOLD_DOI = "10.1093/nar/gkac937"
_ENSEMBL_HOME = "https://www.ensembl.org"
_ENSEMBL_PMID = "34791404"
_ENSEMBL_DOI = "10.1093/nar/gkab1049"
_GNOMAD_HOME = "https://gnomad.broadinstitute.org"
_GNOMAD_PMID = "32461654"
_GNOMAD_DOI = "10.1038/s41586-020-2308-7"
_OPENTARGETS_HOME = "https://platform.opentargets.org"
_OPENTARGETS_PMID = "34711957"
_OPENTARGETS_DOI = "10.1093/nar/gkab1016"
_GWAS_HOME = "https://www.ebi.ac.uk/gwas"
_GWAS_PMID = "38014047"
_GWAS_DOI = "10.1093/nar/gkad978"
_JASPAR_HOME = "https://jaspar.elixir.no"
_JASPAR_PMID = "33137113"
_JASPAR_DOI = "10.1093/nar/gkaa1051"


def _client(timeout: int | None = None) -> httpx.Client:
    return httpx.Client(
        timeout=timeout or settings.http_timeout_seconds,
        follow_redirects=True,
        headers={
            "Accept": "application/json",
            "User-Agent": "qPTM_agent/1.0 (academic research)",
        },
    )


def _resolve_target(
    *,
    gene: str | None = None,
    uniprot_ac: str | None = None,
    organism: str | None = "human",
) -> dict[str, Any]:
    org = (organism or "human").lower()
    tax = _ORG_TAXON.get(org, 9606)
    identity = resolve_identity(
        gene=gene,
        uniprot_ac=uniprot_ac,
        organism_id=tax,
    )
    if identity:
        return identity
    if gene:
        hit = lookup_by_gene(gene, organism_id=tax)
        if hit:
            return hit
    return {}


def _ensembl_species(organism: str | None) -> str:
    return _ORG_ENSEMBL.get((organism or "human").lower(), "homo_sapiens")


def _ensembl_lookup_gene(gene: str, organism: str | None = "human") -> dict[str, Any]:
    species = _ensembl_species(organism)
    base = settings.ensembl_api_base_url.rstrip("/")
    url = f"{base}/lookup/symbol/{species}/{gene}?expand=1"
    with _client() as client:
        resp = client.get(url)
        resp.raise_for_status()
        return resp.json()


def _ensembl_gene_id(gene: str, organism: str | None = "human") -> str | None:
    try:
        data = _ensembl_lookup_gene(gene, organism)
        return data.get("id")
    except httpx.HTTPError as exc:
        logger.warning("Ensembl lookup failed for %s: %s", gene, exc)
        return None


def _canonical_translation_id(gene: str, organism: str | None = "human") -> str | None:
    try:
        data = _ensembl_lookup_gene(gene, organism)
        for tx in data.get("Transcript") or []:
            if tx.get("is_canonical"):
                tr = tx.get("Translation") or {}
                return tr.get("id")
        for tx in data.get("Transcript") or []:
            tr = tx.get("Translation") or {}
            if tr.get("id"):
                return tr.get("id")
    except httpx.HTTPError as exc:
        logger.warning("Ensembl transcript lookup failed for %s: %s", gene, exc)
    return None


def _map_protein_position(
    translation_id: str,
    position: int,
) -> dict[str, Any] | None:
    base = settings.ensembl_api_base_url.rstrip("/")
    url = f"{base}/map/translation/{translation_id}/{position}..{position}"
    try:
        with _client() as client:
            resp = client.get(url)
            resp.raise_for_status()
            payload = resp.json()
        mappings = payload.get("mappings") or []
        return mappings[0] if mappings else None
    except httpx.HTTPError as exc:
        logger.warning("Ensembl map/translation failed: %s", exc)
        return None


def alphafold_structure(
    *,
    uniprot_ac: str | None = None,
    gene: str | None = None,
    position: int | None = None,
    organism: str | None = "human",
) -> dict[str, Any]:
    """AlphaFold DB structure summary and global confidence (pLDDT)."""
    ident = _resolve_target(gene=gene, uniprot_ac=uniprot_ac, organism=organism)
    ac = (ident.get("uniprot_ac") or uniprot_ac or "").strip().upper()
    if not ac:
        return {"error": "UniProt accession or gene symbol is required"}

    base = settings.alphafold_api_base_url.rstrip("/")
    try:
        with _client() as client:
            pred_resp = client.get(f"{base}/prediction/{ac}")
            pred_resp.raise_for_status()
            predictions = pred_resp.json()
            summary_resp = client.get(f"{base}/uniprot/summary/{ac}.json")
            summary_resp.raise_for_status()
            summary = summary_resp.json()
    except httpx.HTTPError as exc:
        logger.warning("AlphaFold API failed for %s: %s", ac, exc)
        return {"error": f"AlphaFold API request failed: {exc}"}

    pred = predictions[0] if isinstance(predictions, list) and predictions else {}
    structures = (summary.get("structures") or [{}])
    struct0 = structures[0].get("summary") or {}
    entry = summary.get("uniprot_entry") or {}

    model_id = pred.get("modelEntityId") or struct0.get("model_identifier")
    plddt = pred.get("globalMetricValue") or struct0.get("confidence_avg_local_score")
    model_url = struct0.get("model_page_url") or (
        f"{_ALPHAFOLD_HOME}/entry/{model_id}" if model_id else _ALPHAFOLD_HOME
    )

    region_note = None
    if position is not None:
        region_note = (
            f"Residue {position} maps to UniProt coordinate {position} "
            f"(inspect pLDDT locally in AlphaFold viewer; API does not expose per-residue scores here)."
        )

    summary_text = (
        f"AlphaFold: {ident.get('gene') or ac} ({ac}) — model {model_id or 'n/a'}, "
        f"global pLDDT {plddt:.1f}" if plddt is not None else
        f"AlphaFold: {ident.get('gene') or ac} ({ac}) — model {model_id or 'n/a'}"
    )

    return {
        "summary": summary_text,
        "gene": ident.get("gene") or gene,
        "uniprot_ac": ac,
        "model_id": model_id,
        "global_plddt": plddt,
        "sequence_length": entry.get("sequence_length"),
        "latest_version": pred.get("latestVersion"),
        "fraction_plddt_very_high": pred.get("fractionPlddtVeryHigh"),
        "fraction_plddt_low": pred.get("fractionPlddtLow"),
        "model_url": model_url,
        "region_note": region_note,
        "homepage": _ALPHAFOLD_HOME,
        "pmid": _ALPHAFOLD_PMID,
        "doi": _ALPHAFOLD_DOI,
    }


def ensembl_gene(
    *,
    gene: str | None = None,
    uniprot_ac: str | None = None,
    organism: str | None = "human",
) -> dict[str, Any]:
    """Ensembl gene coordinates, strand, and canonical transcript."""
    ident = _resolve_target(gene=gene, uniprot_ac=uniprot_ac, organism=organism)
    symbol = (ident.get("gene") or gene or "").strip().upper()
    if not symbol:
        return {"error": "Gene symbol is required"}

    try:
        data = _ensembl_lookup_gene(symbol, organism)
    except httpx.HTTPError as exc:
        logger.warning("Ensembl gene lookup failed: %s", exc)
        return {"error": f"Ensembl API request failed: {exc}"}

    canonical = None
    for tx in data.get("Transcript") or []:
        if tx.get("is_canonical"):
            canonical = tx
            break
    if canonical is None and data.get("Transcript"):
        canonical = data["Transcript"][0]

    translation_id = None
    if canonical:
        translation_id = (canonical.get("Translation") or {}).get("id")

    return {
        "summary": (
            f"Ensembl {symbol}: {data.get('id')} on {data.get('seq_region_name')}:"
            f"{data.get('start')}-{data.get('end')} ({data.get('assembly_name')}, "
            f"strand {data.get('strand')})"
        ),
        "gene": symbol,
        "ensembl_gene_id": data.get("id"),
        "display_name": data.get("display_name"),
        "chromosome": data.get("seq_region_name"),
        "start": data.get("start"),
        "end": data.get("end"),
        "strand": data.get("strand"),
        "assembly": data.get("assembly_name"),
        "biotype": data.get("biotype"),
        "description": data.get("description"),
        "canonical_transcript": canonical.get("id") if canonical else None,
        "canonical_translation": translation_id,
        "homepage": _ENSEMBL_HOME,
        "pmid": _ENSEMBL_PMID,
        "doi": _ENSEMBL_DOI,
    }


def gnomad_variants(
    *,
    gene: str | None = None,
    uniprot_ac: str | None = None,
    position: int | None = None,
    organism: str | None = "human",
    max_variants: int = 12,
) -> dict[str, Any]:
    """Population variants for a gene (gnomAD GraphQL with Ensembl fallback)."""
    ident = _resolve_target(gene=gene, uniprot_ac=uniprot_ac, organism=organism)
    symbol = (ident.get("gene") or gene or "").strip().upper()
    if not symbol:
        return {"error": "Gene symbol is required"}

    max_variants = max(1, min(int(max_variants or 12), 25))
    source = "gnomAD"
    constraint: dict[str, Any] = {}
    variants: list[dict[str, Any]] = []

    # ── Try gnomAD GraphQL (may be blocked from some hosts) ─────────
    gql = """
    query GeneConstraint($symbol: String!) {
      gene(gene_symbol: $symbol, reference_genome: GRCh38) {
        gene_id
        symbol
        chrom
        start
        stop
        gnomad_constraint {
          pLI
          oe_lof
          oe_lof_lower
          oe_lof_upper
        }
      }
    }
    """
    gnomad_url = settings.gnomad_api_base_url.rstrip("/")
    try:
        with _client() as client:
            resp = client.post(
                gnomad_url,
                json={"query": gql, "variables": {"symbol": symbol}},
            )
            if resp.status_code == 200:
                payload = resp.json()
                gene_data = (payload.get("data") or {}).get("gene") or {}
                if gene_data:
                    constraint = gene_data.get("gnomad_constraint") or {}
            else:
                raise httpx.HTTPStatusError(
                    "gnomAD blocked",
                    request=resp.request,
                    response=resp,
                )
    except httpx.HTTPError:
        source = "Ensembl (gnomAD frequencies via variation API)"

    # Site-specific or gene-wide variants via Ensembl
    translation_id = _canonical_translation_id(symbol, organism)
    region = None
    if position is not None and translation_id:
        region = _map_protein_position(translation_id, int(position))

    base = settings.ensembl_api_base_url.rstrip("/")
    try:
        with _client() as client:
            if region:
                chrom = region.get("seq_region_name")
                start = region.get("start")
                end = region.get("end")
                ov_url = (
                    f"{base}/overlap/region/human/{chrom}:{start}-{end}:1"
                    "?feature=variation"
                )
                ov_resp = client.get(ov_url)
                ov_resp.raise_for_status()
                for row in ov_resp.json()[:max_variants]:
                    rs = row.get("id")
                    freqs: list[dict[str, Any]] = []
                    if rs:
                        try:
                            var_resp = client.get(
                                f"{base}/variation/human/{rs}?pops=1"
                            )
                            if var_resp.status_code == 200:
                                var_data = var_resp.json()
                                for pop in (var_data.get("populations") or [])[:6]:
                                    if str(pop.get("population", "")).startswith("gnomAD"):
                                        freqs.append(
                                            {
                                                "population": pop.get("population"),
                                                "allele": pop.get("allele"),
                                                "frequency": pop.get("frequency"),
                                            }
                                        )
                        except httpx.HTTPError:
                            pass
                    variants.append(
                        {
                            "id": rs,
                            "consequence": row.get("consequence_type"),
                            "clinical_significance": row.get("clinical_significance"),
                            "alleles": row.get("alleles"),
                            "genomic_start": row.get("start"),
                            "population_frequencies": freqs,
                        }
                    )
            elif translation_id:
                # Gene-level: variation consequences on canonical protein
                ov_url = (
                    f"{base}/overlap/translation/{translation_id}"
                    "?feature=variation"
                )
                ov_resp = client.get(ov_url)
                ov_resp.raise_for_status()
                for row in ov_resp.json()[:max_variants]:
                    variants.append(
                        {
                            "id": row.get("id"),
                            "consequence": row.get("consequence_type"),
                            "clinical_significance": row.get("clinical_significance"),
                            "protein_start": row.get("start"),
                            "protein_end": row.get("end"),
                        }
                    )
    except httpx.HTTPError as exc:
        logger.warning("Ensembl variation query failed: %s", exc)
        if not variants:
            return {"error": f"Variant query failed: {exc}"}

    site_label = f" at residue {position}" if position else ""
    summary = (
        f"{source}: {len(variants)} variant(s) for {symbol}{site_label}"
        if variants
        else f"{source}: no population variants returned for {symbol}{site_label}"
    )
    if constraint:
        summary += (
            f"; constraint pLI={constraint.get('pLI')}, "
            f"oe_lof={constraint.get('oe_lof')}"
        )

    return {
        "summary": summary,
        "gene": symbol,
        "position": position,
        "data_source": source,
        "constraint": constraint,
        "variants": variants,
        "total": len(variants),
        "homepage": _GNOMAD_HOME,
        "pmid": _GNOMAD_PMID,
        "doi": _GNOMAD_DOI,
    }


def opentargets_disease(
    *,
    gene: str | None = None,
    uniprot_ac: str | None = None,
    organism: str | None = "human",
    limit: int = 12,
) -> dict[str, Any]:
    """Open Targets disease–target association scores."""
    ident = _resolve_target(gene=gene, uniprot_ac=uniprot_ac, organism=organism)
    symbol = (ident.get("gene") or gene or "").strip().upper()
    if not symbol:
        return {"error": "Gene symbol is required"}

    ensembl_id = _ensembl_gene_id(symbol, organism)
    if not ensembl_id:
        return {"error": f"Could not resolve Ensembl gene ID for {symbol}"}

    limit = max(1, min(int(limit or 12), 25))
    query = """
    query TargetDiseases($ensemblId: String!, $size: Int!) {
      target(ensemblId: $ensemblId) {
        approvedSymbol
        associatedDiseases(page: {index: 0, size: $size}) {
          count
          rows {
            score
            disease { id name }
          }
        }
      }
    }
    """
    url = settings.opentargets_api_base_url.rstrip("/")
    try:
        with _client() as client:
            resp = client.post(
                url,
                json={
                    "query": query,
                    "variables": {"ensemblId": ensembl_id, "size": limit},
                },
            )
            resp.raise_for_status()
            payload = resp.json()
    except httpx.HTTPError as exc:
        logger.warning("Open Targets query failed: %s", exc)
        return {"error": f"Open Targets API request failed: {exc}"}

    target = (payload.get("data") or {}).get("target") or {}
    assoc = target.get("associatedDiseases") or {}
    rows = assoc.get("rows") or []
    diseases = [
        {
            "disease": (row.get("disease") or {}).get("name"),
            "disease_id": (row.get("disease") or {}).get("id"),
            "score": row.get("score"),
        }
        for row in rows
    ]

    return {
        "summary": (
            f"Open Targets: {assoc.get('count', len(diseases))} disease association(s) "
            f"for {target.get('approvedSymbol') or symbol}; "
            f"showing top {len(diseases)}"
        ),
        "gene": target.get("approvedSymbol") or symbol,
        "ensembl_gene_id": ensembl_id,
        "total": assoc.get("count", len(diseases)),
        "diseases": diseases,
        "homepage": _OPENTARGETS_HOME,
        "pmid": _OPENTARGETS_PMID,
        "doi": _OPENTARGETS_DOI,
    }


def gwas_catalog_assoc(
    *,
    gene: str | None = None,
    uniprot_ac: str | None = None,
    organism: str | None = "human",
    limit: int = 10,
) -> dict[str, Any]:
    """GWAS Catalog SNP–trait associations linked to a gene."""
    ident = _resolve_target(gene=gene, uniprot_ac=uniprot_ac, organism=organism)
    symbol = (ident.get("gene") or gene or "").strip().upper()
    if not symbol:
        return {"error": "Gene symbol is required"}

    limit = max(1, min(int(limit or 10), 20))
    base = settings.gwas_catalog_api_base_url.rstrip("/")

    associations: list[dict[str, Any]] = []
    try:
        with _client(timeout=90) as client:
            snp_url = (
                f"{base}/singleNucleotidePolymorphisms/search/findByGene"
                f"?geneName={symbol}&size={min(limit, 5)}"
            )
            snp_resp = client.get(snp_url)
            snp_resp.raise_for_status()
            snps = (
                (snp_resp.json().get("_embedded") or {})
                .get("singleNucleotidePolymorphisms")
                or []
            )
            for snp in snps[:3]:
                rs_id = snp.get("rsId")
                if not rs_id:
                    continue
                assoc_resp = client.get(
                    f"{base}/singleNucleotidePolymorphisms/{rs_id}/associations?size={limit}"
                )
                if assoc_resp.status_code != 200:
                    continue
                for row in (
                    (assoc_resp.json().get("_embedded") or {}).get("associations")
                    or []
                )[:limit]:
                    trait = None
                    for link in (row.get("_links") or {}).values():
                        if isinstance(link, dict) and "efoTraits" in str(link.get("href", "")):
                            trait = link
                    associations.append(
                        {
                            "rs_id": rs_id,
                            "pvalue": (
                                f"{row.get('pvalueMantissa')}e{row.get('pvalueExponent')}"
                                if row.get("pvalueMantissa") is not None
                                else None
                            ),
                            "risk_allele": (
                                ((row.get("loci") or [{}])[0].get("strongestRiskAlleles") or [{}])[0]
                                .get("riskAlleleName")
                            ),
                            "beta_direction": row.get("betaDirection"),
                            "trait_hint": trait,
                        }
                    )
    except httpx.HTTPError as exc:
        logger.warning("GWAS Catalog query failed: %s", exc)
        return {"error": f"GWAS Catalog API request failed: {exc}"}

    # Deduplicate by rs_id + pvalue
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for row in associations:
        key = f"{row.get('rs_id')}|{row.get('pvalue')}"
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)
        if len(unique) >= limit:
            break

    return {
        "summary": (
            f"GWAS Catalog: {len(unique)} SNP–trait association(s) for {symbol}"
            if unique
            else f"GWAS Catalog: no associations returned for {symbol}"
        ),
        "gene": symbol,
        "total": len(unique),
        "associations": unique,
        "homepage": _GWAS_HOME,
        "pmid": _GWAS_PMID,
        "doi": _GWAS_DOI,
    }


def jaspar_tf_motifs(
    *,
    gene: str | None = None,
    query: str | None = None,
    organism: str | None = "human",
    limit: int = 8,
) -> dict[str, Any]:
    """JASPAR TF binding profiles matching a gene or keyword."""
    search = (query or gene or "").strip()
    if not search:
        return {"error": "Gene symbol or search keyword is required"}

    tax_id = _ORG_TAXON.get((organism or "human").lower(), 9606)
    limit = max(1, min(int(limit or 8), 15))
    base = settings.jaspar_api_base_url.rstrip("/")
    url = (
        f"{base}/matrix/?search={search}&tax_id={tax_id}"
        f"&collection=CORE&page_size={limit}"
    )

    try:
        with _client() as client:
            resp = client.get(url)
            resp.raise_for_status()
            payload = resp.json()
    except httpx.HTTPError as exc:
        logger.warning("JASPAR query failed: %s", exc)
        return {"error": f"JASPAR API request failed: {exc}"}

    motifs = [
        {
            "matrix_id": row.get("matrix_id"),
            "name": row.get("name"),
            "collection": row.get("collection"),
            "version": row.get("version"),
            "url": row.get("url"),
            "logo": row.get("sequence_logo"),
        }
        for row in (payload.get("results") or [])[:limit]
    ]

    return {
        "summary": (
            f"JASPAR: {payload.get('count', len(motifs))} TF profile(s) matching '{search}'; "
            f"returning {len(motifs)}"
        ),
        "query": search,
        "total": payload.get("count", len(motifs)),
        "motifs": motifs,
        "homepage": _JASPAR_HOME,
        "pmid": _JASPAR_PMID,
        "doi": _JASPAR_DOI,
    }


def register_biomni_e1_tools() -> None:
    """Register Biomni-E1 complementary REST tools."""
    registry.register(
        name="alphafold_structure",
        description=(
            "Query AlphaFold DB for predicted protein structure metadata and global "
            "pLDDT confidence. Useful for structural context around a PTM site."
        ),
        parameters={
            "type": "object",
            "properties": {
                "uniprot_ac": {"type": "string", "description": "UniProt accession"},
                "gene": {"type": "string", "description": "Gene symbol (e.g. TP53)"},
                "position": {
                    "type": "integer",
                    "description": "PTM site residue position (optional)",
                },
                "organism": {
                    "type": "string",
                    "enum": ["human", "mouse", "rat", "yeast"],
                    "default": "human",
                },
            },
        },
        handler=alphafold_structure,
    )
    registry.register(
        name="ensembl_gene",
        description=(
            "Query Ensembl for gene genomic coordinates, strand, and canonical "
            "transcript / protein IDs."
        ),
        parameters={
            "type": "object",
            "properties": {
                "gene": {"type": "string", "description": "Gene symbol"},
                "uniprot_ac": {"type": "string", "description": "UniProt accession"},
                "organism": {
                    "type": "string",
                    "enum": ["human", "mouse", "rat", "yeast"],
                    "default": "human",
                },
            },
        },
        handler=ensembl_gene,
    )
    registry.register(
        name="gnomad_variants",
        description=(
            "Query population variants for a gene or PTM residue (gnomAD constraint + "
            "Ensembl/gnomAD allele frequencies). Complements ClinVar/PTMVar mutation tools."
        ),
        parameters={
            "type": "object",
            "properties": {
                "gene": {"type": "string", "description": "Gene symbol"},
                "uniprot_ac": {"type": "string", "description": "UniProt accession"},
                "position": {
                    "type": "integer",
                    "description": "Protein residue position (optional)",
                },
                "organism": {
                    "type": "string",
                    "enum": ["human", "mouse", "rat", "yeast"],
                    "default": "human",
                },
                "max_variants": {
                    "type": "integer",
                    "description": "Max variants to return (default 12)",
                    "default": 12,
                },
            },
        },
        handler=gnomad_variants,
    )
    registry.register(
        name="opentargets_disease",
        description=(
            "Query Open Targets for disease–target association scores. "
            "Useful for therapeutic / disease context beyond PTM-specific databases."
        ),
        parameters={
            "type": "object",
            "properties": {
                "gene": {"type": "string", "description": "Gene symbol"},
                "uniprot_ac": {"type": "string", "description": "UniProt accession"},
                "organism": {
                    "type": "string",
                    "enum": ["human", "mouse", "rat", "yeast"],
                    "default": "human",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max diseases to return (default 12)",
                    "default": 12,
                },
            },
        },
        handler=opentargets_disease,
    )
    registry.register(
        name="gwas_catalog_assoc",
        description=(
            "Query GWAS Catalog for SNP–trait associations linked to a gene. "
            "Complements dbPTM nsSNP and PTMVar evidence."
        ),
        parameters={
            "type": "object",
            "properties": {
                "gene": {"type": "string", "description": "Gene symbol"},
                "uniprot_ac": {"type": "string", "description": "UniProt accession"},
                "organism": {
                    "type": "string",
                    "enum": ["human", "mouse", "rat", "yeast"],
                    "default": "human",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max associations to return (default 10)",
                    "default": 10,
                },
            },
        },
        handler=gwas_catalog_assoc,
    )
    registry.register(
        name="jaspar_tf_motifs",
        description=(
            "Search JASPAR for transcription-factor binding profiles. "
            "Useful when the upstream regulator may be a TF rather than a kinase."
        ),
        parameters={
            "type": "object",
            "properties": {
                "gene": {"type": "string", "description": "Gene / TF symbol to search"},
                "query": {
                    "type": "string",
                    "description": "Optional keyword override for motif search",
                },
                "organism": {
                    "type": "string",
                    "enum": ["human", "mouse", "rat", "yeast"],
                    "default": "human",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max profiles to return (default 8)",
                    "default": 8,
                },
            },
        },
        handler=jaspar_tf_motifs,
    )
