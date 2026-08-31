"""Orchestrator data contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from app.models.schemas import ToolResult

AgentName = Literal["orchestrator", "database", "literature", "writer"]


@dataclass
class LiteratureClue:
    pmid: str
    source_tool: str
    source_db: str
    context: str
    gene: str | None = None
    site: str | None = None
    evidence_level: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "pmid": self.pmid,
            "source_tool": self.source_tool,
            "source_db": self.source_db,
            "context": self.context,
            "gene": self.gene,
            "site": self.site,
            "evidence_level": self.evidence_level,
        }


@dataclass
class AgentTask:
    agent: Literal["database", "literature"]
    parallel_group: int = 1
    focus: str = ""
    enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent": self.agent,
            "parallel_group": self.parallel_group,
            "focus": self.focus,
            "enabled": self.enabled,
        }


@dataclass
class OrchestratorPlan:
    user_goal: str
    tasks: list[AgentTask]
    run_literature: bool = True
    literature_independent: bool = False
    depth_hint: str = "light"
    reasoning: str = ""
    max_tool_rounds: int = 3
    top_k_tools: int = 5
    mechanism_question: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_goal": self.user_goal,
            "tasks": [t.to_dict() for t in self.tasks],
            "run_literature": self.run_literature,
            "literature_independent": self.literature_independent,
            "depth_hint": self.depth_hint,
            "reasoning": self.reasoning,
            "max_tool_rounds": self.max_tool_rounds,
            "top_k_tools": self.top_k_tools,
            "mechanism_question": self.mechanism_question,
        }


@dataclass
class DatabaseBrief:
    summary: str = ""
    key_findings: list[str] = field(default_factory=list)
    tool_results: list[ToolResult] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    literature_clues: list[LiteratureClue] = field(default_factory=list)


@dataclass
class LiteratureBrief:
    summary: str = ""
    recommended_papers: list[dict[str, Any]] = field(default_factory=list)
    tool_results: list[ToolResult] = field(default_factory=list)
    seed_pmids_fetched: list[str] = field(default_factory=list)
    clues_addressed: list[str] = field(default_factory=list)
    mechanism_steps: list[dict[str, Any]] = field(default_factory=list)
    search_traces: list[dict[str, Any]] = field(default_factory=list)
