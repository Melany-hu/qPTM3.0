"""Minimal stdio MCP server for qPTM tools (Python 3.9+)."""

from __future__ import annotations

import json
import logging
import sys
from typing import Any

from app.sources.catalog import get_catalog
from app.tools.register_all import register_all_tools
from mcp_tools import qptm_get, qptm_invoke, qptm_search

logger = logging.getLogger(__name__)

PROTO_VERSION = "2024-11-05"


def _send(msg: dict[str, Any]) -> None:
    body = json.dumps(msg, ensure_ascii=False)
    sys.stdout.write(f"Content-Length: {len(body.encode('utf-8'))}\r\n\r\n{body}")
    sys.stdout.flush()


def _read_message() -> dict[str, Any] | None:
    headers: dict[str, str] = {}
    while True:
        line = sys.stdin.readline()
        if not line:
            return None
        line = line.strip()
        if not line:
            break
        if ":" in line:
            k, v = line.split(":", 1)
            headers[k.strip().lower()] = v.strip()
    length = int(headers.get("content-length", "0"))
    if length <= 0:
        return None
    raw = sys.stdin.read(length)
    return json.loads(raw)


def _tool_definitions() -> list[dict[str, Any]]:
    return [
        {
            "name": "qptm_search",
            "description": "Search qPTM-integrated PTM databases by entity.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "entity": {"type": "string"},
                    "query": {"type": "string"},
                    "gene": {"type": "string"},
                    "position": {"type": "integer"},
                    "uniprot_ac": {"type": "string"},
                },
                "required": ["entity", "query"],
            },
        },
        {
            "name": "qptm_get",
            "description": "Get focused PTM record details.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "entity": {"type": "string"},
                    "id": {"type": "string"},
                    "section": {"type": "string"},
                },
                "required": ["entity", "id"],
            },
        },
        {
            "name": "qptm_invoke",
            "description": "Direct invoke of a registered tool by name.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "tool_name": {"type": "string"},
                    "arguments_json": {"type": "string"},
                },
                "required": ["tool_name"],
            },
        },
    ]


def _handle(msg: dict[str, Any]) -> None:
    method = msg.get("method")
    req_id = msg.get("id")
    params = msg.get("params") or {}

    if method == "initialize":
        _send(
            {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": PROTO_VERSION,
                    "capabilities": {"tools": {}, "resources": {}},
                    "serverInfo": {"name": "qptm-mcp", "version": "1.0.0"},
                },
            }
        )
        return

    if method == "notifications/initialized":
        return

    if method == "tools/list":
        _send({"jsonrpc": "2.0", "id": req_id, "result": {"tools": _tool_definitions()}})
        return

    if method == "resources/list":
        _send(
            {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "resources": [
                        {
                            "uri": "qptm://sources",
                            "name": "qPTM source catalog",
                            "mimeType": "text/plain",
                        }
                    ]
                },
            }
        )
        return

    if method == "resources/read":
        uri = params.get("uri")
        text = get_catalog().llm_catalog_text() if uri == "qptm://sources" else ""
        _send(
            {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"contents": [{"uri": uri, "mimeType": "text/plain", "text": text}]},
            }
        )
        return

    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        try:
            if name == "qptm_search":
                text = qptm_search(
                    args.get("entity", "site"),
                    args.get("query", ""),
                    args.get("gene", ""),
                    int(args.get("position") or 0),
                    args.get("uniprot_ac", ""),
                )
            elif name == "qptm_get":
                text = qptm_get(args.get("entity", ""), args.get("id", ""), args.get("section", ""))
            elif name == "qptm_invoke":
                text = qptm_invoke(args.get("tool_name", ""), args.get("arguments_json", "{}"))
            else:
                text = json.dumps({"success": False, "summary": f"Unknown tool {name}"})
            _send(
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {"content": [{"type": "text", "text": text}], "isError": False},
                }
            )
        except Exception as exc:
            _send(
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": str(exc)}],
                        "isError": True,
                    },
                }
            )
        return

    if req_id is not None:
        _send({"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Unknown method {method}"}})


def main() -> None:
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    register_all_tools()
    while True:
        msg = _read_message()
        if msg is None:
            break
        _handle(msg)


if __name__ == "__main__":
    main()
