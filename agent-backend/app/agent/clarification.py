"""LLM-driven clarification before deep PTM research."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from app.agent.llm_fallback import log_llm_fallback
from app.agent.memory import InvestigationMemory

logger = logging.getLogger(__name__)

_CLARIFICATION_ASSESS_TIMEOUT_S = 12.0
_CLARIFICATION_MODES = frozenset({"research", "followup", "compare", "literature"})

_ASSESS_SYSTEM = """You are a PTM (post-translational modification) research planner for qPTM Agent.

Your job is NOT to decide whether a database lookup is possible — almost any gene+site can be \
looked up. Your job is to decide whether **one short clarification** would help the agent run a \
**deeper, more meaningful** investigation instead of a shallow generic summary.

## Default stance
When the user only names a protein/site/PTM (or gives a very short phrase) without stating \
**what they want to learn**, you SHOULD ask for clarification. The user can skip and run anyway.

## Ask for clarification when (common cases)
- Bare site mention: e.g. "TP53 S15磷酸化", "AKT1 S473", "STAT3 Y705 phosphorylation" — \
  no investigative angle stated
- Multiple equally plausible deep paths (WHO kinases / WHEN conditions / WHERE localization / \
  WHY function-disease) and the user did not prioritize
- Missing scope that would materially change retrieval: organism, stimulus, disease/cell line, \
  time point, comparison baseline
- Incomplete or truncated question; user has not finished stating the research goal

## Skip clarification ONLY when
- The user already states a clear investigative angle or specific factual question, e.g.:
  - "Which kinases phosphorylate TP53 S15?"
  - "TP53 S15 fold change under DNA damage"
  - "Functional role of TP53 S15 phosphorylation in apoptosis"
- Greeting, capability, or broad conceptual overview (not site research)
- Follow-up in the same session that already scoped the investigation

When asking, propose 1–2 **research-direction** fields (not just gene/site — those are often \
already known). Always include a free-text line for the user to state their goal in their own words.

Return ONLY valid JSON (no markdown fences):
{
  "needs_clarification": true or false,
  "intro": "one sentence in the user's language",
  "fields": [
    {
      "id": "snake_case",
      "label": "field label",
      "options": ["chip option 1", "chip option 2"],
      "option_values": ["optional", "parallel", "ids"],
      "allow_custom": true,
      "placeholder": "optional custom input hint"
    }
  ],
  "free_text": {
    "label": "bottom text area label",
    "placeholder": "hint for free-form input"
  },
  "submit_label": "button label",
  "skip_label": "skip button label"
}

If needs_clarification is false, return only: {"needs_clarification": false}
Max 2 fields. Match Chinese if the user wrote Chinese, otherwise English."""


def _detect_lang(question: str) -> str:
    zh = sum(1 for ch in question if "\u4e00" <= ch <= "\u9fff")
    latin = sum(1 for ch in question if "a" <= ch.lower() <= "z")
    return "zh" if zh >= 2 and zh >= latin * 0.35 else "en"


def should_assess_clarification(mode: str) -> bool:
    return (mode or "").lower() in _CLARIFICATION_MODES


def _parse_json_object(raw: str) -> dict[str, Any] | None:
    text = (raw or "").strip()
    if not text:
        return None
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _normalize_field(field: Any) -> dict[str, Any] | None:
    if not isinstance(field, dict):
        return None
    field_id = str(field.get("id") or "").strip()
    label = str(field.get("label") or "").strip()
    if not field_id or not label:
        return None
    options = field.get("options") or []
    if not isinstance(options, list):
        options = []
    options = [str(o).strip() for o in options if str(o).strip()][:6]
    option_values = field.get("option_values") or []
    if not isinstance(option_values, list):
        option_values = []
    option_values = [str(v).strip() for v in option_values][: len(options)]
    return {
        "id": field_id,
        "label": label,
        "options": options,
        "option_values": option_values,
        "allow_custom": bool(field.get("allow_custom", True)),
        "placeholder": str(field.get("placeholder") or ""),
    }


def _normalize_clarification_payload(
    data: dict[str, Any],
    question: str,
    lang: str,
) -> dict[str, Any] | None:
    if not data.get("needs_clarification"):
        return None

    intro = str(data.get("intro") or "").strip()
    if not intro:
        intro = (
            "为进行更有深度的位点级研究，请补充以下信息（也可跳过直接执行）："
            if lang == "zh"
            else "To run a deeper site-level investigation, please add the following (or skip and run anyway):"
        )

    fields: list[dict[str, Any]] = []
    for raw_field in (data.get("fields") or [])[:2]:
        normalized = _normalize_field(raw_field)
        if normalized:
            fields.append(normalized)

    free_raw = data.get("free_text") or {}
    if not isinstance(free_raw, dict):
        free_raw = {}
    free_label = str(free_raw.get("label") or "").strip()
    free_placeholder = str(free_raw.get("placeholder") or "").strip()
    if not free_label:
        free_label = "其他补充（可选）" if lang == "zh" else "Additional notes (optional)"
    if not free_placeholder:
        free_placeholder = (
            "请用一句话说明您最想了解的内容…"
            if lang == "zh"
            else "Describe what you most want to learn…"
        )

    submit_label = str(data.get("submit_label") or "").strip()
    skip_label = str(data.get("skip_label") or "").strip()
    if not submit_label:
        submit_label = "开始研究" if lang == "zh" else "Start research"
    if not skip_label:
        skip_label = "跳过，直接执行" if lang == "zh" else "Skip and run"

    # Require at least one actionable input (chips or free text)
    if not fields and not free_label:
        return None

    return {
        "intro": intro,
        "original_question": question,
        "fields": fields,
        "free_text": {
            "id": "notes",
            "label": free_label,
            "placeholder": free_placeholder,
        },
        "submit_label": submit_label,
        "skip_label": skip_label,
    }


def _build_assess_prompt(
    question: str,
    entities: dict[str, Any],
    memory: InvestigationMemory,
    history: list[dict[str, str]],
) -> str:
    entity_lines = [
        f"- gene: {entities.get('gene') or 'unknown'}",
        f"- site/position: {entities.get('position') or 'unknown'}",
        f"- ptm_type: {entities.get('ptm_type') or 'unknown'}",
        f"- organism: {entities.get('organism') or memory.organism or 'unknown'}",
        f"- pmid: {entities.get('pmid') or 'none'}",
    ]
    hist = ""
    if history:
        tail = history[-4:]
        hist = "\n".join(f"{m.get('role', 'user')}: {m.get('content', '')[:300]}" for m in tail)
    memory_block = memory.to_prompt_block() or "(empty)"
    q = question.strip()
    wordish = len(q.split()) + len(re.findall(r"[\u4e00-\u9fff]", q))
    return (
        f"## Parsed entities\n" + "\n".join(entity_lines) + "\n\n"
        f"## Session memory\n{memory_block}\n\n"
        f"## Recent conversation\n{hist or '(none)'}\n\n"
        f"## Question brevity signal (hint only — you decide)\n"
        f"- characters: {len(q)}\n"
        f"- approximate tokens/words: {wordish}\n"
        f"- states investigative angle explicitly: unknown — use your judgment\n\n"
        f"## Current user question\n{question}\n"
    )


async def assess_clarification_need(
    llm: Any,
    question: str,
    entities: dict[str, Any],
    memory: InvestigationMemory,
    history: list[dict[str, str]],
    *,
    lang: str | None = None,
) -> dict[str, Any] | None:
    """Ask the LLM whether to show a clarification modal; return payload or None."""
    lang = lang or _detect_lang(question)
    prompt = _build_assess_prompt(question, entities, memory, history)

    def _call() -> str:
        result = llm.chat_completion(
            messages=[
                {"role": "system", "content": _ASSESS_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=800,
            disable_thinking=True,
        )
        return result.get("content") or ""

    try:
        raw = await asyncio.wait_for(asyncio.to_thread(_call), timeout=_CLARIFICATION_ASSESS_TIMEOUT_S)
    except Exception as exc:
        log_llm_fallback(
            "Clarification assessment",
            exc,
            timeout_s=_CLARIFICATION_ASSESS_TIMEOUT_S,
            detail="skipping clarification modal",
        )
        return None

    data = _parse_json_object(raw)
    if not data:
        logger.warning("Clarification assessment returned non-JSON: %s", raw[:200])
        return None

    payload = _normalize_clarification_payload(data, question, lang)
    if payload:
        logger.info("Clarification requested by LLM for: %s", question[:80])
    return payload


def build_literature_clarification_request(
    question: str,
    *,
    lang: str | None = None,
) -> dict[str, Any]:
    """Deterministic clarification when the user wants papers but no target is set."""
    lang = lang or _detect_lang(question)
    if lang == "zh":
        return {
            "intro": "为了推荐有针对性的文献，请补充您关注的蛋白、修饰位点或研究主题（也可跳过，系统将尽量检索）：",
            "original_question": question,
            "fields": [
                {
                    "id": "literature_focus",
                    "label": "您更关注哪类文献？",
                    "options": [
                        "位点机制与功能",
                        "上游激酶/调控",
                        "疾病与临床关联",
                        "实验/组学方法",
                        "领域综述",
                    ],
                    "option_values": [
                        "mechanism",
                        "kinase",
                        "disease",
                        "methods",
                        "review",
                    ],
                    "allow_custom": True,
                    "placeholder": "其他方向…",
                },
            ],
            "free_text": {
                "id": "notes",
                "label": "蛋白、位点或研究主题",
                "placeholder": "例如：TP53 S15 磷酸化、AKT1 S473、DNA 损伤应激下的 p53 修饰…",
            },
            "submit_label": "推荐文献",
            "skip_label": "跳过，直接检索",
        }
    return {
        "intro": (
            "To recommend relevant papers, please specify the protein/site or research topic "
            "(or skip and I will search with what you provided):"
        ),
        "original_question": question,
        "fields": [
            {
                "id": "literature_focus",
                "label": "What type of papers do you want?",
                "options": [
                    "Site mechanism & function",
                    "Upstream kinases/regulation",
                    "Disease & clinical links",
                    "Methods / omics",
                    "Field review",
                ],
                "option_values": ["mechanism", "kinase", "disease", "methods", "review"],
                "allow_custom": True,
                "placeholder": "Other focus…",
            },
        ],
        "free_text": {
            "id": "notes",
            "label": "Protein, site, or topic",
            "placeholder": "e.g. TP53 S15 phosphorylation, AKT1 S473, p53 under DNA damage…",
        },
        "submit_label": "Recommend papers",
        "skip_label": "Skip and search",
    }


def merge_clarification_answers(
    original_question: str,
    selections: dict[str, str],
    free_text: str = "",
) -> str:
    """Merge modal answers into an enriched research question."""
    notes = (free_text or "").strip()
    sel_parts = [v.strip() for v in selections.values() if v and str(v).strip()]

    if notes:
        if len(notes) >= max(20, len(original_question) * 0.5) or "?" in notes or "？" in notes:
            base = notes
        else:
            zh = bool(re.search(r"[\u4e00-\u9fff]", original_question + notes))
            base = f"{original_question.strip()}\n{'补充' if zh else 'Notes'}: {notes}"
    else:
        base = original_question.strip()

    if sel_parts:
        zh = bool(re.search(r"[\u4e00-\u9fff]", base))
        joined = "；".join(sel_parts) if zh else "; ".join(sel_parts)
        base = f"{base}\n{'研究侧重' if zh else 'Focus'}: {joined}"

    return base
