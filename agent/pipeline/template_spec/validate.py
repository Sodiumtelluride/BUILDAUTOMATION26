"""
Validate a candidate design spec the way the site template will.

Mirrors BUILD_TEMPLATE_REPO/lib/spec/schema.ts (Zod + superRefine) and the
font whitelist of scripts/apply-tokens.mjs, so the API path can retry with
specific issues and the manual path gets a reason without leaving Python.
The template's own `next build` remains the acceptance test.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence

import jsonschema

from .catalog import TemplateCatalog, load_catalog, load_schema

MEMBER_FORM_TYPE = "member-application-form"
FORM_RECIPE = "form_submissions"
BODY_FONT = "Inter"


def _path(parts: Sequence[Any]) -> str:
    out = ""
    for part in parts:
        out += f"[{part}]" if isinstance(part, int) else (f".{part}" if out else str(part))
    return out or "(root)"


def _schema_issues(spec: Mapping[str, Any]) -> List[str]:
    validator = jsonschema.Draft202012Validator(load_schema())
    errors = sorted(validator.iter_errors(spec), key=lambda e: list(map(str, e.absolute_path)))
    return [f"{_path(list(e.absolute_path))}: {e.message}" for e in errors]


def _section_issues(spec: Mapping[str, Any], catalog: TemplateCatalog) -> List[str]:
    issues: List[str] = []
    seen_ids: set[str] = set()
    for p, page in enumerate(spec["pages"]):
        for s, section in enumerate(page["sections"]):
            at = f"pages[{p}].sections[{s}]"
            if section["id"] in seen_ids:
                issues.append(f"{at}.id: duplicate section id {section['id']}")
            seen_ids.add(section["id"])
            type_id = section["type"]
            blocks = catalog.types.get(type_id)
            if blocks is None:
                issues.append(f"{at}.type: unknown section type '{type_id}'")
                continue
            declared: Dict[str, Mapping[str, Any]] = {b["id"]: b for b in section["content_blocks"]}
            for block_id in catalog.required_blocks(type_id):
                if block_id not in declared:
                    issues.append(f"{at}.content_blocks: missing required block {block_id}")
            for i, block in enumerate(section["content_blocks"]):
                expected = blocks.get(block["id"])
                if expected is None:
                    issues.append(f"{at}.content_blocks[{i}].id: {block['id']} is not a block of {type_id}")
                elif block["kind"] != expected.kind:
                    issues.append(f"{at}.content_blocks[{i}].kind: {block['id']} must be {expected.kind}, got {block['kind']}")
            if type_id == MEMBER_FORM_TYPE and not any(d["recipe"] == FORM_RECIPE for d in spec["data_requirements"]):
                issues.append(f"{at}.type: {MEMBER_FORM_TYPE} requires data_requirements {FORM_RECIPE}")
    return issues


def _font_issues(spec: Mapping[str, Any], catalog: TemplateCatalog) -> List[str]:
    issues: List[str] = []
    fonts = spec["tokens"]["fonts"]
    allowed = ", ".join(catalog.fonts)
    for role in ("heading", "body"):
        if fonts[role] not in catalog.fonts:
            issues.append(f"tokens.fonts.{role}: {fonts[role]!r} is not bundled; allowed: {allowed}")
    if fonts["body"] in catalog.fonts and fonts["body"] != BODY_FONT:
        issues.append(f"tokens.fonts.body: must be {BODY_FONT}")
    return issues


def _page_issues(spec: Mapping[str, Any], requested_slugs: Sequence[str]) -> List[str]:
    present = [page["slug"] for page in spec["pages"]]
    issues = [f"pages: missing requested page {slug}" for slug in requested_slugs if slug not in present]
    issues += [f"pages: {slug} was not requested" for slug in present if slug not in requested_slugs]
    return issues


def validate_template_spec(spec: Mapping[str, Any], *, requested_slugs: Optional[Sequence[str]] = None) -> List[str]:
    """Return every problem with ``spec`` as "<path>: <reason>"; empty means valid.

    Schema problems are reported alone (the other checks assume the shape).
    """
    issues = _schema_issues(spec)
    if issues:
        return issues
    catalog = load_catalog()
    issues = _section_issues(spec, catalog) + _font_issues(spec, catalog)
    if requested_slugs is not None:
        issues += _page_issues(spec, requested_slugs)
    has_form_section = any(s["type"] == MEMBER_FORM_TYPE for p in spec["pages"] for s in p["sections"])
    if any(d["recipe"] == FORM_RECIPE for d in spec["data_requirements"]) and not has_form_section:
        issues.append(f"data_requirements: {FORM_RECIPE} requires a {MEMBER_FORM_TYPE} section")
    return issues
