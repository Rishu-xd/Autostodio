"""Tests for AutoStudio Pipeline Orchestrator."""

import shutil
from pathlib import Path
from unittest.mock import MagicMock
import pytest

from core.artifact_manager import ArtifactManager
from core.orchestrator import Orchestrator
from core.renderer import RenderResult
from core.retry_manager import RetryManager, RevisionLimitExceeded
from core.state_manager import StateManager
from core.video_inspector import VideoInspectionResult, VideoMetadata
from schemas.generation import GeneratedCodeArtifact
from schemas.project import ProjectConfig, ProjectMetadata, ProjectStatus, TokenUsage
from schemas.research import AudienceExplanation, CoreConcept, ResearchArtifact
from schemas.review import (
    CodeReview,
    ResearchReview,
    StoryboardReview,
    VideoReview,
)
from schemas.storyboard import Storyboard, StoryboardScene


@pytest.fixture
def temp_environment(tmp_path):
    storage_dir = tmp_path / "storage" / "projects"
    db_path = tmp_path / "storage" / "autostudio.db"
    storage_dir.mkdir(parents=True, exist_ok=True)

    state = StateManager(db_path=db_path)
    yield storage_dir, state
    shutil.rmtree(tmp_path, ignore_errors=True)


def test_create_project(temp_environment):
    storage_dir, state = temp_environment
    orchestrator = Orchestrator(state_manager=state)

    config = ProjectConfig(topic="Backpropagation", video_duration=45.0)
    meta = orchestrator.create_project(topic="Backpropagation", config=config, project_id="test_backprop")

    assert meta.project_id == "test_backprop"
    assert meta.status == ProjectStatus.CREATED
    assert meta.current_stage == "INITIALIZED"

    saved = state.get_project("test_backprop")
    assert saved is not None
    assert saved.topic == "Backpropagation"


def test_retry_manager_bounds():
    rm = RetryManager(max_revisions=2)
    assert rm.can_revise("RESEARCH")

    rm.record_revision("RESEARCH")  # 1
    assert rm.can_revise("RESEARCH")

    rm.record_revision("RESEARCH")  # 2
    assert not rm.can_revise("RESEARCH")

    with pytest.raises(RevisionLimitExceeded):
        rm.record_revision("RESEARCH")  # 3 > 2 -> Raises


def test_orchestrator_pipeline_with_mocks(temp_environment):
    storage_dir, state = temp_environment

    # Mock Gemini Client
    mock_gemini = MagicMock()
    mock_gemini.token_usage = TokenUsage(input_tokens=1000, output_tokens=500, total_tokens=1500, estimated_cost_usd=0.002)

    # Mock Renderer
    mock_renderer = MagicMock()
    mock_renderer.render.return_value = RenderResult(
        success=True,
        video_path=str(storage_dir / "test_pipe" / "output" / "final.mp4"),
        duration_seconds=12.5,
        exit_code=0,
    )

    # Mock Video Inspector
    mock_inspector = MagicMock()
    mock_inspector.inspect_video.return_value = VideoInspectionResult(
        video_path="final.mp4",
        metadata=VideoMetadata(duration_seconds=30.0, width=854, height=480, fps=30.0, total_frames=900, file_size_bytes=1024),
        extracted_frames=[],
        is_valid=True,
    )

    # Set up canned agent responses
    sample_research = ResearchArtifact(
        topic="QuickSort",
        target_audience="Engineers",
        summary="Divide and conquer sorting.",
        core_concepts=[CoreConcept(name="Pivot", description="Partitioning element", visual_analogy="A glowing barrier")],
        audience_explanation=AudienceExplanation(narrative_hook="Sorting fast", intuitive_explanation="Partition and conquer"),
    )
    sample_research_review = ResearchReview(
        topic="QuickSort",
        overall_score=92,
        approval_status="approved",
        summary="Factually accurate.",
    )
    sample_storyboard = Storyboard(
        project_id="test_pipe",
        title="QuickSort Explained",
        description="Animation",
        target_audience="Engineers",
        estimated_duration=30.0,
        scenes=[
            StoryboardScene(
                scene_id="scene_1",
                title="Intro",
                purpose="Show unsorted array",
                narration="Here is an unsorted list.",
                duration=30.0,
                visual_description="Array bars appear.",
                animation_plan=["Create bars"],
                expected_final_state="Bars on screen",
            )
        ],
    )
    sample_storyboard_review = StoryboardReview(
        overall_score=88,
        approval_status="approved",
        summary="Feasible and well structured.",
    )
    sample_code = GeneratedCodeArtifact(
        project_id="test_pipe",
        code="from manim import *\nclass MainScene(Scene):\n    def construct(self):\n        pass\n",
    )
    sample_code_review = CodeReview(
        syntax_valid=True,
        overall_score=95,
        approval_status="approved",
        summary="Valid syntax.",
    )
    sample_video_review = VideoReview(
        overall_score=90,
        approval_status="approved",
        visual_quality_rating=9,
        summary="Excellent animation render.",
    )

    # Schema-based dispatch for mock structured returns
    def mock_generate_structured(prompt, response_schema, **kwargs):
        if response_schema == ResearchArtifact:
            return sample_research
        elif response_schema == ResearchReview:
            return sample_research_review
        elif response_schema == Storyboard:
            return sample_storyboard
        elif response_schema == StoryboardReview:
            return sample_storyboard_review
        elif response_schema == GeneratedCodeArtifact:
            return sample_code
        elif response_schema == CodeReview:
            return sample_code_review
        elif response_schema == VideoReview:
            return sample_video_review
        return sample_research

    mock_gemini.generate_structured.side_effect = mock_generate_structured
    mock_gemini.generate_multimodal.return_value = sample_video_review

    orchestrator = Orchestrator(
        gemini_client=mock_gemini,
        state_manager=state,
        renderer=mock_renderer,
        video_inspector=mock_inspector,
    )

    # Create project
    meta = orchestrator.create_project(
        topic="QuickSort",
        config=ProjectConfig(topic="QuickSort", video_duration=30.0),
        project_id="test_pipe",
    )

    # Run pipeline
    result = orchestrator.run_pipeline("test_pipe")

    assert result.status == ProjectStatus.COMPLETED
    assert result.current_stage == "FINISHED"

    # Verify state in DB
    final_db = state.get_project("test_pipe")
    assert final_db.status == ProjectStatus.COMPLETED
