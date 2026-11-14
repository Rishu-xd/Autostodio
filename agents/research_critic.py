"""Research Critic Agent for AutoStudio."""

from __future__ import annotations

from typing import Optional
from agents.base import BaseAgent
from config import GEMINI_REVIEW_MODEL
from schemas.research import ResearchArtifact
from schemas.review import ResearchReview


class ResearchCritic(BaseAgent[ResearchArtifact, ResearchReview]):
    """Critiques and validates research artifacts for factual accuracy and clarity."""

    name = "ResearchCritic"
    prompt_file = "research_critic.md"
    output_schema = ResearchReview

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

    def run(self, research: ResearchArtifact, **kwargs) -> ResearchReview:
        self.log(f"Evaluating research artifact for topic: '{research.topic}'...")

        prompt = f"""
Evaluate the following research for an educational animation project:

RESEARCH ARTIFACT:
{research.model_dump_json(indent=2)}

Check:
1. Technical correctness and factual consistency.
2. Appropriateness for target audience '{research.target_audience}'.
3. Whether analogies provide effective spatial/visual intuition.
4. Completeness of core concepts.
5. Identification of any dubious unverified facts.

Provide a detailed review with scores and actionable revision instructions.
"""

        review = self.client.generate_structured(
            prompt=prompt,
            response_schema=self.output_schema,
            model=self.model,
            system_instruction=self.system_prompt,
            temperature=0.1,
        )

        # Enforce deterministic Python rules on approval status
        has_critical = any(issue.severity == "critical" for issue in review.issues)
        has_high = any(issue.severity == "high" for issue in review.issues)

        if has_critical or review.overall_score < 50:
            review.approval_status = "rejected"
        elif has_high or review.overall_score < 80:
            review.approval_status = "needs_revision"
        else:
            review.approval_status = "approved"

        self.log(f"Evaluation complete. Score: {review.overall_score}/100, Status: {review.approval_status.upper()}")

        if self.artifact_manager:
            self.artifact_manager.save_research_review(review)

        return review

