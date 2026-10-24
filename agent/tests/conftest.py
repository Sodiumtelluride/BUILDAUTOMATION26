"""Shared pytest fixtures."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Callable, Dict

import pytest

FIXTURES = Path(__file__).parent / "fixtures"

_VALID_SPEC: Dict[str, Any] = json.loads((FIXTURES / "design_spec_valid.json").read_text())


@pytest.fixture
def make_spec() -> Callable[[], Dict[str, Any]]:
    """Returns a fresh, valid design_spec dict each call. Tests break one thing each."""
    return lambda: copy.deepcopy(_VALID_SPEC)
