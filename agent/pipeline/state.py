"""
PipelineState — the single shared state object that flows through every node.

APPEND-ONLY CONTRACT:
  Each node receives the full PipelineState and must return ONLY a dict
  containing the key(s) it is responsible for. LangGraph merges these dicts.
  No node may overwrite another node's output field.

  Correct:   return {"intake_output": IntakeOutput(...)}
  Incorrect: return state.model_copy(update={"intake_output": ...})
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class JobStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    AWAITING_REVIEW = "AWAITING_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class StageEnum(str, Enum):
    INTAKE = "INTAKE"
    DESIGN = "DESIGN"
    CODE_GENERATION = "CODE_GENERATION"
    CONTENT = "CONTENT"
    SEO = "SEO"
    APPROVAL_GATE = "APPROVAL_GATE"
    DEPLOYMENT = "DEPLOYMENT"


class ReviewReason(str, Enum):
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
    TESTS_FAILING = "TESTS_FAILING"
    MANUAL_REJECTION = "MANUAL_REJECTION"
    STAGE_ERROR_THRESHOLD = "STAGE_ERROR_THRESHOLD"


class ErrorCode(str, Enum):
    TOKEN_BUDGET_EXCEEDED = "TOKEN_BUDGET_EXCEEDED"
    RETRIEVAL_FAILED = "RETRIEVAL_FAILED"
    TEST_SUITE_FAILED = "TEST_SUITE_FAILED"
    DEPLOYMENT_FAILED = "DEPLOYMENT_FAILED"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    LLM_ERROR = "LLM_ERROR"
    TIMEOUT = "TIMEOUT"


class WarningCode(str, Enum):
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    PARTIAL_RETRIEVAL = "PARTIAL_RETRIEVAL"
    COST_THRESHOLD_APPROACHING = "COST_THRESHOLD_APPROACHING"
    TEST_WARNINGS = "TEST_WARNINGS"


# ---------------------------------------------------------------------------
# Supporting models
# ---------------------------------------------------------------------------


class StatusTransition(BaseModel):
    """Records every status change with the stage that triggered it."""

    stage: StageEnum
    status: JobStatus
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ReviewFlag(BaseModel):
    """Attached to state when a stage needs human attention before proceeding."""

    reason: ReviewReason
    flagged_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    flagged_by_stage: StageEnum
    reviewer_notes: Optional[str] = None


class StageCost(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: float = 0.0
    model_id: str


class CostSummary(BaseModel):
    per_stage: Dict[str, StageCost] = Field(default_factory=dict)
    total_estimated_cost_usd: float = 0.0


class ErrorEnvelope(BaseModel):
    stage: StageEnum
    error_code: ErrorCode
    message: str
    retryable: bool
    retry_count: int = 0
    max_retries: int = 3
    failed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class WarningEnvelope(BaseModel):
    stage: StageEnum
    warning_code: WarningCode
    message: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class StageTiming(BaseModel):
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None


class Trace(BaseModel):
    trace_id: Optional[str] = None
    langsmith_run_id: Optional[str] = None
    stage_timings: Dict[str, StageTiming] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Per-stage output models
# ---------------------------------------------------------------------------


class IntakeOutput(BaseModel):
    """Written exclusively by the INTAKE node."""

    project_spec: Dict[str, Any]
    similar_projects: List[Dict[str, Any]] = Field(default_factory=list)
    validated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DesignOutput(BaseModel):
    """Written exclusively by the DESIGN node."""

    page_map: Dict[str, Any]
    component_patterns: List[str] = Field(default_factory=list)
    design_spec: Optional[Dict[str, Any]] = None
    """The validated design_spec contract (pipeline.design_spec.schema.DesignSpec),
    stored as plain JSON so downstream stages and reruns can re-validate it."""
    designed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CodeGenerationOutput(BaseModel):
    """Written exclusively by the CODE_GENERATION node."""

    repo_url: str
    test_results: Dict[str, Any] = Field(default_factory=dict)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ContentOutput(BaseModel):
    """Written exclusively by the CONTENT node."""

    page_copy: Dict[str, Any]
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SEOOutput(BaseModel):
    """Written exclusively by the SEO node."""

    meta_tags: Dict[str, Any]
    sitemap_url: str
    robots_txt: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ApprovalGateOutput(BaseModel):
    """Written exclusively by the APPROVAL_GATE node. Marks a human pause point."""

    preview_url: str
    paused_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DeploymentOutput(BaseModel):
    """Written exclusively by the DEPLOYMENT node."""

    live_url: str
    github_pr_url: str
    vercel_deployment_id: str
    deployed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# Root state model
# ---------------------------------------------------------------------------


class PipelineState(BaseModel):
    """
    Single source of truth for a BUILD UMass automation job.

    Lifecycle:
        PENDING → RUNNING (intake)
        RUNNING → RUNNING (design, code_generation, content, seo)
        RUNNING → AWAITING_REVIEW (approval_gate — pipeline pauses here)
        APPROVED → COMPLETED (deployment — APPROVED set externally by reviewer)
        Any stage → FAILED (on unrecoverable error)

    Do not instantiate this class directly in nodes. Return a partial dict
    containing only the field(s) your node owns.
    """

    # -- Job identity --------------------------------------------------------
    job_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    org_id: uuid.UUID
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # -- Job status ----------------------------------------------------------
    status: JobStatus = JobStatus.PENDING
    status_history: List[StatusTransition] = Field(default_factory=list)

    # -- Intake inputs -------------------------------------------------------
    raw_form_payload: Dict[str, Any] = Field(default_factory=dict)
    asset_references: List[str] = Field(default_factory=list)

    # -- Retrieved context (keyed by stage name) -----------------------------
    retrieved_context: Dict[str, List[Dict[str, Any]]] = Field(default_factory=dict)

    # -- Per-stage outputs (None until that stage runs) ----------------------
    intake_output: Optional[IntakeOutput] = None
    design_output: Optional[DesignOutput] = None
    code_generation_output: Optional[CodeGenerationOutput] = None
    content_output: Optional[ContentOutput] = None
    seo_output: Optional[SEOOutput] = None
    approval_gate_output: Optional[ApprovalGateOutput] = None
    deployment_output: Optional[DeploymentOutput] = None

    # -- Human review signals ------------------------------------------------
    approved: Optional[bool] = None
    reviewer_notes: Optional[str] = None
    preview_url: Optional[str] = None
    review_flag: Optional[ReviewFlag] = None

    # -- Cost tracking -------------------------------------------------------
    cost_summary: CostSummary = Field(default_factory=CostSummary)

    # -- Errors and warnings -------------------------------------------------
    errors: List[ErrorEnvelope] = Field(default_factory=list)
    warnings: List[WarningEnvelope] = Field(default_factory=list)

    # -- Observability -------------------------------------------------------
    trace: Trace = Field(default_factory=Trace)

    model_config = {"use_enum_values": False}
