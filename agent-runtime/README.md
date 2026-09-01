# qPTM Agent Runtime (TypeScript)

TypeScript agent for Q&A and Deep Research. Replaces Python `/chat` when deployed per `deploy/apache-agent-runtime.conf`.

## Requirements

- Node.js >= 22.19 (`/opt/node22/bin/node`)
- Python venv at `agent-backend/.venv` for qPTM MCP stdio server

## Setup

```bash
cd agent-runtime
cp .env.example .env
# Copy DEEPSEEK_API_KEY from agent-backend/.env

export PATH=/opt/node22/bin:$PATH
npm install
npm run build
```

## Run

```bash
export PATH=/opt/node22/bin:$PATH
node dist/index.js
# Listens on PORT (default 8101)
```

## Modes

- `mode: "qa"` — fast biology Q&A (default)
- `mode: "deep_research"` — clarification → plan → multi-database + literature report

## MCP

- **qPTM MCP**: `agent-backend/mcp_stdio_server.py` (stdio, wraps existing Python tools)
- **BioMCP**: optional `biomcp serve` if installed; falls back to CLI

## Apache cutover

See `deploy/apache-agent-runtime.conf` — routes `/agent-api/chat`, `/conversations`, `/classify` to :8101; `/collection` stays on Python :8100.
