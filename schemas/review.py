"""Review Schemas for AutoStudio Critics and Video Inspection."""

from __future__ import annotations

from typing import List, Literal, Optional
from pydantic import BaseModel, Field


# -------------------------------------------------------------
# Research Review
# -------------------------------------------------------------

class ReviewIssue(BaseModel):
    section: str = Field(..., description="Section or concept where issue was found.")
    severity: Literal["critical", "high", "medium", "low"] = Field(..., description="Severity level.")
    problem: str = Field(..., description="Specific problem identified.")
    explanation: str = Field(..., description="Why this is problematic.")
    suggested_correction: str = Field(..., description="Actionable correction.")


class SourceAudit(BaseModel):
    source_url: str = Field(..., description="Referenced source.")
    related_claim: str = Field(..., description="Associated claim.")
    status: Literal["not_independently_verified", "needs_verification", "potentially_misleading", "verified"] = Field(
        ..., description="Verification status."
    )
    reason: str = Field(..., description="Explanation of status.")


class SectionReview(BaseModel):
    section: str
    score: int = Field(ge=0, le=100)
    feedback: str


class ResearchReview(BaseModel):
    topic: str
    overall_score: int = Field(ge=0, le=100, description="Overall score 0-100.")
    approval_status: Literal["approved", "needs_revision", "rejected"] = Field(
        ..., description="Approval decision."
    )
    summary: str = Field(..., description="Executive review summary.")
    strengths: List[str] = Field(default_factory=list)
    issues: List[ReviewIssue] = Field(default_factory=list)
    missing_concepts: List[str] = Field(default_factory=list)
    section_reviews: List[SectionReview] = Field(default_factory=list)
    source_audits: List[SourceAudit] = Field(default_factory=list)
    revision_instructions: List[str] = Field(default_factory=list)


# -------------------------------------------------------------
# Storyboard Review
# -------------------------------------------------------------

class StoryboardReviewIssue(BaseModel):
    scene_id: str = Field(..., description="Scene ID where issue exists.")
    category: Literal[
        "narrative_flow",
        "visual_clarity",
        "math_correctness",
        "continuity",
        "timing",
        "manim_feasibility"
    ] = Field(..., description="Dimension of issue.")
    severity: Literal["critical", "high", "medium", "low"]
    problem: str = Field(..., description="Issue description.")
    suggested_correction: str = Field(..., description="Recommended fix.")


class StoryboardReview(BaseModel):
    overall_score: int = Field(ge=0, le=100)
    approval_status: Literal["approved", "needs_revision", "rejected"]
    summary: str
    strengths: List[str] = Field(default_factory=list)
    issues: List[StoryboardReviewIssue] = Field(default_factory=list)
    manim_feasibility_score: int = Field(default=80, ge=0, le=100)
    timing_score: int = Field(default=80, ge=0, le=100)
    visual_clarity_score: int = Field(default=80, ge=0, le=100)
    revision_instructions: List[str] = Field(default_factory=list)


# -------------------------------------------------------------
# Code Review
# -------------------------------------------------------------

class CodeReviewIssue(BaseModel):
    line_number: Optional[int] = None
    category: Literal[
        "syntax",
        "undefined_variable",
        "missing_import",
        "invalid_manim_api",
        "scene_construction",
        "missing_requirement",
        "math_error",
        "performance",
        "timing"
    ]
    severity: Literal["critical", "high", "medium", "low"]
    problem: str
    suggested_correction: str


class CodeReview(BaseModel):
    syntax_valid: bool = Field(default=True, description="Whether Python AST parsing passed.")
    manim_imports_valid: bool = Field(default=True, description="Whether required Manim classes are imported.")
    overall_score: int = Field(ge=0, le=100)
    approval_status: Literal["approved", "needs_revision", "rejected"]
    summary: str
    issues: List[CodeReviewIssue] = Field(default_factory=list)
    corrected_code_suggestion: Optional[str] = None
    revision_instructions: List[str] = Field(default_factory=list)


# -------------------------------------------------------------
# Video Review
# -------------------------------------------------------------

class VideoReviewIssue(BaseModel):
    timestamp_or_frame: str = Field(default="", description="Time or frame identifier.")
    scene_id: Optional[str] = None
    category: Literal[
        "visual_correctness",
        "text_readability",
        "clipping",
        "overlapping",
        "blank_frames",
        "missing_animation",
        "continuity",
        "concept_clarity"
    ]
    severity: Literal["critical", "high", "medium", "low"]
    problem: str
    suggested_fix: str


class VideoReview(BaseModel):
    overall_score: int = Field(ge=0, le=100)
    approval_status: Literal["approved", "needs_revision", "rejected"]
    visual_quality_rating: int = Field(ge=1, le=10, description="1-10 aesthetic rating.")
    summary: str
    issues: List[VideoReviewIssue] = Field(default_factory=list)
    scenes_needing_revision: List[str] = Field(default_factory=list, description="List of scene IDs requiring rework.")
    revision_instructions: List[str] = Field(default_factory=list)

