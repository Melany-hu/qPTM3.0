# qPTM Agent: Methods

> **Document purpose.** This file describes the methodology of the qPTM Agent—a large-language-model (LLM) research assistant integrated with the quantitative post-translational modification (PTM) database qPTM ([https://qptm3.omicsbio.info](https://qptm3.omicsbio.info)). The text is written in academic English and is intended for reuse in manuscripts, supplementary materials, or technical reports.

---

## 1. Overview

The qPTM Agent is a conversational AI system designed to help researchers investigate PTM sites in a structured, evidence-attributed manner. Given a natural-language question (e.g., *"Under what conditions is TP53 S15 phosphorylated?"* or *"Where does EGFR Y1173 phosphorylation occur?"*), the agent retrieves information from qPTM and more than thirty external PTM-related databases, synthesizes a narrative answer, and links each factual claim to its originating data source.

The agent follows a **ReAct** (Reasoning + Acting) architecture: an LLM iteratively decides which database tools to invoke, inspects structured JSON results, and terminates when sufficient evidence has been collected. Tool selection is scoped per question through a **Tool Retriever** that exposes only the top-*K* relevant tools (default *K* = 6; up to 10 for site-importance questions), rather than the full catalog of 49 tools. Answers are streamed to the user interface via Server-Sent Events (SSE) and are accompanied by a numbered **Sources** list generated from tool-level citation metadata.

Internally, the agent organizes evidence along four investigative dimensions—**regulators (WHO)**, **kinetics and conditions (WHEN)**, **cellular and sequence context (WHERE)**, and **functional significance (WHY)**—but these labels are not shown to end users; responses are written as natural scientific prose with topic headings matched to the question.

---

## 2. System Architecture

### 2.1 Components

| Layer | Technology | Role |
|-------|------------|------|
| Chat front end | HTML/JavaScript (`agent.php`) | User interface; SSE client; markdown rendering; citation display; suggested follow-up chips |
| Agent API | Python 3, FastAPI (`agent-backend/`) | ReAct loop, tool dispatch, session state, conversation persistence |
| qPTM data API | PHP + MySQL (`api/`) | Quantitative PTM events, site conditions, kinase–substrate associations |
| LLM | DeepSeek V4 Flash (OpenAI-compatible API) | Tool-calling, reasoning, answer synthesis |
| Local data store | TSV/CSV + SQLite indexes (`agent-backend/data/`) | Bulk downloads from public PTM resources |
| External APIs | REST endpoints (UniProt, iPTMnet, STRING, Reactome, PubTator3, etc.) | Live queries where local mirrors are unavailable |

### 2.2 End-to-end data flow

```
User (browser)
    │  natural-language question
    ▼
agent.php  ──POST /chat (SSE)──►  FastAPI (port 8100)
                                      │
                    ┌─────────────────┼─────────────────┐
                    ▼                 ▼                 ▼
              Query Gate        Tool Retriever      Session Memory
              (mode classify)   (top-K tools)       (gene, site, findings)
                    │                 │
                    └────────┬────────┘
                             ▼
                    ReAct loop (≤ 5 rounds)
                    LLM → tool_call → execute → JSON + citations
                             │
                             ▼
                    Final answer (streamed text)
                    + Sources event (numbered references)
                             │
                             ▼
                    agent.php renders markdown, tables, Sources footer
```

The web server proxies `/agent-api/*` to the Python backend (`qptm-agent.service`, Uvicorn on port 8100). The chat front end maintains conversation history locally and passes the last ten turns as context on each request.

### 2.3 ReAct agent loop

For each user message, the agent executes the following pipeline (`app/agent/react.py`):

1. **Session and memory update.** Parsed entities (gene symbol, UniProt accession, residue position, PTM type, organism, PMID, mutation label) are merged into per-session `InvestigationMemory`.
2. **Query gate.** The message is classified into a query mode (e.g., `research`, `literature`, `greeting`, `capability`). Modes that do not require database access receive a static or LLM-free reply without tool invocation.
3. **Target resolution.** For site-level research queries, gene symbols are resolved to UniProt accessions via the UniProt ID mapping service when an accession is not already known.
4. **Tool retrieval.** The Tool Retriever ranks tools by keyword alignment with investigative dimensions and query intent, returning 6–10 tool names.
5. **Iterative reasoning.** The LLM receives a system prompt, conversation history, investigation memory, and JSON schemas for the selected tools. Up to **five** tool rounds are permitted (`MAX_TOOL_ROUNDS = 5`). In each round the model may either (a) emit one or more `tool_call` requests or (b) produce the final answer text.
6. **Tool execution.** Each tool returns a structured dictionary with `success`, `summary`, `data`, and `evidence_level` fields. Results are enriched with standardized citations (`attach_citations`) and merged into a global citation registry (`merge_citations`).
7. **Answer streaming.** The final narrative is streamed in text chunks. A separate SSE `sources` event delivers the citation list for front-end rendering. If the round limit is reached without a natural-language answer, a forced synthesis pass is triggered using accumulated tool evidence.

### 2.4 Tool Retriever

The Tool Retriever (`app/agent/retriever.py`) reduces prompt size and irrelevant database calls by exposing only question-relevant tools. Selection uses a **heuristic keyword scorer** by default (`use_llm_tool_retriever = False`); an optional LLM-based router can rank tools from the full catalog.

Scoring dimensions mirror the internal investigative map:

| Dimension | Example keywords | Representative tools |
|-----------|------------------|----------------------|
| Regulators (WHO) | kinase, enzyme, upstream, drug | `qptm_kinases`, `iptmnet_enzymes`, `gps6_kinases`, `pmads_drug_ptm` |
| Conditions (WHEN) | condition, treatment, fold change, log2 | `qptm_site_conditions`, `qptm_search`, `ekpi_quantitative` |
| Context (WHERE) | where, localization, compartment, NLS | `compartments_localization`, `inuloc_nls_nes`, `signalp_prediction`, `interpro_domains` |
| Significance (WHY) | function, disease, stability, LLPS | `psp_regulatory`, `ptm_stability`, `ptmd_disease`, `ptmphase_llps` |

For **site-importance** questions (e.g., *"Why does TP53 S15 matter?"*), the retriever expands the tool budget to include localization motifs, phase-separation databases, protein–protein interaction resources, and disease annotations. For **narrow** questions (e.g., localization only), the dominant dimension receives priority and unrelated tools are deprioritized.

### 2.5 Investigation memory

`InvestigationMemory` (`app/agent/memory.py`) maintains a lightweight, session-scoped record of the biological target and cumulative tool findings. After each tool call, a one-line summary is appended to the memory block injected into subsequent LLM turns. This enables multi-turn follow-up questions (e.g., *"What about its kinase regulators?"*) without re-stating the protein and site.

### 2.6 Evidence attribution and citations

Every tool result is tagged with an **evidence level**:

- **experimental** — quantitative or curated experimental data (including qPTM measurements and literature-backed curated sets);
- **predicted** — computational predictions (e.g., GPS kinase specificity, PhosLLPS).

Citations are assigned globally across a single answer: the first distinct database invoked becomes [S1], the second [S2], and so on. The front end renders narrative attributions by **database name** (e.g., **qPTM**, **PhosphoSitePlus**) and appends a numbered **Sources** section with hyperlinks to each database homepage or record URL. Structured multi-row facts are presented in markdown tables with a dedicated **Source** column rather than inline reference numbers in prose.

The agent is instructed **not** to enumerate empty database results or internal tool failures; limitations are mentioned only when the user's primary question cannot be answered with available resources (e.g., solvent-accessible surface area, proteoform catalogs).

---

## 3. Registered Tools and Data Sources

As of the current deployment, **49 tools** are registered in `app/tools/registry.py`. Each tool maps to one primary database (see `app/tools/metadata.py`). Data are accessed through three mechanisms:

1. **qPTM REST API** — live queries against the qPTM MySQL backend;
2. **Local indexed files** — TSV/CSV tables under `agent-backend/data/`, optionally compiled to SQLite via `python -m app.sources.build_index`;
3. **External REST APIs** — on-demand HTTP requests with configurable timeouts.

Thirty-seven local source folders include a `SOURCE.yaml` manifest documenting provenance, PMID, and access mode.

### 3.1 qPTM quantitative proteomics (core)

| Tool | Description | Access |
|------|-------------|--------|
| `qptm_search` | Search PTM events by gene, UniProt accession, PTM type, or condition | qPTM API |
| `qptm_site_conditions` | Quantitative fold changes for a specific site across experimental conditions | qPTM API |
| `qptm_kinases` | Integrated experimental and predicted kinase–substrate associations for a site | qPTM API |

### 3.2 Enzymes and upstream regulators (WHO)

| Tool | Database | Evidence type |
|------|----------|---------------|
| `iptmnet_enzymes` | iPTMnet | Experimental + curated |
| `psp_kinase_substrate` | PhosphoSitePlus | Curated |
| `gps6_kinases` | GPS 6.0 | Experimental (kinase specificity) |
| `gpsuber_e3_sites` | GPS-Uber | Predicted (E3 ligase sites) |
| `gpssumo2_sites` | GPS-SUMO 2.0 | Curated + predicted |
| `weram_regulators` | WERAM | Curated (histone acetylation/methylation) |
| `ubibrowser_interactions` | UbiBrowser | Curated (ubiquitin system) |
| `kaka_kinase_mutations` | KAKA | Curated (kinase activity alterations) |
| `ekpi_kinases`, `ekpi_quantitative` | eKPI | Experimental (quantitative kinase–substrate correlations) |
| `pmads_drug_ptm` | PMADS | Curated (drug–PTM–disease) |
| `drugbank_targets` | DrugBank 6.0 | Curated (drug–target) |
| `decryptm_drug_ptm` | decryptM | Experimental dose–response PTM |

### 3.3 Regulation, stability, and functional scores (WHY)

| Tool | Database | Content |
|------|----------|---------|
| `psp_regulatory` | PhosphoSitePlus | ON_FUNCTION / ON_PROCESS regulatory annotations |
| `psp_ptmvar` | PhosphoSitePlus | PTM-disrupting variants |
| `funcscore_phosphosite` | Funcscore | Phosphosite functional priority scores |
| `ptm_stability` | PTM-stability curated set | PTM effects on protein stability (Batista et al., *Nat. Commun.* 2023) |
| `ptmcode_associations` | PTMcode2 | Intra- and inter-protein PTM crosstalk |
| `ptmint_ppi` | PTMint | PTM-dependent protein–protein interactions |

### 3.4 Subcellular localization and sequence context (WHERE)

| Tool | Database | Content |
|------|----------|---------|
| `uniprot_annotation` | UniProt | Protein function, domains, subcellular location keywords |
| `compartments_localization` | COMPARTMENTS | Literature-mined subcellular localization |
| `subcell_scsi` | SubCELL | Compartment-specific interaction context |
| `inuloc_nls_nes`, `inuloc_nuclear_prob` | iNuLoC | NLS/NES/DNL motifs; nuclear localization probability |
| `signalp_prediction` | SignalP 6.0 | Signal peptide and cleavage site predictions |
| `interpro_domains`, `pfam_domains` | InterPro / Pfam | Protein domains and families |

### 3.5 Phase separation

| Tool | Database | Content |
|------|----------|---------|
| `ptmphase_llps`, `ptmphase_phosllps` | PTMPhaSe | Curated PTM–LLPS links; phosphorylation-driven LLPS |
| `dscope_literature`, `dscope_predictions` | dSCOPE | Literature and predicted LLPS regions |

### 3.6 Disease, cancer, and mutations

| Tool | Database | Content |
|------|----------|---------|
| `dbptm_functional` | dbPTM | Functional and disease annotations |
| `ptmd_disease` | PTMD | Disease-associated PTMs |
| `psp_disease_sites` | PhosphoSitePlus | Disease-linked sites |
| `cancerproteome_disease` | CancerProteome | Cancer vs. normal PTM/protein abundance |
| `activedriver_mutations`, `activedriver_kinase_network` | ActiveDriverDB | Mutation–PTM signaling context |

### 3.7 Protein–protein interactions and pathways

| Tool | Database | Access |
|------|----------|--------|
| `iptmnet_ptm_ppi` | iPTMnet | PTM-dependent PPI |
| `string_ppi` | STRING | Association network |
| `biogrid_interactions` | BioGRID | Curated interactions |
| `intact_interactions` | IntAct | IMEx molecular interactions |
| `reactome_pathways` | Reactome | Pathway membership |
| `kegg_pathways` | KEGG | Pathway maps |
| `pathbank_pathways` | PathBank | Metabolic/signaling pathway diagrams |

### 3.8 Literature search

| Tool | Database | Content |
|------|----------|---------|
| `pubtator_literature_search` | PubTator3 | Biomedical literature search and entity tagging |

### 3.9 Local data organization

Local datasets are organized by **PTM research aspect** rather than by vendor name (`agent-backend/data/README.md`):

```
data/
├── enzymes/          # Writers, erasers, predicted regulators
├── regulation/       # Regulatory site annotations, functional scores
├── interactions/     # PPI and PTM crosstalk
├── pathways/         # Signaling and metabolic maps
├── domains/          # InterPro/Pfam domain annotations
├── stability/        # Curated PTM–stability relationships
├── phase_separation/ # LLPS resources
├── disease/          # Disease and cancer associations
├── drug/             # Drug–target and drug–PTM links
└── localization/     # Compartments, motifs, signal peptides
```

---

## 4. Query Handling

### 4.1 Supported query modes

| Mode | Description | Tools invoked |
|------|-------------|---------------|
| `research` | Site- or protein-level PTM investigation | Yes |
| `literature` | Field or method surveys | Primarily `pubtator_literature_search` |
| `pmid_lookup` | Summarize a specific publication | PubTator + synthesis |
| `compare` | Compare two sites on one protein | Multi-tool |
| `followup` | Continue prior session target | Yes |
| `greeting`, `help`, `concept` | Onboarding and education | No |
| `capability`, `meta_db` | Product coverage questions | No |
| `clarify`, `off_topic` | Disambiguation or refusal | No |

Entity parsing extracts gene symbols (e.g., *EGFR*), residue positions (e.g., *Y1173*), UniProt accessions, PTM types, organisms, PMIDs, and mutation labels from free text.

### 4.2 Types of information retrievable

Researchers can obtain, subject to database coverage:

- **Identification and quantification** — PTM site occupancy, log₂ fold changes, and treatment conditions from qPTM;
- **Upstream regulation** — kinases, E3 ligases, methyltransferases, and drug-induced PTM changes;
- **Temporal and conditional dynamics** — stimuli, time courses, and comparative proteomics conditions;
- **Cellular context** — subcellular compartments, cell lines, tissues, NLS/NES motifs, signal peptides, and domain architecture;
- **Functional consequences** — regulatory annotations, stability effects, PTM crosstalk, PTM-dependent PPI rewiring;
- **Disease and clinical relevance** — cancer-associated PTMs, somatic/germline variants affecting PTM sites, biomarker context;
- **Phase separation** — LLPS-driving segments and phosphorylation-linked condensate biology;
- **Literature** — PubMed records linked to genes, sites, or methods.

### 4.3 Known capability boundaries

The following question classes are **not** fully supported and should be interpreted cautiously:

- Solvent-accessible surface area (SASA) and residue burial/exposure;
- Complete proteoform catalogs or combinatorial multi-PTM states;
- Systematic PTM crosstalk networks beyond PTMcode2 curated subsets;
- De novo structural modeling beyond domain annotations from InterPro/Pfam.

When a question falls entirely outside available tools, the agent provides a brief honest statement rather than inventing measurements.

---

## 5. User Interface and Usage

### 5.1 Access

The agent is available at the qPTM web portal chat page (`agent.php`), deployed alongside the main qPTM database interface. No separate installation is required for end users.

### 5.2 Interaction modes

Two modes are offered:

1. **Research Q&A (研究问答)** — default ReAct agent described in this document;
2. **Data collection (数据收集)** — literature-mining pipeline for extracting PTM quantitative tables from publications (PMID-driven; Node.js subprocess; outputs CSV for curator review). This mode is distinct from site investigation and is not covered in detail here.

### 5.3 Typical workflow

1. Open the chat interface and enter a question in English or Chinese.
2. The agent displays tool-call indicators while querying databases (collapsible panel).
3. The answer streams in markdown format with headings, tables, and evidence labels (*experimental* / *predicted* or 实验验证 / 计算预测).
4. A **Sources** section lists numbered references with database hyperlinks.
5. **Suggested follow-ups** appear as clickable chips for common next questions (e.g., kinase regulators after a conditions query).
6. Conversation history is persisted server-side per client IP session and can be resumed from the sidebar.

### 5.4 Answer formatting conventions

- **Narrative prose** attributes facts by **bold database name** and evidence level; inline numeric citations are avoided in body text.
- **Tables** carry a **Source** (or 来源) column for multi-row structured results.
- **Language** matches the user question (English or Chinese throughout, including headings and follow-ups).
- Empty or irrelevant tool results are omitted from the user-visible answer.

---

## 6. LLM Configuration

| Parameter | Default |
|-----------|---------|
| Model | DeepSeek V4 Flash (`deepseek-v4-flash`) |
| API | OpenAI-compatible chat completions with function calling |
| Max tool rounds | 5 |
| Max output tokens | 8,192 (streaming) |
| Tool retriever | Heuristic (keyword-based); LLM retriever optional |
| Temperature | Model default; tool routing uses temperature 0 |

The system prompt (`app/llm/prompts.py`, `REACT_SYSTEM_PROMPT`) encodes investigative strategy, citation style, evidence-label rules, language lock, and instructions to answer only the asked dimension.

---

## 7. Evaluation

Automated regression evaluation is performed with `agent-backend/runtime/eval/run_agent_eval.py`, which issues a benchmark set of 30 questions (Q1–Q30) covering kinase identification, conditions, localization, disease, mutations, capability-gap honesty, and non-TP53 proteins. Results are logged as JSONL with tool-call traces, keyword checks, and latency.

---

## 8. Software Availability

| Component | Location |
|-----------|----------|
| Agent backend | `agent-backend/` (Python ≥ 3.10, FastAPI, Uvicorn) |
| Chat front end | `agent.php` |
| qPTM REST API | `api/` |
| Local datasets | `agent-backend/data/` |
| Systemd service | `qptm-agent.service` (port 8100) |

Backend setup:

```bash
cd agent-backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # configure DEEPSEEK_API_KEY, database paths
uvicorn app.main:app --host 0.0.0.0 --port 8100
```

Index local tables after downloading source files:

```bash
python -m app.sources.build_index <source_id>
```

---

## 9. Summary

The qPTM Agent combines (i) quantitative PTM measurements from qPTM, (ii) federated annotations from more than thirty specialized PTM and genomics resources, and (iii) LLM-driven ReAct reasoning with tool-scoped retrieval and standardized evidence attribution. The design prioritizes **question-focused answers**, **traceable database provenance**, and **separation of experimental versus predicted evidence**, while hiding internal orchestration details from the user. This architecture enables interactive, multi-turn investigation of PTM sites without requiring users to manually query each database or synthesize cross-resource evidence by hand.

---

## References (selected integrated databases)

| Database | PMID (primary) |
|----------|----------------|
| qPTM | Omics platform — [qptm3.omicsbio.info](https://qptm3.omicsbio.info) |
| PhosphoSitePlus | 30445427 |
| iPTMnet | 29145615 |
| UniProt | 37431678 |
| COMPARTMENTS | 24573882 |
| PTMPhaSe | 41360972 |
| PTMint | 36548389 |
| PTMcode2 | 25361965 |
| ActiveDriverDB | — |
| PubTator3 | 38457913 |

Full provenance for each local source is recorded in the corresponding `SOURCE.yaml` file under `agent-backend/data/`.

---

*Document version: August 2026. Reflects ReAct architecture (v2.0.0), 54 registered tools, and scheme-C citation formatting.*
