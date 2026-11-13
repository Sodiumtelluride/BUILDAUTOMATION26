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
| `pipeline/nodes/` | One module per stage node (`intake.py`, `design.py` and `code_generation.py` are implemented) |
| `pipeline/graph.py`, `pipeline/run.py` | The demo-site graph and its one-shot entrypoint (see "One-click demo site") |
| `pipeline/template_spec/` | Intake answers → Claude prompt → `design-spec.json` in the site template's contract. Used by the DESIGN node and the CLI (mock provider by default) |
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
# The DESIGN node also needs intake_output.project_spec in the {intake, notes} shape written by
# pipeline.template_spec.intake_mapping.to_project_spec; any other shape is flagged for human review.

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
# 1. Generate a spec. The default provider is a mock that replies with tests/fixtures/template_design_reply_valid.json.
python -m pipeline.template_spec.cli --answers tests/fixtures/intake_answers_complete.json --out /tmp/design-spec.json

# 2. Build the site from it (scaffold placeholder content, apply tokens, lint, typecheck, build).
scripts/build_site_from_spec.sh /tmp/design-spec.json            # template dir defaults to ../BUILD_TEMPLATE_REPO

# Manual path: write the prompt, paste system.md then user.md into Claude Code, save its reply, then check it.
# --out writes the final spec (the reply's {text, field} assumptions become the plain strings the template expects).
python -m pipeline.template_spec.cli --answers tests/fixtures/intake_answers_complete.json --print-prompt /tmp/prompt
python -m pipeline.template_spec.cli --answers tests/fixtures/intake_answers_complete.json \
  --validate /tmp/claude-reply.json --out /tmp/claude-spec.json
```

`--provider ollama` calls a local model through Ollama (JSON mode, temperature 0, 32k context); the model is
`AGENT_LOCAL_MODEL_ID`, default `qwen2.5:14b-instruct` (`pipeline/config.py`). `--provider anthropic` calls the
Messages API through `langchain_anthropic` with the DESIGN node's model (`ANTHROPIC_API_KEY` from Doppler). It is
wired but not yet exercised end-to-end.

### What the DESIGN node adds around the spec

`pipeline/nodes/design.py` runs the same generate / validate / repair loop and writes `DesignOutput`:

- **Logo colors (BUI-71).** With a logo and no brand colors, the logo is fetched (direct `https://` only) and its
  two main colors become `brand_colors`; `brand_colors_source` records `"intake"` or `"logo"`. The colors are
  reused on reruns while the logo URL is unchanged. A logo that cannot be fetched or read adds a
  `logo_unreadable` flag to the spec. Intake uploads are stored as `supabase://` URLs, which the fetcher cannot
  read yet (BUI-93), so today every uploaded logo gets that flag.
- **Reruns.** `reviewer_notes` always go into the prompt. When `design_output` already holds a spec, the previous
  spec goes in too and `revision` goes up by one. Surviving sections must keep their ids (`template_spec/revisions.py`): an
  unambiguous regenerated id is written back in code; an ambiguous one costs the repair round, then the job is
  flagged for human review.
- **Source log.** `source_log` has one row per value in the spec saying where it came from: `intake`, `logo`,
  `rule` or `claude` (`template_spec/sources.py`). It is append-only across revisions. It lives only in pipeline
  state for now, so that state has to be stored durably; a table comes when the admin console reads the log.

### One-click demo site (local)

The graph in `pipeline/graph.py` runs `INTAKE → DESIGN → CODE_GENERATION` unattended:

- **INTAKE** maps the stored blob to `project_spec` (no model call).
- **DESIGN** asks the model for the spec.
- **CODE_GENERATION** clones the template's committed HEAD into the job folder, runs `npm ci` and
  `scripts/build_site_from_spec.sh`, and starts `next start` on a free port.

A `review_flag` (unmappable answers, or no valid spec after the repair round) ends the run early. Advisory spec
flags such as `logo_unreadable` do not: the site still builds.

**From the admin console.** Set these where the console runs (in `.env.local` on the demo laptop):

```bash
DEMO_SITES_DIR=/Users/<you>/build-demo-sites   # turns the button on; one folder per intake
# optional:
AGENT_PROVIDER=ollama                          # or anthropic, or mock
AGENT_LOCAL_MODEL_ID=qwen2.5:32b-instruct      # the local model
AGENT_PYTHON=/path/to/python                   # default: agent/.venv/bin/python
BUILD_TEMPLATE_SOURCE=/path/or/git/url         # default: ../BUILD_TEMPLATE_REPO (committed HEAD only)
```

Open an intake under `/intakes` and press **Generate demo site** at the bottom. The run is detached from the
console: reload the page to see it finish. The row's `demo_url`, `demo_status` and `demo_error` are filled from the
job folder's `result.json` on the next page load, so restarting `next dev` mid-run is safe. The agent gets only
`PATH`, `HOME` and `AGENT_*`/`OLLAMA_*`/`BUILD_TEMPLATE_SOURCE`, never the console's `DATABASE_URL` or secrets.

**From the shell**, with the same job-folder layout:

```bash
python -m pipeline.run --job-dir /tmp/demo-job --provider mock < tests/fixtures/intake_answers_complete.json
```

The job folder holds `intake.json`, `design-spec.json`, `site/`, `build.log`, `server.log`, `run.log`, `state.json`
(final pipeline state with the source log) and `result.json`. Generating again for the same intake stops its
previous server. Demo URLs stop working when the laptop restarts; generate again to bring one back.

Page copy is still the template's `[PLACEHOLDER]` scaffold until a CONTENT node exists. To fill it by hand, edit
`site/content/content.json` and `site/content/seo.json` in the job folder (value shapes are in the template's
AGENTS.md section 2), then rebuild there.

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
page-header") goes into the numbered rules in `pipeline/template_spec/prompt.py` with a test. Finally generate
the demo again; existing content for unchanged section ids survives `content:scaffold`, only new blocks
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
