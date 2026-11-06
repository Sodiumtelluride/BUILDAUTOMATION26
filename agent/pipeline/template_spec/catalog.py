"""
The site template's contract, vendored from BUILD_TEMPLATE_REPO/lib/spec:

  - design-spec.schema.json  (npm run schema:export)   -> load_schema()
  - section-catalog.json     (npm run catalog:export)  -> load_catalog()

Never hand-edit the files under template/. tests/test_template_spec_catalog.py
checks them byte-for-byte against the template checkout when
BUILD_TEMPLATE_REPO is set.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

TEMPLATE_DIR = Path(__file__).parent / "template"


@dataclass(frozen=True)
class BlockDef:
    kind: str
    optional: bool = False


@dataclass(frozen=True)
class TemplateCatalog:
    types: Dict[str, Dict[str, BlockDef]]
    """section type id -> block id -> definition, in the template's order."""
    themes: Dict[str, Dict[str, str]]
    """theme id -> role -> section type id."""
    fonts: Tuple[str, ...]
    """font names the template bundles (the only values tokens.fonts may use)."""

    def required_blocks(self, type_id: str) -> List[str]:
        return [block_id for block_id, block in self.types[type_id].items() if not block.optional]

    def theme_of(self, type_id: str) -> Optional[str]:
        return next((theme for theme, roles in self.themes.items() if type_id in roles.values()), None)


@lru_cache(maxsize=1)
def load_catalog() -> TemplateCatalog:
    raw = json.loads((TEMPLATE_DIR / "section-catalog.json").read_text())
    types = {
        type_id: {block_id: BlockDef(kind=b["kind"], optional=bool(b.get("optional", False))) for block_id, b in blocks.items()}
        for type_id, blocks in raw["catalog"].items()
    }
    return TemplateCatalog(types=types, themes=raw["themes"], fonts=tuple(raw["fonts"]))


@lru_cache(maxsize=1)
def load_schema() -> Dict[str, Any]:
    schema: Dict[str, Any] = json.loads((TEMPLATE_DIR / "design-spec.schema.json").read_text())
    return schema
