"""Centralized Gemini Client for AutoStudio.

Manages connection to the Google Gen AI API using the official google-genai SDK.
Handles structured outputs, multimodal requests, retries, backoff, schema compatibility,
and token usage tracking.
"""

from __future__ import annotations

import json
import logging
import random
import re
import time
from typing import Any, List, Optional, Tuple, Type, TypeVar
from pydantic import BaseModel, ValidationError

from google import genai
from google.genai import types
from google.genai.errors import APIError

from config import (
    GEMINI_API_KEY,
    DEFAULT_GEMINI_MODEL,
    API_TIMEOUT_SECONDS,
    MAX_RETRIES,
    PRICE_PER_1M_INPUT_TOKENS,
    PRICE_PER_1M_OUTPUT_TOKENS,
    validate_api_key,
)
from schemas.project import TokenUsage

logger = logging.getLogger("autostudio.gemini")

T = TypeVar("T", bound=BaseModel)


class GeminiClientError(Exception):
    """Raised when an unrecoverable Gemini API error occurs."""
    pass


class GeminiSchemaError(GeminiClientError):
    """Raised when a schema contains constructs unsupported by the Gemini Developer API."""
    pass


def inspect_schema_for_unsupported_constructs(schema_data: Any, path: str = "") -> List[str]:
    """Recursively checks a JSON Schema dict for features unsupported by Gemini Developer API."""
    issues = []
    if isinstance(schema_data, dict):
        if "additionalProperties" in schema_data:
            issues.append(f"{path or 'root'}: 'additionalProperties' is not supported in Gemini Developer API mode.")
        if "additional_properties" in schema_data:
            issues.append(f"{path or 'root'}: 'additional_properties' is not supported in Gemini Developer API mode.")
        if "exclusiveMinimum" in schema_data and isinstance(schema_data["exclusiveMinimum"], (int, float)):
            issues.append(f"{path or 'root'}: 'exclusiveMinimum' (numeric) is not supported; use 'minimum' or ge=... instead.")
        if "exclusiveMaximum" in schema_data and isinstance(schema_data["exclusiveMaximum"], (int, float)):
            issues.append(f"{path or 'root'}: 'exclusiveMaximum' (numeric) is not supported; use 'maximum' or le=... instead.")

        for key, value in schema_data.items():
            sub_path = f"{path}.{key}" if path else key
            issues.extend(inspect_schema_for_unsupported_constructs(value, sub_path))
    elif isinstance(schema_data, list):
        for idx, item in enumerate(schema_data):
            issues.extend(inspect_schema_for_unsupported_constructs(item, f"{path}[{idx}]"))
    return issues


def validate_pydantic_schema_compatibility(model_cls: Type[BaseModel]) -> Tuple[bool, List[str]]:
    """Validate that a Pydantic model produces an OpenAPI schema 100% compatible with Gemini Developer API."""
    try:
        raw_schema = model_cls.model_json_schema()
        issues = inspect_schema_for_unsupported_constructs(raw_schema)
        return len(issues) == 0, issues
    except Exception as e:
        return False, [f"Failed to generate JSON schema: {e}"]


class GeminiClient:
    """Centralized client wrapping Google Gen AI operations."""

    def __init__(self, api_key: Optional[str] = None, default_model: Optional[str] = None):
        self.api_key = api_key if api_key is not None else GEMINI_API_KEY
        self.default_model = default_model or DEFAULT_GEMINI_MODEL
        self._client: Optional[genai.Client] = None
        self.token_usage = TokenUsage()

        if validate_api_key(self.api_key):
            try:
                self._client = genai.Client(api_key=self.api_key)
            except Exception as e:
                logger.warning(f"Failed to initialize GenAI client: {e}")
                self._client = None

    @property
    def is_configured(self) -> bool:
        """Returns True if the client is configured with a valid API key."""
        return self._client is not None and validate_api_key(self.api_key)

    def _ensure_client(self):
        """Raise a user-friendly error if the API key is not configured."""
        if not self.is_configured:
            raise GeminiClientError(
                "Gemini API key is not configured or is invalid. "
                "Please set GEMINI_API_KEY in your .env file or environment."
            )

    def _clean_json_text(self, text: str) -> str:
        """Strip markdown code fence wrappers from raw LLM responses if present."""
        text = text.strip()
        # Remove ```json ... ``` wrapper
        match = re.search(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return text

    def _prepare_response_schema(self, schema_cls: Type[T]) -> Any:
        """Validate schema compatibility before passing to google-genai."""
        if isinstance(schema_cls, type) and issubclass(schema_cls, BaseModel):
            is_valid, issues = validate_pydantic_schema_compatibility(schema_cls)
            if not is_valid:
                err_msg = (
                    f"Schema '{schema_cls.__name__}' is incompatible with Gemini Developer API: "
                    f"{'; '.join(issues)}. Unrestricted dictionaries and additionalProperties are only supported "
                    "in Gemini Enterprise Agent Platform mode. Use explicit Pydantic models."
                )
                logger.error(err_msg)
                raise GeminiSchemaError(err_msg)
        return schema_cls

    def _record_usage(self, response: Any):
        """Update cumulative token usage and cost."""
        try:
            if hasattr(response, "usage_metadata") and response.usage_metadata:
                in_tokens = getattr(response.usage_metadata, "prompt_token_count", 0) or 0
                out_tokens = getattr(response.usage_metadata, "candidates_token_count", 0) or 0
                self.token_usage.add(
                    in_tokens,
                    out_tokens,
                    cost_per_1m_in=PRICE_PER_1M_INPUT_TOKENS,
                    cost_per_1m_out=PRICE_PER_1M_OUTPUT_TOKENS,
                )
        except Exception as e:
            logger.debug(f"Could not record token usage: {e}")

    def generate_structured(
        self,
        prompt: str,
        response_schema: Type[T],
        model: Optional[str] = None,
        system_instruction: Optional[str] = None,
        temperature: float = 0.2,
        max_retries: int = MAX_RETRIES,
    ) -> T:
        """Generate structured data validated against a Pydantic schema."""
        self._ensure_client()
        target_model = model or self.default_model

        # Pre-flight schema validation against Gemini Developer API restrictions
        prepared_schema = self._prepare_response_schema(response_schema)

        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=prepared_schema,
            temperature=temperature,
            system_instruction=system_instruction,
        )

        last_error = None
        for attempt in range(1, max_retries + 1):
            try:
                response = self._client.models.generate_content(
                    model=target_model,
                    contents=prompt,
                    config=config,
                )
                self._record_usage(response)

                raw_text = response.text or ""
                cleaned_text = self._clean_json_text(raw_text)
                return response_schema.model_validate_json(cleaned_text)

            except ValidationError as e:
                last_error = e
                logger.warning(f"Pydantic validation error on LLM response (attempt {attempt}/{max_retries}): {e}")
                if attempt < max_retries:
                    time.sleep(1.0)
                else:
                    raise GeminiClientError(f"Failed to validate model response into {response_schema.__name__}: {e}") from e

            except APIError as e:
                last_error = e
                if e.code in (429, 500, 503, 504) and attempt < max_retries:
                    wait_time = (2 ** attempt) + random.uniform(0.5, 1.5)
                    logger.warning(
                        f"Transient Gemini API error (status {e.code}). Retrying in {wait_time:.1f}s (attempt {attempt}/{max_retries})..."
                    )
                    time.sleep(wait_time)
                else:
                    raise GeminiClientError(f"Gemini API Error [{e.code}]: {e.message}") from e

            except GeminiSchemaError:
                raise

            except Exception as e:
                last_error = e
                if attempt < max_retries:
                    wait_time = (1.5 ** attempt) + random.uniform(0.2, 0.8)
                    logger.warning(f"Error during generation: {e}. Retrying in {wait_time:.1f}s...")
                    time.sleep(wait_time)
                else:
                    raise GeminiClientError(f"Failed to generate structured response: {e}") from e

        raise GeminiClientError(f"Exceeded max retries ({max_retries}). Last error: {last_error}")

    def generate_text(
        self,
        prompt: str,
        model: Optional[str] = None,
        system_instruction: Optional[str] = None,
        temperature: float = 0.3,
        max_retries: int = MAX_RETRIES,
    ) -> str:
        """Generate unstructured text from Gemini."""
        self._ensure_client()
        target_model = model or self.default_model

        config = types.GenerateContentConfig(
            temperature=temperature,
            system_instruction=system_instruction,
        )

        last_error = None
        for attempt in range(1, max_retries + 1):
            try:
                response = self._client.models.generate_content(
                    model=target_model,
                    contents=prompt,
                    config=config,
                )
                self._record_usage(response)
                return (response.text or "").strip()

            except Exception as e:
                last_error = e
                if attempt < max_retries:
                    wait_time = (2 ** attempt) + random.uniform(0.2, 0.8)
                    time.sleep(wait_time)
                else:
                    raise GeminiClientError(f"Failed to generate text: {e}") from e

        raise GeminiClientError(f"Exceeded max retries. Last error: {last_error}")

    def generate_multimodal(
        self,
        prompt: str,
        image_bytes_list: List[bytes],
        mime_types: Optional[List[str]] = None,
        response_schema: Optional[Type[T]] = None,
        model: Optional[str] = None,
        system_instruction: Optional[str] = None,
        temperature: float = 0.2,
        max_retries: int = MAX_RETRIES,
    ) -> Any:
        """Generate response with image frames for video review."""
        self._ensure_client()
        target_model = model or self.default_model

        contents: List[Any] = [prompt]
        if mime_types is None:
            mime_types = ["image/png"] * len(image_bytes_list)

        for img_bytes, mime in zip(image_bytes_list, mime_types):
            part = types.Part.from_bytes(data=img_bytes, mime_type=mime)
            contents.append(part)

        config_kwargs: dict[str, Any] = {
            "temperature": temperature,
            "system_instruction": system_instruction,
        }
        if response_schema is not None:
            prepared_schema = self._prepare_response_schema(response_schema)
            config_kwargs["response_mime_type"] = "application/json"
            config_kwargs["response_schema"] = prepared_schema

        config = types.GenerateContentConfig(**config_kwargs)

        last_error = None
        for attempt in range(1, max_retries + 1):
            try:
                response = self._client.models.generate_content(
                    model=target_model,
                    contents=contents,
                    config=config,
                )
                self._record_usage(response)

                raw_text = response.text or ""
                if response_schema is not None:
                    cleaned_text = self._clean_json_text(raw_text)
                    return response_schema.model_validate_json(cleaned_text)
                return raw_text.strip()

            except Exception as e:
                last_error = e
                if attempt < max_retries:
                    wait_time = (2 ** attempt) + random.uniform(0.5, 1.0)
                    time.sleep(wait_time)
                else:
                    raise GeminiClientError(f"Failed multimodal generation: {e}") from e

        raise GeminiClientError(f"Exceeded max retries. Last error: {last_error}")


# Global default client instance
_default_gemini_client: Optional[GeminiClient] = None


def get_gemini_client() -> GeminiClient:
    """Returns the shared GeminiClient instance."""
    global _default_gemini_client
    if _default_gemini_client is None:
        _default_gemini_client = GeminiClient()
    return _default_gemini_client
