"""AutoStudio Configuration Module.

Centralizes all environment variables, paths, and default settings.
"""

from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file from project root if present
load_dotenv()

# Base directories
BASE_DIR = Path(__file__).resolve().parent
STORAGE_DIR = Path(os.getenv("AUTOSTUDIO_STORAGE_DIR", BASE_DIR / "storage" / "projects"))
DB_PATH = Path(os.getenv("AUTOSTUDIO_DB_PATH", BASE_DIR / "storage" / "autostudio.db"))
PROMPTS_DIR = BASE_DIR / "prompts"

# Ensure storage base directory exists
STORAGE_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

# Gemini API Configuration
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
DEFAULT_GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
GEMINI_MODEL = DEFAULT_GEMINI_MODEL
GEMINI_RESEARCH_MODEL = os.getenv("GEMINI_RESEARCH_MODEL", DEFAULT_GEMINI_MODEL)
GEMINI_CODE_MODEL = os.getenv("GEMINI_CODE_MODEL", DEFAULT_GEMINI_MODEL)
GEMINI_REVIEW_MODEL = os.getenv("GEMINI_REVIEW_MODEL", DEFAULT_GEMINI_MODEL)

# Execution and Retry Settings
MAX_REVISION_COUNT = int(os.getenv("MAX_REVISION_COUNT", "3"))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
RENDER_TIMEOUT_SECONDS = int(os.getenv("RENDER_TIMEOUT_SECONDS", "300"))
API_TIMEOUT_SECONDS = float(os.getenv("API_TIMEOUT_SECONDS", "60.0"))

# Manim Rendering Defaults
DEFAULT_VIDEO_QUALITY = os.getenv("DEFAULT_VIDEO_QUALITY", "low")  # "low", "medium", "high"
DEFAULT_FRAME_RATE = int(os.getenv("DEFAULT_FRAME_RATE", "30"))
DEFAULT_RESOLUTION = os.getenv("DEFAULT_RESOLUTION", "854x480")  # 854x480 for low, 1280x720 for med, 1920x1080 for high

# Sandbox security
SANDBOX_RESTRICTED_MODE = os.getenv("SANDBOX_RESTRICTED_MODE", "true").lower() in ("true", "1", "yes")

# Token pricing estimates (per million tokens in USD)
PRICE_PER_1M_INPUT_TOKENS = float(os.getenv("PRICE_PER_1M_INPUT_TOKENS", "0.10"))
PRICE_PER_1M_OUTPUT_TOKENS = float(os.getenv("PRICE_PER_1M_OUTPUT_TOKENS", "0.40"))


def validate_api_key(api_key: str | None = None) -> bool:
    """Check if a Gemini API key is configured and non-empty."""
    key = api_key if api_key is not None else GEMINI_API_KEY
    return bool(key and key.strip() and key != "your_key_here")
