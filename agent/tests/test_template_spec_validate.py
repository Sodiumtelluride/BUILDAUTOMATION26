"""Template-side validation of a candidate design spec, in the template's own terms."""

from __future__ import annotations

import copy
import json
import pathlib
from typing import Any, Dict

from pipeline.template_spec.catalog import load_catalog
from pipeline.template_spec.validate import validate_template_spec

SPEC: Dict[str, Any] = json.loads((pathlib.Path(__file__).parent / "fixtures" / "template_design_spec_valid.json").read_text())
SLUGS = ["/", "/about", "/team", "/donate", "/contact", "/faq"]


def _spec() -> Dict[str, Any]:
    return copy.deepcopy(SPEC)


def test_fixture_is_valid() -> None:
    assert validate_template_spec(SPEC, requested_slugs=SLUGS) == []


def test_schema_issue_unknown_color_role() -> None:
    s = _spec()
    s["tokens"]["colors"]["primary_foreground"] = "#FFFFFF"
    assert any(i.startswith("tokens.colors") for i in validate_template_spec(s))


def test_unknown_section_type() -> None:
    s = _spec()
    s["pages"][0]["sections"][0]["type"] = "hero-split"
    assert "pages[0].sections[0].type: unknown section type 'hero-split'" in validate_template_spec(s)


def test_missing_required_block() -> None:
    s = _spec()
    stats = s["pages"][0]["sections"][1]
    stats["content_blocks"] = [b for b in stats["content_blocks"] if b["id"] != "stats.stat_3"]
    assert "pages[0].sections[1].content_blocks: missing required block stats.stat_3" in validate_template_spec(s)


def test_wrong_block_kind_and_foreign_block() -> None:
    s = _spec()
    blocks = s["pages"][0]["sections"][0]["content_blocks"]
    blocks[0]["kind"] = "body"
    blocks.append({"id": "programs.items", "kind": "items"})
    issues = validate_template_spec(s)
    assert "pages[0].sections[0].content_blocks[0].kind: hero.headline must be headline, got body" in issues
    assert "pages[0].sections[0].content_blocks[5].id: programs.items is not a block of hero-bold" in issues


def test_duplicate_section_id() -> None:
    s = _spec()
    s["pages"][1]["sections"][0]["id"] = "hero-1"
    assert "pages[1].sections[0].id: duplicate section id hero-1" in validate_template_spec(s)


def test_font_not_bundled() -> None:
    s = _spec()
    s["tokens"]["fonts"]["heading"] = "Source Serif 4"
    assert "tokens.fonts.heading: 'Source Serif 4' is not bundled; allowed: Inter, Instrument Serif" in validate_template_spec(s)


def test_body_font_must_be_inter() -> None:
    s = _spec()
    s["tokens"]["fonts"]["body"] = "Instrument Serif"
    assert "tokens.fonts.body: must be Inter" in validate_template_spec(s)


def test_requested_pages_missing_and_extra() -> None:
    s = _spec()
    s["pages"].pop()
    s["pages"].append({"slug": "/blog", "sections": []})
    issues = validate_template_spec(s, requested_slugs=SLUGS)
    assert "pages: missing requested page /faq" in issues
    assert "pages: /blog was not requested" in issues


def test_duplicate_page_slug() -> None:
    s = _spec()
    s["pages"][2]["slug"] = "/about"
    assert "pages[2].slug: duplicate page slug /about" in validate_template_spec(s)


def test_form_submissions_needs_member_form_section() -> None:
    s = _spec()
    s["data_requirements"] = [{"recipe": "form_submissions"}]
    assert "data_requirements: form_submissions requires a member-application-form section" in validate_template_spec(s)


def test_member_form_section_needs_form_submissions() -> None:
    s = _spec()
    s["pages"][4]["sections"].append(
        {
            "id": "form-1",
            "type": "member-application-form",
            "components": ["input", "label", "textarea", "button"],
            "content_blocks": [
                {"id": "form.headline", "kind": "headline", "max_chars": 80},
                {"id": "form.submit_label", "kind": "label", "max_chars": 40},
                {"id": "form.success_message", "kind": "body", "max_chars": 400},
                {"id": "form.error_message", "kind": "body", "max_chars": 400},
            ],
            "source_fields": ["features"],
        }
    )
    assert "pages[4].sections[2].type: member-application-form requires data_requirements form_submissions" in validate_template_spec(s)


def test_fixture_uses_the_bold_family() -> None:
    bold = set(load_catalog().themes["bold"].values())
    types = {s["type"] for p in SPEC["pages"] for s in p["sections"]}
    assert types <= bold
