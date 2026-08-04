"""Entity parsing from user questions (gene, site, PTM type, mutations)."""

from __future__ import annotations

import re
from typing import Any

_AA1 = set("ACDEFGHIKLMNPQRSTVWY")
_AA3_TO_1 = {
    "ALA": "A", "ARG": "R", "ASN": "N", "ASP": "D", "CYS": "C",
    "GLN": "Q", "GLU": "E", "GLY": "G", "HIS": "H", "ILE": "I",
    "LEU": "L", "LYS": "K", "MET": "M", "PHE": "F", "PRO": "P",
    "SER": "S", "THR": "T", "TRP": "W", "TYR": "Y", "VAL": "V",
    "TER": "*", "STOP": "*",
}

_GENE_LEFT = r"(?<![A-Za-z0-9_])"
_GENE_RIGHT = r"(?![A-Za-z0-9_])"
_SITE_RIGHT = r"(?![A-Za-z0-9_])"

_GENE_STOPWORDS = {
    "PTM", "DNA", "RNA", "ATP", "GTP", "WHO", "WHY", "WHEN", "WHERE", "THE", "AND", "FOR",
    "HUMAN", "MOUSE", "SEARCH", "WHAT", "WHICH", "UNDER", "STAGE", "WITH", "FROM", "THAT",
    "THIS", "THAN", "THEN", "THEY", "THEM", "HAVE", "HAS", "HAD", "WAS", "WERE", "ARE",
    "BEEN", "BEING", "WILL", "WOULD", "COULD", "SHOULD", "ABOUT", "INTO", "OVER", "AFTER",
    "BEFORE", "BETWEEN", "THROUGH", "DURING", "WITHOUT", "WITHIN",
    "AT", "IN", "ON", "BY", "TO", "OF", "OR", "IS", "AS", "AN", "BE", "IF", "NO", "UP",
    "SO", "WE", "IT", "DO", "MY", "ME", "AM", "US", "OUR", "YOU", "YOUR", "HIS", "HER",
    "ITS", "NOT", "BUT", "CAN", "MAY", "HOW", "ALL", "ANY", "BOTH", "EACH", "FEW", "MORE",
    "MOST", "OTHER", "SOME", "SUCH", "ONLY", "OWN", "SAME", "THAN", "TOO", "VERY",
    "E3", "E1", "E2", "DUB", "ESI", "DSI", "ESR", "SSER", "SSERS", "PMID",
    "API", "NAR", "GPS", "UBER", "HAT", "HDAC", "HMT", "HDM",
    "SUMO", "SIM", "SUMOYLATION", "UBIQUITINATION", "UBIQUITYLATION",
    "PHOSPHORYLATION", "ACETYLATION", "METHYLATION", "GLYCOSYLATION",
    "PHOSPHORYLATES", "PHOSPHORYLATE", "PHOSPHORYLATED", "KINASE", "KINASES",
    "ENZYME", "ENZYMES", "PROTEIN", "PROTEINS", "SITE", "SITES", "RESIDUE", "RESIDUES",
    "POSITION", "POSITIONS", "MUTATION", "MUTATIONS", "VARIANT", "VARIANTS",
    "CLINVAR", "PCAWG", "MC3", "SNV", "SNP", "INDEL", "QUERY", "TELL", "PLEASE",
    "DOES", "DID", "DONE", "FIND", "SHOW", "LIST", "GIVE", "GET",
    "HELLO", "HI", "HEY", "THANKS", "THANK", "BYE", "GOODBYE", "PLEASE",
    "HELP", "WHAT", "WHO", "WHY", "WHEN", "WHERE", "HOW", "YES", "OK", "OKAY",
    "WEATHER", "TODAY", "TOMORROW", "SORRY", "WELCOME", "MORNING", "EVENING",
    "NIGHT", "TEST", "DEMO", "EXAMPLE", "NULL", "NONE", "TRUE", "FALSE",
    "POST", "TRANSLATIONAL", "MODIFICATION", "MODIFICATIONS", "EXPLAIN",
    "ABOUT", "DEFINE", "DEFINITION", "INTRODUCTION", "OVERVIEW", "GENERAL",
    "MEANING", "PURPOSE", "ROLE", "ROLES", "ACTION", "ACTIONS",
    "SINGLE", "CELL", "CELLS", "OMICS", "PROTEOMICS", "PHOSPHOPROTEOMICS",
    "TRANSCRIPTOMICS", "METABOLOMICS", "TECHNOLOGY", "METHOD", "METHODS",
    "PTMOMICS", "THERE", "EXIST", "EXISTS", "EMERGING", "FRONTIER", "RECENT",
    "PROGRESS", "ADVANCES", "STATE", "ART", "REVIEW", "LITERATURE",
}


def _normalize_aa_token(token: str) -> str | None:
    t = (token or "").strip().upper()
    if not t:
        return None
    if t in ("*", "X", "DEL", "FS"):
        return "*" if t in ("*", "X") else t[0]
    if len(t) == 1 and t in _AA1:
        return t
    return _AA3_TO_1.get(t)


def is_plausible_gene(token: str | None) -> bool:
    if not token:
        return False
    t = token.strip().upper()
    if not t or t in _GENE_STOPWORDS or t.isdigit():
        return False
    if len(t) < 2:
        return False
    if re.fullmatch(r"[STYKR]\d{1,4}", t):
        return False
    return bool(re.fullmatch(r"[A-Z][A-Z0-9]{1,14}", t))


def parse_query_entities(message: str) -> dict[str, Any]:
    """Extract protein/site/mutation entities from a user question."""
    entities: dict[str, Any] = {
        "gene": None,
        "uniprot_ac": None,
        "position": None,
        "ptm_type": "phosphorylation",
        "organism": "human",
        "query": message.strip(),
        "mutation_ref": None,
        "mutation_alt": None,
        "mutation_label": None,
        "narrative": None,
    }

    msg_lower = message.lower()

    ptm_keywords = {
        "acetyl": "acetylation",
        "ubiquit": "ubiquitylation",
        "methyl": "methylation",
        "glycosyl": "glycosylation",
        "sumo": "sumoylation",
        "phosph": "phosphorylation",
    }
    for kw, ptm in ptm_keywords.items():
        if kw in msg_lower:
            entities["ptm_type"] = ptm
            break

    if re.search(r"\b(mouse|mus musculus)\b", msg_lower) or "小鼠" in msg_lower:
        entities["organism"] = "mouse"
    elif re.search(r"\b(rat|rattus)\b", msg_lower) or "大鼠" in msg_lower:
        entities["organism"] = "rat"
    elif re.search(r"\b(yeast|saccharomyces)\b", msg_lower) or "酿酒酵母" in msg_lower:
        entities["organism"] = "yeast"

    uni_match = re.search(
        r"\b([OPQ][0-9][A-Z0-9]{3}[0-9](?:-[0-9]+)?|[A-NR-Z][0-9][A-Z][A-Z0-9]{2}[0-9](?:-[0-9]+)?)\b",
        message,
        re.I,
    )
    if uni_match:
        entities["uniprot_ac"] = uni_match.group(1).upper()

    mut_match = re.search(
        _GENE_LEFT + r"([A-Z][A-Z0-9]{1,14})\s+(?:p\.)?"
        r"([A-Z]{1,3})(\d+)([A-Z*]{1,3}|\*)" + _SITE_RIGHT,
        message,
        re.I,
    )
    if mut_match and is_plausible_gene(mut_match.group(1)):
        ref = _normalize_aa_token(mut_match.group(2))
        alt = _normalize_aa_token(mut_match.group(4))
        pos = int(mut_match.group(3))
        if ref and alt and ref != alt:
            entities["gene"] = mut_match.group(1).upper()
            entities["position"] = pos
            entities["mutation_ref"] = ref
            entities["mutation_alt"] = alt
            entities["mutation_label"] = f"{ref}{pos}{alt}"
            if ref in ("S", "T", "Y") and not any(
                k in msg_lower for k in ("acetyl", "ubiquit", "methyl", "glycosyl", "sumo")
            ):
                entities["ptm_type"] = "phosphorylation"

    if not entities["mutation_label"]:
        lone_mut = re.search(
            _GENE_LEFT + r"(?:p\.)?([A-Z]{1,3})(\d+)([A-Z*]{1,3}|\*)" + _SITE_RIGHT,
            message,
            re.I,
        )
        if lone_mut:
            ref = _normalize_aa_token(lone_mut.group(1))
            alt = _normalize_aa_token(lone_mut.group(3))
            if ref and alt and ref != alt:
                entities["position"] = int(lone_mut.group(2))
                entities["mutation_ref"] = ref
                entities["mutation_alt"] = alt
                entities["mutation_label"] = f"{ref}{entities['position']}{alt}"

    if not entities["position"] or not entities["gene"]:
        at_site = re.search(
            _GENE_LEFT + r"([A-Z][A-Z0-9]{1,14})\s+at\s+(?:p\.)?"
            r"(?:([STYKR])(\d+)|(Ser|Thr|Tyr|Lys|Arg)(\d+))" + _SITE_RIGHT,
            message,
            re.I,
        )
        if at_site and is_plausible_gene(at_site.group(1)):
            entities["gene"] = at_site.group(1).upper()
            if at_site.group(2):
                entities["position"] = int(at_site.group(3))
            else:
                entities["position"] = int(at_site.group(5))

    if not entities["position"]:
        site_match = re.search(
            _GENE_LEFT + r"([A-Z][A-Z0-9]{1,14})\s+([STYKR])(\d+)" + _SITE_RIGHT,
            message,
            re.I,
        )
        if site_match and is_plausible_gene(site_match.group(1)):
            entities["gene"] = site_match.group(1).upper()
            entities["position"] = int(site_match.group(3))
    elif entities["gene"] and not is_plausible_gene(entities["gene"]):
        entities["gene"] = None

    if not entities["position"]:
        ser_site = re.search(
            _GENE_LEFT + r"([A-Z][A-Z0-9]{1,14})\s+(Ser|Thr|Tyr|Lys|Arg)(\d+)" + _SITE_RIGHT,
            message,
            re.I,
        )
        if ser_site and is_plausible_gene(ser_site.group(1)):
            entities["gene"] = ser_site.group(1).upper()
            entities["position"] = int(ser_site.group(3))

    if not entities["position"]:
        lone_site = re.search(
            _GENE_LEFT + r"(?:p\.)?(?:([STYKR])(\d+)|(Ser|Thr|Tyr|Lys|Arg)(\d+))" + _SITE_RIGHT,
            message,
            re.I,
        )
        if lone_site:
            if lone_site.group(1):
                entities["position"] = int(lone_site.group(2))
            else:
                entities["position"] = int(lone_site.group(4))

    if re.search(r"\bhistone\s+h3\b", msg_lower):
        entities["gene"] = entities["gene"] or "H3"
        entities["query"] = "histone H3"

    if not entities["gene"]:
        for match in re.finditer(_GENE_LEFT + r"([A-Z][A-Z0-9]{1,14})" + _GENE_RIGHT, message):
            token = match.group(1)
            if is_plausible_gene(token):
                entities["gene"] = token.upper()
                break
        if not entities["gene"]:
            for match in re.finditer(
                _GENE_LEFT + r"([A-Za-z][A-Za-z0-9]{1,14})" + _GENE_RIGHT, message
            ):
                token = match.group(1).upper()
                if is_plausible_gene(token):
                    entities["gene"] = token
                    break

    if entities["gene"] and not is_plausible_gene(entities["gene"]):
        entities["gene"] = None

    return entities
