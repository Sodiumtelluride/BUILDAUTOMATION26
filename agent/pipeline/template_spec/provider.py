"""
Where the model reply comes from.

A provider is ``async (system, user) -> raw text``. The mock returns a file
(a valid model reply by default) so the whole flow runs with no network; the
Anthropic provider is the production path and is not exercised by tests.
"""

from __future__ import annotations

from pathlib import Path
from typing import Awaitable, Callable, Optional

from pipeline.config import get_node_config

SpecProvider = Callable[[str, str], Awaitable[str]]

DEFAULT_MOCK_SPEC = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "template_design_reply_valid.json"


def mock_provider(path: Path = DEFAULT_MOCK_SPEC) -> SpecProvider:
    """Returns the file's text as the model reply, whatever the prompt says."""

    async def provide(system: str, user: str) -> str:
        return path.read_text()

    return provide


def anthropic_provider(model_id: Optional[str] = None) -> SpecProvider:
    """One Messages API call per attempt via langchain_anthropic (model from the DESIGN node config).

    Needs ANTHROPIC_API_KEY in the environment (Doppler in production).
    """
    resolved = model_id if model_id is not None else str(get_node_config("DESIGN").model_id)

    async def provide(system: str, user: str) -> str:
        from langchain_anthropic import ChatAnthropic  # deferred: tests never import a provider
        from langchain_core.messages import HumanMessage, SystemMessage

        model = ChatAnthropic(model_name=resolved, timeout=None, stop=None)
        response = await model.ainvoke([SystemMessage(content=system), HumanMessage(content=user)])
        content = response.content
        return content if isinstance(content, str) else "".join(str(part) for part in content)

    return provide
