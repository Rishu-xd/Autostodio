"""Tests for Gemini Developer API Schema Compatibility and Structured Output.

Ensures that:
1. All agent response schemas are 100% compatible with the Gemini Developer API.
2. No schemas contain unsupported 'additionalProperties' or 'additional_properties'.
3. Nested schemas are completely valid according to OpenAPI 3.0 / google-genai constraints.
4. Mock Gemini responses parse into Pydantic models.
5. Malformed or invalid responses are handled cleanly without unhandled crashes.
6. Every agent can construct its structured generation request.
"""

from typing import Any, Dict
from unittest.mock import MagicMock
import pytest
from pydantic import BaseModel, ValidationError

from google import genai
from google.genai import _transformers, types
from core.gemini_client import (
    GeminiClient,
    GeminiClientError,
    GeminiSchemaError,
    inspect_schema_for_unsupported_constructs,
    validate_pydantic_schema_compatibility,
)
from schemas.generation import GeneratedCodeArtifact
from schemas.project import (
    ProjectConfig,
    ProjectMetadata,
    StageExecutionRecord,
    StageRevision,
    TokenUsage,
)
from schemas.research import (
    AudienceExplanation,
    CoreConcept,
    Misconception,
    ResearchArtifact,
    SourceReference,
    TermDefinition,
    UnverifiedFact,
)
from schemas.review import (
    CodeReview,
    CodeReviewIssue,
    ResearchReview,
    ReviewIssue,
    SectionReview,
    SourceAudit,
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
from core.retry_manager import RetryManager
from agents.researcher import Researcher
from agents.research_critic import ResearchCritic
from agents.storyboard_planner import StoryboardPlanner
from agents.storyboard_critic import StoryboardCritic
from agents.code_generator import CodeGenerator
from agents.code_critic import CodeCritic
from agents.video_reviewer import VideoReviewer
from core.video_inspector import VideoInspectionResult, VideoMetadata


ALL_AGENT_RESPONSE_SCHEMAS = [
    ResearchArtifact,
    ResearchReview,
    Storyboard,
    StoryboardReview,
    GeneratedCodeArtifact,
    CodeReview,
    VideoReview,
]

ALL_SYSTEM_MODELS = [
    ProjectConfig,
    ProjectMetadata,
    TokenUsage,
    StageExecutionRecord,
    StageRevision,
    TermDefinition,
    CoreConcept,
    AudienceExplanation,
    Misconception,
    SourceReference,
    UnverifiedFact,
    ResearchArtifact,
    SceneObject,
    SceneTransition,
    StoryboardScene,
    Storyboard,
    ReviewIssue,
    SourceAudit,
    SectionReview,
    ResearchReview,
    StoryboardReviewIssue,
    StoryboardReview,
    CodeReviewIssue,
    CodeReview,
    VideoReviewIssue,
    VideoReview,
    GeneratedCodeArtifact,
]


# ---------------------------------------------------------------------------
# 1. Inspect all agent response schemas
# 2. Detect unsupported additionalProperties declarations
# 3. Validate nested schema compatibility
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("schema_cls", ALL_AGENT_RESPONSE_SCHEMAS)
def test_agent_response_schemas_free_of_additional_properties(schema_cls):
    """Ensure no agent response schema contains additionalProperties."""
    json_schema = schema_cls.model_json_schema()
    issues = inspect_schema_for_unsupported_constructs(json_schema)
    assert len(issues) == 0, f"Schema {schema_cls.__name__} has unsupported constructs: {issues}"


@pytest.mark.parametrize("model_cls", ALL_SYSTEM_MODELS)
def test_all_models_sdk_transformer_compatible(model_cls):
    """Ensure every model can be converted via google.genai._transformers.t_schema in Developer API mode."""
    # Dummy client with vertexai=False (Developer API mode)
    client = genai.Client(api_key="dummy_api_key_for_testing")
    assert not client._api_client.vertexai, "Test client must be in Developer API mode"

    # Must not raise ValueError about additionalProperties or ValidationError
    converted_schema = _transformers.t_schema(client._api_client, model_cls)
    assert converted_schema is not None
    assert isinstance(converted_schema, types.Schema)


def test_strict_positive_fields_keep_validation_and_use_supported_wire_schemas():
    cases = [
        (ProjectConfig, {"topic": "Test", "video_duration": 0}, "video_duration"),
        (ProjectConfig, {"topic": "Test", "max_api_budget": 0}, "max_api_budget"),
        (
            StoryboardScene,
            {
                "scene_id": "s1",
                "title": "Scene",
                "purpose": "Explain",
                "narration": "Text",
                "duration": 0,
                "visual_description": "Visual",
                "animation_plan": ["Draw"],
                "expected_final_state": "Done",
            },
            "duration",
        ),
        (
            Storyboard,
            {
                "project_id": "p1",
                "title": "Title",
                "description": "Description",
                "target_audience": "Learners",
                "estimated_duration": 0,
                "scenes": [
                    {
                        "scene_id": "s1",
                        "title": "Scene",
                        "purpose": "Explain",
                        "narration": "Text",
                        "duration": 1,
                        "visual_description": "Visual",
                        "animation_plan": ["Draw"],
                        "expected_final_state": "Done",
                    }
                ],
            },
            "estimated_duration",
        ),
        (
            GeneratedCodeArtifact,
            {"project_id": "p1", "code": "pass", "estimated_runtime_seconds": 0},
            "estimated_runtime_seconds",
        ),
    ]

    for model_cls, model_data, field_name in cases:
        field_schema = model_cls.model_json_schema()["properties"][field_name]
        assert field_schema["minimum"] == 0
        assert "exclusiveMinimum" not in field_schema
        with pytest.raises(ValidationError):
            model_cls.model_validate(model_data)


def test_schema_compatibility_validator_detects_bad_schema():
    """Verify our validator catches unsupported dicts / additionalProperties."""
    class IncompatibleModel(BaseModel):
        bad_dict: Dict[str, Any]  # Arbitrary dict -> additionalProperties

    is_valid, issues = validate_pydantic_schema_compatibility(IncompatibleModel)
    assert is_valid is False
    assert any("additionalProperties" in issue for issue in issues)


def test_schema_compatibility_validator_detects_nested_dynamic_fields():
    class NestedModel(BaseModel):
        values: Dict[str, Any]

    class ParentModel(BaseModel):
        nested: NestedModel

    is_valid, issues = validate_pydantic_schema_compatibility(ParentModel)
    assert is_valid is False
    assert any("additionalProperties" in issue for issue in issues)


def test_client_rejects_incompatible_schema_with_clear_error():
    """Verify GeminiClient._prepare_response_schema raises GeminiSchemaError on bad schemas."""
    class BadModel(BaseModel):
        untyped_dict: Dict[str, str]

    client = GeminiClient(api_key="test_key")
    with pytest.raises(GeminiSchemaError, match="Unrestricted dictionaries and additionalProperties"):
        client._prepare_response_schema(BadModel)


# ---------------------------------------------------------------------------
# 4. Mock Gemini responses and validate Pydantic parsing
# ---------------------------------------------------------------------------

def test_research_artifact_parsing_with_term_definitions():
    """Verify ResearchArtifact parses term definitions cleanly and supports backward-compatible dictionary access."""
    sample_json = """
    {
      "topic": "Backpropagation",
      "target_audience": "Engineers",
      "target_duration_seconds": 60.0,
      "summary": "Chain rule applied to neural networks.",
      "core_concepts": [
        {
          "name": "Chain Rule",
          "description": "Calculates derivative of composition",
          "visual_analogy": "Gears turning each other",
          "importance": "essential"
        }
      ],
      "audience_explanation": {
        "narrative_hook": "How weights learn from errors",
        "intuitive_explanation": "Propagating gradients backward",
        "key_takeaways": ["Gradients guide parameter updates"]
      },
      "important_terminology": [
        {
          "term": "Gradient",
          "definition": "Vector of partial derivatives"
        },
        {
          "term": "Learning Rate",
          "definition": "Step size along the negative gradient"
        }
      ],
      "misconceptions": [],
      "examples_and_analogies": ["Flowing water through pipes"],
      "sources": [],
      "unverified_facts": [],
      "narrative_arc": ["Setup", "Math", "Conclusion"]
    }
    """
    artifact = ResearchArtifact.model_validate_json(sample_json)
    assert len(artifact.important_terminology) == 2
    assert artifact.important_terminology[0].term == "Gradient"
    # Backward compatible dict property
    assert artifact.terminology_dict["Gradient"] == "Vector of partial derivatives"
    assert artifact.terminology_dict["Learning Rate"] == "Step size along the negative gradient"


def test_research_artifact_coerces_legacy_dictionary():
    """Verify backward compatibility: if a dictionary is provided, it is automatically coerced into List[TermDefinition]."""
    data = {
        "topic": "Calculus",
        "target_audience": "Students",
        "summary": "Study of change.",
        "core_concepts": [
            {
                "name": "Derivative",
                "description": "Instantaneous rate of change",
                "visual_analogy": "Slope of tangent line",
                "importance": "essential",
            }
        ],
        "audience_explanation": {
            "narrative_hook": "How fast are we moving?",
            "intuitive_explanation": "Zooming into curves until they look straight.",
            "key_takeaways": ["Tangent slope gives speed"],
        },
        "important_terminology": {
            "Derivative": "Slope at a point",
            "Integral": "Area under curve",
        },
    }
    artifact = ResearchArtifact.model_validate(data)
    assert len(artifact.important_terminology) == 2
    terms = {t.term: t.definition for t in artifact.important_terminology}
    assert terms["Derivative"] == "Slope at a point"
    assert terms["Integral"] == "Area under curve"


def test_project_revision_counts_keep_legacy_mapping_and_retry_behavior():
    metadata = ProjectMetadata(
        project_id="p1",
        title="Title",
        topic="Topic",
        config=ProjectConfig(topic="Topic"),
        revision_counts={"RESEARCH": 2, "STORYBOARD": 1},
    )
    assert metadata.revision_counts_dict == {"RESEARCH": 2, "STORYBOARD": 1}

    retry_manager = RetryManager()
    retry_manager.load_counts(metadata.revision_counts)
    assert retry_manager.export_counts() == {"RESEARCH": 2, "STORYBOARD": 1}


# ---------------------------------------------------------------------------
# 5. Verify malformed responses are handled correctly
# ---------------------------------------------------------------------------

def test_generate_structured_handles_malformed_json():
    """Verify that malformed JSON from an LLM is caught and raises GeminiClientError with details."""
    client = GeminiClient(api_key="test_key")
    mock_genai_client = MagicMock()
    client._client = mock_genai_client

    mock_resp = MagicMock()
    mock_resp.text = "{ malformed json: not valid at all ... "
    mock_resp.usage_metadata.prompt_token_count = 10
    mock_resp.usage_metadata.candidates_token_count = 10
    mock_genai_client.models.generate_content.return_value = mock_resp

    with pytest.raises(GeminiClientError, match="Failed to validate model response|Failed to generate structured response"):
        client.generate_structured(
            prompt="Test prompt",
            response_schema=ResearchArtifact,
            max_retries=1,
        )


# ---------------------------------------------------------------------------
# 6. Verify every agent can construct its structured generation request
# ---------------------------------------------------------------------------

def test_all_agents_can_construct_structured_requests():
    """Verify that all 7 agents can invoke generate_structured / generate_multimodal without schema errors."""
    client = GeminiClient(api_key="test_key")
    mock_genai_client = MagicMock()
    client._client = mock_genai_client

    # Researcher
    researcher = Researcher(client=client)
    mock_genai_client.models.generate_content.return_value = MagicMock(
        text=ResearchArtifact(
            topic="Test",
            target_audience="Devs",
            summary="Sum",
            core_concepts=[CoreConcept(name="C", description="D", visual_analogy="A")],
            audience_explanation=AudienceExplanation(narrative_hook="H", intuitive_explanation="E"),
        ).model_dump_json(),
        usage_metadata=MagicMock(prompt_token_count=10, candidates_token_count=10),
    )
    r_art = researcher.run(ProjectConfig(topic="Test"))
    assert isinstance(r_art, ResearchArtifact)

    # Research Critic
    r_critic = ResearchCritic(client=client)
    mock_genai_client.models.generate_content.return_value = MagicMock(
        text=ResearchReview(
            topic="Test",
            overall_score=90,
            approval_status="approved",
            summary="Good",
        ).model_dump_json(),
        usage_metadata=MagicMock(prompt_token_count=10, candidates_token_count=10),
    )
    r_rev = r_critic.run(r_art)
    assert isinstance(r_rev, ResearchReview)

    # Storyboard Planner
    planner = StoryboardPlanner(client=client)
    mock_genai_client.models.generate_content.return_value = MagicMock(
        text=Storyboard(
            project_id="test",
            title="Title",
            description="Desc",
            target_audience="Devs",
            estimated_duration=10.0,
            scenes=[
                StoryboardScene(
                    scene_id="s1",
                    title="Scene 1",
                    purpose="P",
                    narration="N",
                    duration=10.0,
                    visual_description="V",
                    animation_plan=["A"],
                    expected_final_state="F",
                )
            ],
        ).model_dump_json(),
        usage_metadata=MagicMock(prompt_token_count=10, candidates_token_count=10),
    )
    sb = planner.run(research=r_art, config=ProjectConfig(topic="Test"))
    assert isinstance(sb, Storyboard)

    # Storyboard Critic
    sb_critic = StoryboardCritic(client=client)
    mock_genai_client.models.generate_content.return_value = MagicMock(
        text=StoryboardReview(
            overall_score=85,
            approval_status="approved",
            summary="Approved",
        ).model_dump_json(),
        usage_metadata=MagicMock(prompt_token_count=10, candidates_token_count=10),
    )
    sb_rev = sb_critic.run(sb)
    assert isinstance(sb_rev, StoryboardReview)

    # Code Generator
    code_gen = CodeGenerator(client=client)
    mock_genai_client.models.generate_content.return_value = MagicMock(
        text=GeneratedCodeArtifact(
            project_id="test",
            code="from manim import *\nclass MainScene(Scene):\n    def construct(self):\n        pass\n",
        ).model_dump_json(),
        usage_metadata=MagicMock(prompt_token_count=10, candidates_token_count=10),
    )
    code_art = code_gen.run(storyboard=sb, config=ProjectConfig(topic="Test"))
    assert isinstance(code_art, GeneratedCodeArtifact)

    # Code Critic
    code_critic = CodeCritic(client=client)
    mock_genai_client.models.generate_content.return_value = MagicMock(
        text=CodeReview(
            syntax_valid=True,
            overall_score=95,
            approval_status="approved",
            summary="Clean",
        ).model_dump_json(),
        usage_metadata=MagicMock(prompt_token_count=10, candidates_token_count=10),
    )
    c_rev = code_critic.run(code_art, storyboard=sb)
    assert isinstance(c_rev, CodeReview)

    # Video Reviewer
    video_rev = VideoReviewer(client=client)
    mock_genai_client.models.generate_content.return_value = MagicMock(
        text=VideoReview(
            overall_score=92,
            approval_status="approved",
            visual_quality_rating=9,
            summary="Crisp frames",
        ).model_dump_json(),
        usage_metadata=MagicMock(prompt_token_count=10, candidates_token_count=10),
    )
    dummy_inspection = VideoInspectionResult(
        video_path="dummy.mp4",
        metadata=VideoMetadata(duration_seconds=10.0, width=854, height=480, fps=30.0, total_frames=300, file_size_bytes=100),
        extracted_frames=[],
        is_valid=True,
    )
    v_rev = video_rev.run(inspection=dummy_inspection, storyboard=sb)
    assert isinstance(v_rev, VideoReview)

