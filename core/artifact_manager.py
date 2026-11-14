"""Artifact Manager for AutoStudio.

Manages all file artifacts, atomic writes, versioned history archiving,
and the organized directory structure for each video production project.
"""

from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Type, TypeVar
from pydantic import BaseModel

from config import STORAGE_DIR
from schemas.generation import GeneratedCodeArtifact
from schemas.project import ProjectMetadata
from schemas.research import ResearchArtifact
from schemas.review import (
    CodeReview,
    ResearchReview,
    StoryboardReview,
    VideoReview,
)
from schemas.storyboard import Storyboard

T = TypeVar("T", bound=BaseModel)


class ArtifactManager:
    """Handles project file system layout, atomic writes, and versioning."""

    def __init__(self, project_id: str, base_storage_dir: Path = STORAGE_DIR):
        self.project_id = project_id
        self.project_dir = Path(base_storage_dir) / project_id

        # Define subdirectories
        self.research_dir = self.project_dir / "research"
        self.research_history_dir = self.research_dir / "research_history"

        self.storyboard_dir = self.project_dir / "storyboard"
        self.storyboard_history_dir = self.storyboard_dir / "storyboard_history"

        self.src_dir = self.project_dir / "src"
        self.scenes_dir = self.src_dir / "scene_implementations"

        self.rendering_dir = self.project_dir / "rendering"
        self.logs_dir = self.rendering_dir / "logs"
        self.frames_dir = self.rendering_dir / "frames"
        self.temp_dir = self.rendering_dir / "temporary"

        self.reviews_dir = self.project_dir / "reviews"
        self.revision_history_dir = self.reviews_dir / "revision_history"

        self.output_dir = self.project_dir / "output"
        self.metadata_dir = self.project_dir / "metadata"

        self._init_directories()

    def _init_directories(self):
        """Create all project folder structures."""
        dirs = [
            self.project_dir,
            self.research_dir,
            self.research_history_dir,
            self.storyboard_dir,
            self.storyboard_history_dir,
            self.src_dir,
            self.scenes_dir,
            self.rendering_dir,
            self.logs_dir,
            self.frames_dir,
            self.temp_dir,
            self.reviews_dir,
            self.revision_history_dir,
            self.output_dir,
            self.metadata_dir,
        ]
        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)

    def _write_text_atomic(self, file_path: Path, content: str):
        """Write content to a temp file first, then atomically replace the target."""
        file_path.parent.mkdir(parents=True, exist_ok=True)
        temp_file = file_path.with_suffix(f"{file_path.suffix}.tmp.{os.getpid()}")
        try:
            with open(temp_file, "w", encoding="utf-8") as f:
                f.write(content)
            temp_file.replace(file_path)
        except Exception:
            if temp_file.exists():
                temp_file.unlink(missing_ok=True)
            raise

    def _write_json_atomic(self, file_path: Path, model: BaseModel):
        """Write Pydantic model as formatted JSON atomically."""
        json_str = model.model_dump_json(indent=2)
        self._write_text_atomic(file_path, json_str)

    def _archive_file_if_exists(self, file_path: Path, archive_dir: Path):
        """Archive existing file with timestamp before replacing."""
        if file_path.exists():
            archive_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            archived_name = f"{timestamp}_{file_path.name}"
            archived_path = archive_dir / archived_name
            shutil.copy2(file_path, archived_path)

    def _load_model(self, file_path: Path, model_cls: Type[T]) -> Optional[T]:
        """Safely load and parse a Pydantic model from a JSON file."""
        if not file_path.exists():
            return None
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = f.read()
            return model_cls.model_validate_json(data)
        except Exception:
            return None

    # --- Project Metadata ---
    @property
    def project_meta_path(self) -> Path:
        return self.project_dir / "project.json"

    def save_metadata(self, metadata: ProjectMetadata):
        self._write_json_atomic(self.project_meta_path, metadata)
        # Also copy to metadata/execution.json
        exec_path = self.metadata_dir / "execution.json"
        self._write_json_atomic(exec_path, metadata)

    def load_metadata(self) -> Optional[ProjectMetadata]:
        return self._load_model(self.project_meta_path, ProjectMetadata)

    # --- Research ---
    @property
    def research_path(self) -> Path:
        return self.research_dir / "research.json"

    @property
    def research_review_path(self) -> Path:
        return self.research_dir / "research_review.json"

    def save_research(self, research: ResearchArtifact, archive: bool = True):
        if archive:
            self._archive_file_if_exists(self.research_path, self.research_history_dir)
        self._write_json_atomic(self.research_path, research)

    def load_research(self) -> Optional[ResearchArtifact]:
        return self._load_model(self.research_path, ResearchArtifact)

    def save_research_review(self, review: ResearchReview, archive: bool = True):
        if archive:
            self._archive_file_if_exists(self.research_review_path, self.research_history_dir)
        self._write_json_atomic(self.research_review_path, review)

    def load_research_review(self) -> Optional[ResearchReview]:
        return self._load_model(self.research_review_path, ResearchReview)

    # --- Storyboard ---
    @property
    def storyboard_path(self) -> Path:
        return self.storyboard_dir / "storyboard.json"

    @property
    def storyboard_review_path(self) -> Path:
        return self.storyboard_dir / "storyboard_review.json"

    def save_storyboard(self, storyboard: Storyboard, archive: bool = True):
        if archive:
            self._archive_file_if_exists(self.storyboard_path, self.storyboard_history_dir)
        self._write_json_atomic(self.storyboard_path, storyboard)

    def load_storyboard(self) -> Optional[Storyboard]:
        return self._load_model(self.storyboard_path, Storyboard)

    def save_storyboard_review(self, review: StoryboardReview, archive: bool = True):
        if archive:
            self._archive_file_if_exists(self.storyboard_review_path, self.storyboard_history_dir)
        self._write_json_atomic(self.storyboard_review_path, review)

    def load_storyboard_review(self) -> Optional[StoryboardReview]:
        return self._load_model(self.storyboard_review_path, StoryboardReview)

    # --- Code Generation ---
    @property
    def main_code_path(self) -> Path:
        return self.src_dir / "main.py"

    @property
    def code_artifact_path(self) -> Path:
        return self.src_dir / "code_artifact.json"

    @property
    def code_review_path(self) -> Path:
        return self.reviews_dir / "code_review.json"

    def save_generated_code(self, artifact: GeneratedCodeArtifact, archive: bool = True):
        if archive and self.main_code_path.exists():
            self._archive_file_if_exists(self.main_code_path, self.revision_history_dir)
            self._archive_file_if_exists(self.code_artifact_path, self.revision_history_dir)

        # Write executable main.py
        self._write_text_atomic(self.main_code_path, artifact.code)
        # Write metadata JSON
        self._write_json_atomic(self.code_artifact_path, artifact)

    def load_generated_code(self) -> Optional[GeneratedCodeArtifact]:
        return self._load_model(self.code_artifact_path, GeneratedCodeArtifact)

    def save_code_review(self, review: CodeReview, archive: bool = True):
        if archive:
            self._archive_file_if_exists(self.code_review_path, self.revision_history_dir)
        self._write_json_atomic(self.code_review_path, review)

    def load_code_review(self) -> Optional[CodeReview]:
        return self._load_model(self.code_review_path, CodeReview)

    # --- Video & Video Review ---
    @property
    def final_video_path(self) -> Path:
        return self.output_dir / "final.mp4"

    @property
    def video_review_path(self) -> Path:
        return self.reviews_dir / "video_review.json"

    def save_video_review(self, review: VideoReview, archive: bool = True):
        if archive:
            self._archive_file_if_exists(self.video_review_path, self.revision_history_dir)
        self._write_json_atomic(self.video_review_path, review)

    def load_video_review(self) -> Optional[VideoReview]:
        return self._load_model(self.video_review_path, VideoReview)

