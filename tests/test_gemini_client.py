"""Tests for AutoStudio Gemini Client."""

from unittest.mock import MagicMock
import pytest

from core.gemini_client import GeminiClient, GeminiClientError
from schemas.project import TokenUsage
from schemas.research import AudienceExplanation, CoreConcept, ResearchArtifact


def test_missing_api_key_raises_gracefully():
    client = GeminiClient(api_key="")
    assert not client.is_configured
    with pytest.raises(GeminiClientError, match="Gemini API key is not configured"):
        client.generate_text("Hello")


def test_clean_json_text():
    client = GeminiClient(api_key="test_key")

    raw_json = '{"key": "value"}'
    assert client._clean_json_text(raw_json) == '{"key": "value"}'

    markdown_json = '```json\n{"key": "value"}\n```'
    assert client._clean_json_text(markdown_json) == '{"key": "value"}'

    markdown_generic = '```\n{"key": "value"}\n```'
    assert client._clean_json_text(markdown_generic) == '{"key": "value"}'


def test_token_tracking_with_mock():
    client = GeminiClient(api_key="test_key")

    mock_resp = MagicMock()
    mock_resp.usage_metadata.prompt_token_count = 500
    mock_resp.usage_metadata.candidates_token_count = 200

    client._record_usage(mock_resp)

    assert client.token_usage.input_tokens == 500
    assert client.token_usage.output_tokens == 200
    assert client.token_usage.total_tokens == 700
    assert client.token_usage.estimated_cost_usd > 0


def test_generate_structured_with_mock_client():
    client = GeminiClient(api_key="test_key")
    mock_genai_client = MagicMock()
    client._client = mock_genai_client

    sample_json = """
    {
      "topic": "Neural Networks",
      "target_audience": "Beginners",
      "summary": "A collection of connected nodes.",
      "core_concepts": [
        {
          "name": "Neuron",
          "description": "Calculates weighted sum",
          "visual_analogy": "A glowing circle",
          "importance": "essential"
        }
      ],
      "audience_explanation": {
        "narrative_hook": "How brains compute",
        "intuitive_explanation": "Signals pass between nodes"
      }
    }
    """
    mock_response = MagicMock()
    mock_response.text = sample_json
    mock_response.usage_metadata.prompt_token_count = 100
    mock_response.usage_metadata.candidates_token_count = 80
    mock_genai_client.models.generate_content.return_value = mock_response

    result = client.generate_structured(
        prompt="Explain neural networks",
        response_schema=ResearchArtifact,
    )

    assert isinstance(result, ResearchArtifact)
    assert result.topic == "Neural Networks"
    assert len(result.core_concepts) == 1
    assert result.core_concepts[0].name == "Neuron"

