"""Visual Themes System for AutoStudio Manim Animations."""

from __future__ import annotations

from typing import Dict
from pydantic import BaseModel


class VisualTheme(BaseModel):
    name: str
    background_color: str
    primary_color: str
    secondary_color: str
    accent_color: str
    text_color: str
    math_color: str
    highlight_color: str
    description: str

    def get_manim_setup_code(self) -> str:
        """Returns standard styling boilerplate to inject into the Scene."""
        return f"""
        # --- Theme Styling: {self.name} ---
        self.camera.background_color = "{self.background_color}"
        PRIMARY_COLOR = "{self.primary_color}"
        SECONDARY_COLOR = "{self.secondary_color}"
        ACCENT_COLOR = "{self.accent_color}"
        TEXT_COLOR = "{self.text_color}"
        MATH_COLOR = "{self.math_color}"
        HIGHLIGHT_COLOR = "{self.highlight_color}"
"""


THEMES: Dict[str, VisualTheme] = {
    "Dark Technical": VisualTheme(
        name="Dark Technical",
        background_color="#0f172a",  # Deep slate navy
        primary_color="#38bdf8",     # Cyan
        secondary_color="#818cf8",   # Indigo / violet
        accent_color="#34d399",      # Emerald green
        text_color="#f8fafc",        # Off white
        math_color="#facc15",        # Warm yellow
        highlight_color="#f43f5e",   # Rose / Coral
        description="Clean, modern high-tech developer aesthetic with high contrast glowing accents."
    ),
    "Minimal Scientific": VisualTheme(
        name="Minimal Scientific",
        background_color="#18181b",  # Dark zinc
        primary_color="#60a5fa",     # Blue
        secondary_color="#94a3b8",   # Slate grey
        accent_color="#2dd4bf",      # Teal
        text_color="#ffffff",        # Pure white
        math_color="#fde047",        # Soft gold
        highlight_color="#fb7185",   # Soft crimson
        description="Refined academic and scientific style, reminiscent of 3Blue1Brown."
    ),
    "Mathematical Whiteboard": VisualTheme(
        name="Mathematical Whiteboard",
        background_color="#1e2922",  # Deep chalkboard forest green
        primary_color="#fef08a",     # Chalk yellow
        secondary_color="#bae6fd",   # Chalk blue
        accent_color="#bbf7d0",      # Chalk mint
        text_color="#f0fdf4",        # Soft white chalk
        math_color="#fef08a",        # Bright chalk yellow
        highlight_color="#fca5a5",   # Chalk pink
        description="Classic blackboard / chalkboard lecture aesthetic with pastel chalk colors."
    ),
    "Modern Educational": VisualTheme(
        name="Modern Educational",
        background_color="#0a192f",  # Deep space blue
        primary_color="#ffd166",     # Warm amber
        secondary_color="#06d6a0",   # Vibrant mint
        accent_color="#118ab2",      # Ocean blue
        text_color="#f1faee",        # Crisp off-white
        math_color="#ffd166",        # Gold
        highlight_color="#ef476f",   # Coral punch
        description="Engaging, warm, and inviting for general audience educational explainers."
    ),
    "Cinematic Abstract": VisualTheme(
        name="Cinematic Abstract",
        background_color="#000000",  # Pure AMOLED black
        primary_color="#a855f7",     # Purple glow
        secondary_color="#06b6d4",   # Neon cyan
        accent_color="#ec4899",      # Neon magenta
        text_color="#ffffff",        # White
        math_color="#e0e7ff",        # Electric lavender
        highlight_color="#fbbf24",   # Radiant gold
        description="High-contrast cinematic aesthetic with bold neon color contrasts."
    ),
}


def get_theme(theme_name: str) -> VisualTheme:
    """Retrieve a theme by name, or fallback to Dark Technical."""
    for key, theme in THEMES.items():
        if key.lower() == theme_name.lower():
            return theme
    return THEMES["Dark Technical"]

