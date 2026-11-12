"""Vendored template contract: catalog, themes, fonts, JSON Schema, and the sync guard."""

from __future__ import annotations

import os
import pathlib

import pytest

from pipeline.template_spec.catalog import TEMPLATE_DIR, load_catalog, load_schema


def test_catalog_has_35_types_and_4_themes() -> None:
    cat = load_catalog()
    assert len(cat.types) == 35
    assert set(cat.themes["bold"]) == {"hero", "programs", "stats", "team", "cta", "story", "page-header"}
    assert set(cat.themes) == {"classic", "minimal", "editorial", "bold"}
    assert cat.fonts == ("Inter", "Instrument Serif")


def test_required_blocks_for_hero_centered() -> None:
    assert load_catalog().required_blocks("hero-centered") == ["hero.headline", "hero.subhead", "hero.primary_cta"]


def test_theme_of() -> None:
    cat = load_catalog()
    assert cat.theme_of("cta-bold") == "bold"
    assert cat.theme_of("story-bold") == "bold"
    assert cat.theme_of("member-application-form") is None
    assert cat.theme_of("event-list") is None


def test_schema_requires_assumptions() -> None:
    assert "assumptions" in load_schema()["required"]


@pytest.mark.skipif("BUILD_TEMPLATE_REPO" not in os.environ, reason="set BUILD_TEMPLATE_REPO to check vendored files")
@pytest.mark.parametrize("name", ["design-spec.schema.json", "section-catalog.json"])
def test_vendored_file_matches_template(name: str) -> None:
    ours = (TEMPLATE_DIR / name).read_bytes()
    theirs = (pathlib.Path(os.environ["BUILD_TEMPLATE_REPO"]) / "lib/spec" / name).read_bytes()
    assert ours == theirs, f"{name} is stale: copy it from the template repo"
