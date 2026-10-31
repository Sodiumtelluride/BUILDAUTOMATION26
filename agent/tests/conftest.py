"""Shared pytest fixtures."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Callable, Dict

import pytest

FIXTURES = Path(__file__).parent / "fixtures"

_VALID_SPEC: Dict[str, Any] = json.loads((FIXTURES / "design_spec_valid.json").read_text())

_COMPLETE_INTAKE: Dict[str, Any] = json.loads((FIXTURES / "design_intake_complete.json").read_text())

# A layout plan covering every page in design_intake_complete.json, using only
# approved catalog types. Tests mutate their copy to break one thing each.
_VALID_PLAN: Dict[str, Any] = {
    "pages": [
        {
            "page": "home",
            "sections": [
                {"type": "hero-centered", "sources": ["organization_description", "tone"]},
                {"type": "stats-bar", "sources": ["organization_description"]},
                {"type": "newsletter-signup", "sources": ["features"]},
                {"type": "cta-band", "sources": ["primary_goal"]},
            ],
        },
        {
            "page": "about",
            "sections": [
                {"type": "about-story", "sources": ["organization_description"]},
                {"type": "quote-spotlight", "sources": ["tone", "target_audience"]},
            ],
        },
        {"page": "team", "sections": [{"type": "team-grid", "sources": ["pages"]}]},
        {
            "page": "donate",
            "sections": [
                {"type": "donation-cta", "sources": ["primary_goal", "features"]},
                {"type": "cta-band", "sources": ["primary_goal"]},
            ],
        },
        {"page": "contact", "sections": [{"type": "contact-form", "sources": ["features"]}]},
        {"page": "faq", "sections": [{"type": "faq-accordion", "sources": ["pages"]}]},
    ],
    "radius": "0.75rem",
}


@pytest.fixture
def make_spec() -> Callable[[], Dict[str, Any]]:
    """Returns a fresh, valid design_spec dict each call. Tests break one thing each."""
    return lambda: copy.deepcopy(_VALID_SPEC)


@pytest.fixture
def make_intake() -> Callable[[], Dict[str, Any]]:
    """Returns a fresh, complete Stage 1 intake dict each call."""
    return lambda: copy.deepcopy(_COMPLETE_INTAKE)


@pytest.fixture
def make_plan() -> Callable[[], Dict[str, Any]]:
    """Returns a fresh LayoutPlan dict covering every page of the complete intake."""
    return lambda: copy.deepcopy(_VALID_PLAN)
