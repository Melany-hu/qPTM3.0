"""Query helpers for SQLite indexes built by build_index."""

from __future__ import annotations

import sqlite3
from typing import Any

from app.sources.build_index import index_path_for
from app.sources.catalog import get_catalog
from app.sources.models import DataFile, SourceManifest


def open_index(manifest: SourceManifest, file_meta: DataFile) -> sqlite3.Connection | None:
    path = index_path_for(manifest, file_meta)
    if not path.exists():
        return None
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def _table_columns(conn: sqlite3.Connection) -> set[str]:
    return {r[1] for r in conn.execute("PRAGMA table_info(records)")}


def query_by_gene(
    source_id: str,
    file_id: str,
    gene: str,
    *,
    site_position: int | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Look up rows for a gene (optional site filter) from a built index."""
    manifest = get_catalog().require(source_id)
    meta = manifest.file_by_id(file_id)
    if meta is None:
        raise KeyError(f"Unknown file id {file_id} for {source_id}")

    conn = open_index(manifest, meta)
    if conn is None:
        raise FileNotFoundError(
            f"Index missing for {source_id}/{file_id}. "
            f"Run: python -m app.sources.build_index {source_id}"
        )

    gene_u = gene.strip().upper()
    try:
        cols = _table_columns(conn)
        params: list[Any] = []
        where: list[str] = []

        if "gene" in cols:
            where.append('UPPER("gene") = ?')
            params.append(gene_u)
        elif "target_symbol" in cols:
            where.append('UPPER("target_symbol") = ?')
            params.append(gene_u)
        else:
            return []

        if site_position is not None:
            if "site_position" in cols:
                where.append('"site_position" = ?')
                params.append(str(site_position))
            elif "target_sequence_position" in cols:
                where.append('"target_sequence_position" = ?')
                params.append(str(site_position))

        sql = f'SELECT * FROM records WHERE {" AND ".join(where)} LIMIT ?'
        params.append(limit)
        cur = conn.execute(sql, params)
        return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


def query_records(
    source_id: str,
    file_id: str,
    *,
    equals: dict[str, str] | None = None,
    equals_ci: dict[str, str] | None = None,
    like_prefix_ci: dict[str, str] | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Generic equality filters against a built SQLite index.

    equals: case-sensitive column = value
    equals_ci: UPPER(column) = UPPER(value)
    like_prefix_ci: UPPER(column) LIKE UPPER(value) || '%'
    """
    manifest = get_catalog().require(source_id)
    meta = manifest.file_by_id(file_id)
    if meta is None:
        raise KeyError(f"Unknown file id {file_id} for {source_id}")

    conn = open_index(manifest, meta)
    if conn is None:
        raise FileNotFoundError(
            f"Index missing for {source_id}/{file_id}. "
            f"Run: python -m app.sources.build_index {source_id}"
        )

    try:
        cols = _table_columns(conn)
        where: list[str] = []
        params: list[Any] = []

        for col, val in (equals or {}).items():
            if col not in cols:
                continue
            where.append(f'"{col}" = ?')
            params.append(str(val))

        for col, val in (equals_ci or {}).items():
            if col not in cols:
                continue
            where.append(f'UPPER("{col}") = ?')
            params.append(str(val).strip().upper())

        for col, val in (like_prefix_ci or {}).items():
            if col not in cols:
                continue
            where.append(f'UPPER("{col}") LIKE ?')
            params.append(str(val).strip().upper() + "%")

        if not where:
            return []

        sql = f'SELECT * FROM records WHERE {" AND ".join(where)} LIMIT ?'
        params.append(limit)
        cur = conn.execute(sql, params)
        return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


def index_exists(source_id: str, file_id: str) -> bool:
    manifest = get_catalog().get(source_id)
    if not manifest:
        return False
    meta = manifest.file_by_id(file_id)
    if not meta:
        return False
    return index_path_for(manifest, meta).exists()
