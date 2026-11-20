"""
The same design spec in every theme family.

The model picks one family (``family_of``). Because every family fills the same
roles (hero, programs, stats, team, cta, story, page-header) and shares block ids
per role, the other families follow mechanically: each themed section's type id
moves to the target family's type for its role, and its content blocks are the
blocks that type declares. Base sections (donate, contact-block, ...) have one
look everywhere and are left alone.

Where the template ships a theme preset (lib/spec/theme-presets/<family>.json),
the variant takes the preset's fonts and radius, which that family was designed
with. Colors stay the client's.
"""

from __future__ import annotations

import copy
from collections import Counter
from typing import Any, Dict, Mapping, Optional

from .catalog import TemplateCatalog, load_catalog, load_presets
from .prompt import MAX_CHARS


def family_of(spec: Mapping[str, Any], catalog: Optional[TemplateCatalog] = None) -> Optional[str]:
    """The family most themed sections belong to; None when the spec has only base sections."""
    catalog = catalog or load_catalog()
    counts = Counter(
        family
        for page in spec["pages"]
        for section in page["sections"]
        if (family := catalog.theme_of(section["type"])) is not None
    )
    return counts.most_common(1)[0][0] if counts else None


def _moved_section(section: Mapping[str, Any], new_type: str, catalog: TemplateCatalog) -> Dict[str, Any]:
    declared = {block["id"]: block for block in section["content_blocks"]}
    blocks = []
    for block_id, block in catalog.types[new_type].items():
        if block_id in declared:
            blocks.append(copy.deepcopy(declared[block_id]))
        elif not block.optional:
            new_block: Dict[str, Any] = {"id": block_id, "kind": block.kind}
            if block.kind in MAX_CHARS:
                new_block["max_chars"] = MAX_CHARS[block.kind]
            blocks.append(new_block)
    moved = copy.deepcopy(dict(section))
    moved["type"] = new_type
    moved["content_blocks"] = blocks
    return moved


def spec_in_family(spec: Mapping[str, Any], family: str, catalog: Optional[TemplateCatalog] = None) -> Dict[str, Any]:
    """A deep copy of ``spec`` whose themed sections use ``family``'s type ids."""
    catalog = catalog or load_catalog()
    if family not in catalog.themes:
        raise ValueError(f"unknown theme family {family!r}; the template has {', '.join(catalog.themes)}")
    roles = catalog.themes[family]
    out = copy.deepcopy(dict(spec))
    for page in out["pages"]:
        page["sections"] = [
            section if (role := catalog.role_of(section["type"])) is None or roles[role] == section["type"] else _moved_section(section, roles[role], catalog)
            for section in page["sections"]
        ]
    preset = load_presets().get(family)
    if preset is not None:
        out["tokens"]["fonts"] = dict(preset["fonts"])
        out["tokens"]["radius"] = preset["radius"]
    return out


def specs_in_every_family(spec: Mapping[str, Any], catalog: Optional[TemplateCatalog] = None) -> Dict[str, Dict[str, Any]]:
    """family -> spec, in the catalog's family order."""
    catalog = catalog or load_catalog()
    return {family: spec_in_family(spec, family, catalog) for family in catalog.themes}
