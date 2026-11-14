"""Research Schemas for AutoStudio."""

from __future__ import annotations

from typing import Any, Dict, List, Literal
from pydantic import BaseModel, Field, field_validator


class TermDefinition(BaseModel):
    """Explicit typed model for technical terms and their definitions."""
    term: str = Field(..., description="Technical term or keyword.")
    definition: str = Field(..., description="Clear, jargon-free explanation.")


class CoreConcept(BaseModel):
    name: str = Field(..., description="Concept title or component name.")
    description: str = Field(..., description="Clear explanation of the concept.")
    visual_analogy: str = Field(..., description="Suggested visual representation or animation idea.")
    importance: Literal["essential", "supporting", "advanced"] = Field(
        default="essential",
        description="Priority of concept in the video."
    )


class AudienceExplanation(BaseModel):
    narrative_hook: str = Field(..., description="An engaging opening angle.")
    intuitive_explanation: str = Field(..., description="Plain-language explanation.")
    key_takeaways: List[str] = Field(default_factory=list, description="Core insights the viewer must retain.")


class Misconception(BaseModel):
    misconception: str = Field(..., description="Common incorrect assumption.")
    reality: str = Field(..., description="Accurate scientific/technical fact.")
    explanation: str = Field(..., description="Why the misconception arises and how to clear it.")


class SourceReference(BaseModel):
    title: str = Field(..., description="Document or source title.")
    url: str = Field(default="", description="Source URL or reference citation.")
    relevance: str = Field(..., description="How this source supports the explanation.")
    verified: bool = Field(default=False, description="Whether independently verified.")


class UnverifiedFact(BaseModel):
    claim: str = Field(..., description="Fact or assertion that needs scrutiny.")
    reason_for_caution: str = Field(..., description="Why this claim may be imprecise or controversial.")
    verification_suggestion: str = Field(..., description="Suggested verification method or fallback.")


class ResearchArtifact(BaseModel):
    """Complete structured research artifact produced by Researcher agent."""
    topic: str
    target_audience: str
    target_duration_seconds: float = 60.0
    summary: str = Field(..., description="High-level overview of the topic.")
    core_concepts: List[CoreConcept] = Field(..., min_length=1, description="List of fundamental concepts.")
    audience_explanation: AudienceExplanation
    important_terminology: List[TermDefinition] = Field(
        default_factory=list,
        description="Glossary of essential technical terms and their definitions."
    )
    misconceptions: List[Misconception] = Field(default_factory=list)
    examples_and_analogies: List[str] = Field(default_factory=list, description="Concrete analogies for visualization.")
    sources: List[SourceReference] = Field(default_factory=list)
    unverified_facts: List[UnverifiedFact] = Field(default_factory=list)
    narrative_arc: List[str] = Field(default_factory=list, description="Suggested progression of ideas.")

    @field_validator("important_terminology", mode="before")
    @classmethod
    def _coerce_terminology(cls, v: Any) -> Any:
        """Allow legacy dict format to be gracefully coerced into List[TermDefinition]."""
        if isinstance(v, dict):
            return [TermDefinition(term=k, definition=str(val)) for k, val in v.items()]
        return v

    @property
    def terminology_dict(self) -> Dict[str, str]:
        """Provides backward-compatible dictionary access to terms and definitions."""
        return {item.term: item.definition for item in self.important_terminology}
