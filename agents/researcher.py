"""Researcher Agent for AutoStudio."""

from __future__ import annotations

from typing import Optional
from agents.base import BaseAgent
from config import GEMINI_RESEARCH_MODEL
from schemas.project import ProjectConfig
from schemas.research import ResearchArtifact
from schemas.review import ResearchReview


class Researcher(BaseAgent[ProjectConfig, ResearchArtifact]):
    """Conducts deep domain research on the topic and structures key concepts."""

    name = "Researcher"
    prompt_file = "researcher.md"
    output_schema = ResearchArtifact

    def __init__(
        self,
        client=None,
        model: Optional[str] = None,
        artifact_manager=None,
    ):
        super().__init__(
            client=client,
            model=model or GEMINI_RESEARCH_MODEL,
            artifact_manager=artifact_manager,
        )

    def run(
        self,
        config: ProjectConfig,
        revision_feedback: Optional[ResearchReview] = None,
        **kwargs,
    ) -> ResearchArtifact:
        self.log(f"Conducting research on topic: '{config.topic}' (Target: {config.target_audience})...")

        prompt_parts = [
            f"TOPIC: {config.topic}",
            f"TARGET AUDIENCE: {config.target_audience}",
            f"TARGET DURATION: {config.video_duration} seconds",
            f"RESEARCH DEPTH: {config.research_depth}",
            f"LANGUAGE: {config.language}",
        ]

        if revision_feedback:
            prompt_parts.append("\nPREVIOUS CRITIC FEEDBACK TO ADDRESS:")
            prompt_parts.append(f"Critic Score: {revision_feedback.overall_score}/100")
            prompt_parts.append(f"Critic Summary: {revision_feedback.summary}")
            if revision_feedback.missing_concepts:
                prompt_parts.append(f"Missing Concepts to Add: {', '.join(revision_feedback.missing_concepts)}")
            if revision_feedback.revision_instructions:
                prompt_parts.append("Specific Instructions:")
                for inst in revision_feedback.revision_instructions:
                    prompt_parts.append(f"- {inst}")
            if revision_feedback.issues:
                prompt_parts.append("Issues to Fix:")
                for issue in revision_feedback.issues:
                    prompt_parts.append(f"- [{issue.severity.upper()}] {issue.problem} -> Fix: {issue.suggested_correction}")

        prompt = "\n".join(prompt_parts)

        artifact = self.client.generate_structured(
            prompt=prompt,
            response_schema=self.output_schema,
            model=self.model,
            system_instruction=self.system_prompt,
            temperature=0.3,
        )

        self.log(f"Research completed successfully. Found {len(artifact.core_concepts)} core concepts.")

        if self.artifact_manager:
            self.artifact_manager.save_research(artifact)

        return artifact

