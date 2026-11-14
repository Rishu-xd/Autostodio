"""Base Agent Abstraction for AutoStudio."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Generic, Optional, Type, TypeVar
from pydantic import BaseModel

from config import DEFAULT_GEMINI_MODEL, PROMPTS_DIR
from core.artifact_manager import ArtifactManager
from core.gemini_client import GeminiClient, get_gemini_client

logger = logging.getLogger("autostudio.agent")

InputT = TypeVar("InputT")
OutputT = TypeVar("OutputT", bound=BaseModel)


class BaseAgent(Generic[InputT, OutputT]):
    """Abstract foundation for all AutoStudio specialized agents."""

    name: str = "BaseAgent"
    prompt_file: str = ""
    output_schema: Type[OutputT]

    def __init__(
        self,
        client: Optional[GeminiClient] = None,
        model: Optional[str] = None,
        artifact_manager: Optional[ArtifactManager] = None,
    ):
        self.client = client or get_gemini_client()
        self.model = model or DEFAULT_GEMINI_MODEL
        self.artifact_manager = artifact_manager
        self.system_prompt = self._load_system_prompt()

    def _load_system_prompt(self) -> str:
        """Load markdown system instructions from prompts directory."""
        if not self.prompt_file:
            return ""
        path = PROMPTS_DIR / self.prompt_file
        if path.exists():
            return path.read_text(encoding="utf-8").strip()
        logger.warning(f"System prompt file not found at {path}")
        return ""

    def log(self, message: str, level: int = logging.INFO):
        """Format and emit agent execution log."""
        logger.log(level, f"[{self.name}] {message}")

    def run(self, input_data: InputT, **kwargs) -> OutputT:
        """Execute agent workflow on input data and return validated output schema."""
        raise NotImplementedError("Subclasses must implement run()")

