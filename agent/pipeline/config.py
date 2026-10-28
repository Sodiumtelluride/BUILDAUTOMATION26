"""
Per-node model and budget configuration.

Each stage has a default NodeConfig. Values can be overridden at runtime via
environment variables using the pattern:

    AGENT_{STAGE_UPPER}_{FIELD_UPPER}

Examples:
    AGENT_CODE_GENERATION_MODEL_ID=claude-sonnet-4-6
    AGENT_CODE_GENERATION_TOKEN_BUDGET=120000
    AGENT_INTAKE_MAX_RETRIES=5

Environment variables are read at call time (not import time), so patching
os.environ in tests works without module-level mocking side effects.

All model strings live ONLY in this file. No hardcoded secrets anywhere.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

from pydantic import BaseModel


class NodeConfig(BaseModel):
    """Runtime configuration for a single pipeline node."""

    model_id: Optional[str]
    max_retries: int = 3
    retry_backoff_seconds: float = 2.0
    token_budget: int
    cost_budget_usd: float
    feature_flags: Dict[str, Any] = {}


# ---------------------------------------------------------------------------
# Default configurations per stage.
# Indexed by the stage's string value (matches StageEnum.value).
# ---------------------------------------------------------------------------

_DEFAULTS: Dict[str, Dict[str, Any]] = {
    "INTAKE": {
        "model_id": "claude-haiku-4-5-20251001",
        "token_budget": 8_000,
        "cost_budget_usd": 0.05,
    },
    "DESIGN": {
        "model_id": "claude-haiku-4-5-20251001",
        "token_budget": 12_000,
        "cost_budget_usd": 0.08,
        # D20: "retry this node alone (maximum two attempts)" = 1 retry.
        "max_retries": 1,
    },
    "CODE_GENERATION": {
        "model_id": "claude-sonnet-4-6",
        "token_budget": 100_000,
        "cost_budget_usd": 2.00,
        "max_retries": 5,
    },
    "CONTENT": {
        "model_id": "claude-haiku-4-5-20251001",
        "token_budget": 16_000,
        "cost_budget_usd": 0.10,
    },
    "SEO": {
        "model_id": "claude-haiku-4-5-20251001",
        "token_budget": 8_000,
        "cost_budget_usd": 0.05,
    },
    "APPROVAL_GATE": {
        "model_id": None,
        "token_budget": 0,
        "cost_budget_usd": 0.0,
    },
    "DEPLOYMENT": {
        "model_id": "claude-haiku-4-5-20251001",
        "token_budget": 4_000,
        "cost_budget_usd": 0.02,
    },
}

# Fields that support env var overrides and their cast functions
_OVERRIDE_FIELDS: Dict[str, type] = {
    "MODEL_ID": str,
    "MAX_RETRIES": int,
    "RETRY_BACKOFF_SECONDS": float,
    "TOKEN_BUDGET": int,
    "COST_BUDGET_USD": float,
}


def get_node_config(stage: str) -> NodeConfig:
    """
    Return the NodeConfig for `stage`, with any env var overrides applied.

    Args:
        stage: The StageEnum value string, e.g. "CODE_GENERATION".

    Raises:
        KeyError: If `stage` is not a known stage name.
    """
    stage_upper = stage.upper()
    if stage_upper not in _DEFAULTS:
        raise KeyError(
            f"Unknown stage: {stage!r}. Valid stages: {list(_DEFAULTS.keys())}"
        )

    config_dict: Dict[str, Any] = dict(_DEFAULTS[stage_upper])

    for field_upper, cast in _OVERRIDE_FIELDS.items():
        env_key = f"AGENT_{stage_upper}_{field_upper}"
        raw = os.environ.get(env_key)
        if raw is not None:
            field_lower = field_upper.lower()
            try:
                config_dict[field_lower] = cast(raw)
            except (ValueError, TypeError) as exc:
                raise ValueError(
                    f"Invalid value for {env_key}={raw!r}: {exc}"
                ) from exc

    return NodeConfig(**config_dict)
