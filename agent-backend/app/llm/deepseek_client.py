"""OpenCode LLM client with function calling and model fallbacks.

Uses the OpenAI Python SDK against OpenCode Go / Zen OpenAI-compatible endpoints.
Supports streaming responses via SSE for real-time chat.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Iterator

from openai import OpenAI
import httpx

from app.config import settings
from app.llm.model_routing import base_url_for_model, model_chain

logger = logging.getLogger(__name__)


class DeepSeekClient:
    """Wrapper around OpenCode's OpenAI-compatible API with fallback models."""

    def __init__(self) -> None:
        # Hard caps so a stalled upstream provider cannot hang the chat UI forever.
        # connect: TCP/TLS; read: idle between stream chunks / full response body.
        self._timeout = httpx.Timeout(
            connect=10.0,
            read=float(getattr(settings, "llm_read_timeout_seconds", 120) or 120),
            write=30.0,
            pool=10.0,
        )
        self._clients: dict[str, OpenAI] = {}
        self.model = settings.deepseek_model
        self.models = model_chain(
            settings.deepseek_model,
            getattr(settings, "deepseek_fallback_models", None),
        )
        self._go_base = settings.deepseek_base_url.rstrip("/")
        self._zen_base = (
            getattr(settings, "deepseek_zen_base_url", None)
            or "https://opencode.ai/zen/v1"
        ).rstrip("/")

    def _client_for(self, model: str) -> OpenAI:
        base = base_url_for_model(model, self._go_base, self._zen_base)
        cached = self._clients.get(base)
        if cached is not None:
            return cached
        client = OpenAI(
            api_key=settings.deepseek_api_key,
            base_url=base,
            timeout=self._timeout,
            max_retries=0,
        )
        self._clients[base] = client
        return client

    def chat_completion(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        *,
        disable_thinking: bool = False,
    ) -> dict[str, Any]:
        """Non-streaming completion with optional function calling.

        Tries primary then fallback models on request failure / empty content.
        """
        errors: list[str] = []
        for i, model in enumerate(self.models):
            try:
                result = self._chat_completion_once(
                    model,
                    messages,
                    tools=tools,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    disable_thinking=disable_thinking,
                )
            except Exception as exc:
                msg = f"{model}: {type(exc).__name__}: {exc}"
                errors.append(msg)
                logger.warning("LLM completion failed (%s); trying next", msg)
                continue

            if result.get("content") or result.get("tool_calls"):
                if i > 0:
                    logger.info("LLM fallback succeeded with model=%s", model)
                return result

            errors.append(f"{model}: empty content (finish_reason={result.get('finish_reason')})")
            logger.warning(
                "LLM returned empty content for model=%s; trying next",
                model,
            )

        raise RuntimeError(
            "All LLM models failed. "
            + " | ".join(errors[-5:] or ["no models configured"])
        )

    def _chat_completion_once(
        self,
        model: str,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None,
        temperature: float,
        max_tokens: int,
        disable_thinking: bool,
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        if disable_thinking:
            # deepseek-v4-flash otherwise spends the token budget on reasoning_content
            # and can finish with empty visible content (finish_reason=length).
            kwargs["extra_body"] = {"thinking": {"type": "disabled"}}

        response = self._client_for(model).chat.completions.create(**kwargs)
        choice = response.choices[0]
        return {
            "role": choice.message.role,
            "content": choice.message.content,
            "tool_calls": self._parse_tool_calls(choice.message.tool_calls),
            "finish_reason": choice.finish_reason,
            "model": model,
        }

    def chat_completion_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.3,
        max_tokens: int = 8192,
        *,
        disable_thinking: bool = False,
    ) -> Iterator[dict[str, Any]]:
        """Streaming completion that yields events.

        Yields dicts:
          - {"type": "text", "content": "..."} for text chunks
          - {"type": "tool_call", "name": "...", "arguments": {...}} for tool calls
          - {"type": "done", "finish_reason": "..."} when complete
          - {"type": "error", "message": "..."} when all models fail
        """
        errors: list[str] = []
        for i, model in enumerate(self.models):
            if i > 0:
                logger.info("LLM stream falling back to model=%s", model)
            outcome = "fail"
            try:
                for event in self._chat_completion_stream_once(
                    model,
                    messages,
                    tools=tools,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    disable_thinking=disable_thinking,
                ):
                    if event.get("type") == "_fallback":
                        errors.append(f"{model}: {event.get('message', 'failed')}")
                        outcome = "fail"
                        break
                    if event.get("type") == "done":
                        outcome = "ok"
                    yield event
            except Exception as exc:
                msg = f"{type(exc).__name__}: {exc}"
                errors.append(f"{model}: {msg}")
                logger.warning("LLM stream failed for model=%s: %s", model, msg)
                outcome = "fail"

            if outcome == "ok":
                return

        yield {
            "type": "error",
            "message": (
                "LLM request timed out or failed while generating the answer. "
                + " | ".join(errors[-3:] or ["no models configured"])
            ),
        }
        yield {"type": "done", "finish_reason": "error"}

    def _chat_completion_stream_once(
        self,
        model: str,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None,
        temperature: float,
        max_tokens: int,
        disable_thinking: bool,
    ) -> Iterator[dict[str, Any]]:
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        if disable_thinking:
            kwargs["extra_body"] = {"thinking": {"type": "disabled"}}

        try:
            stream = self._client_for(model).chat.completions.create(**kwargs)
        except Exception as exc:
            yield {
                "type": "_fallback",
                "message": f"start failed ({type(exc).__name__}: {exc})",
            }
            return

        tool_call_buffers: dict[int, dict[str, Any]] = {}
        emitted_useful = False
        last_finish: str | None = None

        try:
            for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                finish_reason = chunk.choices[0].finish_reason
                if finish_reason:
                    last_finish = finish_reason

                if delta.content:
                    emitted_useful = True
                    yield {"type": "text", "content": delta.content}

                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index
                        if idx not in tool_call_buffers:
                            tool_call_buffers[idx] = {
                                "id": tc.id,
                                "name": "",
                                "arguments_str": "",
                            }
                        if tc.function:
                            if tc.function.name:
                                tool_call_buffers[idx]["name"] = tc.function.name
                            if tc.function.arguments:
                                tool_call_buffers[idx]["arguments_str"] += tc.function.arguments

                if finish_reason:
                    for idx in sorted(tool_call_buffers):
                        buf = tool_call_buffers[idx]
                        try:
                            args = json.loads(buf["arguments_str"]) if buf["arguments_str"] else {}
                        except json.JSONDecodeError:
                            logger.warning(
                                "Failed to parse tool call arguments: %s",
                                buf["arguments_str"],
                            )
                            args = {}
                        emitted_useful = True
                        yield {
                            "type": "tool_call",
                            "id": buf["id"],
                            "name": buf["name"],
                            "arguments": args,
                        }

                    if not emitted_useful:
                        yield {
                            "type": "_fallback",
                            "message": (
                                f"empty content (finish_reason={last_finish or 'unknown'})"
                            ),
                        }
                        return

                    yield {"type": "done", "finish_reason": finish_reason}
                    return
        except Exception as exc:
            if emitted_useful:
                # Already streamed partial answer — do not restart with another model.
                logger.error("LLM stream aborted after output: %s", exc, exc_info=True)
                yield {
                    "type": "error",
                    "message": (
                        "LLM request timed out or failed while generating the answer. "
                        f"({type(exc).__name__}: {exc})"
                    ),
                }
                yield {"type": "done", "finish_reason": "error"}
                return
            yield {
                "type": "_fallback",
                "message": f"stream aborted ({type(exc).__name__}: {exc})",
            }

    @staticmethod
    def _parse_tool_calls(tool_calls) -> list[dict[str, Any]]:
        """Parse tool_calls from a non-streaming response."""
        if not tool_calls:
            return []
        result = []
        for tc in tool_calls:
            try:
                args = json.loads(tc.function.arguments) if tc.function.arguments else {}
            except (json.JSONDecodeError, AttributeError):
                args = {}
            result.append({
                "id": tc.id,
                "name": tc.function.name,
                "arguments": args,
            })
        return result


# Singleton
_client: DeepSeekClient | None = None


def get_llm_client() -> DeepSeekClient:
    global _client
    if _client is None:
        _client = DeepSeekClient()
    return _client
