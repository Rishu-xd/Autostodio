"""Helpers for Pydantic JSON Schemas sent to the Gemini Developer API."""

from typing import Any


def nonnegative_wire_schema(schema: dict[str, Any]) -> None:
    """Express a strict positive bound using the Developer API's supported schema subset."""
    schema.pop("exclusiveMinimum", None)
    schema["minimum"] = 0
