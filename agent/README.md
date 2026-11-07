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
| `pipeline/nodes/` | One module per stage node (not yet implemented) |
| `pipeline/template_spec/` | Intake answers → Claude prompt → `design-spec.json` in the site template's contract (mock provider by default) |
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

## Intake to design-spec.json (demo flow)

Turns a stored intake (the `{version, answers, attachments, jobId}` blob the intake API writes) into the
`design-spec.json` that `../BUILD_TEMPLATE_REPO` builds a site from. The contract (JSON Schema and section
catalog) is vendored from the template under `pipeline/template_spec/template/`; `pytest` checks it is in sync
when `BUILD_TEMPLATE_REPO` points at a checkout.

```bash
# 1. Generate a spec. The default provider is a mock that replies with tests/fixtures/template_design_spec_valid.json.
python -m pipeline.template_spec.cli --answers tests/fixtures/intake_answers_complete.json --out /tmp/design-spec.json

# 2. Build the site from it (scaffold placeholder content, apply tokens, lint, typecheck, build).
scripts/build_site_from_spec.sh /tmp/design-spec.json            # template dir defaults to ../BUILD_TEMPLATE_REPO

# Manual path: write the prompt, paste system.md then user.md into Claude Code, save its reply, then validate it.
python -m pipeline.template_spec.cli --answers tests/fixtures/intake_answers_complete.json --print-prompt /tmp/prompt
python -m pipeline.template_spec.cli --answers tests/fixtures/intake_answers_complete.json --validate /tmp/claude-spec.json
```

`--provider anthropic` calls the Messages API through `langchain_anthropic` with the DESIGN node's model
(`ANTHROPIC_API_KEY` from Doppler). It is wired but not yet exercised end-to-end.

### Rerunning the full demo from a stored intake

Run from `agent/` with the venv active. Steps 1 and 2 are the real pipeline; 3 and 5 stand in for the DESIGN and
CONTENT/SEO agents until those nodes exist.

```bash
# 1. Pull the intake blob out of Postgres (DATABASE_URL is in the web app's .env.local; the id is the
#    intake_submissions row the form created, printed by POST /api/intake as "id").
(set -a; . ../.env.local; set +a; psql "$DATABASE_URL" -At \
  -c "select notes from intake_submissions where id = '<submission uuid>'") > /tmp/intake.json

# 2. Render the prompt for that intake.
python -m pipeline.template_spec.cli --answers /tmp/intake.json --print-prompt /tmp/prompt

# 3. Play the DESIGN agent: in Claude Code, "Read /tmp/prompt/system.md and /tmp/prompt/user.md and write only
#    the JSON to /tmp/claude-spec.json". Then check it the way the API path would.
python -m pipeline.template_spec.cli --answers /tmp/intake.json --validate /tmp/claude-spec.json

# 4. Drop the spec into the template: deletes the old content, scaffolds placeholders, applies tokens, builds.
scripts/build_site_from_spec.sh /tmp/claude-spec.json          # template dir defaults to ../BUILD_TEMPLATE_REPO

# 5. Play the CONTENT and SEO agents: replace every "[PLACEHOLDER] ..." value in
#    BUILD_TEMPLATE_REPO/content/content.json and content/seo.json with real copy (value shapes are in the
#    template's AGENTS.md section 2; event-list item bodies are "<date> · <place>\n<description>"), then
(cd ../../BUILD_TEMPLATE_REPO && npm run build && npm run dev)
```

Only the content step needs to be repeated after a restyle: if the template changes how a section looks but
not the catalog, the spec and content stay valid and `npm run build` is enough.

### When the template's catalog changes

Adding a section type, a theme role or a block id changes the contract the agent is vendoring, so:

```bash
(cd ../../BUILD_TEMPLATE_REPO && npm run catalog:export && npm run schema:export)
cp ../../BUILD_TEMPLATE_REPO/lib/spec/{section-catalog.json,design-spec.schema.json} pipeline/template_spec/template/
BUILD_TEMPLATE_REPO=../../BUILD_TEMPLATE_REPO pytest      # the sync test must pass
```

Then update the type count in `tests/test_template_spec_catalog.py`, and if the new section renders an intake
feature, add the pair to `FEATURE_SECTIONS` in `pipeline/template_spec/validate.py` (the prompt's rule 7 and the
flag reconciliation both read it). Any layout rule the template adds (for example "non-home pages start with a
page-header") goes into the numbered rules in `pipeline/template_spec/prompt.py` with a test. Finally regenerate
the spec (step 3 above); existing content for unchanged section ids survives `content:scaffold`, only new blocks
come back as placeholders.

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
