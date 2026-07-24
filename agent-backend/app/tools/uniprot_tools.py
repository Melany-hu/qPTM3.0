"""UniProt tools — query the UniProt REST API for protein annotations.

Stage 3 tool:
  6. uniprot_annotation — get functional annotations, PTM descriptions, domains, disease

UniProt REST API: https://rest.uniprot.org
No authentication required.

The API returns complex nested JSON. Key structures:
  - comments[].texts[].value          — for FUNCTION, PTM, PATHWAY
  - comments[].note.texts[].value     — for DISEASE, SUBCELLULAR LOCATION
  - comments[].subcellularLocations[].location.value — subcellular location names
  - features[] with type=Region/DNA binding/Domain — functional domains
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import settings
from app.tools.registry import registry

logger = logging.getLogger(__name__)


def _uniprot_get(path: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Make a GET request to the UniProt REST API."""
    url = f"{settings.uniprot_api_base_url}/{path.lstrip('/')}"
    try:
        with httpx.Client(timeout=settings.http_timeout_seconds) as client:
            resp = client.get(url, params=params, headers={"Accept": "application/json"})
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPError as e:
        logger.warning(f"UniProt API error for {path}: {e}")
        return None
    except Exception as e:
        logger.error(f"UniProt request failed for {path}: {e}")
        return None


def _extract_text_values(texts: list[dict] | None) -> list[str]:
    """Extract 'value' from a list of UniProt text objects.

    UniProt text objects have structure: {"value": "...", "evidences": [...]}
    """
    if not texts:
        return []
    values = []
    for t in texts:
        if isinstance(t, dict):
            # UniProt stores text in "value" key
            val = t.get("value")
            if val is None:
                # Fallback: some older formats use nested "text" -> "value"
                text_obj = t.get("text")
                if isinstance(text_obj, dict):
                    val = text_obj.get("value", "")
                elif isinstance(text_obj, str):
                    val = text_obj
            if val and isinstance(val, str):
                values.append(val)
    return values


def _extract_note_texts(comment: dict) -> list[str]:
    """Extract text values from a comment's note.texts structure.

    Used by DISEASE and SUBCELLULAR LOCATION comments.
    """
    note = comment.get("note", {})
    if not isinstance(note, dict):
        return []
    return _extract_text_values(note.get("texts", []))


# ── Tool 6: uniprot_annotation ────────────────────────────────────

def _uniprot_annotation(uniprot_ac: str) -> dict[str, Any]:
    """Get UniProt functional annotations, PTM descriptions, domains, and disease associations."""
    # Fetch the full entry (without fields filter to get complete comment structure)
    data = _uniprot_get(f"uniprotkb/{uniprot_ac}", params={"format": "json"})

    if data is None:
        return {
            "summary": f"No UniProt entry found for {uniprot_ac}.",
            "uniprot_ac": uniprot_ac,
        }

    # ── Gene names ──
    gene_names = []
    for g in data.get("genes", []):
        if isinstance(g, dict):
            name = g.get("geneName", {})
            if isinstance(name, dict):
                gene_names.append(name.get("value", ""))
            elif isinstance(name, str):
                gene_names.append(name)

    # ── Protein name ──
    protein_name = ""
    desc = data.get("proteinDescription", {})
    if isinstance(desc, dict):
        rec = desc.get("recommendedName", {})
        if isinstance(rec, dict):
            full = rec.get("fullName", {})
            protein_name = full.get("value", "") if isinstance(full, dict) else str(full)

    # ── Extract comment sections ──
    comments = data.get("comments", [])

    function_texts: list[str] = []
    ptm_texts: list[str] = []
    disease_texts: list[str] = []
    subcellular_texts: list[str] = []
    pathway_texts: list[str] = []

    for c in comments:
        if not isinstance(c, dict):
            continue
        ctype = c.get("commentType", "")

        if ctype == "FUNCTION":
            function_texts.extend(_extract_text_values(c.get("texts", [])))

        elif ctype == "PTM":
            ptm_texts.extend(_extract_text_values(c.get("texts", [])))

        elif ctype == "DISEASE":
            # DISEASE comments store text in note.texts, plus disease metadata
            note_texts = _extract_note_texts(c)
            disease_texts.extend(note_texts)
            # Also check for diseaseId field
            disease_id = c.get("diseaseId", "")
            if disease_id and disease_id not in note_texts:
                disease_texts.append(disease_id)

        elif ctype == "SUBCELLULAR LOCATION":
            # Subcellular location has both note.texts and subcellularLocations[].location.value
            note_texts = _extract_note_texts(c)
            subcellular_texts.extend(note_texts)
            for loc in c.get("subcellularLocations", []):
                if isinstance(loc, dict):
                    location = loc.get("location", {})
                    if isinstance(location, dict):
                        val = location.get("value", "")
                        if val:
                            subcellular_texts.append(val)

        elif ctype == "PATHWAY":
            pathway_texts.extend(_extract_text_values(c.get("texts", [])))

    # ── Extract functional domains/regions from features ──
    features = data.get("features", [])
    domains: list[str] = []
    domain_types = {"Domain", "Region", "DNA binding", "Zinc finger", "Repeat"}
    for f in features:
        if isinstance(f, dict) and f.get("type") in domain_types:
            desc_text = f.get("description", "")
            ftype = f.get("type", "")
            if desc_text:
                domains.append(f"{ftype}: {desc_text}")
            elif ftype:
                domains.append(ftype)

    # Deduplicate domains while preserving order
    seen = set()
    unique_domains = []
    for d in domains:
        if d not in seen:
            seen.add(d)
            unique_domains.append(d)

    # ── Build summary ──
    function_text = " ".join(function_texts)
    ptm_text = " ".join(ptm_texts)
    disease_text = " ".join(disease_texts)
    subcellular_text = " ".join(subcellular_texts)
    pathway_text = " ".join(pathway_texts)

    parts = []
    if gene_names:
        parts.append(f"Gene: {gene_names[0]}")
    if protein_name:
        parts.append(f"Protein: {protein_name}")
    if function_text:
        parts.append(f"Function: {function_text[:300]}")
    if ptm_text:
        parts.append(f"PTM info: {ptm_text[:300]}")
    if unique_domains:
        parts.append(f"Domains/Regions: {', '.join(unique_domains[:5])}")
    if disease_text:
        parts.append(f"Disease associations: {disease_text[:200]}")
    if subcellular_text:
        parts.append(f"Subcellular location: {subcellular_text[:200]}")
    if pathway_text:
        parts.append(f"Pathway: {pathway_text[:200]}")

    summary = " | ".join(parts) if parts else f"UniProt entry found for {uniprot_ac} but no annotations extracted."

    return {
        "summary": summary,
        "uniprot_ac": uniprot_ac,
        "gene": gene_names[0] if gene_names else None,
        "protein_name": protein_name,
        "function": function_text[:1000] if function_text else None,
        "ptm_description": ptm_text[:1500] if ptm_text else None,
        "domains": unique_domains[:10],
        "disease_associations": disease_texts[:10],
        "subcellular_location": subcellular_text[:500] if subcellular_text else None,
        "pathway": pathway_text[:500] if pathway_text else None,
    }


# ── Register tool ─────────────────────────────────────────────────

def register_uniprot_tools() -> None:
    """Register UniProt tools with the global registry."""
    registry.register(
        name="uniprot_annotation",
        description=(
            "Get comprehensive protein annotations from UniProt: functional description, "
            "PTM-specific descriptions (what the modification does to the protein), protein domains, "
            "disease associations, subcellular localization, and pathway information. "
            "Use this for Stage 3: understanding the functional consequences of a modification. "
            "The cc_ptm field often contains specific descriptions of what individual PTMs do."
        ),
        parameters={
            "type": "object",
            "properties": {
                "uniprot_ac": {
                    "type": "string",
                    "description": "UniProt accession (e.g., P04637 for TP53, P31749 for AKT1)",
                },
            },
            "required": ["uniprot_ac"],
        },
        handler=_uniprot_annotation,
    )
