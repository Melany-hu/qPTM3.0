"""Load SOURCE.yaml manifests from data/<aspect>/<Source>/."""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from app.config import settings
from app.sources.models import SourceManifest

logger = logging.getLogger(__name__)

_ASPECT_DIRS = (
    "enzymes",
    "regulation",
    "interactions",
    "pathways",
    "domains",
    "stability",
    "phase_separation",
    "disease",
    "drug",
    "disease_drug",  # legacy alias if any leftovers
    "localization",
)


class SourceCatalog:
    """In-memory registry of all SOURCE.yaml manifests."""

    def __init__(self, sources: dict[str, SourceManifest]) -> None:
        self._sources = sources

    def get(self, source_id: str) -> SourceManifest | None:
        return self._sources.get(source_id)

    def require(self, source_id: str) -> SourceManifest:
        src = self.get(source_id)
        if src is None:
            raise KeyError(f"Unknown source: {source_id}")
        return src

    def by_aspect(self, aspect: str) -> list[SourceManifest]:
        return [s for s in self._sources.values() if s.aspect == aspect]

    def by_tool(self, tool_name: str) -> SourceManifest | None:
        for s in self._sources.values():
            if tool_name in s.tools:
                return s
        return None

    def all(self) -> list[SourceManifest]:
        return list(self._sources.values())

    def llm_catalog_text(self) -> str:
        """Compact catalog text for planning / synthesis prompts."""
        lines = []
        for s in sorted(self._sources.values(), key=lambda x: (x.aspect, x.id)):
            access = s.access.value
            lines.append(
                f"- **{s.name}** (`{s.id}`) · aspect=`{s.aspect}` · access=`{access}`\n"
                f"  {s.description.strip()[:280]}\n"
                f"  tools={', '.join(s.tools) or '—'} · "
                f"homepage={s.homepage or '—'} · api={s.api_docs or s.api_base or '—'}"
            )
        return "\n".join(lines) if lines else "(No SOURCE.yaml manifests found.)"


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"SOURCE.yaml must be a mapping: {path}")
    return data


def discover_sources(data_root: Path | None = None) -> dict[str, SourceManifest]:
    root = Path(data_root or settings.data_root)
    found: dict[str, SourceManifest] = {}

    for aspect in _ASPECT_DIRS:
        aspect_dir = root / aspect
        if not aspect_dir.is_dir():
            continue
        for child in sorted(aspect_dir.iterdir()):
            if not child.is_dir() or child.name.startswith("."):
                continue
            manifest_path = child / "SOURCE.yaml"
            if not manifest_path.exists():
                continue
            try:
                raw = _load_yaml(manifest_path)
                raw.setdefault("aspect", aspect)
                raw.setdefault("id", child.name.lower().replace(" ", "_"))
                manifest = SourceManifest.model_validate(raw)
                manifest.root = child.resolve()
                if manifest.id in found:
                    logger.warning(
                        "Duplicate source id %s at %s (keeping first)",
                        manifest.id, child,
                    )
                    continue
                found[manifest.id] = manifest
                logger.info("Loaded source manifest: %s (%s)", manifest.id, child)
            except Exception as e:
                logger.error("Failed to load %s: %s", manifest_path, e)

    return found


@lru_cache(maxsize=1)
def get_catalog() -> SourceCatalog:
    return SourceCatalog(discover_sources())


def reload_catalog() -> SourceCatalog:
    get_catalog.cache_clear()
    return get_catalog()
