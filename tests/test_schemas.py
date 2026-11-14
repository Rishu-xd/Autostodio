"""Tests for AutoStudio Pydantic Schemas."""

import pytest
from pydantic import ValidationError

from schemas.project import (
    ProjectConfig,
    ProjectMetadata,
    ProjectStatus,
    StageExecutionRecord,
    TokenUsage,
)
from schemas.research import (
    AudienceExplanation,
    CoreConcept,
    Misconception,
    ResearchArtifact,
    SourceReference,
)
from schemas.review import (
    CodeReview,
    CodeReviewIssue,
    ResearchReview,
    ReviewIssue,
    StoryboardReview,
    StoryboardReviewIssue,
    VideoReview,
    VideoReviewIssue,
)
from schemas.storyboard import (
    SceneObject,
    SceneTransition,
    Storyboard,
    StoryboardScene,
)
from schemas.generation import GeneratedCodeArtifact


class TestProjectSchemas:
    def test_project_config_defaults(self):
        cfg = ProjectConfig(topic="Fourier Transform")
        assert cfg.topic == "Fourier Transform"
        assert cfg.video_duration == 60.0
        assert cfg.visual_style == "Dark Technical"
        assert cfg.rendering_quality == "low"

    def test_project_config_invalid_duration(self):
        with pytest.raises(ValidationError):
            ProjectConfig(topic="Test", video_duration=-10.0)

    def test_token_usage_accumulation(self):
        usage = TokenUsage()
        usage.add(1000, 2000, cost_per_1m_in=0.10, cost_per_1m_out=0.40)
        assert usage.input_tokens == 1000
        assert usage.output_tokens == 2000
        assert usage.total_tokens == 3000
        assert round(usage.estimated_cost_usd, 6) == 0.0009


class TestResearchSchemas:
    def test_valid_research_artifact(self):
        artifact = ResearchArtifact(
            topic="Gradient Descent",
            target_audience="Engineers",
            target_duration_seconds=60.0,
            summary="An optimization algorithm for training models.",
            core_concepts=[
                CoreConcept(
                    name="Loss Surface",
                    description="Mathematical manifold representing error.",
                    visual_analogy="A 3D valley landscape.",
                    importance="essential",
                )
            ],
            audience_explanation=AudienceExplanation(
                narrative_hook="Imagine hiking down a foggy mountain.",
                intuitive_explanation="Take steps in the steepest downhill direction.",
                key_takeaways=["Steps downhill minimize loss."],
            ),
        )
        assert artifact.topic == "Gradient Descent"
        assert len(artifact.core_concepts) == 1

    def test_research_artifact_requires_concepts(self):
        with pytest.raises(ValidationError):
            ResearchArtifact(
                topic="Empty",
                target_audience="General",
                summary="Nothing",
                core_concepts=[],  # min_length=1
                audience_explanation=AudienceExplanation(
                    narrative_hook="Hook",
                    intuitive_explanation="Explain",
                ),
            )


class TestStoryboardSchemas:
    def test_valid_storyboard(self):
        sb = Storyboard(
            project_id="p1",
            title="Gradient Descent",
            description="Explaining gradient descent",
            target_audience="Beginners",
            estimated_duration=10.0,
            scenes=[
                StoryboardScene(
                    scene_id="scene_1",
                    title="Introduction",
                    purpose="Hook the audience",
                    narration="How does a machine learn?",
                    duration=5.0,
                    visual_description="A neural net graph appears.",
                    animation_plan=["Draw nodes", "Pulse connections"],
                    expected_final_state="Nodes illuminated",
                ),
                StoryboardScene(
                    scene_id="scene_2",
                    title="The Loss Function",
                    purpose="Show the error landscape",
                    narration="We visualize the error.",
                    duration=5.0,
                    visual_description="A parabolic curve draws.",
                    animation_plan=["Draw axes", "Plot parabola"],
                    expected_final_state="Curve on screen",
                ),
            ],
        )
        assert len(sb.scenes) == 2
        assert sb.estimated_duration == 10.0

    def test_storyboard_duplicate_scene_ids(self):
        with pytest.raises(ValueError, match="Duplicate scene_id"):
            Storyboard(
                project_id="p1",
                title="Bad Storyboard",
                description="Duplicate IDs",
                target_audience="All",
                estimated_duration=10.0,
                scenes=[
                    StoryboardScene(
                        scene_id="dup_id",
                        title="Scene A",
                        purpose="A",
                        narration="A",
                        duration=5.0,
                        visual_description="A",
                        animation_plan=["A"],
                        expected_final_state="A",
                    ),
                    StoryboardScene(
                        scene_id="dup_id",  # DUPLICATE
                        title="Scene B",
                        purpose="B",
                        narration="B",
                        duration=5.0,
                        visual_description="B",
                        animation_plan=["B"],
                        expected_final_state="B",
                    ),
                ],
            )

    def test_storyboard_negative_duration(self):
        with pytest.raises(ValidationError):
            StoryboardScene(
                scene_id="scene_1",
                title="Invalid",
                purpose="Fail",
                narration="Fail",
                duration=-5.0,  # Negative duration
                visual_description="Fail",
                animation_plan=["Fail"],
                expected_final_state="Fail",
            )


class TestReviewSchemas:
    def test_research_review(self):
        rev = ResearchReview(
            topic="Calculus",
            overall_score=85,
            approval_status="approved",
            summary="Strong factual presentation.",
            issues=[],
        )
        assert rev.overall_score == 85
        assert rev.approval_status == "approved"

    def test_code_review(self):
        cr = CodeReview(
            syntax_valid=True,
            manim_imports_valid=True,
            overall_score=90,
            approval_status="approved",
            summary="Clean Manim implementation.",
            issues=[],
        )
        assert cr.syntax_valid is True

    def test_video_review(self):
        vr = VideoReview(
            overall_score=88,
            approval_status="approved",
            visual_quality_rating=9,
            summary="Crisp visuals and legible equations.",
            issues=[],
        )
        assert vr.visual_quality_rating == 9

