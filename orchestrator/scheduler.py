"""
Recurring Scheduler — wraps existing cron/ system for orchestrator workflows.

Allows workflows and single-agent tasks to be placed on recurring schedules
using cron expressions.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class OrchestratorScheduler:
    """Schedule recurring orchestrator workflows using the existing cron system."""

    def __init__(self):
        self._ensure_cron_available()

    def _ensure_cron_available(self):
        """Check that the cron module is importable."""
        try:
            from cron.jobs import create_job, list_jobs
            self._available = True
        except ImportError:
            logger.warning("Cron module not available — scheduling disabled")
            self._available = False

    def schedule_workflow(
        self,
        name: str,
        goal: str,
        cron_expression: str,
        workflow_yaml: Optional[str] = None,
        model_override: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """Create a recurring cron job that triggers an orchestrator workflow.

        Args:
            name: Human-readable schedule name
            goal: The high-level goal to orchestrate each run
            cron_expression: Cron schedule (e.g., '0 9 * * 1' for Monday 9am)
            workflow_yaml: Optional pre-defined workflow YAML string
            model_override: Optional model override for all agents
            context: Optional additional context dict

        Returns:
            Job ID if created, None if scheduling unavailable
        """
        if not self._available:
            logger.error("Cannot schedule: cron module not available")
            return None

        from cron.jobs import create_job

        # Build the orchestration prompt that will run on schedule
        prompt_parts = [
            f"Execute orchestrator workflow: {goal}",
        ]
        if workflow_yaml:
            prompt_parts.append(f"\nPre-defined workflow:\n```yaml\n{workflow_yaml}\n```")
        if model_override:
            prompt_parts.append(f"\nModel override: {model_override}")
        if context:
            prompt_parts.append(f"\nContext: {json.dumps(context)}")

        prompt = "\n".join(prompt_parts)

        # Create the cron job using the existing system
        job = create_job(
            name=name,
            prompt=prompt,
            schedule=cron_expression,
            skill="orchestrate",
        )

        if job:
            job_id = job.get("id") or job.get("job_id")
            logger.info("Scheduled workflow '%s' with cron: %s (ID: %s)", name, cron_expression, job_id)
            return job_id
        return None

    def schedule_single_agent(
        self,
        name: str,
        agent_name: str,
        task: str,
        cron_expression: str,
        model_override: Optional[str] = None,
    ) -> Optional[str]:
        """Schedule a recurring single-agent task.

        Args:
            name: Human-readable schedule name
            agent_name: Agent name from roster
            task: Task description
            cron_expression: Cron schedule

        Returns:
            Job ID if created
        """
        if not self._available:
            return None

        from cron.jobs import create_job

        prompt = (
            f"Spawn orchestrator agent '{agent_name}' with task:\n{task}"
            + (f"\nModel override: {model_override}" if model_override else "")
        )

        job = create_job(
            name=name,
            prompt=prompt,
            schedule=cron_expression,
            skill="orchestrate",
        )

        return job.get("id") if job else None

    def list_scheduled(self) -> List[Dict[str, Any]]:
        """List all scheduled orchestrator workflows."""
        if not self._available:
            return []

        from cron.jobs import list_jobs

        all_jobs = list_jobs() or []
        # Filter to orchestrator jobs
        return [
            j for j in all_jobs
            if j.get("skill") == "orchestrate"
            or "orchestrator" in (j.get("prompt", "") or "").lower()
        ]

    def cancel_schedule(self, schedule_id: str) -> bool:
        """Cancel a scheduled workflow."""
        if not self._available:
            return False

        from cron.jobs import remove_job

        return bool(remove_job(schedule_id))

    def pause_schedule(self, schedule_id: str) -> bool:
        """Pause a scheduled workflow."""
        if not self._available:
            return False

        from cron.jobs import pause_job

        return bool(pause_job(schedule_id))

    def resume_schedule(self, schedule_id: str) -> bool:
        """Resume a paused scheduled workflow."""
        if not self._available:
            return False

        from cron.jobs import resume_job

        return bool(resume_job(schedule_id))
