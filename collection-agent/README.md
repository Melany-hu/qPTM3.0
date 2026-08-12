# qPTM Collection Agent

Interactive literature collection pipeline for **qPTM2026** (`agent.php` → Data collection mode).

Each PMID runs as a single job under `collection-agent/runtime/collection/jobs/{job_id}/`. The user steps through Stage 1–6 with Continue / upload prompts; outputs are CSV artifacts for download (no MySQL).

## CLI (invoked by agent-backend)

```bash
npx tsx src/index.ts run-job --pmid <id> --out-dir <dir> --job-id <id> [options]
npx tsx src/index.ts ingest-fulltext --pmid <id> --file <path> --out-dir <dir>
npx tsx src/index.ts ingest-supp --pmid <id> --file <path> --out-dir <dir>
```

## Pipeline

| Stage | UI label | Purpose |
|-------|----------|---------|
| 1 | Screen | LLM abstract screening |
| 2 | Full text | Repository IDs + OA fulltext fetch |
| 3 | Metadata | `literature_info` row |
| 4 | Supplementary | Scout / manual table upload |
| 5 | Quant table | Parse to qratio schema |
| 6 | MS URLs | PRIDE / iProX / jPOST download links |

Stage 6 uses Python helpers in `scripts/`:

- `1_html_pride_extract.py`
- `2_xml_iprox_extract.py`
- `3_html_jpost_extract.py`

Schema reference: `files/example_qratio.csv`.

## Layout

```
collection-agent/
├── src/
│   ├── index.ts              # CLI entry (run-job, ingest-*)
│   ├── pipeline/             # run-job orchestration + stage runners
│   ├── chains/               # LLM chains (screen, meta, qratio)
│   ├── stage1/ … stage6/     # Stage implementations
│   ├── ingest/               # Manual fulltext / supplementary ingest
│   └── utils/
├── scripts/                  # Stage 6 repository extractors
└── files/example_qratio.csv
```

## Environment

Copy `.env.example` → `.env`. Typical keys:

- `OPENCODE_API_KEY` or `DEEPSEEK_API_KEY`
- `MODEL` (e.g. `opencode-go/deepseek-v4-flash`)
- `UNPAYWALL_EMAIL`
- `NCBI_API_KEY` / `NCBI_EMAIL`

Node **≥ 22.19** (`/opt/node22/bin/node` on the qPTM server).
