"""Project and Configuration Schemas for AutoStudio."""

from __future__ import annotations

from enum import Enum
from datetime import datetime, timezone
from typing import Any, Dict, Optional, List
from pydantic import BaseModel, Field, field_validator

from schemas._gemini_compat import nonnegative_wire_schema


class ProjectStatus(str, Enum):
    CREATED = "CREATED"
    RESEARCHING = "RESEARCHING"
    RESEARCH_REVIEW = "RESEARCH_REVIEW"
    PLANNING = "PLANNING"
    STORYBOARD_REVIEW = "STORYBOARD_REVIEW"
    GENERATING_CODE = "GENERATING_CODE"
    CODE_REVIEW = "CODE_REVIEW"
    RENDERING = "RENDERING"
    VIDEO_REVIEW = "VIDEO_REVIEW"
    REVISING = "REVISING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ProjectConfig(BaseModel):
    """User-configurable project settings."""
    topic: str = Field(..., description="The main subject or concept to explain.")
    video_title: str = Field(default="", description="Optional custom video title.")
    target_audience: str = Field(
        default="curious learners and technical enthusiasts",
        description="Target audience knowledge level and interest."
    )
    video_duration: float = Field(
        default=60.0,
        gt=0,
        json_schema_extra=nonnegative_wire_schema,
        description="Target duration of video in seconds."
    )
    language: str = Field(default="English", description="Narration and text language.")
    visual_style: str = Field(
        default="Dark Technical",
        description="Visual style theme: 'Dark Technical', 'Minimal Scientific', 'Mathematical Whiteboard', 'Modern Educational', 'Cinematic Abstract'."
    )
    animation_complexity: str = Field(
        default="medium",
        description="Complexity level: 'low', 'medium', 'high'."
    )
    resolution: str = Field(default="854x480", description="Video resolution e.g. 854x480, 1280x720, 1920x1080.")
    frame_rate: int = Field(default=30, ge=15, le=60, description="Animation frames per second.")
    rendering_quality: str = Field(
        default="low",
        description="Manim render quality: 'low' (-ql), 'medium' (-qm), 'high' (-qh)."
    )
    research_depth: str = Field(
        default="comprehensive",
        description="Research depth: 'brief', 'comprehensive', 'deep_technical'."
    )
    max_revision_count: int = Field(default=3, ge=1, le=10, description="Max critic revision loops per stage.")
    max_api_budget: float = Field(
        default=5.0,
        gt=0,
        json_schema_extra=nonnegative_wire_schema,
        description="Maximum API budget allowance in USD.",
    )
    require_approval_before_rendering: bool = Field(
        default=False,
        description="Whether to pause for user confirmation before rendering."
    )
    auto_revise_rejected_scenes: bool = Field(
        default=True,
        description="Whether to automatically revise code when video review flags issues."
    )


class TokenUsage(BaseModel):
    """Cumulative token usage tracking."""
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0

    def add(self, input_t: int, output_t: int, cost_per_1m_in: float = 0.10, cost_per_1m_out: float = 0.40):
        self.input_tokens += input_t
        self.output_tokens += output_t
        self.total_tokens += (input_t + output_t)
        self.estimated_cost_usd += (input_t * cost_per_1m_in / 1_000_000) + (output_t * cost_per_1m_out / 1_000_000)


class StageExecutionRecord(BaseModel):
    """Record of a single stage attempt."""
    stage_name: str
    status: str
    attempt: int = 1
    started_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: Optional[str] = None
    duration_seconds: float = 0.0
    error: Optional[str] = None


class StageRevision(BaseModel):
    """Typed model for stage revision counts avoiding unrestricted dictionary schemas."""
    stage_name: str = Field(..., description="Pipeline stage identifier.")
    count: int = Field(default=0, ge=0, description="Revisions attempted.")


class ProjectMetadata(BaseModel):
    """Overall project metadata stored in state manager and project.json."""
    project_id: str
    title: str
    topic: str
    status: ProjectStatus = ProjectStatus.CREATED
    current_stage: str = "INITIALIZED"
    revision_counts: List[StageRevision] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    config: ProjectConfig
    output_video_path: Optional[str] = None
    token_usage: TokenUsage = Field(default_factory=TokenUsage)
    history: List[StageExecutionRecord] = Field(default_factory=list)

    @field_validator("revision_counts", mode="before")
    @classmethod
    def _coerce_revision_counts(cls, v: Any) -> Any:
        if isinstance(v, dict):
            return [StageRevision(stage_name=k, count=c) for k, c in v.items()]
        return v

    @property
    def revision_counts_dict(self) -> Dict[str, int]:
        return {r.stage_name: r.count for r in self.revision_counts}
