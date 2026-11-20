"""One spec in every theme family: type ids move by role, blocks follow the catalog, tokens follow the preset."""

from __future__ import annotations

import copy
import json
import pathlib
from typing import Any, Dict

import pytest

from pipeline.template_spec.catalog import load_catalog, load_presets
from pipeline.template_spec.validate import validate_template_spec
from pipeline.template_spec.variants import family_of, spec_in_family, specs_in_every_family

SPEC: Dict[str, Any] = json.loads((pathlib.Path(__file__).parent / "fixtures" / "template_design_spec_valid.json").read_text())


def _spec() -> Dict[str, Any]:
    return copy.deepcopy(SPEC)


def _types(spec: Dict[str, Any]) -> list[str]:
    return [s["type"] for p in spec["pages"] for s in p["sections"]]


def test_family_of_is_the_majority_family() -> None:
    assert family_of(_spec()) == "bold"
    mixed = _spec()
    mixed["pages"][0]["sections"][0]["type"] = "hero-centered"  # one classic section among bold ones
    assert family_of(mixed) == "bold"


def test_every_family_variant_is_valid_and_keeps_structure() -> None:
    spec = _spec()
    variants = specs_in_every_family(spec)
    assert list(variants) == ["classic", "bold", "civic", "collage", "transit"]
    for family, variant in variants.items():
        assert validate_template_spec(variant) == [], family
        assert family_of(variant) == family
        assert [p["slug"] for p in variant["pages"]] == [p["slug"] for p in spec["pages"]]
        assert [s["id"] for p in variant["pages"] for s in p["sections"]] == [s["id"] for p in spec["pages"] for s in p["sections"]]
        assert variant["tokens"]["colors"] == spec["tokens"]["colors"]
        assert variant["job_id"] == spec["job_id"] and variant["flags"] == spec["flags"]
    assert variants["bold"] == spec  # the model's own family is unchanged
    assert variants["bold"] is not spec


def test_base_sections_stay_and_themed_sections_move() -> None:
    civic = spec_in_family(_spec(), "civic")
    assert "newsletter-signup" in _types(civic) and "donate" in _types(civic) and "contact-block" in _types(civic)
    assert "hero-civic" in _types(civic) and not any(t.endswith("-bold") for t in _types(civic))


def test_blocks_the_target_type_lacks_are_dropped_and_required_ones_added() -> None:
    spec = _spec()
    hero = spec["pages"][0]["sections"][0]
    assert hero["type"] == "hero-bold"
    hero["content_blocks"].insert(0, {"id": "hero.eyebrow", "kind": "label", "max_chars": 40})
    classic_hero = spec_in_family(spec, "classic")["pages"][0]["sections"][0]
    assert classic_hero["type"] == "hero-centered"
    ids = [b["id"] for b in classic_hero["content_blocks"]]
    assert "hero.eyebrow" not in ids  # hero-centered has no eyebrow
    assert ids[:3] == ["hero.headline", "hero.subhead", "hero.primary_cta"]
    # the kind and max_chars of a kept block are copied from the source section
    assert {b["id"]: b for b in classic_hero["content_blocks"]}["hero.headline"] == {b["id"]: b for b in hero["content_blocks"]}["hero.headline"]

    # a classic cta-band has no steps; moving back to bold adds nothing optional but keeps the required blocks
    back = spec_in_family(spec_in_family(spec, "classic"), "bold")
    bold_cta = next(s for p in back["pages"] for s in p["sections"] if s["type"] == "cta-bold")
    assert [b["id"] for b in bold_cta["content_blocks"]] == ["cta.headline", "cta.body", "cta.button"]


def test_preset_fonts_and_radius_apply_where_the_template_has_one() -> None:
    spec = _spec()
    presets = load_presets()
    for family, preset in presets.items():
        variant = spec_in_family(spec, family)
        assert variant["tokens"]["fonts"] == preset["fonts"] and variant["tokens"]["radius"] == preset["radius"]
    assert spec_in_family(spec, "classic")["tokens"]["fonts"] == spec["tokens"]["fonts"]


def test_unknown_family_is_an_error() -> None:
    with pytest.raises(ValueError):
        spec_in_family(_spec(), "editorial")
    assert "editorial" not in load_catalog().themes
