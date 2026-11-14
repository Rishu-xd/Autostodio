"""Storyboard Critic Agent for AutoStudio."""

from __future__ import annotations

from typing import Optional
from agents.base import BaseAgent
from config import GEMINI_REVIEW_MODEL
from schemas.research import ResearchArtifact
from schemas.review import StoryboardReview
from schemas.storyboard import Storyboard


class StoryboardCritic(BaseAgent[Storyboard, StoryboardReview]):
    """Critiques the storyboard for narrative flow, visual clarity, and Manim feasibility."""

    name = "StoryboardCritic"
    prompt_file = "storyboard_critic.md"
    output_schema = StoryboardReview

    def __init__(
        self,
        client=None,
        model: Optional[str] = None,
        artifact_manager=None,
    ):
        super().__init__(
            client=client,
            model=model or GEMINI_REVIEW_MODEL,
            artifact_manager=artifact_manager,
        )

    def run(
        self,
        storyboard: Storyboard,
        research: Optional[ResearchArtifact] = None,
        **kwargs,
    ) -> StoryboardReview:
        self.log(f"Critiquing storyboard with {len(storyboard.scenes)} scenes...")

        research_context = (
            f"\nORIGINAL RESEARCH CONTEXT:\n{research.model_dump_json(indent=2)}" if research else ""
        )

        prompt = f"""
Evaluate the following storyboard for an automated Manim video production:

STORYBOARD:
{storyboard.model_dump_json(indent=2)}
{research_context}

Evaluate:
1. Narrative flow and conceptual progression.
2. Visual clarity and avoidance of overcrowded text slides.
3. Manim feasibility (can standard Manim primitives animate this smoothly?).
4. Mathematical & formula correctness.
5. Timing balance and scene transitions.

Provide structured feedback, scores, and clear revision instructions if needed.
"""

        review = self.client.generate_structured(
            prompt=prompt,
            response_schema=self.output_schema,
            model=self.model,
            system_instruction=self.system_prompt,
            temperature=0.1,
        )

        has_critical = any(issue.severity == "critical" for issue in review.issues)
        has_high = any(issue.severity == "high" for issue in review.issues)

        if has_critical or review.overall_score < 50:
            review.approval_status = "rejected"
        elif has_high or review.overall_score < 80:
            review.approval_status = "needs_revision"
        else:
            review.approval_status = "approved"

        self.log(f"Storyboard review complete. Score: {review.overall_score}/100, Status: {review.approval_status.upper()}")

        if self.artifact_manager:
            self.artifact_manager.save_storyboard_review(review)

        return review

