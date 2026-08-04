"""Investigation memory — lightweight per-session target and findings tracking."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from app.agent.entities import parse_query_entities
from app.models.schemas import ToolResult


@dataclass
class InvestigationMemory:
    """Per-session investigation context for ReAct agent."""

    gene: str | None = None
    uniprot_ac: str | None = None
    position: int | None = None
    ptm_type: str | None = "phosphorylation"
    organism: str = "human"
    pmid: str | None = None
    mutation_label: str | None = None
    query_mode: str | None = None
    findings_summary: str = ""
    entities: dict[str, Any] = field(default_factory=dict)

    @property
    def has_target(self) -> bool:
        return bool(self.uniprot_ac or self.gene or self.position)

    @property
    def target_gene(self) -> str | None:
        return self.gene

    @property
    def target_uniprot_ac(self) -> str | None:
        return self.uniprot_ac

    @property
    def target_position(self) -> int | None:
        return self.position

    @property
    def target_ptm_type(self) -> str | None:
        return self.ptm_type

    def update_from_message(self, message: str) -> dict[str, Any]:
        """Parse entities from user message and merge into memory."""
        parsed = parse_query_entities(message)
        self.entities = {**self.entities, **parsed}

        if parsed.get("gene"):
            self.gene = parsed["gene"]
        if parsed.get("uniprot_ac"):
            self.uniprot_ac = parsed["uniprot_ac"]
        if parsed.get("position"):
            self.position = parsed["position"]
        if parsed.get("ptm_type"):
            self.ptm_type = parsed["ptm_type"]
        if parsed.get("organism"):
            self.organism = parsed["organism"]
        if parsed.get("pmid"):
            self.pmid = parsed["pmid"]
        if parsed.get("mutation_label"):
            self.mutation_label = parsed["mutation_label"]

        return parsed

    def update_from_tool(self, enriched: ToolResult) -> None:
        """Accumulate a short finding summary from tool results."""
        summary = (enriched.summary or "").strip()
        if not summary:
            return
        line = f"- [{enriched.tool}] {summary[:300]}"
        if line not in self.findings_summary:
            if self.findings_summary:
                self.findings_summary += "\n"
            self.findings_summary += line

        raw = enriched.data or {}
        if enriched.tool == "qptm_search":
            events = raw.get("events") or []
            if events:
                ev = events[0]
                if ev.get("gene") and not self.gene:
                    self.gene = ev["gene"]
                if ev.get("uniprot_ac") and not self.uniprot_ac:
                    self.uniprot_ac = ev["uniprot_ac"]
                if ev.get("position") and not self.position:
                    self.position = ev["position"]
        elif enriched.tool == "qptm_site_conditions":
            if raw.get("uniprot_ac") and not self.uniprot_ac:
                self.uniprot_ac = raw["uniprot_ac"]
            site = raw.get("site") or {}
            if site.get("position") and not self.position:
                self.position = site["position"]

    def to_prompt_block(self) -> str:
        """Format memory for injection into the system prompt."""
        parts: list[str] = []
        if self.gene:
            parts.append(f"gene={self.gene}")
        if self.uniprot_ac:
            parts.append(f"UniProt={self.uniprot_ac}")
        if self.position:
            parts.append(f"site=S{self.position}")
        if self.ptm_type:
            parts.append(f"ptm_type={self.ptm_type}")
        if self.mutation_label:
            parts.append(f"mutation={self.mutation_label}")
        if self.pmid:
            parts.append(f"PMID={self.pmid}")
        if self.query_mode:
            parts.append(f"mode={self.query_mode}")

        block = "Current investigation target: " + (", ".join(parts) if parts else "(not set)")
        if self.findings_summary:
            block += "\n\nFindings so far:\n" + self.findings_summary
        return block

    def to_dict(self) -> dict[str, Any]:
        return {
            "gene": self.gene,
            "uniprot_ac": self.uniprot_ac,
            "position": self.position,
            "ptm_type": self.ptm_type,
            "organism": self.organism,
            "pmid": self.pmid,
            "mutation_label": self.mutation_label,
            "query_mode": self.query_mode,
            "findings_summary": self.findings_summary,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> InvestigationMemory:
        return cls(
            gene=data.get("gene"),
            uniprot_ac=data.get("uniprot_ac"),
            position=data.get("position"),
            ptm_type=data.get("ptm_type"),
            organism=data.get("organism", "human"),
            pmid=data.get("pmid"),
            mutation_label=data.get("mutation_label"),
            query_mode=data.get("query_mode"),
            findings_summary=data.get("findings_summary", ""),
            entities=data.get("entities") or {},
        )


def tool_result_message(tool_call_id: str, enriched: ToolResult) -> dict[str, Any]:
    """Build an OpenAI-compatible tool result message for the LLM."""
    payload = {
        "tool": enriched.tool,
        "database": enriched.database,
        "success": enriched.success,
        "summary": enriched.summary,
        "data": enriched.data,
    }
    if enriched.citations:
        payload["citations"] = [
            {
                "id": enriched.citation_map.get(c.id, c.id),
                "source_db": c.source_db,
                "label": c.label,
                "source_type": c.source_type,
                "url": c.url,
                "pmid": c.pmid,
                "doi": c.doi,
            }
            for c in enriched.citations
        ]
    return {
        "role": "tool",
        "tool_call_id": tool_call_id,
        "content": json.dumps(payload, ensure_ascii=False),
    }
