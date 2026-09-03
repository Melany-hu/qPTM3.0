# qPTM 2026 — Quantitative PTM Database & AI Agent

A comprehensive resource for quantitative post-translational modification (PTM) proteomics data, integrated with an AI research assistant that guides users through a structured PTM investigation workflow.

## Repository Structure

```
qPTM2026/
│
│  ── Website Frontend (existing) ──
├── index.html               Home page with search & database stats
├── search.html              Advanced search interface
├── result.html              Search results display
├── browse.html              Browse database by organism/PTM type
├── query.html               Batch query interface
├── qkinact.html             Kinase activity prediction (qKinAct)
├── download.html            Dataset download request form
├── about.html               About page
├── help.html                Help/documentation
├── citation.html            Citation information
├── header.html / footer.html  Shared page components
├── getfile.php              File download handler
├── sendemail.php            Email sending handler
├── resource/
│   └── functions.php        Website backend (AJAX, returns HTML)
├── assets/                  JavaScript, CSS, images
│
│  ── AI Agent Chat Interface ──
├── agent.php                Chat frontend (deploys to web root, connects to Python backend)
│
│  ── Agent REST API (PHP, returns JSON) ──
├── api/
│   ├── db.php               Shared MySQL connection & helpers
│   ├── search.php           GET /api/search?q=TP53
│   ├── site.php             GET /api/site?uniprot=P04637&pos=15
│   ├── conditions.php       GET /api/conditions?q=IL-33
│   ├── kinases.php          GET /api/kinases/P04637/15
│   ├── protein.php          GET /api/protein/P04637
│   ├── browse.php           GET /api/browse?org=human&mod=phosphorylation
│   └── .htaccess            URL rewriting rules
│
│  ── Agent Backend (Python FastAPI) ──
└── agent-backend/
    ├── app/
    │   ├── main.py              FastAPI app: SSE streaming, agent loop, tool dispatch
    │   ├── config.py            Settings (API keys, URLs, data paths)
    │   ├── llm/
    │   │   ├── deepseek_client.py   DeepSeek V3 client (OpenAI-compatible, streaming)
    │   │   └── prompts.py           System prompt with 3-stage workflow
    │   ├── models/
    │   │   └── schemas.py           Pydantic models (ChatRequest, WorkflowStage, etc.)
    │   ├── tools/
    │   │   ├── registry.py          Tool registry (JSON schema + handler dispatch)
    │   │   ├── qptm_tools.py        Tools 1-3: qPTM search, conditions, kinases
    │   │   ├── iptmnet_tools.py     Tools 4-5: iPTMnet enzymes, PTM-dependent PPI
    │   │   ├── uniprot_tools.py     Tool 6: UniProt annotations
    │   │   ├── psp_tools.py         Tool 7: PhosphoSitePlus regulatory sites
    │   │   ├── dbptm_tools.py       Tool 8: dbPTM functional/disease annotations
    │   │   └── stability_tools.py   Tool 9: PTM-stability curated dataset (Direction 3)
    │   └── workflow/
    │       ├── state.py             Conversation state machine (per-session)
    │       └── stages.py            Stage detection, advancement, suggestions
    ├── tests/
    │   └── test_tools.py            15 end-to-end tests (all passing)
    ├── data/
    │   ├── psp/                     PhosphoSitePlus Regulatory_sites (user download)
    │   ├── dbptm/                   dbPTM bulk data files (user download)
    │   ├── stability/               PTM-stability curated dataset (included)
    │   │   └── ptm_stability_curated.tsv  78 entries, 34 proteins, 7 PTM types
    │   ├── ptmphase/                PTMPhaSe data (future tool)
    │   └── ptmint/                  PTMint data (future tool)
    ├── requirements.txt
    └── .env.example
```

## Architecture

```
┌─────────────────┐     SSE      ┌──────────────────┐     HTTP     ┌─────────────┐
│  Chat Frontend  │ ──────────→  │  Python Backend  │ ──────────→  │  PHP API    │
│  (agent.php)    │              │  (FastAPI)       │              │  (api/)     │
│  on web server  │  ←────────── │  port 8100       │  ←────────── │  MySQL      │
└─────────────────┘   SSE events └────────┬─────────┘   JSON       └─────────────┘
                                         │
                    ┌────────────────────┼────────────────────┐
                    │                    │                    │
              ┌─────▼─────┐      ┌──────▼──────┐      ┌──────▼──────┐
              │  UniProt  │      │  iPTMnet    │      │  Local data │
              │  REST API │      │  REST API   │      │  (TSV/CSV)  │
              └───────────┘      └─────────────┘      └─────────────┘
```

| Component | Technology | Location | Port |
|-----------|-----------|----------|------|
| Website frontend | HTML/JS/CSS | Root `*.html` | 80/443 |
| Website backend | PHP + MySQL | `resource/functions.php` | 80/443 |
| Agent chat UI | HTML/JS/CSS | `agent.php` | 80/443 |
| Agent REST API | PHP + MySQL | `api/*.php` | 80/443 |
| Agent backend | Python + FastAPI | `agent-backend/` | 8100 |
| LLM | DeepSeek V3 | External API | — |

## Tools

The agent backend registers tools that the LLM can call during a conversation. Each tool queries a specific data source and returns structured results.

### Current Tools (9)

| # | Tool | Stage | Data Source | Direction |
|---|------|-------|-------------|-----------|
| 1 | `qptm_search` | Stage 1 | qPTM database (PHP API) | 1: PTM identification |
| 2 | `qptm_site_conditions` | Stage 1 | qPTM database (PHP API) | 1: PTM identification |
| 3 | `qptm_kinases` | Stage 2 | qPTM database (PHP API) | 1: PTM identification |
| 4 | `iptmnet_enzymes` | Stage 2 | iPTMnet REST API | 2: Writer/Eraser/Reader |
| 5 | `iptmnet_ptm_ppi` | Stage 2/3 | iPTMnet REST API | 3: PTM effects |
| 6 | `uniprot_annotation` | Stage 3 | UniProt REST API | 3: PTM effects |
| 7 | `psp_regulatory` | Stage 3 | PhosphoSitePlus local file | 3/5: PTM effects / cellular process |
| 8 | `dbptm_functional` | Stage 3 | dbPTM local file / web | 6: Disease association |
| 9 | `ptm_stability` | Stage 3 | Curated dataset (PMC9839724) | 3: PTM effects on stability |

### Planned Tools (Direction 3/5/7 extensions)

| Tool | Data Source | Direction | Status |
|------|-------------|-----------|--------|
| `ptm_phase_separation` | PTMPhaSe | 3: PTM effects on phase separation | Planned |
| `ptm_ppi_effect` | PTMint | 3: PTM effects on interactions | Planned |
| `ptm_structural_context` | AlphaFold DB API | 3: Structural context | Planned |
| `deepmvp_prediction` | DeepMVP | 7: AI prediction | Planned |
| `ptm_cellular_process` | PSP ON_PROCESS | 5: Cellular process regulation | Planned |

### 7-Direction PTM Research Framework

| Direction | Description | Coverage |
|-----------|-------------|----------|
| 1 | PTM identification & mapping | qPTM core (tools 1-3) |
| 2 | Writer/Eraser/Reader | iPTMnet (tool 4, partial — writer only) |
| 3 | PTM effects on protein properties | ptm_stability (tool 9) + planned tools |
| 4 | PTM crosstalk | Deferred |
| 5 | PTM regulation of cellular processes | Planned (PSP ON_PROCESS) |
| 6 | PTM & disease | dbPTM/PTMD (tool 8, already integrated by qPTM) |
| 7 | AI & PTM prediction | Planned (DeepMVP) |

## Four-Stage Logic Line (WHO → WHEN → WHERE → WHY)

The agent guides users through investigating a PTM site:

1. **Stage 1 — WHO**: Who regulates it (drugs / ligands → targets → kinases/enzymes)?
   - Tools: `qptm_kinases`, `iptmnet_enzymes`, `activedriver_kinase_network`, `pmads_drug_ptm`, `decryptm_drug_ptm`
   - Output: upstream regulators, enzyme names, evidence type

2. **Stage 2 — WHEN**: When does the site change (kinetics / fold change)?
   - Tools: `qptm_search`, `qptm_site_conditions`
   - Output: time points, treatments, log2 ratios, transient vs sustained

3. **Stage 3 — WHERE**: Where does it happen (cell background + localization)?
   - Tools: `uniprot_annotation`, `compartments_localization`, `inuloc_nls_nes`, `inuloc_nuclear_prob`
   - Output: sample/cell context, subcellular location, complex/pathway role

4. **Stage 4 — WHY**: Why does it matter (mechanism → outcome → value)?
   - Tools: `psp_regulatory`, `ptm_stability`, `funcscore_phosphosite`, `ptmd_disease`, `dbptm_functional`, …
   - Output: pathway meaning, phenotype, biomarker / therapeutic implication

## PTM-Stability Curated Dataset

The `ptm_stability` tool (tool 9) uses a manually curated dataset extracted from:

> Batista et al. "Control of protein stability by post-translational modifications." *Nature Communications* 14, 2023. doi:10.1038/s41467-023-35795-8. PMC9839724.

**Dataset statistics:**
- 78 curated PTM-stability relationships
- 34 substrate proteins (UniProt accessions verified)
- 7 PTM types: phosphorylation, methylation, acetylation, ubiquitylation, SUMOylation, hydroxylation, glycosylation
- 39 stabilizing / 39 destabilizing entries
- Each entry includes: effect direction, molecular mechanism, writer/eraser/reader enzymes, ubiquitination sites

**TSV format** (`data/stability/ptm_stability_curated.tsv`):

| Column | Description |
|--------|-------------|
| `uniprot_ac` | UniProt accession (e.g., P04637) |
| `gene` | Gene symbol (e.g., TP53) |
| `ptm_type` | PTM type (phosphorylation, methylation, etc.) |
| `position` | Residue position (- if unspecified) |
| `effect_direction` | stabilize or destabilize |
| `mechanism` | Molecular mechanism description |
| `writer` | Enzyme that writes the modification |
| `eraser` | Enzyme that removes the modification |
| `reader` | Protein that recognizes the modification |
| `ubiquitin_sites` | Lysines targeted for ubiquitination |
| `evidence` | Evidence type (all entries: experimental) |
| `source` | Source reference (PMC9839724) |

## Deployment

### 1. Website (existing)

The website files (`*.html`, `resource/`, `assets/`) are already deployed on the qPTM web server.

### 2. Agent REST API (PHP)

Copy `api/` to the web server:

```bash
scp -r api/* user@qptm-server:/var/www/html/qptm/api/
```

Update `api/db.php` with MySQL credentials matching the qPTM database.

### 3. Agent Backend (Python)

```bash
# On the server
cd /opt/qptm-agent  # or wherever you deploy agent-backend/
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env: set DEEPSEEK_API_KEY and QPTM_API_BASE_URL

# Run
uvicorn app.main:app --host 0.0.0.0 --port 8100
```

**systemd service** (`/etc/systemd/system/qptm-agent.service`):

```ini
[Unit]
Description=qPTM Agent Backend
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/qptm-agent
EnvironmentFile=/opt/qptm-agent/.env
ExecStart=/opt/qptm-agent/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8100
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### 4. Agent Chat Frontend

```bash
scp agent.php user@qptm-server:/var/www/html/qptm/agent.php
```

The frontend connects to `http://localhost:8100/chat` by default. Override via:
- Environment variable: `SetEnv QPTM_AGENT_BACKEND_URL http://your-backend-host:8100`
- Or edit `$BACKEND_URL` in `agent.php`

### 5. Optional: Load Local Data Files

| Tool | Data File | Source | Location |
|------|-----------|--------|----------|
| `psp_regulatory` | `Regulatory_sites` | phosphosite.org (free account) | `data/psp/` |
| `dbptm_functional` | Experimental PTM sites | biomics.lab.nycu.edu.tw/dbPTM | `data/dbptm/` |
| `ptm_stability` | `ptm_stability_curated.tsv` | Included in this repo | `data/stability/` |

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check + tool count |
| POST | `/chat` | Streaming chat (SSE) |
| GET | `/tools` | List all registered tools |
| GET | `/session/{id}` | Get session workflow state |
| DELETE | `/session/{id}` | Reset session |

## Testing

```bash
cd agent-backend
python tests/test_tools.py
```

```
qPTM Agent — End-to-End Test Suite
==================================================
Results: 15 passed, 0 failed, 15 total
All tests passed!
```

Tests cover: tool registration (9 tools), UniProt annotation, iPTMnet enzymes (with position filter), iPTMnet PPI, PSP graceful degradation, dbPTM graceful degradation, PTM-stability (TP53, filtered, not-found, HTT), qPTM error handling, workflow state machine, unknown tool, invalid accession.

## Configuration

Environment variables (`.env` file in `agent-backend/`):

| Variable | Default | Description |
|----------|---------|-------------|
| `DEEPSEEK_API_KEY` | (required) | DeepSeek API key |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | DeepSeek API endpoint |
| `DEEPSEEK_MODEL` | `deepseek-chat` | Model name (DeepSeek V3) |
| `QPTM_API_BASE_URL` | `https://qptm3.omicsbio.info/api` | qPTM PHP API base URL |
| `UNIPROT_API_BASE_URL` | `https://rest.uniprot.org` | UniProt REST API |
| `IPTMNET_API_BASE_URL` | `https://research.bioinformatics.udel.edu/iptmnet/api` | iPTMnet API |
| `PSP_DATA_DIR` | `./data/psp` | PhosphoSitePlus data directory |
| `DBPTM_DATA_DIR` | `./data/dbptm` | dbPTM data directory |
| `STABILITY_DATA_DIR` | `./data/stability` | PTM-stability dataset directory |
| `HOST` | `0.0.0.0` | Backend bind address |
| `PORT` | `8100` | Backend port |
| `CORS_ORIGINS` | `http://localhost,http://qptm3.omicsbio.info` | Allowed CORS origins |

## Key References

- **qPTM 3.0**: PMID 36165955 — 14M+ quantitative PTM events, 796K sites, 73K proteins
- **PTM-stability review**: Nature Comms 2023, doi:10.1038/s41467-023-35795-8, PMC9839724
- **iPTMnet**: research.bioinformatics.udel.edu/iptmnet
- **PhosphoSitePlus**: phosphosite.org
- **dbPTM**: biomics.lab.nycu.edu.tw/dbPTM (PMID 39526378)
- **PTMD**: ptmd.biocuckoo.cn (disease-associated PTMs, integrated by qPTM)
- **DeepMVP**: Nature Methods 2025, doi:10.1038/s41592-025-02797-x (planned integration)
- **PTMPhaSe**: Commun Chem 2025, doi:10.1038/s42004-025-01773-y (planned integration)
- **PTMint**: Bioinformatics 2023, doi:10.1093/bioinformatics/btac823 (planned integration)
