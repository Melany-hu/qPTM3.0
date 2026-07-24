"""External PTM data-source pipeline.

Each database under data/<aspect>/<SourceName>/ carries a SOURCE.yaml manifest.
This package loads manifests, resolves local paths / API bases, and provides
helpers for tools + citations.

Adding a new source
-------------------
1. Pick aspect folder (e.g. disease_drug/).
2. Create data/<aspect>/<SourceName>/ with raw files (and optional indexes/).
3. Add SOURCE.yaml (see ActiveDriverDB for a template).
4. Implement app/tools/<name>_tools.py using SourceCatalog + LocalTableIndex.
5. Register tool + planner routing + citation branch.
6. Rebuild index if needed: python -m app.sources.build_index <source_id>
"""

from __future__ import annotations

from app.sources.catalog import SourceCatalog, get_catalog
from app.sources.models import AccessMode, DataFile, SourceManifest

__all__ = [
    "AccessMode",
    "DataFile",
    "SourceCatalog",
    "SourceManifest",
    "get_catalog",
]
