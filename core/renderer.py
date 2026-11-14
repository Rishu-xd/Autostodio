"""Local Renderer for AutoStudio using Manim Community Edition.

Handles:
- AST syntax & Scene class validation
- Sandboxed subprocess execution
- Configurable render qualities (-ql, -qm, -qh)
- Stdout / Stderr capture to project logs
- Output verification (non-empty MP4)
- Automated copy to final project output
"""

from __future__ import annotations

import ast
import os
import shutil
import sys
import time
from pathlib import Path
from typing import List, Optional, Tuple
from pydantic import BaseModel

from config import RENDER_TIMEOUT_SECONDS
from core.execution_sandbox import ExecutionSandbox


class RenderResult(BaseModel):
    success: bool
    video_path: Optional[str] = None
    log_path: Optional[str] = None
    duration_seconds: float = 0.0
    exit_code: int = 0
    error_message: Optional[str] = None


class ManimRenderer:
    """Orchestrates local rendering of Manim scripts."""

    def __init__(self, sandbox: Optional[ExecutionSandbox] = None):
        self.sandbox = sandbox or ExecutionSandbox()

    def find_scene_class_name(self, code_str: str) -> Optional[str]:
        """Inspect code AST to find the first class that subclasses Scene."""
        try:
            tree = ast.parse(code_str)
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    for base in node.bases:
                        if isinstance(base, ast.Name) and "Scene" in base.id:
                            return node.name
                        elif isinstance(base, ast.Attribute) and "Scene" in base.attr:
                            return node.name
        except Exception:
            pass
        return None

    def validate_code(self, code_str: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """Validate syntax, sandbox safety, and presence of a Scene class.
        Returns: (is_valid, scene_class_name, error_message)
        """
        # 1. Syntax check
        try:
            ast.parse(code_str)
        except SyntaxError as e:
            return False, None, f"Python SyntaxError at line {e.lineno}: {e.msg}"

        # 2. Safety check
        safe, violations = self.sandbox.inspect_code(code_str)
        if not safe:
            return False, None, f"Sandbox safety violation: {'; '.join(violations)}"

        # 3. Find scene class
        scene_name = self.find_scene_class_name(code_str)
        if not scene_name:
            return False, None, "No Manim Scene subclass found (e.g. class MainScene(Scene):)."

        return True, scene_name, None

    def render(
        self,
        script_path: Path,
        output_dir: Path,
        logs_dir: Path,
        quality: str = "low",  # "low", "medium", "high"
        timeout_seconds: int = RENDER_TIMEOUT_SECONDS,
        output_filename: str = "final.mp4",
    ) -> RenderResult:
        """Render the script to video locally."""
        start_time = time.time()
        script_path = Path(script_path).resolve()
        output_dir = Path(output_dir).resolve()
        logs_dir = Path(logs_dir).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        logs_dir.mkdir(parents=True, exist_ok=True)

        log_file = logs_dir / f"render_{int(start_time)}.log"

        if not script_path.exists():
            return RenderResult(
                success=False,
                error_message=f"Script not found: {script_path}",
                log_path=str(log_file),
            )

        # Read script and validate
        code_str = script_path.read_text(encoding="utf-8")
        is_valid, scene_name, error_msg = self.validate_code(code_str)
        if not is_valid or not scene_name:
            return RenderResult(
                success=False,
                error_message=error_msg or "Validation failed.",
                log_path=str(log_file),
            )

        # Map quality to Manim flags
        quality_map = {
            "low": "-ql",     # 480p 15fps
            "medium": "-qm",  # 720p 30fps
            "high": "-qh",    # 1080p 60fps
        }
        q_flag = quality_map.get(quality.lower(), "-ql")

        media_dir = output_dir / "manim_media"
        media_dir.mkdir(parents=True, exist_ok=True)

        target_output_path = output_dir / output_filename

        # Build rendering command
        # python -m manim render <file> <scene> <quality> --media_dir <media_dir> -o <target_name>
        cmd = [
            sys.executable,
            "-m",
            "manim",
            "render",
            str(script_path),
            scene_name,
            q_flag,
            "--media_dir",
            str(media_dir),
            "-o",
            output_filename,
            "--disable_caching",
        ]

        exit_code, stdout, stderr = self.sandbox.run_process(
            command=cmd,
            working_dir=script_path.parent,
            timeout_seconds=timeout_seconds,
            log_file=log_file,
        )

        render_duration = round(time.time() - start_time, 2)

        # Look for the generated output video
        # Manim places videos in: <media_dir>/videos/<script_stem>/<resolution>/<output_filename>
        found_video: Optional[Path] = None

        # Check direct target if manim wrote directly
        if target_output_path.exists() and target_output_path.stat().st_size > 0:
            found_video = target_output_path
        else:
            # Search media_dir for any mp4 generated
            mp4_candidates = list(media_dir.glob(f"**/{output_filename}"))
            if not mp4_candidates:
                mp4_candidates = list(media_dir.glob("**/*.mp4"))

            if mp4_candidates:
                # Sort by last modified
                mp4_candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
                candidate = mp4_candidates[0]
                if candidate.stat().st_size > 0:
                    shutil.copy2(candidate, target_output_path)
                    found_video = target_output_path

        if exit_code != 0 or not found_video:
            error_details = (stderr or stdout)[-1000:] if (stderr or stdout) else "Unknown rendering error"
            return RenderResult(
                success=False,
                log_path=str(log_file),
                duration_seconds=render_duration,
                exit_code=exit_code,
                error_message=f"Rendering failed (code {exit_code}): {error_details.strip()}",
            )

        return RenderResult(
            success=True,
            video_path=str(found_video),
            log_path=str(log_file),
            duration_seconds=render_duration,
            exit_code=0,
        )

