"""Generation Schemas for AutoStudio."""

from __future__ import annotations

from typing import List
from pydantic import BaseModel, Field

from schemas._gemini_compat import nonnegative_wire_schema


class GeneratedCodeArtifact(BaseModel):
    """Complete executable Manim code artifact produced by CodeGenerator."""
    project_id: str
    scene_class_name: str = Field(default="MainScene", description="Primary Manim Scene class name.")
    code: str = Field(..., description="Complete executable Python code.")
    imports: List[str] = Field(default_factory=list, description="List of imported modules.")
    helper_functions: List[str] = Field(default_factory=list, description="Helper functions included.")
    visual_theme: str = Field(default="Dark Technical", description="Visual theme applied.")
    estimated_runtime_seconds: float = Field(
        default=60.0,
        gt=0,
        json_schema_extra=nonnegative_wire_schema,
    )
    notes: str = Field(default="", description="Implementation notes or instructions.")

