"""Code Generator Agent for AutoStudio."""

from __future__ import annotations

import re
from typing import Optional
from agents.base import BaseAgent
from config import GEMINI_CODE_MODEL
from core.visual_themes import get_theme
from schemas.generation import GeneratedCodeArtifact
from schemas.project import ProjectConfig
from schemas.review import CodeReview, VideoReview
from schemas.storyboard import Storyboard


class CodeGenerator(BaseAgent[Storyboard, GeneratedCodeArtifact]):
    """Translates storyboard scenes into complete, executable Manim animation code."""

    name = "CodeGenerator"
    prompt_file = "code_generator.md"
    output_schema = GeneratedCodeArtifact

    def __init__(
        self,
        client=None,
        model: Optional[str] = None,
        artifact_manager=None,
    ):
        super().__init__(
            client=client,
            model=model or GEMINI_CODE_MODEL,
            artifact_manager=artifact_manager,
        )

    def _clean_python_code(self, code: str) -> str:
        """Strip markdown python code fences if wrapped."""
        code = code.strip()
        match = re.search(r"^```(?:python)?\s*(.*?)\s*```$", code, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return code

    def run(
        self,
        storyboard: Storyboard,
        config: ProjectConfig,
        project_id: str = "project",
        code_review: Optional[CodeReview] = None,
        video_review: Optional[VideoReview] = None,
        **kwargs,
    ) -> GeneratedCodeArtifact:
        self.log(f"Generating Manim Community Python code for {len(storyboard.scenes)} scenes...")

        theme = get_theme(config.visual_style)
        theme_setup_code = theme.get_manim_setup_code()

        prompt_parts = [
            f"PROJECT ID: {project_id}",
            f"TITLE: {storyboard.title}",
            f"VISUAL THEME: {theme.name}",
            f"TARGET DURATION: {storyboard.estimated_duration:.1f} seconds",
            "\nTHEME PALETTE CONSTANTS:",
            f"- Background Color: '{theme.background_color}'",
            f"- Primary Accent: '{theme.primary_color}'",
            f"- Secondary Accent: '{theme.secondary_color}'",
            f"- Accent Color: '{theme.accent_color}'",
            f"- Text Color: '{theme.text_color}'",
            f"- Math Formula Color: '{theme.math_color}'",
            f"- Highlight Color: '{theme.highlight_color}'",
            "\nTHEME SETUP SNIPPET FOR SCENE.construct():",
            theme_setup_code,
            "\nCOMPLETE STORYBOARD SPECIFICATION:",
            storyboard.model_dump_json(indent=2),
            "\nCODE GENERATION REQUIREMENTS:",
            "1. Output a single primary scene class: `class MainScene(Scene):`.",
            "2. Ensure all imports are included: `from manim import *` and `import numpy as np`.",
            "3. Implement `construct(self):` with each storyboard scene implemented in sequence.",
            "4. Add clear comments marking the start of each scene (e.g. `# --- Scene 1: Introduction ---`).",
            "5. Between scenes, smoothly clear previous visual elements using `self.play(*[FadeOut(m) for m in self.mobjects])` or appropriate transforms to prevent overlapping clutter.",
            "6. Use `Text('...', color=TEXT_COLOR)` and `MathTex(r'...', color=MATH_COLOR)`.",
            "7. All animations MUST use valid Manim Community API methods.",
            "8. The Python code must be 100% executable without placeholders.",
        ]

        if code_review:
            prompt_parts.append("\nPREVIOUS CODE REVIEW FEEDBACK TO FIX:")
            prompt_parts.append(f"Critic Score: {code_review.overall_score}/100")
            prompt_parts.append(f"Summary: {code_review.summary}")
            if code_review.revision_instructions:
                prompt_parts.append("Fix Instructions:")
                for inst in code_review.revision_instructions:
                    prompt_parts.append(f"- {inst}")
            if code_review.issues:
                prompt_parts.append("Specific Code Issues:")
                for issue in code_review.issues:
                    loc = f"Line {issue.line_number}: " if issue.line_number else ""
                    prompt_parts.append(f"- {loc}[{issue.category}] {issue.problem} -> Fix: {issue.suggested_correction}")

        if video_review:
            prompt_parts.append("\nPREVIOUS VIDEO REVIEW FEEDBACK:")
            prompt_parts.append(f"Video Quality Rating: {video_review.visual_quality_rating}/10")
            prompt_parts.append(f"Summary: {video_review.summary}")
            if video_review.scenes_needing_revision:
                prompt_parts.append(f"Scenes Needing Revision: {', '.join(video_review.scenes_needing_revision)}")
            if video_review.revision_instructions:
                prompt_parts.append("Visual Fix Instructions:")
                for inst in video_review.revision_instructions:
                    prompt_parts.append(f"- {inst}")

        prompt = "\n".join(prompt_parts)

        artifact = self.client.generate_structured(
            prompt=prompt,
            response_schema=self.output_schema,
            model=self.model,
            system_instruction=self.system_prompt,
            temperature=0.2,
        )

        artifact.code = self._clean_python_code(artifact.code)
        artifact.project_id = project_id
        artifact.visual_theme = theme.name
        artifact.estimated_runtime_seconds = storyboard.estimated_duration

        self.log(f"Generated {len(artifact.code.splitlines())} lines of Manim code.")

        if self.artifact_manager:
            self.artifact_manager.save_generated_code(artifact)

        return artifact

