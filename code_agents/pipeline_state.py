"""
Pipeline run state management.

Tracks the 6-step CI/CD pipeline: connect → review/test → build → deploy → verify → rollback.
In-memory storage (resets on server restart).
"""

from __future__ import annotations

import enum
import logging
import time
import uuid

logger = logging.getLogger("code_agents.pipeline_state")
from dataclasses import dataclass, field
from typing import Optional


class StepStatus(str, enum.Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    ROLLED_BACK = "rolled_back"


STEP_NAMES = {
    1: "connect",
    2: "review_and_test",
    3: "push_and_build",
    4: "deploy",
    5: "verify",
    6: "rollback",
}


@dataclass
class PipelineRun:
    run_id: str
    branch: str
    repo_path: str
    created_at: float
    current_step: int = 1
    step_status: dict[int, StepStatus] = field(default_factory=lambda: {
        i: StepStatus.PENDING for i in range(1, 7)
    })
    step_details: dict[int, dict] = field(default_factory=dict)

    # Populated during pipeline execution
    build_job: Optional[str] = None
    deploy_job: Optional[str] = None
    build_number: Optional[int] = None
    argocd_app: Optional[str] = None
    argocd_revision: Optional[str] = None
    previous_revision: Optional[int] = None  # For rollback
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "branch": self.branch,
            "repo_path": self.repo_path,
            "created_at": self.created_at,
            "current_step": self.current_step,
            "current_step_name": STEP_NAMES.get(self.current_step, "unknown"),
            "steps": {
                i: {
                    "name": STEP_NAMES[i],
                    "status": self.step_status[i].value,
                    "details": self.step_details.get(i, {}),
                }
                for i in range(1, 7)
            },
            "build_job": self.build_job,
            "deploy_job": self.deploy_job,
            "build_number": self.build_number,
            "argocd_app": self.argocd_app,
            "argocd_revision": self.argocd_revision,
            "previous_revision": self.previous_revision,
            "error": self.error,
        }


class PipelineStateManager:
    """Manages pipeline runs in memory."""

    def __init__(self):
        self._runs: dict[str, PipelineRun] = {}

    def create_run(
        self,
        branch: str,
        repo_path: str,
        build_job: Optional[str] = None,
        deploy_job: Optional[str] = None,
        argocd_app: Optional[str] = None,
    ) -> PipelineRun:
        run_id = uuid.uuid4().hex[:12]
        run = PipelineRun(
            run_id=run_id,
            branch=branch,
            repo_path=repo_path,
            created_at=time.time(),
            build_job=build_job,
            deploy_job=deploy_job,
            argocd_app=argocd_app,
        )
        self._runs[run_id] = run
        logger.info(
            "pipeline CREATE run=%s branch=%s repo=%s build_job=%s deploy_job=%s argocd_app=%s",
            run_id, branch, repo_path, build_job, deploy_job, argocd_app,
        )
        return run

    def get_run(self, run_id: str) -> Optional[PipelineRun]:
        return self._runs.get(run_id)

    def list_runs(self) -> list[PipelineRun]:
        return list(self._runs.values())

    def advance(self, run_id: str) -> PipelineRun:
        """Mark current step as success and move to next step."""
        run = self._runs.get(run_id)
        if not run:
            raise KeyError(f"Pipeline run {run_id} not found")
        prev_step = run.current_step
        run.step_status[run.current_step] = StepStatus.SUCCESS
        if run.current_step < 6:
            run.current_step += 1
            run.step_status[run.current_step] = StepStatus.IN_PROGRESS
        logger.info(
            "pipeline ADVANCE run=%s step %d(%s)→%d(%s) branch=%s",
            run_id, prev_step, STEP_NAMES[prev_step], run.current_step, STEP_NAMES[run.current_step], run.branch,
        )
        return run

    def start_step(self, run_id: str) -> PipelineRun:
        """Mark current step as in-progress."""
        run = self._runs.get(run_id)
        if not run:
            raise KeyError(f"Pipeline run {run_id} not found")
        run.step_status[run.current_step] = StepStatus.IN_PROGRESS
        return run

    def fail_step(self, run_id: str, error: str, details: Optional[dict] = None) -> PipelineRun:
        """Mark current step as failed."""
        run = self._runs.get(run_id)
        if not run:
            raise KeyError(f"Pipeline run {run_id} not found")
        run.step_status[run.current_step] = StepStatus.FAILED
        run.error = error
        if details:
            run.step_details[run.current_step] = details
        logger.error(
            "pipeline FAIL run=%s step=%d(%s) branch=%s error=%s",
            run_id, run.current_step, STEP_NAMES[run.current_step], run.branch, error,
        )
        return run

    def set_step_details(self, run_id: str, step: int, details: dict) -> PipelineRun:
        """Store details for a specific step."""
        run = self._runs.get(run_id)
        if not run:
            raise KeyError(f"Pipeline run {run_id} not found")
        run.step_details[step] = details
        return run

    def trigger_rollback(self, run_id: str) -> PipelineRun:
        """Mark remaining steps as skipped and set current to rollback (step 6)."""
        run = self._runs.get(run_id)
        if not run:
            raise KeyError(f"Pipeline run {run_id} not found")
        from_step = run.current_step
        for i in range(run.current_step + 1, 6):
            run.step_status[i] = StepStatus.SKIPPED
        run.current_step = 6
        run.step_status[6] = StepStatus.IN_PROGRESS
        logger.warning(
            "pipeline ROLLBACK run=%s from_step=%d(%s) branch=%s error=%s",
            run_id, from_step, STEP_NAMES.get(from_step, "?"), run.branch, run.error or "-",
        )
        return run


# Singleton instance
pipeline_manager = PipelineStateManager()
