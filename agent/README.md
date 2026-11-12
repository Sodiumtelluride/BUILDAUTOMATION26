# BUILD UMass — Agent Pipeline

LangGraph automation pipeline for the BUILD UMass nonprofit consulting platform.
Generates full websites (design → code → content → SEO) with a human review gate
before deployment.

## Directory Structure

| Path | Purpose |
|------|---------|
| `pipeline/state.py` | Single Pydantic v2 state model shared across all nodes |
| `pipeline/contracts.py` | Per-stage input/output contracts and readiness checks |
| `pipeline/config.py` | Per-node model/retry/budget config, env-overridable |
| `pipeline/design_spec/logo_palette.py` | D8: derives brand colors from an uploaded logo when none were given |
| `pipeline/nodes/` | One module per stage node (not yet implemented) |
| `tests/fixtures/` | Realistic JSON snapshots for unit testing |
| `pyproject.toml` | Python project metadata and dependencies |

## State Flow

```
raw_form_payload + org_id
         │
         ▼
   ┌─────────────┐
   │   INTAKE    │  PENDING → RUNNING
   │             │  writes: intake_output
   └──────┬──────┘
          │
          ▼
   ┌─────────────┐
   │   DESIGN    │  RUNNING → RUNNING
   │             │  writes: design_output
   └──────┬──────┘
          │
     ┌────┴────┐   (parallel branches)
     │         │
     ▼         ▼
┌──────────┐ ┌─────────┐
│  CODE    │ │ CONTENT │  RUNNING → RUNNING
│ GENERATE │ │         │  each writes its own output field
└────┬─────┘ └────┬────┘
     │             │
     └──────┬──────┘
            │
            ▼
      ┌──────────┐
      │   SEO    │  RUNNING → RUNNING
      │          │  requires: content_output + code_generation_output
      └─────┬────┘
            │
            ▼
   ┌─────────────────┐
   │  APPROVAL_GATE  │  RUNNING → AWAITING_REVIEW
   │                 │  pipeline PAUSES — human reviews preview_url
   └────────┬────────┘
            │
            │  reviewer sets approved=True via Next.js dashboard
            │  orchestrator sets status=APPROVED and resumes graph
            │
            ▼
   ┌──────────────┐
   │  DEPLOYMENT  │  APPROVED → COMPLETED
   │              │  writes: deployment_output
   └──────────────┘
```

**Parallel execution note:** CODE_GENERATION and CONTENT can run concurrently
once design_output is available. Wire them as a fan-out from DESIGN and use a
fan-in join node before SEO.

## Append-Only State Contract

Each node receives the full `PipelineState` and **must return only the dict key
it owns**. LangGraph merges partial dicts into state.

```python
# Correct — node returns only its output field
def run_design(state: PipelineState) -> dict:
    validate_state_for_stage(StageEnum.DESIGN, state)
    # ... do work ...
    return {"design_output": DesignOutput(page_map=..., component_patterns=[...])}

# Wrong — never return the full state or touch another node's field
def run_design(state: PipelineState) -> dict:
    state.design_output = DesignOutput(...)   # mutates state directly
    return state.model_dump()                  # overwrites all fields
```

## Adding a New Stage Node

1. **Add to `StageEnum`** in `pipeline/state.py`:
   ```python
   class StageEnum(str, Enum):
       ...
       MY_NEW_STAGE = "MY_NEW_STAGE"
   ```

2. **Add an output model** in `pipeline/state.py`:
   ```python
   class MyNewStageOutput(BaseModel):
       result_field: str
       generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
   ```

3. **Add the output field** to `PipelineState`:
   ```python
   my_new_stage_output: Optional[MyNewStageOutput] = None
   ```

4. **Register a contract** in `pipeline/contracts.py`:
   ```python
   STAGE_CONTRACTS[StageEnum.MY_NEW_STAGE] = StageContract(
       stage=StageEnum.MY_NEW_STAGE,
       required_fields=["some_upstream_output"],
       output_fields=["my_new_stage_output"],
       pre_status=JobStatus.RUNNING,
       post_status=JobStatus.RUNNING,
   )
   ```

5. **Add default config** in `pipeline/config.py` under `_DEFAULTS`:
   ```python
   "MY_NEW_STAGE": {
       "model_id": "claude-haiku-4-5-20251001",
       "token_budget": 8_000,
       "cost_budget_usd": 0.05,
   },
   ```

6. **Create the node** in `pipeline/nodes/my_new_stage.py`:
   ```python
   from pipeline.state import PipelineState, StageEnum, MyNewStageOutput
   from pipeline.contracts import validate_state_for_stage
   from pipeline.config import get_node_config

   def run_my_new_stage(state: PipelineState) -> dict:
       validate_state_for_stage(StageEnum.MY_NEW_STAGE, state)
       config = get_node_config("MY_NEW_STAGE")
       # ... call LLM, do work ...
       return {"my_new_stage_output": MyNewStageOutput(result_field="...")}
   ```

7. **Wire it into the graph** in `pipeline/graph.py` (when you build it):
   ```python
   graph.add_node("my_new_stage", run_my_new_stage)
   graph.add_edge("upstream_node", "my_new_stage")
   ```

8. **Add a fixture** in `tests/fixtures/` showing valid state after this stage runs.

## Validating State Readiness

```python
from pipeline.contracts import validate_state_for_stage, STAGE_CONTRACTS
from pipeline.state import PipelineState, StageEnum
import pathlib

state = PipelineState.model_validate_json(
    pathlib.Path("tests/fixtures/intake_complete.json").read_text()
)

# Check readiness without raising
ready, missing = STAGE_CONTRACTS[StageEnum.DESIGN].is_ready(state)
print(ready)    # True
print(missing)  # []

# Raise on failure (use this inside nodes)
validate_state_for_stage(StageEnum.DESIGN, state)

# Check something that isn't ready yet
ready, missing = STAGE_CONTRACTS[StageEnum.SEO].is_ready(state)
print(ready)    # False
print(missing)  # ['content_output', 'code_generation_output']
```

## Setup

### Prerequisites

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) (recommended) or pip
- [Doppler CLI](https://docs.doppler.com/docs/install-cli) for secret injection

### Install

```bash
cd agent

# Using uv (recommended)
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"

# Using pip
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### Run tests

```bash
# Without secrets (unit tests only)
pytest

# With Doppler secrets injected
doppler run -- pytest
```

### Type-check

```bash
mypy pipeline/
```

### Override node config at runtime

```bash
export AGENT_CODE_GENERATION_MODEL_ID=claude-sonnet-4-6
export AGENT_CODE_GENERATION_TOKEN_BUDGET=120000
export AGENT_INTAKE_MAX_RETRIES=5
```

Or add them to your Doppler project under the `agent` config. Pattern: `AGENT_{STAGE_UPPER}_{FIELD_UPPER}`.
