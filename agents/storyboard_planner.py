"""Storyboard Planner Agent for AutoStudio."""

from __future__ import annotations

from typing import Optional
from agents.base import BaseAgent
from config import GEMINI_MODEL
from schemas.project import ProjectConfig
from schemas.research import ResearchArtifact
from schemas.review import StoryboardReview
from schemas.storyboard import Storyboard


class StoryboardPlanner(BaseAgent[ResearchArtifact, Storyboard]):
    """Designs a structured, kinetic, scene-by-scene Manim storyboard from research."""

    name = "StoryboardPlanner"
    prompt_file = "storyboard_planner.md"
    output_schema = Storyboard

    def __init__(
        self,
        client=None,
        model: Optional[str] = None,
        artifact_manager=None,
    ):
        super().__init__(
            client=client,
            model=model or GEMINI_MODEL,
            artifact_manager=artifact_manager,
        )

    def run(
        self,
        research: ResearchArtifact,
        config: ProjectConfig,
        project_id: str = "project",
        revision_feedback: Optional[StoryboardReview] = None,
        **kwargs,
    ) -> Storyboard:
        self.log(f"Planning storyboard for topic: '{research.topic}' (Target: {config.video_duration}s)...")

        prompt_parts = [
            f"PROJECT ID: {project_id}",
            f"TOPIC: {research.topic}",
            f"TARGET AUDIENCE: {config.target_audience}",
            f"TARGET DURATION: {config.video_duration} seconds",
            f"VISUAL STYLE: {config.visual_style}",
            "\nRESEARCH FOUNDATION:",
            research.model_dump_json(indent=2),
            "\nSTORYBOARD REQUIREMENTS:",
            "- Break down the explanation into 3 to 6 distinct scenes.",
            "- Avoid wall-of-text slides. Every scene must describe animated visual objects (axes, graphs, dots, arrows, shapes, transforms).",
            "- Allocate positive durations (e.g. 5.0 to 12.0s per scene) such that total duration matches target duration.",
            "- Ensure scene IDs are unique strings like 'scene_1', 'scene_2', etc.",
            "- Provide LaTeX strings for mathematical expressions using MathTex syntax.",
        ]

        if revision_feedback:
            prompt_parts.append("\nPREVIOUS CRITIC FEEDBACK TO RESOLVE:")
            prompt_parts.append(f"Critic Score: {revision_feedback.overall_score}/100")
            prompt_parts.append(f"Summary: {revision_feedback.summary}")
            if revision_feedback.revision_instructions:
                prompt_parts.append("Action Instructions:")
                for inst in revision_feedback.revision_instructions:
                    prompt_parts.append(f"- {inst}")
            if revision_feedback.issues:
                prompt_parts.append("Specific Issues:")
                for issue in revision_feedback.issues:
                    prompt_parts.append(f"- [{issue.scene_id} - {issue.category.upper()}] {issue.problem} -> Fix: {issue.suggested_correction}")

        prompt = "\n".join(prompt_parts)

        storyboard = self.client.generate_structured(
            prompt=prompt,
            response_schema=self.output_schema,
            model=self.model,
            system_instruction=self.system_prompt,
            temperature=0.3,
        )

        storyboard.project_id = project_id
        storyboard.visual_style = config.visual_style

        self.log(f"Storyboard planned with {len(storyboard.scenes)} scenes. Total duration: {storyboard.estimated_duration:.1f}s.")

        if self.artifact_manager:
            self.artifact_manager.save_storyboard(storyboard)

        return storyboard

