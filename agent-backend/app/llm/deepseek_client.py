"""DeepSeek V3 LLM client with function calling support.

Uses the OpenAI Python SDK pointed at DeepSeek's OpenAI-compatible endpoint.
Supports streaming responses via SSE for real-time chat.
"""

import json
import logging
from typing import Any

from openai import OpenAI

from app.config import settings

logger = logging.getLogger(__name__)


class DeepSeekClient:
    """Wrapper around DeepSeek's OpenAI-compatible API."""

    def __init__(self) -> None:
        self._client = OpenAI(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
        )
        self.model = settings.deepseek_model

    def chat_completion(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> dict[str, Any]:
        """Non-streaming completion with optional function calling.

        Returns the full response dict including message content and tool_calls.
        """
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        response = self._client.chat.completions.create(**kwargs)
        choice = response.choices[0]
        return {
            "role": choice.message.role,
            "content": choice.message.content,
            "tool_calls": self._parse_tool_calls(choice.message.tool_calls),
            "finish_reason": choice.finish_reason,
        }

    def chat_completion_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ):
        """Streaming completion that yields events.

        Yields dicts:
          - {"type": "text", "content": "..."} for text chunks
          - {"type": "tool_call", "name": "...", "arguments": {...}} for tool calls
          - {"type": "done", "finish_reason": "..."} when complete
        """
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        stream = self._client.chat.completions.create(**kwargs)

        # Accumulate tool call arguments across chunks
        tool_call_buffers: dict[int, dict[str, Any]] = {}

        for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            finish_reason = chunk.choices[0].finish_reason

            # Text content
            if delta.content:
                yield {"type": "text", "content": delta.content}

            # Tool calls (may arrive in fragments)
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

            # On finish, emit any accumulated tool calls
            if finish_reason:
                for idx in sorted(tool_call_buffers):
                    buf = tool_call_buffers[idx]
                    try:
                        args = json.loads(buf["arguments_str"]) if buf["arguments_str"] else {}
                    except json.JSONDecodeError:
                        logger.warning(f"Failed to parse tool call arguments: {buf['arguments_str']}")
                        args = {}
                    yield {
                        "type": "tool_call",
                        "id": buf["id"],
                        "name": buf["name"],
                        "arguments": args,
                    }
                yield {"type": "done", "finish_reason": finish_reason}
                break

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
