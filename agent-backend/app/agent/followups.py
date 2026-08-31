"""Follow-up question suggestions after each assistant reply."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from app.agent.memory import InvestigationMemory

logger = logging.getLogger(__name__)

_NEXT_STEP_SECTION_RE = re.compile(
    r"##\s*(?:Next step|后续问题|下一步)\s*\n([\s\S]*?)(?=\n##\s|\Z)",
    re.I,
)
_BULLET_RE = re.compile(r"^[\-\*\d.]+\s*")


def extract_followups_from_answer(text: str) -> list[str]:
    """Parse follow-up questions from a ## Next step / ## 后续问题 section."""
    match = _NEXT_STEP_SECTION_RE.search(text or "")
    if not match:
        return []
    out: list[str] = []
    for line in match.group(1).splitlines():
        raw = line.strip()
        if not raw:
            continue
        q = _BULLET_RE.sub("", raw).strip()
        q = re.sub(r"\*\*(.+?)\*\*", r"\1", q)
        if len(q) >= 8 and q not in out:
            out.append(q)
    return out[:4]


def strip_followup_section(text: str) -> str:
    """Remove the follow-up heading block from answer markdown."""
    return _NEXT_STEP_SECTION_RE.sub("", text or "").rstrip()


def _detect_lang(question: str) -> str:
    zh = sum(1 for ch in question if "\u4e00" <= ch <= "\u9fff")
    latin = sum(1 for ch in question if "a" <= ch.lower() <= "z")
    return "zh" if zh >= 2 and zh >= latin * 0.35 else "en"


def _parse_json_questions(raw: str) -> list[str]:
    text = (raw or "").strip()
    if not text:
        return []
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    items = data if isinstance(data, list) else data.get("questions") or []
    out: list[str] = []
    for item in items:
        if isinstance(item, str):
            q = item.strip()
            if len(q) >= 8 and q not in out:
                out.append(q)
    return out[:4]


async def _llm_followups(
    llm: Any,
    question: str,
    answer: str,
    memory: InvestigationMemory,
    lang: str,
) -> list[str]:
    ctx = memory.to_prompt_block()
    has_target = memory.has_target
    if lang == "zh":
        target_rule = (
            "- 上下文已有蛋白位点：每个问题必须包含该基因与位点，适合数据库检索\n"
            if has_target
            else "- 上下文无具体位点：生成机制/领域层面的科普问题（可直接回答，不要要求用户补充位点）；"
            "也可给 1 个带示例位点的深入问题（如 TP53 S15…）"
        )
        prompt = (
            "你是 qPTM 研究助手。根据用户问题和助手刚给出的回答，生成 3 个可点击的后续问题。\n"
            "要求：\n"
            "- 每个问题是一句完整中文问句（15–80字）\n"
            f"- {target_rule}\n"
            "- 问题必须与当前对话主题紧密相关，不要套用通用模板\n"
            "- 不要生成需要用户「补充蛋白/位点才能回答」的空泛问题\n"
            "- 只输出 JSON 数组，例如：[\"问题1\",\"问题2\",\"问题3\"]\n\n"
            f"调查上下文：\n{ctx}\n\n"
            f"用户问题：{question}\n\n"
            f"助手回答（摘要）：{(answer or '')[:2500]}\n"
        )
    else:
        target_rule = (
            "Each question must include the gene and site from context (database lookup)."
            if has_target
            else "Generate conceptual/mechanism questions answerable without a site, "
            "or one drill-down with an example site (e.g. TP53 S15)."
        )
        prompt = (
            "You are qPTM Agent. Generate 3 clickable follow-up questions.\n"
            "Rules:\n"
            "- Each item is one full question (15–80 words)\n"
            f"- {target_rule}\n"
            "- Questions must be specific to this conversation — no generic templates\n"
            "- Do NOT ask the user to supply a missing gene/site\n"
            "- Output ONLY a JSON array\n\n"
            f"Investigation context:\n{ctx}\n\n"
            f"User question: {question}\n\n"
            f"Assistant answer (excerpt): {(answer or '')[:2500]}\n"
        )

    def _call() -> str:
        result = llm.chat_completion(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,
            max_tokens=512,
            disable_thinking=True,
        )
        return result.get("content") or ""

    try:
        raw = await asyncio.wait_for(asyncio.to_thread(_call), timeout=18.0)
        parsed = _parse_json_questions(raw)
        if len(parsed) >= 2:
            return parsed[:3]
    except Exception as exc:
        logger.warning("Follow-up LLM failed: %s", exc)
    return []


async def generate_follow_up_questions(
    question: str,
    answer: str,
    memory: InvestigationMemory,
    mode: str,
    llm: Any | None,
) -> list[str]:
    """Return 2–3 follow-up questions for the UI panel.

    Sources (in order):
    1. ``## 后续问题`` / ``## Next step`` section in the assistant answer
    2. LLM generation from question + answer + session context
    3. Empty — no panel (never use canned template questions)
    """
    del mode  # reserved for future mode-specific prompts
    extracted = extract_followups_from_answer(answer)
    if len(extracted) >= 2:
        return extracted[:3]

    if llm is not None and (answer or "").strip():
        llm_qs = await _llm_followups(llm, question, answer, memory, _detect_lang(question))
        if len(llm_qs) >= 2:
            return llm_qs[:3]

    return []
