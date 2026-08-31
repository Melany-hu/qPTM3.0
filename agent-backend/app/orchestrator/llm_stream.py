"""Shared streaming + interpret helpers."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, AsyncGenerator

from app.agent.llm_fallback import log_llm_fallback

logger = logging.getLogger(__name__)


async def stream_llm_events(
    llm: Any,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    *,
    max_tokens: int = 8192,
    disable_thinking: bool = True,
) -> AsyncGenerator[dict[str, Any], None]:
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[Any] = asyncio.Queue()

    def _producer() -> None:
        try:
            for event in llm.chat_completion_stream(
                messages,
                tools=tools,
                max_tokens=max_tokens,
                disable_thinking=disable_thinking,
            ):
                loop.call_soon_threadsafe(queue.put_nowait, event)
        except Exception as exc:
            logger.error("LLM stream error: %s", exc, exc_info=True)
            loop.call_soon_threadsafe(queue.put_nowait, {"type": "error", "message": str(exc)})
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)

    loop.run_in_executor(None, _producer)
    while True:
        event = await queue.get()
        if event is None:
            break
        yield event


def parse_json_object(raw: str) -> dict[str, Any] | None:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None


async def llm_json(
    llm: Any,
    system: str,
    user: str,
    *,
    max_tokens: int = 1200,
    timeout_s: float = 12.0,
) -> dict[str, Any] | None:
    def _call() -> str:
        r = llm.chat_completion(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.1,
            max_tokens=max_tokens,
            disable_thinking=True,
        )
        return r.get("content") or ""

    try:
        raw = await asyncio.wait_for(asyncio.to_thread(_call), timeout=timeout_s)
    except Exception as exc:
        log_llm_fallback("llm_json", exc, timeout_s=timeout_s)
        return None
    parsed = parse_json_object(raw)
    if raw and not parsed:
        logger.info("llm_json returned unparseable JSON; caller will use non-LLM fallback")
    return parsed
