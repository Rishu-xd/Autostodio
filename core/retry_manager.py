"""Retry and Revision Management for AutoStudio.

Tracks review cycles per stage, enforces upper bounds on agent critiques,
and provides backoff calculations to avoid infinite revision loops.
"""

from __future__ import annotations

import logging
from typing import Dict, List
from config import MAX_REVISION_COUNT, MAX_RETRIES
from schemas.project import StageRevision

logger = logging.getLogger("autostudio.retry")


class RevisionLimitExceeded(Exception):
    """Raised when maximum critic revision loops are exceeded for a stage."""
    pass


class RetryManager:
    """Manages revision counts and retry boundaries for workflow stages."""

    def __init__(
        self,
        max_revisions: int = MAX_REVISION_COUNT,
        max_transient_retries: int = MAX_RETRIES,
    ):
        self.max_revisions = max_revisions
        self.max_transient_retries = max_transient_retries
        self._revision_counts: Dict[str, int] = {}

    def get_revision_count(self, stage_name: str) -> int:
        """Returns the number of revisions attempted for a specific stage."""
        return self._revision_counts.get(stage_name, 0)

    def record_revision(self, stage_name: str) -> int:
        """Increment and return the revision count for a stage.
        Raises RevisionLimitExceeded if max revisions is breached.
        """
        count = self._revision_counts.get(stage_name, 0) + 1
        self._revision_counts[stage_name] = count
        logger.info(f"Stage '{stage_name}' revision count: {count}/{self.max_revisions}")

        if count > self.max_revisions:
            raise RevisionLimitExceeded(
                f"Stage '{stage_name}' exceeded maximum allowed revisions ({self.max_revisions}). "
                "Halting automated loop to avoid infinite cycling."
            )
        return count

    def can_revise(self, stage_name: str) -> bool:
        """Check if another revision cycle is permitted for this stage."""
        return self.get_revision_count(stage_name) < self.max_revisions

    def reset_stage(self, stage_name: str):
        """Reset counter when a stage is definitively approved or restarted."""
        self._revision_counts.pop(stage_name, None)

    def export_counts(self) -> Dict[str, int]:
        """Export current counts for persistence."""
        return dict(self._revision_counts)

    def load_counts(self, counts: Dict[str, int] | List[StageRevision]) -> None:
        """Load revision counts from the legacy mapping or typed schema representation."""
        if isinstance(counts, dict):
            self._revision_counts = dict(counts)
        elif isinstance(counts, list) and all(isinstance(item, StageRevision) for item in counts):
            self._revision_counts = {
                item.stage_name: item.count
                for item in counts
            }
        else:
            raise TypeError("Revision counts must be a mapping or a list of StageRevision models.")

