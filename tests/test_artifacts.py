"""Tests for AutoStudio Artifact Manager."""

import shutil
from pathlib import Path
import pytest

from core.artifact_manager import ArtifactManager
from schemas.generation import GeneratedCodeArtifact
from schemas.project import ProjectConfig, ProjectMetadata
from schemas.research import AudienceExplanation, CoreConcept, ResearchArtifact
from schemas.storyboard import Storyboard, StoryboardScene


@pytest.fixture
def temp_artifact_manager(tmp_path):
    mgr = ArtifactManager("test_proj_123", base_storage_dir=tmp_path)
    yield mgr
    shutil.rmtree(tmp_path, ignore_errors=True)


def test_directory_initialization(temp_artifact_manager):
    assert temp_artifact_manager.project_dir.exists()
    assert temp_artifact_manager.research_dir.exists()
    assert temp_artifact_manager.research_history_dir.exists()
    assert temp_artifact_manager.storyboard_dir.exists()
    assert temp_artifact_manager.src_dir.exists()
    assert temp_artifact_manager.rendering_dir.exists()
    assert temp_artifact_manager.output_dir.exists()


def test_atomic_write_and_load_research(temp_artifact_manager):
    artifact = ResearchArtifact(
        topic="Transformers",
        target_audience="Engineers",
        summary="Attention is all you need.",
        core_concepts=[
            CoreConcept(
                name="Self-Attention",
                description="Relating different positions of a single sequence.",
                visual_analogy="Connecting lines between words with glowing intensity.",
                importance="essential",
            )
        ],
        audience_explanation=AudienceExplanation(
            narrative_hook="How can models grasp context instantly?",
            intuitive_explanation="Looking at all words at once.",
        ),
    )

    temp_artifact_manager.save_research(artifact, archive=False)
    assert temp_artifact_manager.research_path.exists()

    loaded = temp_artifact_manager.load_research()
    assert loaded is not None
    assert loaded.topic == "Transformers"
    assert loaded.core_concepts[0].name == "Self-Attention"


def test_version_archiving(temp_artifact_manager):
    artifact_v1 = ResearchArtifact(
        topic="Alpha",
        target_audience="General",
        summary="Version 1",
        core_concepts=[CoreConcept(name="C1", description="D1", visual_analogy="A1")],
        audience_explanation=AudienceExplanation(narrative_hook="H1", intuitive_explanation="E1"),
    )
    temp_artifact_manager.save_research(artifact_v1, archive=True)

    # Save v2 with archive=True
    artifact_v2 = ResearchArtifact(
        topic="Alpha",
        target_audience="General",
        summary="Version 2 Updated",
        core_concepts=[CoreConcept(name="C1", description="D1", visual_analogy="A1")],
        audience_explanation=AudienceExplanation(narrative_hook="H1", intuitive_explanation="E1"),
    )
    temp_artifact_manager.save_research(artifact_v2, archive=True)

    # Check that an archived file was written in history
    archived_files = list(temp_artifact_manager.research_history_dir.glob("*.json"))
    assert len(archived_files) >= 1

    current = temp_artifact_manager.load_research()
    assert current.summary == "Version 2 Updated"


def test_save_and_load_code_artifact(temp_artifact_manager):
    code_artifact = GeneratedCodeArtifact(
        project_id="test_proj_123",
        code="from manim import *\nclass MainScene(Scene):\n    def construct(self):\n        pass\n",
        visual_theme="Dark Technical",
    )
    temp_artifact_manager.save_generated_code(code_artifact, archive=False)

    assert temp_artifact_manager.main_code_path.exists()
    assert "class MainScene(Scene):" in temp_artifact_manager.main_code_path.read_text()

    loaded = temp_artifact_manager.load_generated_code()
    assert loaded is not None
    assert loaded.visual_theme == "Dark Technical"

