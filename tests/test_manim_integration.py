"""Integration test for local Manim rendering and video inspection."""

import shutil
from pathlib import Path
import pytest

from core.execution_sandbox import ExecutionSandbox
from core.renderer import ManimRenderer
from core.video_inspector import VideoInspector


def test_manim_render_and_inspection(tmp_path):
    renderer = ManimRenderer(sandbox=ExecutionSandbox())
    inspector = VideoInspector()

    script_path = tmp_path / "test_scene.py"
    output_dir = tmp_path / "output"
    logs_dir = tmp_path / "logs"
    frames_dir = tmp_path / "frames"

    # Minimal 1-second Manim scene
    script_content = """
from manim import *

class QuickTestScene(Scene):
    def construct(self):
        self.camera.background_color = "#0f172a"
        title = Text("AutoStudio Test", font_size=36, color=BLUE)
        self.play(FadeIn(title), run_time=0.5)
        self.wait(0.5)
        self.play(FadeOut(title), run_time=0.5)
"""
    script_path.write_text(script_content, encoding="utf-8")

    # Render at low quality (-ql)
    res = renderer.render(
        script_path=script_path,
        output_dir=output_dir,
        logs_dir=logs_dir,
        quality="low",
        timeout_seconds=60,
        output_filename="test_output.mp4",
    )

    assert res.success is True, f"Rendering failed: {res.error_message}"
    assert res.video_path is not None
    assert Path(res.video_path).exists()
    assert Path(res.video_path).stat().st_size > 0

    # Inspect the rendered video
    inspection = inspector.inspect_video(
        video_path=Path(res.video_path),
        frames_dir=frames_dir,
        max_frames=3,
        expected_duration=1.5,
    )

    assert inspection.is_valid is True
    assert inspection.metadata.duration_seconds > 0
    assert inspection.metadata.width == 854
    assert inspection.metadata.height == 480
    assert len(inspection.extracted_frames) > 0

