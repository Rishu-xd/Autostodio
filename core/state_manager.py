"""SQLite State Manager for AutoStudio Projects and History."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from config import DB_PATH
from schemas.project import (
    ProjectConfig,
    ProjectMetadata,
    ProjectStatus,
    StageExecutionRecord,
    TokenUsage,
)


class StateManager:
    """Manages project persistence and stage execution history in SQLite."""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            conn.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                project_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                topic TEXT NOT NULL,
                status TEXT NOT NULL,
                current_stage TEXT NOT NULL,
                config_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                output_video_path TEXT,
                input_tokens INTEGER DEFAULT 0,
                output_tokens INTEGER DEFAULT 0,
                estimated_cost_usd REAL DEFAULT 0.0
            );
            """)

            conn.execute("""
            CREATE TABLE IF NOT EXISTS stage_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL,
                stage_name TEXT NOT NULL,
                status TEXT NOT NULL,
                attempt INTEGER NOT NULL,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                duration_seconds REAL DEFAULT 0.0,
                error TEXT,
                FOREIGN KEY (project_id) REFERENCES projects(project_id)
            );
            """)
            conn.commit()

    def create_project(self, project_id: str, config: ProjectConfig, title: Optional[str] = None) -> ProjectMetadata:
        """Create a new project record."""
        now = datetime.now(timezone.utc).isoformat()
        final_title = title or config.video_title or config.topic[:40]

        meta = ProjectMetadata(
            project_id=project_id,
            title=final_title,
            topic=config.topic,
            status=ProjectStatus.CREATED,
            current_stage="INITIALIZED",
            created_at=now,
            updated_at=now,
            config=config,
        )

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO projects (
                    project_id, title, topic, status, current_stage,
                    config_json, created_at, updated_at, output_video_path,
                    input_tokens, output_tokens, estimated_cost_usd
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    meta.project_id,
                    meta.title,
                    meta.topic,
                    meta.status.value,
                    meta.current_stage,
                    config.model_dump_json(),
                    meta.created_at,
                    meta.updated_at,
                    None,
                    0,
                    0,
                    0.0,
                ),
            )
            conn.commit()

        return meta

    def get_project(self, project_id: str) -> Optional[ProjectMetadata]:
        """Load project metadata by ID."""
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM projects WHERE project_id = ?", (project_id,))
            row = cur.fetchone()
            if not row:
                return None

            config = ProjectConfig.model_validate_json(row["config_json"])
            token_usage = TokenUsage(
                input_tokens=row["input_tokens"],
                output_tokens=row["output_tokens"],
                total_tokens=row["input_tokens"] + row["output_tokens"],
                estimated_cost_usd=row["estimated_cost_usd"],
            )

            history = self.get_stage_history(project_id)

            return ProjectMetadata(
                project_id=row["project_id"],
                title=row["title"],
                topic=row["topic"],
                status=ProjectStatus(row["status"]),
                current_stage=row["current_stage"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                config=config,
                output_video_path=row["output_video_path"],
                token_usage=token_usage,
                history=history,
            )

    def update_project_status(
        self,
        project_id: str,
        status: ProjectStatus,
        current_stage: str,
    ):
        """Update status and current stage."""
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE projects
                SET status = ?, current_stage = ?, updated_at = ?
                WHERE project_id = ?
                """,
                (status.value, current_stage, now, project_id),
            )
            conn.commit()

    def update_token_usage(self, project_id: str, token_usage: TokenUsage):
        """Update cumulative token usage."""
        now = datetime.now(timezone.utc).isoformat()
        in_tokens = int(getattr(token_usage, "input_tokens", 0) or 0)
        out_tokens = int(getattr(token_usage, "output_tokens", 0) or 0)
        cost = float(getattr(token_usage, "estimated_cost_usd", 0.0) or 0.0)
        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE projects
                SET input_tokens = ?, output_tokens = ?, estimated_cost_usd = ?, updated_at = ?
                WHERE project_id = ?
                """,
                (
                    in_tokens,
                    out_tokens,
                    cost,
                    now,
                    project_id,
                ),
            )
            conn.commit()

    def update_output_video(self, project_id: str, video_path: str):
        """Set the path to the final output video."""
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE projects SET output_video_path = ?, updated_at = ? WHERE project_id = ?",
                (video_path, now, project_id),
            )
            conn.commit()

    def record_stage_start(self, project_id: str, stage_name: str, attempt: int = 1) -> int:
        """Record the beginning of a stage run."""
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO stage_history (project_id, stage_name, status, attempt, started_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (project_id, stage_name, "RUNNING", attempt, now),
            )
            conn.commit()
            return cur.lastrowid

    def record_stage_end(
        self,
        record_id: int,
        status: str,
        error: Optional[str] = None,
        duration_seconds: float = 0.0,
    ):
        """Record stage completion or failure."""
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE stage_history
                SET status = ?, completed_at = ?, duration_seconds = ?, error = ?
                WHERE id = ?
                """,
                (status, now, duration_seconds, error, record_id),
            )
            conn.commit()

    def get_stage_history(self, project_id: str) -> List[StageExecutionRecord]:
        """Retrieve all execution history records for a project."""
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT * FROM stage_history WHERE project_id = ? ORDER BY id ASC",
                (project_id,),
            )
            records = []
            for row in cur.fetchall():
                records.append(
                    StageExecutionRecord(
                        stage_name=row["stage_name"],
                        status=row["status"],
                        attempt=row["attempt"],
                        started_at=row["started_at"],
                        completed_at=row["completed_at"],
                        duration_seconds=row["duration_seconds"],
                        error=row["error"],
                    )
                )
            return records

    def list_projects(self) -> List[ProjectMetadata]:
        """List all projects."""
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT project_id FROM projects ORDER BY created_at DESC")
            projects = []
            for row in cur.fetchall():
                p = self.get_project(row["project_id"])
                if p:
                    projects.append(p)
            return projects
