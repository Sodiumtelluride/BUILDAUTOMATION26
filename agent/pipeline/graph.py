"""
The demo-site graph: INTAKE -> DESIGN -> CODE_GENERATION.

A ``review_flag`` from INTAKE or DESIGN (unmappable answers, or no valid spec
after the repair round) ends the run there. Advisory entries in the spec's own
``flags`` list (e.g. logo_unreadable) do not: the site still builds and the
flags travel with the result.
"""

from __future__ import annotations

from typing import Any, Callable, Dict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from pipeline.nodes.design import run_design
from pipeline.nodes.intake import run_intake
from pipeline.state import PipelineState
from pipeline.template_spec.provider import SpecProvider

Build = Callable[[PipelineState], Dict[str, Any]]


def _continue_unless_flagged(next_node: str) -> Callable[[PipelineState], str]:
    def route(state: PipelineState) -> str:
        return END if state.review_flag is not None else next_node

    return route


def build_graph(provider: SpecProvider, build: Build) -> CompiledStateGraph[Any, Any, Any, Any]:
    async def design(state: PipelineState) -> Dict[str, Any]:
        return await run_design(state, provider)

    def code_generation(state: PipelineState) -> Dict[str, Any]:
        return build(state)

    graph = StateGraph(PipelineState)
    graph.add_node("intake", run_intake)
    graph.add_node("design", design)
    graph.add_node("code_generation", code_generation)
    graph.add_edge(START, "intake")
    graph.add_conditional_edges("intake", _continue_unless_flagged("design"), ["design", END])
    graph.add_conditional_edges("design", _continue_unless_flagged("code_generation"), ["code_generation", END])
    graph.add_edge("code_generation", END)
    return graph.compile()
