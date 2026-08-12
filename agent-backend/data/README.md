# qPTM Agent — local PTM datasets & external source pipeline

Datasets are organized by **PTM research aspect** (研究维度), not by database
name. Each source folder MAY contain a `SOURCE.yaml` manifest consumed by
`app.sources` for tool routing, citations, and LLM context.

## Access policy

| Situation | What to do |
|-----------|------------|
| Database has a stable public API | Call API from `app/tools/*`; optional local cache under the aspect folder |
| No API / API retiring / bulk tables | Manually download tables into `data/<aspect>/<SourceName>/` and add `SOURCE.yaml` |
| Large TSV/CSV (>50k rows) | Do **not** rewrite raw files; build SQLite indexes via `python -m app.sources.build_index <id>` |

## Layout

```
data/
├── enzymes/                     # Stage 1 — WHO (writers/erasers)
│   ├── PhosphoSitePlus/         # Kinase_Substrate_Dataset (PMID 30445427)
│   ├── iPTMnet/                 # API — enzyme–substrate + PTM-PPI (PMID 29145615)
│   ├── WERAM/                   # histone Ac/Me writers/erasers/readers (PMID 27789692)
│   ├── UbiBrowser/              # E3/DUB–substrate ESI/DSI (PMID 34634807)
│   ├── GPS-Uber/                # site-specific E3–substrate ssESRs (PMID 35037020)
│   ├── GPS6.0/                  # predicted kinase-specific p-sites (PMID 37158278)
│   ├── GPS-SUMO2/               # curated SUMOylation sites / SIMs (PMID 38709873)
│   ├── KAKA/                    # kinase activity key alterations (PMID 41839313)
│   └── eKPI/                    # quantitative KPS correlations (PMID 40194556)
├── regulation/
│   ├── PhosphoSitePlus/         # Regulatory_sites + PTMVar (PMID 30445427)
│   └── Funcscore/               # phosphosite functional scores (PMID 31819260)
├── interactions/
│   ├── PTMint/                  # PTM–PPI regulation (PMID 36548389)
│   ├── PTMcode2/                # PTM–PTM associations (PMID 25361965; curated subset)
│   ├── STRING/                  # API — association networks (PMID 39558183)
│   ├── BioGRID/                 # API — curated interactions (PMID 33070389; needs key)
│   └── IntAct/                  # API — IMEx/PSICQUIC (PMID 34761267)
├── pathways/                    # Stage 3–4 — 信号 / 代谢通路
│   ├── Reactome/                # API (PMID 29145629)
│   ├── KEGG/                    # API (PMID 30321428)
│   └── PathBank/                # local SMPDB family index (PMID 31602469)
├── domains/                     # Stage 3 — 蛋白结构域 / 家族
│   ├── InterPro/                # API — families & domains (PMID 30398656)
│   └── Pfam/                    # API via InterPro (PMID 30357350)
├── stability/
│   └── curated/                 # PTM-stability (primary PMIDs; from PMC9839724)
├── phase_separation/
│   ├── ptmphase/                # PTMPhaSe + PhosLLPS (PMID 41360972)
│   └── dscope/                  # optional related LLPS datasets
├── disease/                     # Stage 4 — 疾病 / 突变–PTM
│   ├── ActiveDriverDB/
│   ├── PTMD/                    # disease-associated PTMs (PMID 39329270)
│   ├── CancerProteome/          # cancer vs normal PTM/protein (PMID 37823596)
│   ├── PhosphositePlus/         # Disease-associated_sites (PMID 30445427)
│   └── dbptm/
├── drug/                        # Stage 1 — 药物–PTM 上游调控 (WHO)
│   ├── PMADS/
│   ├── DrugBank/                # drug–target (PMID 37953279)
│   └── decryptM/                # dose-response PTM (PMID 36926954; API)
├── localization/                # Stage 3 — WHERE
│   ├── NLSdb/                   # NLS/NES motifs (PMID 29106588)
│   ├── COMPARTMENTS/            # subcellular localization (PMID 24573882)
│   ├── SubCELL/                 # compartment-specific PPIs (PMID 39373488)
│   └── iNuLoC/                  # DNL + nuclear prob (PMID 40087285)
```

Runtime state (conversations, collection jobs, eval) lives under
`agent-backend/runtime/`, not under `data/`.


## ActiveDriverDB (`disease/ActiveDriverDB`)

Integrates PTM sites with germline/somatic mutations and PTM signalling
context ([activedriverdb.org](https://activedriverdb.org)). REST API docs:
[activedriverdb.org/api/](https://activedriverdb.org/api/). The public service
is scheduled for retirement (2026-05-01); **local tables are the primary
backend**.

### Local tables

```
ActiveDriverDB/
├── SOURCE.yaml
├── mutations/{clinvar,mc3,pcawg,population}.tsv
├── network/kinase_target_sites.tsv
└── indexes/*.sqlite
```

### Agent tools

- `activedriver_mutations` — ClinVar / MC3 / PCAWG / population hits near PTM sites
- `activedriver_kinase_network` — site-specific kinase→target edges

```bash
.venv/bin/python -m app.sources.build_index activedriverdb
```

## PMADS (`drug/PMADS`)

[PMADS](https://pmads-db.org) catalogues curated (~4.8k) and inferred (~43.9k)
drug–PTM–disease associations across >6000 proteins, ~1000 drugs, 19 PTM types,
and ~300 disease classes. Emphasis: drug-induced PTM changes (upstream) and
PTM-mediated drug sensitivity (downstream).

- **PMID**: 41099621  
- **DOI**: [10.1093/nar/gkaf1033](https://doi.org/10.1093/nar/gkaf1033)  
- Access: **local only** (workbook uploaded by curator)

### Local layout

```
PMADS/
├── SOURCE.yaml
├── tables/associations.tsv     # normalized working table
└── indexes/associations.sqlite
```

### Agent tool

- `pmads_drug_ptm` — query by gene / UniProt / drug / disease (default status=Curated)

```bash
.venv/bin/python -m app.sources.build_index pmads
```

## DrugBank (`drug/DrugBank`)

[DrugBank 6.0](https://go.drugbank.com) drug–target associations for proteins in
the qPTM ecosystem: DrugBank ID, drug name/type, approval groups, known
pharmacological action, and literature PMIDs. Complements PMADS/decryptM
(site-level PTM regulation) with protein-level drug targeting.

- **PMID**: 37953279  
- **DOI**: [10.1093/nar/gkad976](https://doi.org/10.1093/nar/gkad976)  
- Access: **local only**

### Local layout

```
DrugBank/
├── SOURCE.yaml
├── DrugBank.txt                 # provenance upload
├── tables/targets.tsv           # working table (~21k; no PTMD id)
└── indexes/targets.sqlite
```

### Agent tool

- `drugbank_targets` — query by gene / UniProt / drug name / DrugBank ID

```bash
.venv/bin/python -m app.sources.build_index drugbank
```

## decryptM (`drug/decryptM`)

[decryptM](https://www.proteomicsdb.org/decryptm) (Zecha et al., *Science* 2023)
quantifies drug–PTM modulation with dose-/time-resolved proteomics: 31 cancer
drugs × 13 cell lines → ~1.8M dose-response curves (phospho / ubiquitin /
acetyl). Hosted in [ProteomicsDB](https://www.proteomicsdb.org/api).

- **PMID**: 36926954  
- **DOI**: [10.1126/science.ade3925](https://doi.org/10.1126/science.ade3925)  
- Access: **hybrid** — local `tables/curves.tsv` (~1.3M rows) + ProteomicsDB API

### Local layout

```
decryptM/
├── SOURCE.yaml
├── tables/curves.tsv
└── indexes/curves.sqlite
```

### Agent tool

- `decryptm_drug_ptm` — local index first, API supplements aggregated dose-response curves

```bash
.venv/bin/python -m app.sources.build_index decryptm
```

## PTMPhaSe (`phase_separation/ptmphase`)

[PTMPhaSe](https://ptmphase.sjtu.edu.cn) is a curated database of PTM regulation
on liquid–liquid phase separation (LLPS), plus the PhosLLPS predictor for
functional phosphorylation sites regulating LLPS (AUC = 0.9116).

- **PMID**: 41360972  
- **DOI**: [10.1038/s42004-025-01773-y](https://doi.org/10.1038/s42004-025-01773-y)  
- Predictor: [ptmphase.sjtu.edu.cn/Predictor](https://ptmphase.sjtu.edu.cn/Predictor)  
- Access: **local** tables

### Local layout

```
ptmphase/
├── SOURCE.yaml
├── tables/
│   ├── experimental_evidence.tsv   # curated (~855)
│   └── predictions.tsv             # PhosLLPS proteome-scale (~457k)
└── indexes/{experimental,predictions}.sqlite
```

### Agent tools

- `ptmphase_llps` — curated experimental promotion/inhibition of LLPS
- `ptmphase_phosllps` — PhosLLPS predicted functional phospho-sites

```bash
.venv/bin/python -m app.sources.build_index ptmphase
```

## dSCOPE (`phase_separation/dscope`)

[dSCOPE](https://dscope.omicsbio.info) predicts protein sequence segments critical
for liquid–liquid phase separation (LLPS). The training set comprises
experimentally identified LLPS-driving regions curated from published literature;
the human proteome file annotates predicted PS-driving regions with probability
scores.

- **PMID**: 36528388  
- **DOI**: [10.1093/bib/bbac550](https://doi.org/10.1093/bib/bbac550)  
- Access: **local** tables

### Local layout

```
dscope/
├── SOURCE.yaml
├── dscope_data.txt          # literature-curated LLPS-driving segments (~121)
├── dscope.proinfo.xls       # human proteome predictions (~20k proteins)
└── indexes/{literature,predictions}.sqlite
```

### Agent tools

- `dscope_literature` — experimentally identified LLPS-driving segments
- `dscope_predictions` — predicted PS-driving regions (Regions + AverageScores)

```bash
.venv/bin/python -m app.sources.build_index dscope
```

## PTMD (`disease/PTMD`)

[PTMD 2.0](https://ptmd.biocuckoo.cn/) catalogues disease-associated PTMs with
342,624 PTM–disease associations (PDAs) across 93 PTM types and 2,083 diseases.
Each PDA is labeled with one of six states: **U/D** (up/down PTM level),
**A/P** (absence/presence), **C/N** (creation/disruption of PTM sites).

- **PMID**: 39329270  
- **DOI**: [10.1093/nar/gkae850](https://doi.org/10.1093/nar/gkae850)  
- Access: **local** tables

### Local layout

```
PTMD/
├── SOURCE.yaml
├── tables/
│   ├── pda_literature.tsv   # curated with PMIDs (~6.7k)
│   └── pda_public.tsv       # integrated public PDAs (~343k)
└── indexes/{literature,public}.sqlite
```

### Agent tool

- `ptmd_disease` — query by gene / UniProt / disease / site / state  
  (distinct from `dbptm_functional`)

```bash
.venv/bin/python -m app.sources.build_index ptmd
```

## CancerProteome (`disease/CancerProteome`)

[CancerProteome](http://bio-bigdata.hrbmu.edu.cn/CancerProteome) functionally
deciphers the cancer proteome landscape: curated / re-analyzed MS quantification
and PTM proteomes across 21 cancer types (tumor vs control).

- **PMID**: 37823596  
- **DOI**: [10.1093/nar/gkad824](https://doi.org/10.1093/nar/gkad824)  
- Access: **local** tables

### Local layout

```
CancerProteome/
├── SOURCE.yaml
├── Cancer-abbreviation.txt   # LUNG → Lung Cancer, …
├── ptm_info.csv              # tumor/control PTM site qratio + FDR
├── protein_inf.txt           # tumor/control protein FC + FDR
└── indexes/{ptm,protein}.sqlite
```

Note: `ptm_info.csv` column `pmid` stores Proteomic Data Commons (PDC) dataset
IDs (e.g. `PDC000232`), not PubMed IDs — cite paper PMID 37823596 for the resource.

### Agent tool

- `cancerproteome_disease` — query by gene / UniProt / site / cancer
  (returns PTM hits + protein abundance; Stage 2 WHEN + Stage 4 WHY)

```bash
.venv/bin/python -m app.sources.build_index cancerproteome
```

## PhosphoSitePlus (split by aspect)

[PhosphoSitePlus](https://www.phosphosite.org) provides curated mammalian PTM
annotations. Local dumps are split by research aspect (not kept as one folder):

| Aspect path | File | Agent tool | Stage |
|-------------|------|------------|-------|
| `enzymes/PhosphoSitePlus/` | `Kinase_Substrate_Dataset` | `psp_kinase_substrate` | WHO |
| `regulation/PhosphoSitePlus/` | `Regulatory_sites` | `psp_regulatory` | WHY |
| `regulation/PhosphoSitePlus/` | `PTMVar.xlsx` | `psp_ptmvar` | WHY |
| `disease/PhosphositePlus/` | `Disease-associated_sites` | `psp_disease_sites` | WHY |

- **PMID**: 30445427  
- **DOI**: [10.1093/nar/gky1159](https://doi.org/10.1093/nar/gky1159)

```bash
.venv/bin/python -m app.sources.build_index psp_enzymes
.venv/bin/python -m app.sources.build_index psp_regulation
.venv/bin/python -m app.sources.build_index psp_disease
```

## PTMint (`interactions/PTMint`)

[PTMint](https://ptmint.sjtu.edu.cn/) catalogues manually curated experimental
evidence that PTMs enhance or inhibit protein–protein interactions across
multiple organisms (~2477 non-redundant sites, 2371 PPI pairs, 357 diseases).

- **PMID**: 36548389  
- **DOI**: [10.1093/bioinformatics/btac823](https://doi.org/10.1093/bioinformatics/btac823)  
- Access: **local** table

### Local layout

```
PTMint/
├── SOURCE.yaml
├── tables/experimental_evidence.tsv
└── indexes/experimental.sqlite
```

### Agent tool

- `ptmint_ppi` — PTM→PPI Enhance/Inhibit (distinct from `iptmnet_ptm_ppi`)

```bash
.venv/bin/python -m app.sources.build_index ptmint
```

## PTMcode2 (`interactions/PTMcode2`)

[PTMcode v2](http://ptmcode.embl.de) predicts functional associations of PTM
pairs **within** proteins and **between** interacting proteins.

- **PMID**: 25361965  
- **DOI**: [10.1093/nar/gku1081](https://doi.org/10.1093/nar/gku1081)

Raw dumps are huge (~35M rows, multi-species, mostly coevolution). For the agent
we keep a **curated subset** for qPTM organisms only:

| Keep | Drop |
|------|------|
| human, mouse, rat, yeast | other species |
| manual / structure / same-residue competition evidence | coevolution-only |
| undirected unique pairs | A↔B duplicates |

```
PTMcode2/
├── SOURCE.yaml
├── PTMcode2_associations_*.txt.gz   # raw provenance (~112MB)
├── tables/
│   ├── within.tsv                   # intra-protein pairs (4 species)
│   └── between.tsv                  # inter-protein pairs (4 species)
└── indexes/{within,between}.sqlite
```

### Agent tool

- `ptmcode_associations` — query by gene (± site, partner); Stage 4 WHY

```bash
.venv/bin/python -m app.sources.prepare_ptmcode2   # rebuild tables from gz
.venv/bin/python -m app.sources.build_index ptmcode2
```

## iPTMnet (API — enzyme–substrate + PTM-dependent PPI)

[iPTMnet](https://research.bioinformatics.udel.edu/iptmnet/) integrates PTM
networks across databases and text mining ([API docs](https://research.bioinformatics.udel.edu/iptmnet/about/api);
[Swagger](https://research.bioinformatics.udel.edu/iptmnet/api/doc/)).

| Tool | Endpoint | Stage |
|------|----------|-------|
| `iptmnet_enzymes` | `GET /v1/{id}/substrate` | WHO |
| `iptmnet_ptm_ppi` | `GET /v1/{id}/ptmppi` | WHY |

Citation: Huang et al. *NAR* 2018 — PMID **29145615** / DOI `10.1093/nar/gkx1104`.

```bash
# optional override
IPTMNET_API_BASE_URL=https://research.bioinformatics.udel.edu/iptmnet/api
```

Manifest: `data/enzymes/iPTMnet/SOURCE.yaml` (`access: api`).

## WERAM (local — histone Ac/Me writers / erasers / readers)

[WERAM](http://weram.biocuckoo.org) catalogues eukaryotic writers, erasers and
readers of histone acetylation and methylation (Xu et al. *NAR* 2017 —
PMID **27789692** / DOI `10.1093/nar/gkw1011`).

Local human subset built from WERAM FASTA downloads (collected + predicted;
acetylation + methylation). ENSP IDs mapped to UniProt/gene.

| Family | Role | Modification |
|--------|------|--------------|
| HAT | writer | acetylation |
| HDAC | eraser | acetylation |
| Ac_Reader | reader | acetylation |
| HMT | writer | methylation |
| HDM | eraser | methylation |
| Me_Reader | reader | methylation |

```
enzymes/WERAM/
├── SOURCE.yaml
├── raw/*.fasta
├── tables/proteins.tsv
└── indexes/proteins.sqlite
```

### Agent tool

- `weram_regulators` — query by gene / UniProt / role / modification / family (Stage 1 WHO)

```bash
.venv/bin/python -m app.sources.build_index weram
```

## UbiBrowser (hybrid — E3 / DUB–substrate interactions)

[UbiBrowser 2.0](http://ubibrowser.bio-it.cn/ubibrowser_v3/home/index) catalogues
proteome-wide known and predicted ubiquitin ligase (E3) and deubiquitinase
(DUB)–substrate interactions (Wang et al. *NAR* 2022 — PMID **34634807** /
DOI `10.1093/nar/gkab962`).

| Layer | Content | Access |
|-------|---------|--------|
| Literature | 4068 ESIs + 967 DSIs (manual curation) | local `tables/interactions.tsv` |
| Predicted | high-confidence proteome-wide ESIs/DSIs | on-demand `downloadData` by UniProt AC |

```
enzymes/UbiBrowser/
├── SOURCE.yaml
├── raw/literature.{E3,DUB}.txt
├── tables/interactions.tsv
└── indexes/interactions.sqlite
```

### Agent tool

- `ubibrowser_interactions` — gene / UniProt; optional E3|DUB filter; known + predicted (Stage 1 WHO)

```bash
.venv/bin/python -m app.sources.build_index ubibrowser
```

## GPS-Uber (local — site-specific E3–substrate ssESRs)

[GPS-Uber](http://gpsuber.biocuckoo.cn/) provides general and E3-specific
lysine ubiquitination site prediction (Wang et al. *Brief Bioinform* 2022 —
PMID **35037020** / DOI `10.1093/bib/bbab574`).

Agent indexes the curated benchmark **Supplementary Table S1**: 1,311
experimentally identified site-specific E3–substrate relations (ssESRs)
between 1,117 human ubiquitination sites (391 proteins) and 177 E3s.

| Field | Meaning |
|-------|---------|
| substrate gene / UniProt / position | Modified lysine site |
| peptide | ±10 aa flank |
| E3 gene / UniProt / class | Writer E3 and family |
| PMIDs | Supporting literature |

```
enzymes/GPS-Uber/
├── SOURCE.yaml
├── table_s1-r1_bbab574.xlsx
├── tables/ssesr.tsv
└── indexes/ssesr.sqlite
```

### Agent tool

- `gpsuber_e3_sites` — query by substrate (± site) or E3 (Stage 1 WHO)

Complements **UbiBrowser** (protein-level ESI/DSI) with **lysine-site** E3 links.

```bash
.venv/bin/python -m app.sources.build_index gpsuber
```

## GPS 6.0 (local — predicted kinase-specific p-sites)

[GPS 6.0](https://gps.biocuckoo.cn) predicts kinase-specific phosphorylation
sites (Chen et al. *NAR* 2023 — PMID **37158278** / DOI `10.1093/nar/gkad383`).

Local dump `GPS_Human.csv` contains human substrate sites with pipe-separated
predicted kinases and GPS scores, expanded to one kinase–site row per prediction.

| Field | Meaning |
|-------|---------|
| gene / UniProt / position / residue | Substrate p-site |
| kinase_gene / group / family / hierarchy | Predicted kinase |
| score | GPS confidence score (higher = stronger) |

```
enzymes/GPS6.0/
├── SOURCE.yaml
├── GPS_Human.csv
├── tables/predictions.tsv
└── indexes/predictions.sqlite
```

### Agent tool

- `gps6_kinases` — query by substrate (± site) or kinase (± min_score); Stage 1 WHO (**predicted**)

Complement curated kinase sources (PSP / qPTM / iPTMnet) with GPS predictions.

```bash
.venv/bin/python -m app.sources.build_index gps6
```

## GPS-SUMO 2.0 (local — curated SUMOylation sites / SIMs)

[GPS-SUMO 2.0](https://sumo.biocuckoo.cn/) predicts SUMOylation sites and
SUMO-interacting motifs (Wang et al. *NAR* 2024 — PMID **38709873** /
DOI `10.1093/nar/gkae346`).

Agent indexes the **curated experimental training/test sets** (Supplementary
Table S2), not predictor scores — real literature/database-backed sites used
to train the model:

| Sheet | Content | Agent table |
|-------|---------|-------------|
| S2A + S2B | SUMOylation sites (train + independent test) | `sumoylation_sites.tsv` |
| S2C | SUMO-interacting motifs (SIMs) | `sims.tsv` |

Kept organisms: human / mouse / rat / yeast.

| Field | Meaning |
|-------|---------|
| UniProt / position / peptide | Modified lysine (sites) or SIM span |
| source_dbs / pmids | Upstream resource + literature |
| dataset_split | `train` or `test` (sites only) |

```
enzymes/GPS-SUMO2/
├── SOURCE.yaml
├── GPS-SUMO2.xlsx
├── tables/{sumoylation_sites,sims}.tsv
└── indexes/{sumoylation_sites,sims}.sqlite
```

### Agent tool

- `gpssumo2_sites` — query by substrate gene/UniProt (± lysine site); returns
  curated SUMOylation sites and SIMs (Stage 1 WHO, **curated experimental**)

```bash
.venv/bin/python -m app.sources.prepare_gpssumo2
.venv/bin/python -m app.sources.build_index gpssumo2
```

## KAKA (local — kinase activity–related key alterations)

[KAKA](https://kaka.omicsbio.info/) curates experimentally validated kinase
activity–related key alterations (KAKAs) from the literature — mutations
classified as **increase**, **decrease**, **kinase-dead**, or **no-effect**
(PMID **41839313** / DOI `10.1016/j.jgg.2026.03.010`).

Dataset: 2553 curated rows across 421 proteins in 8 species
(human, mouse, rat, yeast, fission yeast, arabidopsis, fly, worm).

| Field | Meaning |
|-------|---------|
| gene / uniprot / mutation | Kinase identity and missense allele |
| enzyme_activity | increase / decrease / kinase-dead / no effect |
| organism / species | Short name + binomial |
| pmids / description | Supporting literature + excerpt |

```
enzymes/KAKA/
├── SOURCE.yaml
├── qevent.xlsx
├── tables/events.tsv
└── indexes/events.sqlite
```

### Agent tool

- `kaka_kinase_mutations` — query by kinase gene/UniProt (± mutation / position /
  activity class); Stage 1 WHO + mutation-precision (**curated experimental**)

```bash
.venv/bin/python -m app.sources.prepare_kaka
.venv/bin/python -m app.sources.build_index kaka
```

## eKPI (hybrid — Quantitative kinase–phosphosite correlations)

[eKPI](https://ekpi.omicsbio.info/) integrates cancer multi-omics Spearman
correlations between kinase abundance (mRNA / protein / kinase phosphosites)
and substrate phosphosite levels across 23 tumor + 15 adjacent-normal datasets
(Brief Bioinform 2025 — PMID **40194556** / DOI `10.1093/bib/bbaf143`).

Agent indexes the **phosphosite lookup table** (~197k sites) and reads
**Quantitative** matrices on demand from the local eKPI `final_result/` tree
(per-site `*.csv.gz`; ~78 GB — not copied into `data/`).

| Field | Meaning |
|-------|---------|
| kinase_gene / kinase_feature | Kinase identity; `Pro` / `mRNA` / `pS##` |
| rho / pvalue / n | Spearman correlation, p-value, sample size |
| cohort | `cancer Tumor` or `cancer Normal` |
| pmid | Source multi-omics dataset |

```
enzymes/eKPI/
├── SOURCE.yaml
├── ekpi_all_phosphosite.txt     # provenance copy
├── tables/sites.tsv             # lookup → file_key
└── indexes/sites.sqlite

# External (configure via env):
EKPI_FINAL_RESULT_DIR=/var/www/html/ekpi/final_result
```

### Agent tools

- `ekpi_kinases` — experimental literature KPIs (with PMIDs) + 7-tool predictions
  (+ optional best quantitative hit). Preferred Stage 1 WHO tool
- `ekpi_quantitative` — detailed Spearman correlations (default: tumor, p ≤ 0.05).
  Stage 1 WHO / Stage 2 WHEN (**quantitative correlation** evidence)

```bash
.venv/bin/python -m app.sources.prepare_ekpi
.venv/bin/python -m app.sources.build_index ekpi
```

## InterPro / Pfam (API — protein domains & families)

Protein architecture for Stage 3 WHERE (place a PTM site in domain context).
Both tools call the [InterPro REST API](https://www.ebi.ac.uk/interpro/api/);
Pfam no longer has a standalone public API ([Pfam docs](https://pfam-docs.readthedocs.io/en/latest/api.html)).

| Source | Tool | Endpoint | PMID / DOI |
|--------|------|----------|------------|
| [InterPro](https://www.ebi.ac.uk/interpro/) | `interpro_domains` | `GET /entry/interpro/protein/uniprot/{ac}` + entry detail | 30398656 / 10.1093/nar/gky1100 |
| [Pfam](https://www.ebi.ac.uk/interpro/entry/pfam/) | `pfam_domains` | `GET /entry/pfam/protein/uniprot/{ac}` + entry detail | 30357350 / 10.1093/nar/gky995 |

Both tools enrich top hits with **name, residue span, functional description, GO, literature** (not ID-only).

```bash
INTERPRO_API_BASE_URL=https://www.ebi.ac.uk/interpro/api
```

Manifests: `data/domains/{InterPro,Pfam}/SOURCE.yaml`.

## STRING / BioGRID / IntAct (API — general PPI)

Complement PTMint / iPTMnet (PTM-site–specific PPI) with general protein interaction
APIs for Stage 4 WHY when users ask about binding partners / complexes.

| Source | Tool | Auth | PMID / DOI |
|--------|------|------|------------|
| [STRING](https://string-db.org) | `string_ppi` | none (uses `cn.string-db.org` mirror) | 39558183 / 10.1093/nar/gkae1113 |
| [BioGRID](https://thebiogrid.org) | `biogrid_interactions` | **BIOGRID_ACCESS_KEY** (free) | 33070389 / 10.1002/pro.3978 |
| [IntAct](https://www.ebi.ac.uk/intact) | `intact_interactions` | none (PSICQUIC) | 34761267 / 10.1093/nar/gkab1006 |

```bash
# BioGRID only — register at https://webservice.thebiogrid.org/
# then add to .env:
BIOGRID_ACCESS_KEY=your_32_char_key
```

Manifests live under `data/interactions/{STRING,BioGRID,IntAct}/SOURCE.yaml`
(`access: api`, no local tables).

## Reactome / KEGG / PathBank (`pathways/`)

Protein pathway membership for Stage 3–4 (signaling / metabolism context).

| Source | Tool | Access | PMID / DOI |
|--------|------|--------|------------|
| [Reactome](https://reactome.org) | `reactome_pathways` | Content Service API | 29145629 / 10.1093/nar/gkx1132 |
| [KEGG](https://www.kegg.jp) | `kegg_pathways` | REST API (academic ≤3/s) | 30321428 / 10.1093/nar/gky962 |
| [PathBank](https://pathbank.org) | `pathbank_pathways` | **local** SMPDB protein–pathway index | 31602469 / 10.1093/nar/gkz861 |

Top hits are enriched with **readable names + short descriptions** (Reactome summation /
KEGG DESCRIPTION+CLASS; PathBank uses subject + protein name — no remote abstract).

PathBank.org has **no public REST API** (and downloads are often Cloudflare-blocked).
The agent indexes Wishart-lab [SMPDB protein CSVs](https://smpdb.ca/downloads/smpdb_proteins.csv.zip)
(~304k human protein–pathway rows) under `pathways/PathBank/`.

```bash
.venv/bin/python -m app.sources.prepare_pathbank   # download+consolidate (or --zip local)
.venv/bin/python -m app.sources.build_index pathbank
```

## Funcscore (`regulation/Funcscore`)

From [Ochoa et al., *Nat Biotechnol*](https://www.nature.com/articles/s41587-019-0344-3)
—*The functional landscape of the human phosphoproteome*. Supplementary
functional scores prioritize human phosphosites using 59 ML features
(proteomic, structural, regulatory, evolutionary).

- **PMID**: 31819260  
- **DOI**: [10.1038/s41587-019-0344-3](https://doi.org/10.1038/s41587-019-0344-3)

| File | Meaning | Rows |
|------|---------|------|
| `functional_score.tsv` | `uniprot`, `position`, `functional_score` (0–1) | ~116k |

### Agent tool

- `funcscore_phosphosite` — look up score by UniProt (± site, min_score, top_n)

```bash
.venv/bin/python -m app.sources.build_index funcscore
```

## NLSdb (`localization/NLSdb`)

[NLSdb](https://rostlab.org/services/nlsdb/) collects nuclear localization
signals (NLS) and nuclear export signals (NES), including experimentally
annotated motifs and in silico mutagenesis–expanded sets. Tables were
extracted from the iNuLoC download bundle (which integrates NLSdb among
other resources).

- **PMID**: 29106588  
- **DOI**: [10.1093/nar/gkx1021](https://doi.org/10.1093/nar/gkx1021)

| File | Meaning | Rows |
|------|---------|------|
| `motifs_experimental.tsv` | 实验验证 NLS/NES | ~826 |
| `motifs_predicted.tsv` | 预测 NLS/NES motifs (in silico) | ~4.5k |

### Agent tool (motifs portion)

- `inuloc_nls_nes` — queries NLSdb for NLS/NES; also queries iNuLoC DNL

```bash
.venv/bin/python -m app.sources.build_index nlsdb
```

## COMPARTMENTS (`localization/COMPARTMENTS`)

[COMPARTMENTS](https://compartments.jensenlab.org/) integrates subcellular
localization evidence from curated literature, high-throughput screens, text
mining, and sequence-based predictors, mapped to UniProt/GO with confidence
scores (≈0–5).

- **PMID**: 24573882  
- **DOI**: [10.1093/database/bau012](https://doi.org/10.1093/database/bau012)

| File | Meaning | Rows |
|------|---------|------|
| `localizations.tsv` | uniprot, ensp, gene, go, localization, confidence | ~3.5M |

### Agent tool

- `compartments_localization` — by gene/UniProt (± localization filter, min_confidence)

```bash
.venv/bin/python -m app.sources.build_index compartments
```

## SubCELL (`localization/SubCELL`)

[SubCELL](https://subcell.idrblab.cn/) maps **subcellular compartment-specific
molecular interactions (SCSIs)** — where a protein interacts — plus location
annotations (Zhang et al., NAR 2025).

- **PMID**: 39373488  
- **DOI**: [10.1093/nar/gkae863](https://doi.org/10.1093/nar/gkae863)  
- Access: **local** (official full-data download; no public query API)

Kept for qPTM organisms (human/mouse/rat/yeast): ~201k protein–protein SCSIs,
~49k protein locations.

```
SubCELL/
├── SOURCE.yaml
├── raw/                 # official *.txt downloads
├── tables/{proteins,interactions,locations,compartments}.tsv
└── indexes/*.sqlite
```

### Agent tool

- `subcell_scsi` — gene/UniProt → compartment-resolved PPIs (+ locations)

```bash
.venv/bin/python -m app.sources.prepare_subcell
.venv/bin/python -m app.sources.build_index subcell
```

## iNuLoC (`localization/iNuLoC`)

[iNuLoC](http://inuloc.omicsbio.info/) provides DNL regions and proteome-scale
nuclear localization probabilities (iNuLoC-native data; NLS/NES motifs are
attributed to NLSdb above).

- **PMID**: 40087285  
- **DOI**: [10.1038/s41467-025-57858-8](https://doi.org/10.1038/s41467-025-57858-8)

| File | Meaning | Rows |
|------|---------|------|
| `dnl.tsv` | 核定位序列决定区 (DNL) | ~16k |
| `nuclear_prob.tsv` | 五物种核定位概率 | ~55k |

SAM (shuttling-attacking mutation) tables were **omitted** (not PTM-centric).

### Agent tools

- `inuloc_nls_nes` (DNL portion) / `inuloc_nuclear_prob`

```bash
.venv/bin/python -m app.sources.build_index inuloc
```

## Pipeline: add a new external database

1. **Choose aspect** under `data/` matching the biological question
   (`disease/`, `drug/`, `regulation/`, …).
2. **Create** `data/<aspect>/<SourceName>/`.
3. **Drop files** (API-only sources may be empty aside from `SOURCE.yaml`).
4. **Write** `SOURCE.yaml` (copy ActiveDriverDB or PMADS as a template):
   - `id`, `name`, `aspect`, `access` (`api` | `local` | `hybrid`)
   - `homepage` / `api_base` / `api_docs` / `citation` / `doi` / `pmid`
   - `tools: [tool_name_...]`
   - `files: [{id, path, columns, index_keys, ...}]` for local tables
5. **Index** large tables: `python -m app.sources.build_index <id>`
6. **Implement** `app/tools/<name>_tools.py` using `app.sources.query`
7. **Register** tool in `main.py`, route in `planner.py`, cite in `citations.py`
8. Restart the agent backend

Catalog introspection:

```bash
.venv/bin/python -c "from app.sources import get_catalog; print(get_catalog().llm_catalog_text())"
```

## Aspect ↔ workflow

| Aspect | Stage | Sources | Access |
|--------|-------|---------|--------|
| enzymes / drug | WHO (kinase) | qPTM, **iPTMnet** (API), **PSP kinases**, **GPS 6.0** (predicted), **eKPI** (quantitative KPS correlations), **WERAM**, **UbiBrowser**, **GPS-Uber**, **GPS-SUMO 2.0** (curated SUMO/SIM), **KAKA** (mutation→kinase activity), ActiveDriverDB, **PMADS**, **DrugBank**, decryptM | API / local |
| quantification (no local dir) | WHEN (conditions) | qPTM (API); **CancerProteome** under `disease/` | API / local |
| localization | WHERE | **COMPARTMENTS**, **SubCELL**, NLSdb, **iNuLoC**, UniProt | local / API |
| domains | WHERE (architecture) | **InterPro**, **Pfam** | API |
| regulation | WHY (function) | **PhosphoSitePlus** regulatory/PTMVar, Funcscore | local |
| interactions | WHY (function) | **PTMint**, **PTMcode2**, **STRING**, **BioGRID**, **IntAct**, iPTMnet PPI | local / API |
| pathways | WHERE / WHY | **Reactome**, **KEGG**, **PathBank** | API / local |
| stability | WHY (function) | curated (primary PMIDs; from PMC9839724) | local |
| phase_separation | WHY (function) | **PTMPhaSe** / PhosLLPS, **dSCOPE** | local |
| disease | WHY (function) | ActiveDriverDB, **PTMD**, **CancerProteome** (also WHEN), **PSP disease**, dbPTM | local (+ API) |

## Answer provenance

Every successful tool call is wrapped by `attach_citations()` → `ToolResult`.
Each citation carries an **evidence level**:

| Level | Meaning |
|-------|---------|
| `experimental` | 实验验证（MS / assay / literature-backed experiment） |
| `curated` | 文献策展 / 人工整理（非计算预测） |
| `curated` | 数据库/文献精炼（如 PSP、iPTMnet、**GPS-SUMO 2.0 训练/测试集**） |
| `predicted` | 计算预测（如 GPS 6.0、PhosLLPS、部分 UbiBrowser/NLSdb） |
| `unknown` | 工具未标注 |

Synthesis must:

1. Inline-cite facts with `[Sx]`
2. **Name the database/tool and the evidence level** (never present predicted as experimental)
3. End with **## Sources** containing the **Retrieval Summary Table**
   (database, tool, **Evidence**, record counts, URLs) generated by the backend

## Config keys

See `.env.example`. Notable:

- `ACTIVEDRIVER_DATA_DIR` → `data/disease/ActiveDriverDB`
- `ACTIVEDRIVER_API_BASE_URL` → `https://activedriverdb.org`
- `PMADS_DATA_DIR` → `data/drug/PMADS`
- `DRUGBANK_DATA_DIR` → `data/drug/DrugBank`
- `DECRYPTM_DATA_DIR` → `data/drug/decryptM`
- `PROTEOMICSDB_API_BASE_URL` → `https://www.proteomicsdb.org`
- `PTMPHASE_DATA_DIR` → `data/phase_separation/ptmphase`
- `DSCOP_DATA_DIR` → `data/phase_separation/dscope`
- `PTMD_DATA_DIR` → `data/disease/PTMD`
- `CANCERPROTEOME_DATA_DIR` → `data/disease/CancerProteome`
- `PTMINT_DATA_DIR` → `data/interactions/PTMint`
- `PTMCODE_DATA_DIR` → `data/interactions/PTMcode2`
- `NLSDB_DATA_DIR` → `data/localization/NLSdb`
- `COMPARTMENTS_DATA_DIR` → `data/localization/COMPARTMENTS`
- `INULOC_DATA_DIR` → `data/localization/iNuLoC`
- `DBPTM_DATA_DIR` → `data/disease/dbptm`
- `PSP_DATA_DIR` → `data/regulation/PhosphoSitePlus`
- `FUNCSCORE_DATA_DIR` → `data/regulation/Funcscore`
- `PTMINT_DATA_DIR` → `data/interactions/PTMint`
