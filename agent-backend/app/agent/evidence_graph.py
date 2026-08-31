"""Lightweight PTM evidence graph for ReAct session memory."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.models.schemas import ToolResult

_PMID_RE = re.compile(r"\b(\d{7,8})\b")


@dataclass
class GraphEntity:
    kind: str
    name: str
    detail: str = ""


@dataclass
class PTMEvidenceGraph:
    entities: list[GraphEntity] = field(default_factory=list)
    relations: list[str] = field(default_factory=list)
    papers: dict[str, str] = field(default_factory=dict)

    def add_entity(self, kind: str, name: str, detail: str = "") -> None:
        key = (kind, name.lower())
        for e in self.entities:
            if (e.kind, e.name.lower()) == key:
                if detail and detail not in e.detail:
                    e.detail = (e.detail + "; " + detail).strip("; ")[:400]
                return
        self.entities.append(GraphEntity(kind=kind, name=name[:120], detail=detail[:400]))

    def add_relation(self, text: str) -> None:
        t = text.strip()[:200]
        if t and t not in self.relations:
            self.relations.append(t)

    def add_paper(self, pmid: str, title: str = "") -> None:
        pmid = str(pmid).strip()
        if pmid.isdigit():
            self.papers[pmid] = (title or self.papers.get(pmid, ""))[:160]

    def add_from_tool_result(self, enriched: ToolResult) -> None:
        if not enriched.success:
            return
        tool = enriched.tool or ""
        data = enriched.data or {}
        db = enriched.database or tool

        self.add_entity("DATABASE", db, enriched.summary or "")

        if tool == "qptm_kinases":
            for k in (data.get("kinases") or data.get("results") or [])[:8]:
                if isinstance(k, dict):
                    name = k.get("kinase") or k.get("name") or ""
                    if name:
                        self.add_entity("ENZYME", str(name))
                        self.add_relation(f"{name} → site (via {db})")

        if tool in ("pubtator_literature_search", "pubmed_fetch_abstracts"):
            for p in (data.get("papers") or data.get("abstracts") or [])[:10]:
                if isinstance(p, dict):
                    pmid = str(p.get("pmid") or "")
                    title = str(p.get("title") or "")
                    if pmid.isdigit():
                        self.add_paper(pmid, title)
                        self.add_entity("PAPER", f"PMID:{pmid}", title[:80])

        self._scan_pmids(data)

    def _scan_pmids(self, obj: Any, depth: int = 0) -> None:
        if depth > 6:
            return
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k in ("pmid", "pmids", "experimental_pmids") and v:
                    if isinstance(v, list):
                        for p in v:
                            self.add_paper(str(p))
                    else:
                        self.add_paper(str(v))
                else:
                    self._scan_pmids(v, depth + 1)
        elif isinstance(obj, list):
            for item in obj[:30]:
                self._scan_pmids(item, depth + 1)
        elif isinstance(obj, str):
            for m in _PMID_RE.findall(obj):
                self.add_paper(m)

    def retrieve_summary(self, max_entities: int = 16) -> str:
        if not self.entities and not self.papers:
            return ""
        lines = ["## Evidence graph (session)"]
        for e in self.entities[:max_entities]:
            line = f"- {e.kind}: {e.name}"
            if e.detail:
                line += f" — {e.detail[:100]}"
            lines.append(line)
        if self.relations:
            lines.append("Relations:")
            for r in self.relations[:8]:
                lines.append(f"  • {r}")
        if self.papers:
            lines.append("Literature PMIDs:")
            for pmid, title in list(self.papers.items())[:8]:
                lines.append(f"  • PMID:{pmid} {title}".strip())
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "entities": [{"kind": e.kind, "name": e.name, "detail": e.detail} for e in self.entities],
            "relations": list(self.relations),
            "papers": dict(self.papers),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PTMEvidenceGraph:
        g = cls()
        for e in data.get("entities") or []:
            if isinstance(e, dict):
                g.add_entity(e.get("kind", ""), e.get("name", ""), e.get("detail", ""))
        g.relations = list(data.get("relations") or [])
        g.papers = dict(data.get("papers") or {})
        return g
