"""Planning layer — route user questions to databases/tools before LLM execution.

Architecture:
  1. Parse entities (gene, site, PTM type) from the question
  2. Classify research intent (which workflow stages are needed)
  3. Select databases and tools deterministically (not left to the LLM)
  4. Build a step1 / step2 / step3 research plan for the Agent executor
"""

from __future__ import annotations

import re
from typing import Any

from app.models.schemas import PlanStep, PlanStepStatus, ResearchPlan, WorkflowStage
from app.workflow.stages import detect_stage_from_message, get_stage_label
from app.workflow.state import ConversationState

# ── Database & tool catalog (planning metadata) ──────────────────

DATABASE_CATALOG: dict[str, dict[str, str]] = {
    "qPTM": {
        "name": "qPTM",
        "type": "database",
        "description": "Quantitative PTM events, site conditions, integrated kinases",
        "url": "https://qptm3.omicsbio.info",
    },
    "iPTMnet": {
        "name": "iPTMnet",
        "type": "database",
        "description": (
            "Integrated PTM network resource — enzyme–substrate sites and "
            "PTM-dependent PPI via REST API v1; PMID 29145615"
        ),
        "url": "https://research.bioinformatics.udel.edu/iptmnet/",
    },
    "UniProt": {
        "name": "UniProt",
        "type": "database",
        "description": "Protein function, PTM annotations, disease associations",
        "url": "https://www.uniprot.org",
    },
    "InterPro": {
        "name": "InterPro",
        "type": "database",
        "description": (
            "Protein family classification and predicted domains via REST API; "
            "PMID 30398656"
        ),
        "url": "https://www.ebi.ac.uk/interpro/",
    },
    "Pfam": {
        "name": "Pfam",
        "type": "database",
        "description": (
            "Manually curated protein families (via InterPro API); PMID 30357350"
        ),
        "url": "https://www.ebi.ac.uk/interpro/entry/pfam/",
    },
    "PhosphoSitePlus": {
        "name": "PhosphoSitePlus",
        "type": "database",
        "description": "Regulatory sites, kinases, disease PTMs, PTMVars; PMID 30445427",
        "url": "https://www.phosphosite.org",
    },
    "dbPTM": {
        "name": "dbPTM",
        "type": "database",
        "description": "nsSNP-linked disease associations for PTM sites",
        "url": "https://biomics.lab.nycu.edu.tw/dbPTM/",
    },
    "ActiveDriverDB": {
        "name": "ActiveDriverDB",
        "type": "database",
        "description": "Mutations affecting PTM sites (ClinVar/TCGA/PCAWG/population) and kinase–target network",
        "url": "https://activedriverdb.org",
    },
    "PMADS": {
        "name": "PMADS",
        "type": "database",
        "description": "Drug–PTM–disease associations (curated + inferred); PMID 41099621",
        "url": "https://pmads-db.org",
    },
    "DrugBank": {
        "name": "DrugBank",
        "type": "database",
        "description": "Drug–target associations (DrugBank 6.0); PMID 37953279",
        "url": "https://go.drugbank.com",
    },
    "WERAM": {
        "name": "WERAM",
        "type": "database",
        "description": (
            "Histone acetylation/methylation writers, erasers and readers "
            "(HAT/HDAC/HMT/HDM/readers); PMID 27789692"
        ),
        "url": "http://weram.biocuckoo.org",
    },
    "UbiBrowser": {
        "name": "UbiBrowser",
        "type": "database",
        "description": (
            "E3 ligase / DUB–substrate interactions (known + predicted); "
            "PMID 34634807"
        ),
        "url": "http://ubibrowser.bio-it.cn/ubibrowser_v3/home/index",
    },
    "GPS-Uber": {
        "name": "GPS-Uber",
        "type": "database",
        "description": (
            "Site-specific E3–substrate ubiquitination relations (ssESRs); "
            "PMID 35037020"
        ),
        "url": "http://gpsuber.biocuckoo.cn/",
    },
    "GPS 6.0": {
        "name": "GPS 6.0",
        "type": "database",
        "description": (
            "Predicted kinase-specific phosphorylation sites (GPS 6.0); "
            "PMID 37158278"
        ),
        "url": "https://gps.biocuckoo.cn",
    },
    "GPS-SUMO 2.0": {
        "name": "GPS-SUMO 2.0",
        "type": "database",
        "description": (
            "Curated experimental SUMOylation sites and SIMs "
            "(GPS-SUMO 2.0 training/test sets); PMID 38709873"
        ),
        "url": "https://sumo.biocuckoo.cn/",
    },
    "decryptM": {
        "name": "decryptM",
        "type": "database",
        "description": "Drug–PTM dose-response curves (ProteomicsDB); PMID 36926954",
        "url": "https://www.proteomicsdb.org/decryptm",
    },
    "PTMPhaSe": {
        "name": "PTMPhaSe",
        "type": "database",
        "description": "PTM regulation of LLPS (experimental + PhosLLPS predictions); PMID 41360972",
        "url": "https://ptmphase.sjtu.edu.cn",
    },
    "dSCOPE": {
        "name": "dSCOPE",
        "type": "database",
        "description": "LLPS-driving sequence regions (literature + proteome predictions); PMID 36528388",
        "url": "https://dscope.omicsbio.info",
    },
    "PTMD": {
        "name": "PTMD",
        "type": "database",
        "description": "Disease-associated PTMs (PDAs, 6 state classes); PMID 39329270",
        "url": "https://ptmd.biocuckoo.cn/",
    },
    "CancerProteome": {
        "name": "CancerProteome",
        "type": "database",
        "description": "Cancer vs normal PTM/protein quantification across 21 cancer types; PMID 37823596",
        "url": "http://bio-bigdata.hrbmu.edu.cn/CancerProteome",
    },
    "PTMint": {
        "name": "PTMint",
        "type": "database",
        "description": "PTM regulation of PPIs (Enhance/Inhibit); PMID 36548389",
        "url": "https://ptmint.sjtu.edu.cn/",
    },
    "STRING": {
        "name": "STRING",
        "type": "database",
        "description": "Scored protein association networks; PMID 39558183",
        "url": "https://string-db.org",
    },
    "BioGRID": {
        "name": "BioGRID",
        "type": "database",
        "description": "Curated protein/genetic/chemical interactions; PMID 33070389",
        "url": "https://thebiogrid.org",
    },
    "IntAct": {
        "name": "IntAct",
        "type": "database",
        "description": "Curated molecular interactions (IMEx/PSICQUIC); PMID 34761267",
        "url": "https://www.ebi.ac.uk/intact",
    },
    "Reactome": {
        "name": "Reactome",
        "type": "database",
        "description": "Curated pathway reactions / signaling maps; PMID 29145629",
        "url": "https://reactome.org",
    },
    "KEGG": {
        "name": "KEGG",
        "type": "database",
        "description": "Organism pathway maps from molecular datasets; PMID 30321428",
        "url": "https://www.kegg.jp",
    },
    "PathBank": {
        "name": "PathBank",
        "type": "database",
        "description": "Model-organism pathways (SMPDB/PathBank family index); PMID 31602469",
        "url": "https://pathbank.org",
    },
    "PTMcode2": {
        "name": "PTMcode2",
        "type": "database",
        "description": "Functional PTM–PTM associations within/between proteins; PMID 25361965",
        "url": "http://ptmcode.embl.de",
    },
    "NLSdb": {
        "name": "NLSdb",
        "type": "database",
        "description": "NLS/NES motif database (experimental + in silico); PMID 29106588",
        "url": "https://rostlab.org/services/nlsdb/",
    },
    "COMPARTMENTS": {
        "name": "COMPARTMENTS",
        "type": "database",
        "description": "Protein subcellular localization evidence with confidence; PMID 24573882",
        "url": "https://compartments.jensenlab.org/",
    },
    "SubCELL": {
        "name": "SubCELL",
        "type": "database",
        "description": "Compartment-specific molecular interactions (SCSIs); PMID 39373488",
        "url": "https://subcell.idrblab.cn/",
    },
    "iNuLoC": {
        "name": "iNuLoC",
        "type": "database",
        "description": "DNL regions and nuclear localization probability; PMID 40087285",
        "url": "http://inuloc.omicsbio.info/",
    },
    "PTM-stability": {
        "name": "PTM-stability",
        "type": "curated dataset",
        "description": "PTM effects on protein stability (primary PMIDs; curated from PMC9839724)",
        "url": "",
    },
    "Funcscore": {
        "name": "Funcscore",
        "type": "curated dataset",
        "description": "Functional scores for human phosphosites (Ochoa et al.); PMID 31819260",
        "url": "https://www.nature.com/articles/s41587-019-0344-3",
    },
    "PubTator3": {
        "name": "PubTator3",
        "type": "literature",
        "description": (
            "NCBI biomedical literature search with entity/relation annotations; "
            "PMID 38460829"
        ),
        "url": "https://www.ncbi.nlm.nih.gov/research/pubtator3/",
    },
}

TOOL_ROUTING: dict[str, dict[str, Any]] = {
    "qptm_search": {
        "database": "qPTM",
        "stage": WorkflowStage.conditions,
        "title": "Search quantitative PTM events",
        "description": "Query qPTM for PTM events matching the protein, site, or keyword",
    },
    "qptm_site_conditions": {
        "database": "qPTM",
        "stage": WorkflowStage.conditions,
        "title": "Retrieve site-specific conditions",
        "description": "Get experimental conditions, time points and log2 ratios for a PTM site",
    },
    "qptm_kinases": {
        "database": "qPTM",
        "stage": WorkflowStage.kinase,
        "title": "Identify kinases from qPTM",
        "description": "Query integrated experimental and predicted kinase-substrate data",
    },
    "iptmnet_enzymes": {
        "database": "iPTMnet",
        "stage": WorkflowStage.kinase,
        "title": "Identify enzymes via iPTMnet",
        "description": (
            "REST /v1/{id}/substrate — kinases, acetyltransferases, E3 ligases "
            "(Huang et al. NAR 2018; PMID 29145615)"
        ),
    },
    "psp_regulatory": {
        "database": "PhosphoSitePlus",
        "stage": WorkflowStage.function,
        "title": "Regulatory annotations (PSP)",
        "description": "ON_FUNCTION, ON_PROCESS and interaction effects from Regulatory_sites",
    },
    "psp_kinase_substrate": {
        "database": "PhosphoSitePlus",
        "stage": WorkflowStage.kinase,
        "title": "Kinase–substrate (PSP)",
        "description": "Literature-curated kinase→substrate sites with in vivo/in vitro flags",
    },
    "weram_regulators": {
        "database": "WERAM",
        "stage": WorkflowStage.kinase,
        "title": "Histone Ac/Me writers/erasers/readers (WERAM)",
        "description": (
            "Classify proteins as histone acetylation/methylation writers, "
            "erasers or readers (Xu et al. NAR 2017; PMID 27789692)"
        ),
    },
    "ubibrowser_interactions": {
        "database": "UbiBrowser",
        "stage": WorkflowStage.kinase,
        "title": "E3/DUB–substrate (UbiBrowser)",
        "description": (
            "Literature + predicted ubiquitin ligase/deubiquitinase–substrate "
            "interactions (Wang et al. NAR 2022; PMID 34634807)"
        ),
    },
    "gpsuber_e3_sites": {
        "database": "GPS-Uber",
        "stage": WorkflowStage.kinase,
        "title": "Site-specific E3–substrate (GPS-Uber)",
        "description": (
            "Literature site-specific E3→lysine ubiquitination relations "
            "(Wang et al. Brief Bioinform 2022; PMID 35037020)"
        ),
    },
    "gps6_kinases": {
        "database": "GPS 6.0",
        "stage": WorkflowStage.kinase,
        "title": "Predicted kinases (GPS 6.0)",
        "description": (
            "GPS 6.0 predicted kinase-specific phosphorylation sites "
            "(Chen et al. NAR 2023; PMID 37158278)"
        ),
    },
    "gpssumo2_sites": {
        "database": "GPS-SUMO 2.0",
        "stage": WorkflowStage.kinase,
        "title": "SUMOylation sites / SIMs (GPS-SUMO 2.0)",
        "description": (
            "Curated experimental SUMOylation lysines and SIMs from "
            "GPS-SUMO 2.0 training/test sets (Wang et al. NAR 2024; PMID 38709873)"
        ),
    },
    "psp_disease_sites": {
        "database": "PhosphoSitePlus",
        "stage": WorkflowStage.function,
        "title": "Disease-associated sites (PSP)",
        "description": "PTM sites correlated with disease states (increased/decreased)",
    },
    "psp_ptmvar": {
        "database": "PhosphoSitePlus",
        "stage": WorkflowStage.function,
        "title": "PTMVars (mutation near PTM)",
        "description": "Class I/II variants that perturb PTM residues or ±5 aa flanks",
    },
    "uniprot_annotation": {
        "database": "UniProt",
        "stage": WorkflowStage.where,
        "title": "Protein context annotation",
        "description": "Retrieve function, domains and cellular roles for WHERE context",
    },
    "interpro_domains": {
        "database": "InterPro",
        "stage": WorkflowStage.where,
        "title": "InterPro domains / families",
        "description": (
            "REST entry→protein — families, domains, sites "
            "(Mitchell et al. NAR 2019; PMID 30398656)"
        ),
    },
    "pfam_domains": {
        "database": "Pfam",
        "stage": WorkflowStage.where,
        "title": "Pfam family signatures",
        "description": (
            "Pfam matches via InterPro API "
            "(El-Gebali et al. NAR 2019; PMID 30357350)"
        ),
    },
    "iptmnet_ptm_ppi": {
        "database": "iPTMnet",
        "stage": WorkflowStage.function,
        "title": "PTM-dependent interactions",
        "description": (
            "REST /v1/{id}/ptmppi — interactions modulated by PTM "
            "(PMID 29145615)"
        ),
    },
    "dbptm_functional": {
        "database": "dbPTM",
        "stage": WorkflowStage.function,
        "title": "Disease associations (nsSNP)",
        "description": "Query dbPTM for nsSNP-linked disease associations near PTM sites",
    },
    "ptm_stability": {
        "database": "PTM-stability",
        "stage": WorkflowStage.function,
        "title": "PTM stability effects",
        "description": "Check curated PTM-stability relationships",
    },
    "activedriver_mutations": {
        "database": "ActiveDriverDB",
        "stage": WorkflowStage.function,
        "title": "PTM-site mutations (disease/cancer)",
        "description": "ClinVar / TCGA / PCAWG / population variants affecting PTM sites",
    },
    "activedriver_kinase_network": {
        "database": "ActiveDriverDB",
        "stage": WorkflowStage.kinase,
        "title": "ActiveDriver kinase–target network",
        "description": "Site-specific kinase–substrate edges from ActiveDriverDB",
    },
    "pmads_drug_ptm": {
        "database": "PMADS",
        "stage": WorkflowStage.kinase,
        "title": "Drug–PTM–disease associations",
        "description": "Upstream drugs and drug–PTM links that regulate the site",
    },
    "drugbank_targets": {
        "database": "DrugBank",
        "stage": WorkflowStage.kinase,
        "title": "Drug–target associations (DrugBank)",
        "description": "Drugs that target the protein (ID, action, approval groups)",
    },
    "decryptm_drug_ptm": {
        "database": "decryptM",
        "stage": WorkflowStage.kinase,
        "title": "Drug–PTM dose-response (decryptM)",
        "description": "ProteomicsDB decryptM curves: which drugs regulate this PTM",
    },
    "ptmphase_llps": {
        "database": "PTMPhaSe",
        "stage": WorkflowStage.function,
        "title": "PTM–LLPS experimental evidence",
        "description": "Curated PTM effects on liquid–liquid phase separation",
    },
    "ptmphase_phosllps": {
        "database": "PTMPhaSe",
        "stage": WorkflowStage.function,
        "title": "PhosLLPS predicted LLPS sites",
        "description": "Predicted functional phosphorylation sites regulating LLPS",
    },
    "dscope_literature": {
        "database": "dSCOPE",
        "stage": WorkflowStage.function,
        "title": "dSCOPE literature LLPS-driving segments",
        "description": "Experimentally identified LLPS-driving sequence segments from literature",
    },
    "dscope_predictions": {
        "database": "dSCOPE",
        "stage": WorkflowStage.function,
        "title": "dSCOPE predicted PS-driving regions",
        "description": "Human proteome predictions of phase-separation driving regions",
    },
    "ptmd_disease": {
        "database": "PTMD",
        "stage": WorkflowStage.function,
        "title": "Disease-associated PTMs (PTMD)",
        "description": "PTM–disease associations with U/D/A/P/C/N state classes",
    },
    "cancerproteome_disease": {
        "database": "CancerProteome",
        "stage": WorkflowStage.conditions,
        "title": "Cancer vs normal PTM/protein (CancerProteome)",
        "description": (
            "Tumor/control differential PTM ratios and protein abundance by cancer type "
            "(WHEN quantification + WHY disease context)"
        ),
    },
    "ptmint_ppi": {
        "database": "PTMint",
        "stage": WorkflowStage.function,
        "title": "PTM-regulated PPIs (PTMint)",
        "description": "Curated experimental PTM enhance/inhibit protein interactions",
    },
    "string_ppi": {
        "database": "STRING",
        "stage": WorkflowStage.function,
        "title": "STRING association partners",
        "description": "Scored functional/physical/regulatory protein partners",
    },
    "biogrid_interactions": {
        "database": "BioGRID",
        "stage": WorkflowStage.function,
        "title": "BioGRID curated interactions",
        "description": "Experimental physical/genetic interactions with PMIDs",
    },
    "intact_interactions": {
        "database": "IntAct",
        "stage": WorkflowStage.function,
        "title": "IntAct molecular interactions",
        "description": "IMEx-quality interactions via PSICQUIC",
    },
    "reactome_pathways": {
        "database": "Reactome",
        "stage": WorkflowStage.function,
        "title": "Reactome pathways",
        "description": "Curated pathways containing the protein",
    },
    "kegg_pathways": {
        "database": "KEGG",
        "stage": WorkflowStage.function,
        "title": "KEGG pathways",
        "description": "Organism pathway maps linked to the gene",
    },
    "pathbank_pathways": {
        "database": "PathBank",
        "stage": WorkflowStage.function,
        "title": "PathBank pathways",
        "description": "Metabolic / disease / signaling pathways (PathBank family)",
    },
    "ptmcode_associations": {
        "database": "PTMcode2",
        "stage": WorkflowStage.function,
        "title": "PTM–PTM associations (PTMcode2)",
        "description": "Human high-evidence PTM pairs within proteins or between PPIs",
    },
    "inuloc_nls_nes": {
        "database": "NLSdb",
        "stage": WorkflowStage.where,
        "title": "NLS/NES motifs (NLSdb) + DNL (iNuLoC)",
        "description": "NLSdb experimental/predicted NLS/NES; iNuLoC DNL regions",
    },
    "inuloc_nuclear_prob": {
        "database": "iNuLoC",
        "stage": WorkflowStage.where,
        "title": "Nuclear localization probability",
        "description": "iNuLoC nuclear localization probability",
    },
    "compartments_localization": {
        "database": "COMPARTMENTS",
        "stage": WorkflowStage.where,
        "title": "Subcellular localization (COMPARTMENTS)",
        "description": "GO cellular-component evidence with confidence scores",
    },
    "subcell_scsi": {
        "database": "SubCELL",
        "stage": WorkflowStage.where,
        "title": "Compartment-specific PPIs (SubCELL)",
        "description": "Where the protein interacts (SCSIs) and location annotations",
    },
    "funcscore_phosphosite": {
        "database": "Funcscore",
        "stage": WorkflowStage.function,
        "title": "Phosphosite functional score",
        "description": "Ochoa et al. ML functional priority score (0–1) for human phosphosites",
    },
    "pubtator_literature_search": {
        "database": "PubTator3",
        "stage": WorkflowStage.function,
        "title": "Related literature (PubTator3)",
        "description": (
            "Supplementary PubMed recommendations when integrated databases "
            "cannot fully cover the question (NCBI PubTator3; PMID 38460829)"
        ),
    },
}

# Stage → ordered tools for a full research workflow (WHO → WHEN → WHERE → WHY)
STAGE_TOOL_SEQUENCE: dict[WorkflowStage, list[str]] = {
    WorkflowStage.kinase: [
        "qptm_kinases",
        "iptmnet_enzymes",
        "psp_kinase_substrate",
        "gps6_kinases",
        "weram_regulators",
        "ubibrowser_interactions",
        "gpsuber_e3_sites",
        "gpssumo2_sites",
        "activedriver_kinase_network",
        "pmads_drug_ptm",
        "drugbank_targets",
        "decryptm_drug_ptm",
    ],
    WorkflowStage.conditions: [
        "qptm_search",
        "qptm_site_conditions",
        "cancerproteome_disease",
    ],
    WorkflowStage.where: [
        "uniprot_annotation",
        "interpro_domains",
        "pfam_domains",
        "compartments_localization",
        "subcell_scsi",
        "inuloc_nls_nes",
        "inuloc_nuclear_prob",
    ],
    WorkflowStage.function: [
        "psp_regulatory",
        "psp_disease_sites",
        "psp_ptmvar",
        "cancerproteome_disease",
        "ptmd_disease",
        "ptmcode_associations",
        "funcscore_phosphosite",
        "ptm_stability",
        "iptmnet_ptm_ppi",
        "ptmint_ppi",
        "string_ppi",
        "biogrid_interactions",
        "intact_interactions",
        "reactome_pathways",
        "kegg_pathways",
        "pathbank_pathways",
        "dbptm_functional",
        "activedriver_mutations",
        "ptmphase_llps",
        "dscope_literature",
        "dscope_predictions",
    ],
}


# ── Entity parsing ────────────────────────────────────────────────

def parse_query_entities(message: str) -> dict[str, Any]:
    """Extract protein/site entities from a user question."""
    entities: dict[str, Any] = {
        "gene": None,
        "uniprot_ac": None,
        "position": None,
        "ptm_type": "phosphorylation",
        "organism": "human",
        "query": message.strip(),
    }

    msg_lower = message.lower()

    # PTM type
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

    # Organism
    if any(w in msg_lower for w in ("mouse", "mus musculus", "小鼠")):
        entities["organism"] = "mouse"
    elif any(w in msg_lower for w in ("rat", "大鼠")):
        entities["organism"] = "rat"
    elif any(w in msg_lower for w in ("yeast", "酿酒酵母")):
        entities["organism"] = "yeast"

    # UniProt accession
    uni_match = re.search(
        r"\b([OPQ][0-9][A-Z0-9]{3}[0-9](?:-[0-9]+)?|[A-NR-Z][0-9][A-Z][A-Z0-9]{2}[0-9](?:-[0-9]+)?)\b",
        message,
        re.I,
    )
    if uni_match:
        entities["uniprot_ac"] = uni_match.group(1).upper()

    # Gene + residue position (e.g. TP53 S15, AKT1 S473)
    site_match = re.search(
        r"\b([A-Z][A-Z0-9]{1,14})\s+([STYKR])(\d+)\b",
        message,
        re.I,
    )
    if site_match:
        entities["gene"] = site_match.group(1).upper()
        entities["position"] = int(site_match.group(3))

    # Histone shorthand
    if re.search(r"\bhistone\s+h3\b", msg_lower):
        entities["gene"] = entities["gene"] or "H3"
        entities["query"] = "histone H3"

    # Standalone gene name (uppercase token, skip common words)
    skip_words = {
        "PTM", "DNA", "RNA", "ATP", "GTP", "WHO", "WHY", "WHEN", "WHERE", "THE", "AND", "FOR",
        "HUMAN", "MOUSE", "SEARCH", "WHAT", "WHICH", "UNDER", "STAGE",
        "E3", "E1", "E2", "DUB", "ESI", "DSI", "ESR", "SSER", "SSERS", "PMID",
        "API", "NAR", "GPS", "UBER", "HAT", "HDAC", "HMT", "HDM",
        "SUMO", "SIM", "SUMOYLATION", "UBIQUITINATION", "UBIQUITYLATION",
        "PHOSPHORYLATION", "ACETYLATION", "METHYLATION", "GLYCOSYLATION",
    }
    if not entities["gene"]:
        for match in re.finditer(r"\b([A-Z][A-Z0-9]{1,14})\b", message):
            token = match.group(1).upper()
            if token not in skip_words and not token.isdigit():
                entities["gene"] = token
                break

    return entities


def _mentions_llps(message: str) -> bool:
    """Detect liquid–liquid phase separation (LLPS) intent in a query."""
    llps_keywords = (
        "phase separation", "llps", "condensate", "droplet", "dscope",
        "phasllps", "phosllps", "membraneless", "stress granule", "p-body",
        "相分离", "液液相分离", "凝聚体", "无膜细胞器",
    )
    msg_lower = message.lower()
    return any(kw in msg_lower for kw in llps_keywords)


def _mentions_ppi(message: str) -> bool:
    """Detect protein–protein interaction intent."""
    ppi_keywords = (
        "ppi", "protein-protein", "protein interaction", "interact", "interactor",
        "binding partner", "complex", "string", "biogrid", "intact",
        "互作", "相互作用", "结合伙伴", "蛋白互作", "复合物",
    )
    msg_lower = message.lower()
    return any(kw in msg_lower for kw in ppi_keywords)


def _mentions_pathway(message: str) -> bool:
    """Detect pathway / signaling-map intent."""
    pathway_keywords = (
        "pathway", "pathways", "signaling", "signalling", "reactome", "kegg",
        "pathbank", "smpdb", "cascade", "transduction", "metabolic map",
        "通路", "信号通路", "信号转导", "代谢通路",
    )
    msg_lower = message.lower()
    return any(kw in msg_lower for kw in pathway_keywords)


def _build_pubtator_query(entities: dict[str, Any], message: str) -> str:
    """Build a PubTator keyword query from parsed entities and user context."""
    parts: list[str] = []
    gene = entities.get("gene")
    position = entities.get("position")
    ptm_type = (entities.get("ptm_type") or "").strip()
    uniprot = entities.get("uniprot_ac")

    if gene:
        parts.append(str(gene))
    if position:
        parts.append(str(position))
    if ptm_type:
        parts.append(ptm_type)
    if uniprot and not gene:
        parts.append(str(uniprot))

    if parts:
        return " ".join(parts)

    # Fall back to the user message with workflow boilerplate stripped
    cleaned = re.sub(
        r"\b(who|when|where|why|stage|search|query|tell me|what|which|how)\b",
        " ",
        message,
        flags=re.I,
    )
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:240] if cleaned else message.strip()[:240]


def _mentions_domain(message: str) -> bool:
    """Detect protein domain / family architecture intent."""
    domain_keywords = (
        "domain", "domains", "family", "families", "interpro", "pfam",
        "architecture", "motif", "superfamily", "fold",
        "结构域", "蛋白家族", "结构域架构",
    )
    msg_lower = message.lower()
    return any(kw in msg_lower for kw in domain_keywords)


# ── Intent classification ─────────────────────────────────────────

def classify_research_stages(message: str) -> list[WorkflowStage]:
    """Determine which workflow stages the question requires."""
    detected = detect_stage_from_message(message)
    if detected:
        # Single-stage question — only run that stage
        return [detected]

    # Default / broad questions → full WHO → WHEN → WHERE → WHY pipeline
    return [
        WorkflowStage.kinase,
        WorkflowStage.conditions,
        WorkflowStage.where,
        WorkflowStage.function,
    ]


def _intent_summary(stages: list[WorkflowStage], entities: dict[str, Any]) -> str:
    """Human-readable summary of the planned investigation."""
    target_parts = []
    if entities.get("gene"):
        target_parts.append(entities["gene"])
    if entities.get("position"):
        target_parts.append(f"position {entities['position']}")
    if entities.get("ptm_type"):
        target_parts.append(entities["ptm_type"])
    target = " ".join(target_parts) if target_parts else "the query target"

    stage_labels = [get_stage_label(s) for s in stages]
    return (
        f"Investigate {target} through {len(stages)} stage(s): "
        + " → ".join(stage_labels)
    )


# ── Plan builder ──────────────────────────────────────────────────

def _pick_tools_for_stage(
    stage: WorkflowStage,
    entities: dict[str, Any],
    *,
    include_search: bool = False,
) -> list[str]:
    """Select tools for a stage based on available entity information."""
    has_uniprot = bool(entities.get("uniprot_ac"))
    has_position = bool(entities.get("position"))
    has_gene = bool(entities.get("gene"))

    # Stage 1 WHO — regulators (enzymes + upstream drugs)
    if stage == WorkflowStage.kinase:
        tools: list[str] = []
        if include_search:
            tools.append("qptm_search")
        # Include kinase tools when a site is known; UniProt may resolve mid-plan
        if has_position or has_uniprot:
            tools.extend(["qptm_kinases", "iptmnet_enzymes", "psp_kinase_substrate", "gps6_kinases"])
        elif has_gene and (entities.get("ptm_type") or "") == "phosphorylation":
            tools.append("gps6_kinases")
        # Histone acetylation / methylation writers–erasers–readers (WERAM)
        ptm = (entities.get("ptm_type") or "").lower()
        q = (entities.get("query") or "").lower()
        if (has_gene or has_uniprot) and (
            ptm in ("acetylation", "methylation")
            or any(
                kw in q
                for kw in (
                    "acetyl", "methyl", "histone", "hdac", "bromodomain",
                    "chromodomain", "weram", "writer", "eraser", "reader",
                )
            )
            or re.search(r"\b(hat|hmt|hdm|kat|sirt)\b", q)
        ):
            tools.append("weram_regulators")
        if (has_gene or has_uniprot) and (
            ptm in ("ubiquitylation", "ubiquitination")
            or any(
                k in q
                for k in (
                    "ubiquit", "e3 ligase", "deubiquit", "dub", "ubibrowser",
                    "mdm2", "usp", "gps-uber", "gpsuber", "ssesr",
                )
            )
        ):
            tools.append("ubibrowser_interactions")
            tools.append("gpsuber_e3_sites")
        if (has_gene or has_uniprot) and (
            ptm == "sumoylation"
            or any(
                k in q
                for k in (
                    "sumoylation", "sumoylat", "sumo", "sim motif",
                    "sumo-interacting", "sumo interacting",
                    "gps-sumo", "gpssumo", "gps sumo",
                    "苏素化", "类泛素",
                )
            )
        ):
            tools.append("gpssumo2_sites")
        if has_gene:
            tools.append("pmads_drug_ptm")
        if has_gene or has_uniprot:
            tools.append("drugbank_targets")
        if not tools:
            tools = ["qptm_search"]
        return tools

    # Stage 2 WHEN — kinetics / quantitative conditions
    if stage == WorkflowStage.conditions:
        tools = []
        if include_search:
            tools.append("qptm_search")
        if has_position:
            tools.append("qptm_site_conditions")
        elif not tools:
            tools.append("qptm_search")
        # Cancer tumor-vs-control PTM/protein quantification (also disease-relevant)
        if has_gene or has_uniprot:
            tools.append("cancerproteome_disease")
        return tools

    # Stage 3 WHERE — cell context + localization (+ pathway when asked)
    if stage == WorkflowStage.where:
        tools = []
        if include_search:
            tools.append("qptm_search")
        tools.extend(["uniprot_annotation", "compartments_localization"])
        if has_gene or has_uniprot:
            tools.extend(["interpro_domains", "pfam_domains", "subcell_scsi"])
        elif _mentions_domain(entities.get("query", "")):
            tools.extend(["interpro_domains", "pfam_domains"])
        if (has_gene or has_uniprot) and _mentions_pathway(entities.get("query", "")):
            tools.extend(["reactome_pathways", "kegg_pathways", "pathbank_pathways"])
        return tools

    # Stage 4 WHY — mechanism / outcome / value
    if stage == WorkflowStage.function:
        tools = []
        if include_search:
            tools.append("qptm_search")
        tools.append("psp_regulatory")
        if has_gene or has_uniprot:
            tools.append("psp_disease_sites")
            tools.append("psp_ptmvar")
        if has_gene:
            tools.append("cancerproteome_disease")
            tools.append("ptmd_disease")
            tools.append("ptmcode_associations")
        if entities.get("ptm_type") == "phosphorylation":
            tools.append("funcscore_phosphosite")
        tools.append("dbptm_functional")
        # PPI: PTM-specific always when site known; general PPI when asked
        if has_gene or has_uniprot:
            if has_position or _mentions_ppi(entities.get("query", "")):
                tools.extend(["ptmint_ppi", "iptmnet_ptm_ppi"])
            if _mentions_ppi(entities.get("query", "")):
                tools.extend([
                    "string_ppi",
                    "biogrid_interactions",
                    "intact_interactions",
                    "subcell_scsi",
                ])
            # Pathways: when asked, or for site-level stories (mechanism context)
            if _mentions_pathway(entities.get("query", "")) or has_position:
                tools.extend([
                    "reactome_pathways",
                    "kegg_pathways",
                    "pathbank_pathways",
                ])
        if _mentions_llps(entities.get("query", "")) and (has_gene or has_uniprot):
            tools.extend([
                "ptmphase_llps",
                "ptmphase_phosllps",
                "dscope_literature",
                "dscope_predictions",
            ])
        return tools

    return []


def build_research_plan(
    message: str,
    state: ConversationState | None = None,
) -> ResearchPlan:
    """Build a structured WHO→WHEN→WHERE→WHY research plan.

    This is the planning layer — databases and tools are selected here,
    not delegated to the LLM.
    """
    entities = parse_query_entities(message)

    # Reuse known target from session if the message doesn't specify one
    if state and state.has_target:
        if not entities["gene"] and state.target_gene:
            entities["gene"] = state.target_gene
        if not entities["uniprot_ac"] and state.target_uniprot_ac:
            entities["uniprot_ac"] = state.target_uniprot_ac
        if not entities["position"] and state.target_position:
            entities["position"] = state.target_position
        if state.target_ptm_type:
            entities["ptm_type"] = state.target_ptm_type

    stages = classify_research_stages(message)
    steps: list[PlanStep] = []
    step_num = 1
    seen_tools: set[str] = set()
    need_search = not bool(entities.get("uniprot_ac"))

    for stage in stages:
        tools = _pick_tools_for_stage(
            stage,
            entities,
            include_search=need_search and stage == stages[0],
        )
        stage_label = get_stage_label(stage)

        for tool_name in tools:
            if tool_name in seen_tools:
                continue
            seen_tools.add(tool_name)
            meta = TOOL_ROUTING[tool_name]
            db_info = DATABASE_CATALOG[meta["database"]]
            steps.append(PlanStep(
                step=step_num,
                stage=stage,
                title=f"Step {step_num}: {meta['title']}",
                description=(
                    f"{stage_label} — {meta['description']} "
                    f"[{db_info['name']}]"
                ),
                database=meta["database"],
                tool=tool_name,
            ))
            step_num += 1

    # Cap at a reasonable number of steps for UX (preserve stage order)
    if len(steps) > 10:
        required: set[int] = set()
        seen_stages: set[WorkflowStage] = set()
        for i, step in enumerate(steps):
            if step.stage not in seen_stages:
                required.add(i)
                seen_stages.add(step.stage)
            # Always keep WHEN tools (qPTM + CancerProteome; few and core)
            if step.stage == WorkflowStage.conditions:
                required.add(i)
        extras = [i for i in range(len(steps)) if i not in required]
        keep = sorted(required | set(extras[: max(0, 10 - len(required))]))
        steps = [steps[i] for i in keep]
        for i, step in enumerate(steps, start=1):
            step.step = i
            step.title = f"Step {i}: {TOOL_ROUTING[step.tool]['title']}"

    # Always append PubTator literature search as the final supplementary step
    lit_meta = TOOL_ROUTING["pubtator_literature_search"]
    lit_db = DATABASE_CATALOG[lit_meta["database"]]
    steps.append(PlanStep(
        step=len(steps) + 1,
        stage=WorkflowStage.function,
        title=f"Step {len(steps) + 1}: {lit_meta['title']}",
        description=(
            f"{get_stage_label(WorkflowStage.function)} — {lit_meta['description']} "
            f"[{lit_db['name']}]"
        ),
        database=lit_meta["database"],
        tool="pubtator_literature_search",
    ))

    return ResearchPlan(
        question=message,
        intent_summary=_intent_summary(stages, entities),
        steps=steps,
    )


def infer_tool_arguments(
    tool_name: str,
    entities: dict[str, Any],
    state: ConversationState | None = None,
) -> dict[str, Any]:
    """Infer tool call arguments from parsed entities (deterministic routing)."""
    gene = entities.get("gene") or (state.target_gene if state else None)
    uniprot = entities.get("uniprot_ac") or (state.target_uniprot_ac if state else None)
    position = entities.get("position") or (state.target_position if state else None)
    ptm_type = entities.get("ptm_type") or (state.target_ptm_type if state else "phosphorylation")
    organism = entities.get("organism", "human")
    query = entities.get("query", "")

    if tool_name == "qptm_search":
        search_q = gene or query
        field = "uniprot" if uniprot else ("gene" if gene else "any")
        if uniprot:
            search_q = uniprot
        return {
            "query": search_q,
            "field": field,
            "organism": organism,
            "ptm_type": ptm_type,
            "per_page": 20,
        }

    if tool_name == "qptm_site_conditions":
        if not (uniprot and position):
            return {}
        return {
            "uniprot_ac": uniprot,
            "position": position,
            "ptm_type": ptm_type,
        }

    if tool_name == "qptm_kinases":
        if not (uniprot and position):
            return {}
        return {"uniprot_ac": uniprot, "position": position}

    if tool_name in ("iptmnet_enzymes", "iptmnet_ptm_ppi", "psp_regulatory",
                     "uniprot_annotation", "dbptm_functional", "ptm_stability",
                     "psp_kinase_substrate", "psp_disease_sites", "psp_ptmvar",
                     "interpro_domains", "pfam_domains"):
        args = {}
        if uniprot:
            args["uniprot_ac"] = uniprot
        elif gene:
            args["gene"] = gene
        if position and tool_name != "uniprot_annotation":
            args["position"] = position
        if tool_name in ("psp_regulatory", "ptm_stability", "dbptm_functional"):
            args["ptm_type"] = ptm_type
        return args

    if tool_name in ("activedriver_mutations", "activedriver_kinase_network"):
        if not gene:
            return {}
        args: dict[str, Any] = {"gene": gene}
        if position:
            args["site_position"] = position
        if tool_name == "activedriver_mutations":
            args["datasets"] = "clinvar,mc3"
        return args

    if tool_name == "pmads_drug_ptm":
        args = {}
        if gene:
            args["gene"] = gene
        if uniprot:
            args["uniprot_ac"] = uniprot
        if position:
            args["site_position"] = position
        if ptm_type:
            args["ptm_type"] = ptm_type
        args["status"] = "Curated"
        if not (gene or uniprot):
            return {}
        return args

    if tool_name == "drugbank_targets":
        if not (gene or uniprot):
            return {}
        args: dict[str, Any] = {}
        if gene:
            args["gene"] = gene
        if uniprot:
            args["uniprot_ac"] = uniprot
        return args

    if tool_name == "weram_regulators":
        args: dict[str, Any] = {}
        if gene:
            args["gene"] = gene
        if uniprot:
            args["uniprot_ac"] = uniprot
        if ptm_type in ("acetylation", "methylation"):
            args["modification"] = ptm_type
        if not (gene or uniprot or args.get("modification")):
            return {}
        return args

    if tool_name == "ubibrowser_interactions":
        if not (gene or uniprot):
            return {}
        args: dict[str, Any] = {"include_predicted": True, "min_confidence": 0.8}
        if gene:
            args["gene"] = gene
        if uniprot:
            args["uniprot_ac"] = uniprot
        if ptm_type in ("ubiquitylation", "ubiquitination"):
            args["enzyme_type"] = "any"
        return args

    if tool_name == "gpsuber_e3_sites":
        if not (gene or uniprot):
            return {}
        args: dict[str, Any] = {}
        if gene:
            args["gene"] = gene
        if uniprot:
            args["uniprot_ac"] = uniprot
        if position:
            args["position"] = position
        return args

    if tool_name == "gps6_kinases":
        if not (gene or uniprot):
            return {}
        args: dict[str, Any] = {"min_score": 1.0}
        if gene:
            args["gene"] = gene
        if uniprot:
            args["uniprot_ac"] = uniprot
        if position:
            args["position"] = position
        return args

    if tool_name == "gpssumo2_sites":
        if not (gene or uniprot):
            return {}
        args: dict[str, Any] = {
            "organism": organism or "human",
            "include_sims": True,
        }
        if gene:
            args["gene"] = gene
        if uniprot:
            args["uniprot_ac"] = uniprot
        if position:
            args["position"] = position
        return args

    if tool_name == "decryptm_drug_ptm":
        if not (gene or uniprot):
            return {}
        args: dict[str, Any] = {"only_regulated": True}
        if gene:
            args["gene"] = gene
        if uniprot:
            args["uniprot_ac"] = uniprot
        if position:
            args["site_position"] = position
        if ptm_type:
            args["modification_type"] = ptm_type
        return args

    if tool_name in ("ptmphase_llps", "ptmphase_phosllps", "dscope_literature", "dscope_predictions"):
        if not (gene or uniprot):
            return {}
        args = {}
        if uniprot:
            args["uniprot_ac"] = uniprot
        if gene:
            args["gene"] = gene
        if position:
            args["site_position"] = position
        if tool_name == "ptmphase_llps" and ptm_type:
            args["ptm_type"] = ptm_type
        return args

    if tool_name == "ptmd_disease":
        if not (gene or uniprot):
            return {}
        args = {}
        if uniprot:
            args["uniprot_ac"] = uniprot
        if gene:
            args["gene"] = gene
        if position:
            args["position"] = position
        if ptm_type:
            args["ptm_type"] = ptm_type
        args["source"] = "both"
        return args

    if tool_name == "cancerproteome_disease":
        if not (gene or uniprot):
            return {}
        args: dict[str, Any] = {"query_type": "both"}
        if uniprot:
            args["uniprot_ac"] = uniprot
        if gene:
            args["gene"] = gene
        if position:
            args["position"] = position
        return args

    if tool_name == "ptmint_ppi":
        if not (gene or uniprot):
            return {}
        args = {}
        if uniprot:
            args["uniprot_ac"] = uniprot
        if gene:
            args["gene"] = gene
        if position:
            args["site_position"] = position
        if ptm_type:
            args["ptm_type"] = ptm_type
        return args

    if tool_name in ("string_ppi", "biogrid_interactions", "intact_interactions"):
        if not (gene or uniprot):
            return {}
        args: dict[str, Any] = {"organism": organism or "human"}
        if gene:
            args["gene"] = gene
        if uniprot:
            args["uniprot_ac"] = uniprot
        if tool_name == "string_ppi":
            args["network_type"] = "physical"
            args["required_score"] = 400
        elif tool_name == "biogrid_interactions":
            args["evidence_type"] = "physical"
        return args

    if tool_name in ("reactome_pathways", "kegg_pathways", "pathbank_pathways"):
        if not (gene or uniprot):
            return {}
        args = {"organism": organism or "human"}
        if gene:
            args["gene"] = gene
        if uniprot:
            args["uniprot_ac"] = uniprot
        return args

    if tool_name == "ptmcode_associations":
        if not gene:
            return {}
        args = {"gene": gene, "scope": "both", "organism": organism or "human"}
        if position:
            args["position"] = position
        return args

    if tool_name in ("inuloc_nls_nes", "inuloc_nuclear_prob"):
        if not (gene or uniprot):
            return {}
        args = {}
        if uniprot:
            args["uniprot_ac"] = uniprot
        if gene:
            args["gene"] = gene
        if tool_name == "inuloc_nuclear_prob":
            args["organism"] = organism if organism in ("human", "mouse", "rat", "yeast") else "human"
        return args

    if tool_name == "compartments_localization":
        if not (gene or uniprot):
            return {}
        args: dict[str, Any] = {"min_confidence": 3.0}
        if uniprot:
            args["uniprot_ac"] = uniprot
        if gene:
            args["gene"] = gene
        return args

    if tool_name == "subcell_scsi":
        if not (gene or uniprot):
            return {}
        args = {"organism": organism or "human", "include_locations": True}
        if gene:
            args["gene"] = gene
        if uniprot:
            args["uniprot_ac"] = uniprot
        return args

    if tool_name == "funcscore_phosphosite":
        if not uniprot:
            return {}
        args: dict[str, Any] = {"uniprot_ac": uniprot}
        if position:
            args["site_position"] = position
        return args

    if tool_name == "pubtator_literature_search":
        return {
            "query": _build_pubtator_query(entities, query or ""),
            "limit": 8,
        }

    return {"query": query}
