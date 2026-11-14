"""Storyboard Schemas for AutoStudio."""

from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field, model_validator

from schemas._gemini_compat import nonnegative_wire_schema


class SceneObject(BaseModel):
    name: str = Field(..., description="Unique variable/object identifier in scene.")
    object_type: str = Field(..., description="Manim object type (e.g. Text, MathTex, Circle, Axes, Arrow).")
    description: str = Field(..., description="Description of the visual element.")
    color: str = Field(default="WHITE", description="Color name or hex code.")
    initial_position: str = Field(default="ORIGIN", description="Position descriptor e.g. UP, DOWN*2, LEFT*3.")


class SceneTransition(BaseModel):
    transition_type: str = Field(
        default="FadeOut",
        description="Type of transition out: FadeOut, ReplacementTransform, Uncreate, Transform, None."
    )
    target_state: str = Field(
        default="clear",
        description="Objects carried over or cleared: 'clear_all', 'keep_axes', 'persist_title'."
    )
    duration: float = Field(default=1.0, ge=0.0, description="Transition time in seconds.")


class StoryboardScene(BaseModel):
    scene_id: str = Field(..., description="Unique scene identifier e.g. 'scene_1'.")
    title: str = Field(..., description="Descriptive title of the scene.")
    purpose: str = Field(..., description="Educational objective of this scene.")
    narration: str = Field(..., description="Spoken or voiceover narrative text.")
    duration: float = Field(
        ...,
        gt=0,
        json_schema_extra=nonnegative_wire_schema,
        description="Duration in seconds (strictly positive).",
    )
    visual_description: str = Field(..., description="Visual scene composition and layout.")
    animation_plan: List[str] = Field(..., min_length=1, description="Step-by-step animation instructions.")
    on_screen_text: List[str] = Field(default_factory=list, description="Text labels displayed on screen.")
    mathematical_expressions: List[str] = Field(
        default_factory=list,
        description="LaTeX mathematical expressions formatted for MathTex."
    )
    transition: SceneTransition = Field(default_factory=SceneTransition)
    continuity_notes: str = Field(default="", description="Visual elements carrying over from prior scene.")
    required_objects: List[SceneObject] = Field(default_factory=list, description="Key Manim objects in this scene.")
    expected_final_state: str = Field(..., description="Visual state at the end of the scene.")


class Storyboard(BaseModel):
    """Complete machine-readable storyboard artifact."""
    project_id: str
    title: str
    description: str
    target_audience: str
    estimated_duration: float = Field(..., gt=0, json_schema_extra=nonnegative_wire_schema)
    visual_style: str = "Dark Technical"
    scenes: List[StoryboardScene] = Field(..., min_length=1)
    global_continuity_notes: str = Field(default="", description="Overall visual theme and continuity guidelines.")

    @model_validator(mode="after")
    def validate_storyboard(self) -> Storyboard:
        # Check uniqueness of scene IDs
        seen_ids = set()
        for scene in self.scenes:
            if scene.scene_id in seen_ids:
                raise ValueError(f"Duplicate scene_id found: '{scene.scene_id}'. Scene IDs must be unique.")
            seen_ids.add(scene.scene_id)

        # Calculate sum of scene durations
        total_scene_duration = sum(scene.duration for scene in self.scenes)
        if total_scene_duration <= 0:
            raise ValueError("Total scene duration must be greater than zero.")

        # If estimated_duration diverges by more than 25%, re-sync or raise
        if abs(self.estimated_duration - total_scene_duration) > max(5.0, 0.25 * self.estimated_duration):
            # Align estimated_duration to calculated sum
            self.estimated_duration = round(total_scene_duration, 2)

        return self

