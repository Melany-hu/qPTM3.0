"""SSE phase_update labels for orchestrator and ReAct paths."""

from __future__ import annotations

from typing import Any

_PHASE_LABELS: dict[str, tuple[str, str]] = {
    "planning": ("Planning research…", "规划研究步骤…"),
    "resolving": ("Resolving protein ID…", "解析蛋白标识…"),
    "clarifying": ("Assessing question scope…", "分析问题范围…"),
    "retrieving_tools": ("Selecting database tools…", "选择数据库工具…"),
    "database": ("Searching databases…", "检索数据库…"),
    "literature": ("Searching literature…", "搜索文献…"),
    "synthesis": ("Generating answer…", "生成回答…"),
}


def phase_event(phase: str, lang: str = "en") -> dict[str, Any]:
    labels = _PHASE_LABELS.get(phase, ("Working…", "处理中…"))
    label = labels[1] if lang == "zh" else labels[0]
    return {"type": "phase_update", "phase": phase, "label": label}
