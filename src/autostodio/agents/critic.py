
from google.genai import types

from autostudio.schemas.review import ResearchReview


class ResearchCritic:

    def __init__(self, client, model):
        self.client = client
        self.model = model

    def review(self, research: str) -> ResearchReview:

        print("[Critic] Reviewing research...")

        prompt = f"""
You are a strict technical research reviewer.

Your job is to evaluate research prepared for an
educational technology explainer video.

RESEARCH:
{research}

REVIEW OBJECTIVES:

1. FACTUAL ACCURACY
   - Identify incorrect technical explanations.
   - Identify oversimplifications that could mislead beginners.
   - Check mathematical statements and terminology.

2. COMPLETENESS
   - Identify important missing concepts.
   - Check whether the explanations follow a logical order.
   - Identify unexplained technical terms.

3. SOURCE QUALITY
   - Inspect the source URLs and their relationship to claims.
   - You do NOT have independent web browsing in this task.
   - Never claim a source has been verified when you
     have not inspected its contents.
   - Mark unverified sources appropriately.

4. EDUCATIONAL QUALITY
   - Check whether a beginner could understand the material.
   - Identify confusing explanations.
   - Check whether examples actually explain the concept.

5. REVISION
   - Give precise corrections.
   - Do not rewrite the entire research.
   - Provide actionable instructions for the researcher.

SCORING:

90-100: Excellent, only minor improvements.
75-89: Good, but some improvements are required.
50-74: Significant problems.
0-49: Major factual or structural problems.

APPROVAL RULES:

- Reject research containing critical factual errors.
- Require revision for high-severity issues.
- Do not treat missing source verification as proof
  that a claim is false.
- An approved result is only provisionally approved:
  source verification may still be outstanding.

Be strict, objective and specific.

Return a structured response matching the requested schema.
"""

        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=ResearchReview,
                temperature=0.2
            )
        )

        review = ResearchReview.model_validate_json(
            response.text
        )

        # Enforce basic approval rules in Python too.
        critical = any(
            issue.severity == "critical"
            for issue in review.issues
        )

        high = any(
            issue.severity == "high"
            for issue in review.issues
        )

        if critical:
            review.approval_status = "rejected"

        elif high:
            review.approval_status = "needs_revision"

        print("[Critic] Review completed.")
        print("Score:", review.overall_score)
        print("Status:", review.approval_status)

        return review
