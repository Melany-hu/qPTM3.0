"""Logging helpers when LLM calls fail and code falls back."""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)


def log_llm_fallback(
    component: str,
    exc: BaseException,
    *,
    timeout_s: float | None = None,
    detail: str = "",
) -> None:
    """Log why an LLM call was skipped in favour of a heuristic fallback."""
    if isinstance(exc, asyncio.TimeoutError):
        msg = f"{component} LLM timed out after {timeout_s:g}s"
    else:
        msg = f"{component} LLM failed ({type(exc).__name__}): {exc}"
    if detail:
        msg = f"{msg}; {detail}"
    logger.warning("%s — using fallback", msg)
