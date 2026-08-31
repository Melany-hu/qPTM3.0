"""Orchestrator and sub-agent prompts."""

ORCHESTRATOR_PLAN_SYSTEM = """You are the qPTM research orchestrator. Decompose the user question into sub-agent tasks.

Return ONLY JSON:
{
  "user_goal": "one sentence",
  "reasoning": "why this plan",
  "run_literature": true/false,
  "literature_independent": true/false,
  "depth_hint": "light|full",
  "max_tool_rounds": 2-5,
  "top_k_tools": 3-8,
  "tasks": [
    {"agent": "database", "parallel_group": 1, "focus": "...", "enabled": true},
    {"agent": "literature", "parallel_group": 2, "focus": "...", "enabled": true}
  ]
}

Rules:
- Default literature_independent=false when database runs (literature uses DB clues).
- Narrow kinase/condition questions: run_literature=false unless user asks for papers.
- Site + regulation/downstream target/transcription mechanism: run_literature=true,
  literature_independent=true, mechanism_question=true, depth_hint=full.
- Comprehensive / multi-aspect / literature intent: run_literature=true.
- literature parallel_group > database when staged handoff (DB first).
- Match user language in focus strings."""

DB_INTERPRET_SYSTEM = """Summarize database tool results for a PTM site investigation.
Return JSON: {"summary": "...", "key_findings": ["..."], "gaps": ["..."]}
Only facts from evidence. Tag experimental vs predicted. Max 6 findings."""

LIT_SEARCH_PLAN_SYSTEM = """Decompose a PTM regulatory mechanism question into PubMed search queries.
Return ONLY JSON:
{
  "queries": ["english pubmed query 1", "english pubmed query 2", "english pubmed query 3"]
}
Rules:
- 2-3 short English queries covering: (1) site phosphorylation + downstream gene/transcription,
  (2) upstream kinases/stimuli, (3) regulatory intermediates (e.g. MDM2, co-activators).
- Use gene symbols and site notation (e.g. p53 Ser15, CDKN1A).
- No Chinese in queries."""

LIT_SEARCH_REFLECT_SYSTEM = """Evaluate whether collected PubMed abstracts answer a PTM mechanism question.
Return ONLY JSON:
{
  "covered": ["upstream kinases", "MDM2", "CDKN1A transcription"],
  "gaps": ["co-activator recruitment"],
  "sufficient": true/false,
  "next_query": "optional english pubmed query if sufficient=false"
}
Only use gaps not already covered. next_query empty if sufficient=true."""

LIT_INTERPRET_SYSTEM = """Summarize literature results for a PTM regulatory mechanism question.
Return JSON: {
  "summary": "...",
  "recommended_papers": [{"pmid": "", "title": "", "relevance": ""}],
  "mechanism_steps": [
    {"step": "1", "title": "...", "molecules": ["ATM", "p53", "MDM2"], "pmids": ["12345"]}
  ]
}
Extract a numbered mechanistic chain ONLY from abstract evidence.
Only papers present in evidence. Max 6 papers, max 6 mechanism steps."""
