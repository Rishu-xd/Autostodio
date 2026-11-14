"""Code Critic Agent for AutoStudio."""

from __future__ import annotations

import ast
from typing import Optional
from agents.base import BaseAgent
from config import GEMINI_REVIEW_MODEL
from schemas.generation import GeneratedCodeArtifact
from schemas.review import CodeReview, CodeReviewIssue
from schemas.storyboard import Storyboard


class CodeCritic(BaseAgent[GeneratedCodeArtifact, CodeReview]):
    """Analyzes generated Manim code for syntax errors, API correctness, and scene construction."""

    name = "CodeCritic"
    prompt_file = "code_critic.md"
    output_schema = CodeReview

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

    def _static_syntax_check(self, code_str: str) -> tuple[bool, Optional[str], Optional[int]]:
        """Validate code syntax using standard Python AST."""
        try:
            ast.parse(code_str)
            return True, None, None
        except SyntaxError as e:
            return False, e.msg, e.lineno

    def run(
        self,
        code_artifact: GeneratedCodeArtifact,
        storyboard: Optional[Storyboard] = None,
        **kwargs,
    ) -> CodeReview:
        self.log("Performing static and semantic analysis of generated Manim code...")

        # 1. Deterministic AST syntax check
        syntax_ok, syntax_err, line_no = self._static_syntax_check(code_artifact.code)
        if not syntax_ok:
            self.log(f"Deterministic AST syntax check failed at line {line_no}: {syntax_err}", level=30)
            review = CodeReview(
                syntax_valid=False,
                manim_imports_valid=True,
                overall_score=20,
                approval_status="rejected",
                summary=f"Python SyntaxError at line {line_no}: {syntax_err}",
                issues=[
                    CodeReviewIssue(
                        line_number=line_no,
                        category="syntax",
                        severity="critical",
                        problem=f"SyntaxError: {syntax_err}",
                        suggested_correction="Fix syntax error and ensure valid Python syntax.",
                    )
                ],
                revision_instructions=[f"Fix Python SyntaxError at line {line_no}: {syntax_err}"],
            )
            if self.artifact_manager:
                self.artifact_manager.save_code_review(review)
            return review

        # 2. LLM Semantic & API Inspection
        storyboard_spec = (
            f"\nORIGINAL STORYBOARD REQUIREMENTS:\n{storyboard.model_dump_json(indent=2)}" if storyboard else ""
        )

        prompt = f"""
Review the following generated Manim Community code before rendering:

GENERATED CODE:
```python
{code_artifact.code}
```
{storyboard_spec}

Check:
1. Python syntax & imports (manim, numpy).
2. Manim Community API accuracy (e.g. no deprecated or invented classes/methods).
3. Variable scoping: Are all variables declared before animation calls?
4. Scene hygiene: Does it properly fade out or clear previous objects between scenes to prevent visual overlap?
5. Alignment with storyboard scenes and timing.

Provide scores, issues, and specific corrections.
"""

        review = self.client.generate_structured(
            prompt=prompt,
            response_schema=self.output_schema,
            model=self.model,
            system_instruction=self.system_prompt,
            temperature=0.1,
        )

        review.syntax_valid = True

        has_critical = any(issue.severity == "critical" for issue in review.issues)
        has_high = any(issue.severity == "high" for issue in review.issues)

        if has_critical or review.overall_score < 50:
            review.approval_status = "rejected"
        elif has_high or review.overall_score < 80:
            review.approval_status = "needs_revision"
        else:
            review.approval_status = "approved"

        self.log(f"Code review complete. Score: {review.overall_score}/100, Status: {review.approval_status.upper()}")

        if self.artifact_manager:
            self.artifact_manager.save_code_review(review)

        return review

