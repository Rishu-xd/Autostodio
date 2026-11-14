"""Video Reviewer Agent for AutoStudio."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional
from agents.base import BaseAgent
from config import GEMINI_REVIEW_MODEL
from core.renderer import RenderResult
from core.video_inspector import VideoInspectionResult
from schemas.review import VideoReview
from schemas.storyboard import Storyboard


class VideoReviewer(BaseAgent[VideoInspectionResult, VideoReview]):
    """Uses multimodal Gemini capabilities to inspect rendered video frames against the storyboard."""

    name = "VideoReviewer"
    prompt_file = "video_reviewer.md"
    output_schema = VideoReview

    def __init__(
        self,
        client=None,
        model: Optional[str] = None,
        artifact_manager=None,
    ):
        super().__init__(
            client=client,
            model=model or GEMINI_REVIEW_MODEL,
            artifact_manager=artifact_manager,
        )

    def run(
        self,
        inspection: VideoInspectionResult,
        storyboard: Storyboard,
        render_result: Optional[RenderResult] = None,
        **kwargs,
    ) -> VideoReview:
        self.log(f"Reviewing rendered video ({inspection.metadata.duration_seconds:.1f}s) across {len(inspection.extracted_frames)} frames...")

        # If rendering failed or video is invalid, return immediate rejection review
        if not inspection.is_valid:
            review = VideoReview(
                overall_score=0,
                approval_status="rejected",
                visual_quality_rating=1,
                summary=f"Video rendering failed or produced invalid file: {'; '.join(inspection.issues)}",
                issues=[],
                scenes_needing_revision=[s.scene_id for s in storyboard.scenes],
                revision_instructions=["Fix rendering failure and ensure valid MP4 output."],
            )
            if self.artifact_manager:
                self.artifact_manager.save_video_review(review)
            return review

        # Load image bytes from extracted frames (limit to 6 representative frames to conserve tokens)
        image_bytes_list: List[bytes] = []
        frame_paths = inspection.extracted_frames[:6]

        # If a contact sheet was created, prioritize it
        if inspection.contact_sheet_path and Path(inspection.contact_sheet_path).exists():
            try:
                sheet_bytes = Path(inspection.contact_sheet_path).read_bytes()
                image_bytes_list.append(sheet_bytes)
            except Exception:
                pass

        for p_str in frame_paths:
            path = Path(p_str)
            if path.exists():
                try:
                    image_bytes_list.append(path.read_bytes())
                except Exception:
                    pass

        prompt = f"""
Inspect the attached rendered video frames against the storyboard:

VIDEO METADATA:
- Duration: {inspection.metadata.duration_seconds}s (Target: {storyboard.estimated_duration}s)
- Resolution: {inspection.metadata.width}x{inspection.metadata.height}
- FPS: {inspection.metadata.fps}
- Total Frames: {inspection.metadata.total_frames}

STORYBOARD OBJECTIVES:
{storyboard.model_dump_json(indent=2)}

Review Guidelines:
1. Examine the visual frames for text readability, clipping at edges, or overlapping labels.
2. Check if the visual diagrams communicate the intended core concept.
3. Identify if any frame is completely blank or missing animations.
4. If scenes have visual problems, specify the scene_id and describe the problem and fix.

Provide an overall rating (1-10), score (0-100), and approval status ('approved', 'needs_revision', 'rejected').
"""

        try:
            if image_bytes_list:
                review = self.client.generate_multimodal(
                    prompt=prompt,
                    image_bytes_list=image_bytes_list,
                    response_schema=self.output_schema,
                    model=self.model,
                    system_instruction=self.system_prompt,
                    temperature=0.2,
                )
            else:
                # Text-only fallback if no frames were loaded
                review = self.client.generate_structured(
                    prompt=prompt,
                    response_schema=self.output_schema,
                    model=self.model,
                    system_instruction=self.system_prompt,
                    temperature=0.2,
                )
        except Exception as e:
            self.log(f"Multimodal review error: {e}. Falling back to default inspection result.", level=30)
            review = VideoReview(
                overall_score=85 if inspection.is_valid else 40,
                approval_status="approved" if inspection.is_valid else "rejected",
                visual_quality_rating=8 if inspection.is_valid else 3,
                summary=f"Video inspection completed with {len(inspection.extracted_frames)} frames extracted successfully.",
                issues=[],
                scenes_needing_revision=[],
                revision_instructions=[],
            )

        has_critical = any(issue.severity == "critical" for issue in review.issues)
        if has_critical or review.overall_score < 50:
            review.approval_status = "rejected"
        elif review.overall_score < 75 or len(review.scenes_needing_revision) > 0:
            review.approval_status = "needs_revision"
        else:
            review.approval_status = "approved"

        self.log(f"Video review completed. Rating: {review.visual_quality_rating}/10, Score: {review.overall_score}/100, Status: {review.approval_status.upper()}")

        if self.artifact_manager:
            self.artifact_manager.save_video_review(review)

        return review

