"""
Tests for the Figma -> shadcn mapper (pipeline/figma/).

Run from the agent/ folder:  .venv/bin/python -m pytest tests/test_figma_mapper.py -v
They use a small fake Figma file, so no Figma account or network is needed.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from pipeline.figma import client
from pipeline.figma.catalog import find_component
from pipeline.figma.client import get_file_key, load_figma_file
from pipeline.figma.mapper import get_screen_name, get_viewport, map_design

SAMPLE_FILE = Path(__file__).parent / "fixtures" / "figma_sample.json"


def load_sample() -> dict[str, Any]:
    """Read the fake Figma file used by these tests."""
    data: dict[str, Any] = json.loads(SAMPLE_FILE.read_text())
    return data


# --- catalog ---------------------------------------------------------------


def test_find_component_matches_names_and_aliases() -> None:
    """Exact names, slash variants, aliases, and symbols all resolve; generic names don't."""
    assert find_component("Button") == "button"
    assert find_component("Button/Primary") == "button"
    assert find_component("❖ Navbar") == "navigation-menu"
    assert find_component("Divider") == "separator"
    assert find_component("CardHeader") == "card"
    assert find_component("AvatarGroup") == "avatar"
    assert find_component("Frame 12") is None


# --- screen sizes and names ------------------------------------------------


def test_get_viewport_uses_frame_width() -> None:
    """1440 is desktop, 768 is tablet, 375 is mobile."""
    assert get_viewport(1440) == "desktop"
    assert get_viewport(768) == "tablet"
    assert get_viewport(375) == "mobile"


def test_get_screen_name_drops_size_words() -> None:
    """Desktop and mobile frames of the same screen get the same name."""
    assert get_screen_name("Home – Desktop") == "Home"
    assert get_screen_name("Home / Mobile 375") == "Home"
    assert get_screen_name("Pricing-1440") == "Pricing"


# --- mapping a whole file --------------------------------------------------


def test_map_design_lists_components_per_screen_size() -> None:
    """Desktop and mobile versions of Home each get their own component list."""
    report = map_design(load_sample(), ["screens"])
    home = report["screens"]["Home"]

    # Navbar and Divider are matched by layer name; the hidden Dialog is skipped
    assert home["desktop"]["components"] == ["badge", "button", "card", "input", "navigation-menu", "separator"]
    assert home["mobile"]["components"] == ["button", "card", "input", "sheet"]


def test_map_design_looks_inside_containers() -> None:
    """The Button inside the desktop Card is found."""
    report = map_design(load_sample(), ["screens"])
    layers = [m["layer"] for m in report["screens"]["Home"]["desktop"]["matches"]]
    assert "Home – Desktop > Card > Button" in layers


def test_map_design_flags_unknown_components_but_not_icons() -> None:
    """Logo Cloud isn't a shadcn component, so a human should review it; icons are ignored."""
    report = map_design(load_sample(), ["screens"])
    assert report["screens"]["Home"]["desktop"]["needs_review"] == ["Logo Cloud"]


def test_map_design_finds_frames_inside_sections() -> None:
    """The About frame sits inside a Figma section and is still found."""
    report = map_design(load_sample(), ["screens"])
    assert report["screens"]["About"]["desktop"]["components"] == ["tabs"]


def test_page_filter_skips_other_pages() -> None:
    """With --page Screens, the kit's "↳ Button" docs page is ignored."""
    assert "Button docs" not in map_design(load_sample(), ["screens"])["screens"]
    assert "Button docs" in map_design(load_sample())["screens"]


def test_install_command_lists_every_component() -> None:
    """One install line covers every component in the design."""
    report = map_design(load_sample(), ["screens"])
    assert report["install_command"] == (
        "npx shadcn@latest add badge button card input navigation-menu separator sheet tabs"
    )


# --- loading files ---------------------------------------------------------


def test_get_file_key_reads_figma_urls() -> None:
    """Both /design/ and /file/ links work; anything else is an error."""
    assert get_file_key("https://www.figma.com/design/nB1CRRx/Kit?node-id=1-2") == "nB1CRRx"
    assert get_file_key("https://www.figma.com/file/abc123/Old-Link") == "abc123"
    with pytest.raises(ValueError):
        get_file_key("https://example.com/not-figma")


def test_cached_file_is_used_instead_of_calling_figma(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """If a saved copy exists, the Figma API is never called."""
    monkeypatch.setattr(client, "CACHE_DIR", tmp_path)
    (tmp_path / "abc123.json").write_text(json.dumps({"name": "cached"}))

    def fail_if_called(*args: Any) -> dict[str, Any]:
        raise AssertionError("should not call the Figma API when a cached copy exists")

    monkeypatch.setattr(client, "fetch_from_api", fail_if_called)
    assert load_figma_file("https://www.figma.com/design/abc123/Kit")["name"] == "cached"
