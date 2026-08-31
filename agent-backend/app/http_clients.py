"""Shared HTTP clients for external API calls (connection reuse)."""

from __future__ import annotations

import httpx

from app.config import settings

_uniprot_client: httpx.Client | None = None


def get_uniprot_client() -> httpx.Client:
    """Process-wide UniProt REST client."""
    global _uniprot_client
    if _uniprot_client is None:
        _uniprot_client = httpx.Client(
            timeout=float(settings.http_timeout_seconds),
            headers={"Accept": "application/json"},
        )
    return _uniprot_client
