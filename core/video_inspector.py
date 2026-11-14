"""Video Inspector Module for AutoStudio.

Extracts representative frames, compiles contact sheets, validates duration and resolution,
and prepares visual assets for multimodal Gemini video review.
"""

from __future__ import annotations

import json
import logging
import math
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel
from PIL import Image

logger = logging.getLogger("autostudio.inspector")


class VideoMetadata(BaseModel):
    duration_seconds: float
    width: int
    height: int
    fps: float
    total_frames: int
    file_size_bytes: int
    codec: str = "h264"


class VideoInspectionResult(BaseModel):
    video_path: str
    metadata: VideoMetadata
    extracted_frames: List[str]  # Absolute file paths to PNGs
    contact_sheet_path: Optional[str] = None
    is_valid: bool = True
    issues: List[str] = []


class VideoInspector:
    """Inspects rendered MP4 videos, extracts frames, and builds contact sheets."""

    def __init__(self, output_dir: Optional[Path] = None):
        self.output_dir = output_dir

    def inspect_video(
        self,
        video_path: Path,
        frames_dir: Path,
        max_frames: int = 8,
        expected_duration: Optional[float] = None,
    ) -> VideoInspectionResult:
        """Inspect video file, probe metadata, and extract representative frames."""
        video_path = Path(video_path)
        frames_dir = Path(frames_dir)
        frames_dir.mkdir(parents=True, exist_ok=True)

        issues: List[str] = []

        if not video_path.exists():
            return VideoInspectionResult(
                video_path=str(video_path),
                metadata=VideoMetadata(duration_seconds=0, width=0, height=0, fps=0, total_frames=0, file_size_bytes=0),
                extracted_frames=[],
                is_valid=False,
                issues=["Video file does not exist."],
            )

        file_size = video_path.stat().st_size
        if file_size == 0:
            return VideoInspectionResult(
                video_path=str(video_path),
                metadata=VideoMetadata(duration_seconds=0, width=0, height=0, fps=0, total_frames=0, file_size_bytes=0),
                extracted_frames=[],
                is_valid=False,
                issues=["Video file is 0 bytes (empty render)."],
            )

        metadata = self._probe_video(video_path)

        if metadata.duration_seconds < 1.0:
            issues.append(f"Video duration is unusually short ({metadata.duration_seconds:.1f}s).")

        if expected_duration and abs(metadata.duration_seconds - expected_duration) > max(10.0, expected_duration * 0.4):
            issues.append(
                f"Video duration ({metadata.duration_seconds:.1f}s) differs significantly from target ({expected_duration:.1f}s)."
            )

        # Extract frames
        frame_paths = self._extract_frames(video_path, frames_dir, metadata, max_frames=max_frames)
        if not frame_paths:
            issues.append("Failed to extract any visual frames from video.")

        # Create contact sheet
        contact_sheet_path = None
        if frame_paths:
            contact_sheet_path = self._build_contact_sheet(frame_paths, frames_dir / "contact_sheet.png")

        is_valid = len(issues) == 0

        return VideoInspectionResult(
            video_path=str(video_path),
            metadata=metadata,
            extracted_frames=[str(p) for p in frame_paths],
            contact_sheet_path=str(contact_sheet_path) if contact_sheet_path else None,
            is_valid=is_valid,
            issues=issues,
        )

    def _probe_video(self, video_path: Path) -> VideoMetadata:
        """Probe video with ffprobe or OpenCV fallback."""
        file_size = video_path.stat().st_size

        # Try ffprobe first
        try:
            cmd = [
                "ffprobe",
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                "-show_streams",
                str(video_path),
            ]
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10)
            if result.returncode == 0:
                data = json.loads(result.stdout)
                duration = float(data.get("format", {}).get("duration", 0.0))
                video_stream = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), {})
                width = int(video_stream.get("width", 0))
                height = int(video_stream.get("height", 0))
                codec = video_stream.get("codec_name", "h264")

                fps_str = video_stream.get("r_frame_rate", "30/1")
                if "/" in fps_str:
                    num, den = fps_str.split("/")
                    fps = float(num) / float(den) if float(den) > 0 else 30.0
                else:
                    fps = float(fps_str)

                total_frames = int(video_stream.get("nb_frames", int(duration * fps)))

                return VideoMetadata(
                    duration_seconds=round(duration, 2),
                    width=width,
                    height=height,
                    fps=round(fps, 2),
                    total_frames=total_frames,
                    file_size_bytes=file_size,
                    codec=codec,
                )
        except Exception as e:
            logger.debug(f"ffprobe failed or unavailable: {e}. Trying cv2 fallback.")

        # OpenCV Fallback
        try:
            import cv2
            cap = cv2.VideoCapture(str(video_path))
            if cap.isOpened():
                fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
                total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
                width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 854)
                height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 480)
                duration = total_frames / fps if fps > 0 else 0.0
                cap.release()
                return VideoMetadata(
                    duration_seconds=round(duration, 2),
                    width=width,
                    height=height,
                    fps=round(fps, 2),
                    total_frames=total_frames,
                    file_size_bytes=file_size,
                    codec="h264",
                )
        except Exception as e:
            logger.warning(f"cv2 fallback failed: {e}")

        # Minimal default fallback
        return VideoMetadata(
            duration_seconds=10.0,
            width=854,
            height=480,
            fps=30.0,
            total_frames=300,
            file_size_bytes=file_size,
            codec="h264",
        )

    def _extract_frames(
        self,
        video_path: Path,
        frames_dir: Path,
        metadata: VideoMetadata,
        max_frames: int = 8,
    ) -> List[Path]:
        """Extract evenly distributed frames across the video duration."""
        extracted: List[Path] = []
        if metadata.duration_seconds <= 0 or metadata.total_frames <= 0:
            return extracted

        # Use OpenCV for fast precise frame extraction
        try:
            import cv2
            cap = cv2.VideoCapture(str(video_path))
            if not cap.isOpened():
                return extracted

            total_frames = max(1, metadata.total_frames)
            # Pick evenly spaced frame indices (avoiding frame 0 which is often black fade-in)
            step = max(1, total_frames // (max_frames + 1))
            frame_indices = [min(total_frames - 1, step * (i + 1)) for i in range(max_frames)]

            for idx, frame_idx in enumerate(frame_indices):
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
                ret, frame = cap.read()
                if ret and frame is not None:
                    out_name = f"frame_{idx:02d}_t{int(frame_idx / metadata.fps)}s.png"
                    out_path = frames_dir / out_name
                    cv2.imwrite(str(out_path), frame)
                    extracted.append(out_path)

            cap.release()
            if extracted:
                return extracted

        except Exception as e:
            logger.debug(f"OpenCV frame extraction failed: {e}. Trying ffmpeg...")

        # FFmpeg frame extraction fallback
        try:
            # Extract 1 frame per N seconds
            interval = max(1.0, metadata.duration_seconds / max_frames)
            pattern = str(frames_dir / "frame_%03d.png")
            cmd = [
                "ffmpeg",
                "-y",
                "-i", str(video_path),
                "-vf", f"fps=1/{interval}",
                "-vframes", str(max_frames),
                pattern,
            ]
            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
            extracted = sorted(list(frames_dir.glob("frame_*.png")))
        except Exception as e:
            logger.error(f"FFmpeg frame extraction failed: {e}")

        return extracted

    def _build_contact_sheet(self, frame_paths: List[Path], output_path: Path) -> Optional[Path]:
        """Combine extracted frames into a neat grid image for review."""
        if not frame_paths:
            return None

        try:
            images = [Image.open(p) for p in frame_paths]
            count = len(images)
            cols = min(4, count)
            rows = math.ceil(count / cols)

            # Thumbnail dimensions
            thumb_w = 320
            thumb_h = int(images[0].height * (thumb_w / images[0].width))

            sheet_w = cols * thumb_w
            sheet_h = rows * thumb_h

            sheet = Image.new("RGB", (sheet_w, sheet_h), color=(20, 24, 33))

            for idx, img in enumerate(images):
                r = idx // cols
                c = idx % cols
                resized = img.resize((thumb_w, thumb_h), Image.Resampling.LANCZOS)
                sheet.paste(resized, (c * thumb_w, r * thumb_h))

            sheet.save(output_path, "PNG")
            return output_path
        except Exception as e:
            logger.warning(f"Failed to create contact sheet: {e}")
            return None

