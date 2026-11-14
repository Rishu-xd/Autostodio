"""Central Pipeline Orchestrator for AutoStudio.

Coordinates the multi-agent AI video production workflow from user prompt
to final rendered MP4, managing state persistence, resume capability,
critic revision loops, rendering, and quality inspections.
"""

from __future__ import annotations

import logging
import time
import uuid
from pathlib import Path
from typing import Callable, Optional

from agents.code_critic import CodeCritic
from agents.code_generator import CodeGenerator
from agents.research_critic import ResearchCritic
from agents.researcher import Researcher
from agents.storyboard_critic import StoryboardCritic
from agents.storyboard_planner import StoryboardPlanner
from agents.video_reviewer import VideoReviewer
from config import (
    DEFAULT_GEMINI_MODEL,
    MAX_REVISION_COUNT,
    STORAGE_DIR,
)
from core.artifact_manager import ArtifactManager
from core.execution_sandbox import ExecutionSandbox
from core.gemini_client import GeminiClient, get_gemini_client
from core.renderer import ManimRenderer, RenderResult
from core.retry_manager import RetryManager, RevisionLimitExceeded
from core.state_manager import StateManager
from core.video_inspector import VideoInspectionResult, VideoInspector
from schemas.generation import GeneratedCodeArtifact
from schemas.project import (
    ProjectConfig,
    ProjectMetadata,
    ProjectStatus,
    TokenUsage,
)
from schemas.research import ResearchArtifact
from schemas.review import (
    CodeReview,
    ResearchReview,
    StoryboardReview,
    VideoReview,
)
from schemas.storyboard import Storyboard

logger = logging.getLogger("autostudio.orchestrator")


class OrchestratorError(Exception):
    """Raised when an unrecoverable pipeline failure occurs."""
    pass


class Orchestrator:
    """Coordinates the entire AutoStudio production pipeline."""

    def __init__(
        self,
        gemini_client: Optional[GeminiClient] = None,
        state_manager: Optional[StateManager] = None,
        renderer: Optional[ManimRenderer] = None,
        video_inspector: Optional[VideoInspector] = None,
    ):
        self.gemini_client = gemini_client or get_gemini_client()
        self.state_manager = state_manager or StateManager()
        self.renderer = renderer or ManimRenderer(sandbox=ExecutionSandbox())
        self.video_inspector = video_inspector or VideoInspector()

    def create_project(
        self,
        topic: str,
        config: Optional[ProjectConfig] = None,
        project_id: Optional[str] = None,
    ) -> ProjectMetadata:
        """Create a new project record and initialize its artifact structure."""
        pid = project_id or f"proj_{uuid.uuid4().hex[:8]}"
        project_config = config or ProjectConfig(topic=topic)
        project_config.topic = topic

        # Initialize artifact directory
        artifacts = ArtifactManager(pid)

        # Create record in database
        metadata = self.state_manager.create_project(
            project_id=pid,
            config=project_config,
            title=project_config.video_title or topic[:40],
        )

        artifacts.save_metadata(metadata)
        logger.info(f"Initialized new project '{pid}' for topic: '{topic}'")
        return metadata

    def run_pipeline(
        self,
        project_id: str,
        progress_callback: Optional[Callable[[str, str], None]] = None,
    ) -> ProjectMetadata:
        """Execute the complete end-to-end video production pipeline with resume capability."""
        metadata = self.state_manager.get_project(project_id)
        if not metadata:
            raise OrchestratorError(f"Project '{project_id}' not found.")

        artifacts = ArtifactManager(project_id)
        retry_mgr = RetryManager(max_revisions=metadata.config.max_revision_count)
        retry_mgr.load_counts(metadata.revision_counts)

        # Helper to report progress
        def notify(stage: str, msg: str):
            logger.info(f"[{project_id}] [{stage}] {msg}")
            if progress_callback:
                progress_callback(stage, msg)

        # Instantiate agents for this project
        researcher = Researcher(client=self.gemini_client, artifact_manager=artifacts)
        research_critic = ResearchCritic(client=self.gemini_client, artifact_manager=artifacts)
        planner = StoryboardPlanner(client=self.gemini_client, artifact_manager=artifacts)
        storyboard_critic = StoryboardCritic(client=self.gemini_client, artifact_manager=artifacts)
        code_gen = CodeGenerator(client=self.gemini_client, artifact_manager=artifacts)
        code_critic = CodeCritic(client=self.gemini_client, artifact_manager=artifacts)
        video_rev = VideoReviewer(client=self.gemini_client, artifact_manager=artifacts)

        try:
            # ---------------------------------------------------------
            # STAGE 1: RESEARCH & RESEARCH REVIEW
            # ---------------------------------------------------------
            research = artifacts.load_research()
            research_review = artifacts.load_research_review()

            if not research or not research_review or research_review.approval_status != "approved":
                self._update_stage(project_id, ProjectStatus.RESEARCHING, "RESEARCH")
                notify("RESEARCH", "Conducting topic research...")
                rec_id = self.state_manager.record_stage_start(project_id, "RESEARCH")
                t0 = time.time()

                revision_feedback: Optional[ResearchReview] = research_review

                while True:
                    research = researcher.run(metadata.config, revision_feedback=revision_feedback)
                    self._update_stage(project_id, ProjectStatus.RESEARCH_REVIEW, "RESEARCH_REVIEW")
                    notify("RESEARCH_REVIEW", "Reviewing research accuracy and pedagogical structure...")

                    research_review = research_critic.run(research)
                    if research_review.approval_status == "approved":
                        notify("RESEARCH_REVIEW", f"Research approved (Score: {research_review.overall_score}/100).")
                        break

                    # Check revision allowance
                    if not retry_mgr.can_revise("RESEARCH"):
                        notify("RESEARCH_REVIEW", "Max research revisions reached. Proceeding with best version.")
                        break

                    retry_mgr.record_revision("RESEARCH")
                    notify("RESEARCH", f"Revising research based on critic feedback (Attempt {retry_mgr.get_revision_count('RESEARCH')})...")
                    revision_feedback = research_review

                self.state_manager.record_stage_end(rec_id, "COMPLETED", duration_seconds=time.time() - t0)
            else:
                notify("RESEARCH", "Found previously approved research. Resuming from storyboard...")

            # ---------------------------------------------------------
            # STAGE 2: STORYBOARD PLANNING & REVIEW
            # ---------------------------------------------------------
            storyboard = artifacts.load_storyboard()
            storyboard_review = artifacts.load_storyboard_review()

            if not storyboard or not storyboard_review or storyboard_review.approval_status != "approved":
                self._update_stage(project_id, ProjectStatus.PLANNING, "STORYBOARD_PLANNING")
                notify("STORYBOARD", "Designing animation storyboard and scene progression...")
                rec_id = self.state_manager.record_stage_start(project_id, "STORYBOARD")
                t0 = time.time()

                sb_revision: Optional[StoryboardReview] = storyboard_review

                while True:
                    storyboard = planner.run(
                        research=research,
                        config=metadata.config,
                        project_id=project_id,
                        revision_feedback=sb_revision,
                    )
                    self._update_stage(project_id, ProjectStatus.STORYBOARD_REVIEW, "STORYBOARD_REVIEW")
                    notify("STORYBOARD_REVIEW", "Critiquing storyboard flow, visual clarity, and Manim feasibility...")

                    storyboard_review = storyboard_critic.run(storyboard, research=research)
                    if storyboard_review.approval_status == "approved":
                        notify("STORYBOARD_REVIEW", f"Storyboard approved (Score: {storyboard_review.overall_score}/100).")
                        break

                    if not retry_mgr.can_revise("STORYBOARD"):
                        notify("STORYBOARD_REVIEW", "Max storyboard revisions reached. Proceeding with current plan.")
                        break

                    retry_mgr.record_revision("STORYBOARD")
                    notify("STORYBOARD", f"Revising storyboard (Attempt {retry_mgr.get_revision_count('STORYBOARD')})...")
                    sb_revision = storyboard_review

                self.state_manager.record_stage_end(rec_id, "COMPLETED", duration_seconds=time.time() - t0)
            else:
                notify("STORYBOARD", "Found previously approved storyboard. Resuming from code generation...")

            # ---------------------------------------------------------
            # STAGE 3: CODE GENERATION & CODE REVIEW
            # ---------------------------------------------------------
            code_artifact = artifacts.load_generated_code()
            code_review = artifacts.load_code_review()

            if not code_artifact or not code_review or code_review.approval_status != "approved":
                self._update_stage(project_id, ProjectStatus.GENERATING_CODE, "CODE_GENERATION")
                notify("CODE_GEN", "Writing complete Manim animation Python code...")
                rec_id = self.state_manager.record_stage_start(project_id, "CODE_GEN")
                t0 = time.time()

                c_revision: Optional[CodeReview] = code_review

                while True:
                    code_artifact = code_gen.run(
                        storyboard=storyboard,
                        config=metadata.config,
                        project_id=project_id,
                        code_review=c_revision,
                    )
                    self._update_stage(project_id, ProjectStatus.CODE_REVIEW, "CODE_REVIEW")
                    notify("CODE_REVIEW", "Analyzing code syntax, imports, and Manim constructs...")

                    code_review = code_critic.run(code_artifact, storyboard=storyboard)
                    if code_review.approval_status == "approved":
                        notify("CODE_REVIEW", f"Code approved (Score: {code_review.overall_score}/100).")
                        break

                    if not retry_mgr.can_revise("CODE"):
                        notify("CODE_REVIEW", "Max code revisions reached. Proceeding to test render.")
                        break

                    retry_mgr.record_revision("CODE")
                    notify("CODE_GEN", f"Revising code (Attempt {retry_mgr.get_revision_count('CODE')})...")
                    c_revision = code_review

                self.state_manager.record_stage_end(rec_id, "COMPLETED", duration_seconds=time.time() - t0)
            else:
                notify("CODE_GEN", "Found previously approved code. Resuming from rendering...")

            # Check if user requested approval before rendering
            if metadata.config.require_approval_before_rendering:
                notify("PAUSED", "Project paused: require_approval_before_rendering is enabled.")
                return self.state_manager.get_project(project_id)

            # ---------------------------------------------------------
            # STAGE 4: LOCAL RENDERING
            # ---------------------------------------------------------
            self._update_stage(project_id, ProjectStatus.RENDERING, "LOCAL_RENDERING")
            notify("RENDERING", f"Rendering video locally with Manim ({metadata.config.rendering_quality} quality)...")
            rec_id = self.state_manager.record_stage_start(project_id, "RENDERING")
            t0 = time.time()

            render_res = self.renderer.render(
                script_path=artifacts.main_code_path,
                output_dir=artifacts.output_dir,
                logs_dir=artifacts.logs_dir,
                quality=metadata.config.rendering_quality,
                output_filename="final.mp4",
            )

            if not render_res.success:
                err_msg = f"Rendering failed: {render_res.error_message}"
                self.state_manager.record_stage_end(rec_id, "FAILED", error=err_msg, duration_seconds=time.time() - t0)
                self._update_stage(project_id, ProjectStatus.FAILED, "RENDERING_FAILED")
                raise OrchestratorError(err_msg)

            self.state_manager.record_stage_end(rec_id, "COMPLETED", duration_seconds=time.time() - t0)
            notify("RENDERING", f"Rendering completed successfully in {render_res.duration_seconds:.1f}s.")
            self.state_manager.update_output_video(project_id, render_res.video_path or str(artifacts.final_video_path))

            # ---------------------------------------------------------
            # STAGE 5: VIDEO INSPECTION & MULTIMODAL REVIEW
            # ---------------------------------------------------------
            self._update_stage(project_id, ProjectStatus.VIDEO_REVIEW, "VIDEO_INSPECTION")
            notify("VIDEO_REVIEW", "Extracting frames and inspecting visual clarity...")
            rec_id = self.state_manager.record_stage_start(project_id, "VIDEO_REVIEW")
            t0 = time.time()

            inspection = self.video_inspector.inspect_video(
                video_path=artifacts.final_video_path,
                frames_dir=artifacts.frames_dir,
                expected_duration=storyboard.estimated_duration,
            )

            video_review = video_rev.run(
                inspection=inspection,
                storyboard=storyboard,
                render_result=render_res,
            )

            self.state_manager.record_stage_end(rec_id, "COMPLETED", duration_seconds=time.time() - t0)
            notify("VIDEO_REVIEW", f"Video Review: Rating {video_review.visual_quality_rating}/10, Status: {video_review.approval_status.upper()}")

            # Check if video was rejected and automatic revision is enabled
            if (
                video_review.approval_status != "approved"
                and metadata.config.auto_revise_rejected_scenes
                and retry_mgr.can_revise("VIDEO")
            ):
                retry_mgr.record_revision("VIDEO")
                notify("REVISING", "Automatic revision requested by Video Reviewer. Regenerating code...")
                self._update_stage(project_id, ProjectStatus.REVISING, "VIDEO_REVISION")

                # Re-run code generator with video review guidance
                code_artifact = code_gen.run(
                    storyboard=storyboard,
                    config=metadata.config,
                    project_id=project_id,
                    video_review=video_review,
                )
                # Re-render
                render_res = self.renderer.render(
                    script_path=artifacts.main_code_path,
                    output_dir=artifacts.output_dir,
                    logs_dir=artifacts.logs_dir,
                    quality=metadata.config.rendering_quality,
                    output_filename="final.mp4",
                )

            # ---------------------------------------------------------
            # FINALIZE PROJECT
            # ---------------------------------------------------------
            self._update_stage(project_id, ProjectStatus.COMPLETED, "FINISHED")
            self.state_manager.update_token_usage(project_id, self.gemini_client.token_usage)
            notify("COMPLETED", f"Video production complete! Output saved to: {artifacts.final_video_path}")

            final_meta = self.state_manager.get_project(project_id)
            if final_meta:
                artifacts.save_metadata(final_meta)
            return final_meta

        except Exception as e:
            self._update_stage(project_id, ProjectStatus.FAILED, f"ERROR: {str(e)}")
            logger.error(f"Pipeline error for project '{project_id}': {e}", exc_info=True)
            raise

    def render_preview(self, project_id: str) -> RenderResult:
        """Render a fast low-quality preview of the currently generated code."""
        artifacts = ArtifactManager(project_id)
        if not artifacts.main_code_path.exists():
            raise OrchestratorError(f"No generated code found for project '{project_id}'.")

        return self.renderer.render(
            script_path=artifacts.main_code_path,
            output_dir=artifacts.output_dir,
            logs_dir=artifacts.logs_dir,
            quality="low",
            output_filename="preview.mp4",
        )

    def render_final(self, project_id: str, quality: Optional[str] = None) -> RenderResult:
        """Render final video for project."""
        artifacts = ArtifactManager(project_id)
        metadata = self.state_manager.get_project(project_id)
        if not metadata or not artifacts.main_code_path.exists():
            raise OrchestratorError(f"No generated code found for project '{project_id}'.")

        q = quality or metadata.config.rendering_quality
        res = self.renderer.render(
            script_path=artifacts.main_code_path,
            output_dir=artifacts.output_dir,
            logs_dir=artifacts.logs_dir,
            quality=q,
            output_filename="final.mp4",
        )
        if res.success and res.video_path:
            self.state_manager.update_output_video(project_id, res.video_path)
        return res

    def _update_stage(self, project_id: str, status: ProjectStatus, current_stage: str):
        """Update DB and project status."""
        self.state_manager.update_project_status(project_id, status, current_stage)
        self.state_manager.update_token_usage(project_id, self.gemini_client.token_usage)

