# qPTM integrated databases — when to use what

## Core quantitative (experimental)
- **qPTM** (`qptm_search`, `qptm_site_conditions`, `qptm_kinases`): primary quantitative PTM events and site-level fold-changes.
- **eKPI**: quantitative kinase–substrate correlations.

## Curated regulators (WHO)
- **PhosphoSitePlus**: curated kinase–substrate, regulatory sites, disease sites, PTMVar.
- **iPTMnet**: enzyme–substrate and PTM-dependent PPI.
- **GPS 6.0**: **predicted** kinase-specific sites (not experimental).
- **GPS-Uber / GPS-SUMO**: predicted E3 / SUMO sites.
- **WERAM / UbiBrowser**: histone acetylation / ubiquitin system.

## Function & disease (WHY)
- **Funcscore**: phosphosite functional priority scores.
- **PTM-stability**: PTM effects on protein stability.
- **PTMD / CancerProteome / ActiveDriverDB**: disease-associated PTMs and mutations.
- **PTMcode2 / PTMint**: PTM crosstalk and PTM-regulated PPI.

## Context (WHERE)
- **COMPARTMENTS / iNuLoC / InterPro**: localization, motifs, domains.
- **PTMPhaSe / dSCOPE**: phase separation (LLPS).

## Pathways & PPI
- **Reactome / KEGG / PathBank**: pathways.
- **STRING / BioGRID / IntAct**: PPI networks.

## Literature
- **PubTator3 / PubMed** via BioMCP `search article` / `get article`.

## Rules
- Prefer qPTM for **quantitative** human PTM when available.
- Use GPS only with "predicted" label.
- Empty DB result → state limitation; do not fabricate.
