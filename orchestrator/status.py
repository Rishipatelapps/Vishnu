"""
Job Status Tracking & Event Streaming

Provides real-time status tracking for orchestrator jobs with
SSE (Server-Sent Events) support for the GUI layer.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections import defaultdict
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from orchestrator.models import (
    Job,
    JobState,
    JobStatus,
    WorkerResult,
)

logger = logging.getLogger(__name__)


class StatusEvent:
    """A single status event for SSE streaming."""

    def __init__(self, job_id: str, event_type: str, data: Dict[str, Any]):
        self.job_id = job_id
        self.event_type = event_type
        self.data = data
        self.timestamp = datetime.utcnow().isoformat()

    def to_sse(self) -> str:
        """Format as Server-Sent Event string."""
        payload = {
            "job_id": self.job_id,
            "event": self.event_type,
            "data": self.data,
            "timestamp": self.timestamp,
        }
        return f"data: {json.dumps(payload)}\n\n"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "event": self.event_type,
            "data": self.data,
            "timestamp": self.timestamp,
        }


class JobTracker:
    """Thread-safe job status tracker with event history and SSE support."""

    def __init__(self, max_events_per_job: int = 500):
        self._lock = threading.Lock()
        self._jobs: Dict[str, Job] = {}
        self._statuses: Dict[str, JobStatus] = {}
        self._events: Dict[str, List[StatusEvent]] = defaultdict(list)
        self._subscribers: Dict[str, List[Callable[[StatusEvent], None]]] = defaultdict(list)
        self._max_events = max_events_per_job

    def register_job(self, job: Job) -> None:
        """Register a new job for tracking."""
        with self._lock:
            self._jobs[job.id] = job
            self._statuses[job.id] = JobStatus(
                job_id=job.id,
                state=job.state,
                steps_total=len(job.workflow.steps) if job.workflow else 0,
            )
        self._emit(job.id, "job.registered", {"goal": job.goal, "state": job.state.value})

    def update_state(self, job_id: str, state: JobState) -> None:
        """Update the overall job state."""
        with self._lock:
            if job_id in self._jobs:
                self._jobs[job_id].state = state
                self._jobs[job_id].updated_at = datetime.utcnow()
            if job_id in self._statuses:
                self._statuses[job_id].state = state
        self._emit(job_id, "job.state_changed", {"state": state.value})

    def update_step(self, job_id: str, step_id: str, event: str, result: Optional[WorkerResult] = None) -> None:
        """Update a specific step's status."""
        with self._lock:
            status = self._statuses.get(job_id)
            if status:
                status.current_step = step_id
                if result:
                    status.step_results.append(result)
                    if result.status.value == "completed":
                        status.steps_completed += 1
                    status.total_tokens += result.tokens_used

        data: Dict[str, Any] = {"step_id": step_id, "event": event}
        if result:
            data["agent_name"] = result.agent_name
            data["status"] = result.status.value
            data["duration"] = result.duration_seconds
        self._emit(job_id, f"step.{event}", data)

    def complete_job(self, job_id: str, final_output: str, state: JobState = JobState.COMPLETED) -> None:
        """Mark a job as completed with final output."""
        with self._lock:
            if job_id in self._jobs:
                self._jobs[job_id].state = state
                self._jobs[job_id].completed_at = datetime.utcnow()
            if job_id in self._statuses:
                self._statuses[job_id].state = state
                self._statuses[job_id].final_output = final_output
        self._emit(job_id, "job.completed", {"state": state.value, "output_length": len(final_output)})

    def get_status(self, job_id: str) -> Optional[JobStatus]:
        """Get the current status of a job."""
        with self._lock:
            return self._statuses.get(job_id)

    def get_job(self, job_id: str) -> Optional[Job]:
        """Get a job by ID."""
        with self._lock:
            return self._jobs.get(job_id)

    def list_jobs(self, state: Optional[JobState] = None) -> List[Job]:
        """List all tracked jobs, optionally filtered by state."""
        with self._lock:
            jobs = list(self._jobs.values())
        if state:
            jobs = [j for j in jobs if j.state == state]
        return sorted(jobs, key=lambda j: j.created_at, reverse=True)

    def get_events(self, job_id: str, since: int = 0) -> List[StatusEvent]:
        """Get events for a job since a given index."""
        with self._lock:
            events = self._events.get(job_id, [])
            return events[since:]

    def subscribe(self, job_id: str, callback: Callable[[StatusEvent], None]) -> Callable:
        """Subscribe to events for a job. Returns an unsubscribe function."""
        with self._lock:
            self._subscribers[job_id].append(callback)

        def unsubscribe():
            with self._lock:
                try:
                    self._subscribers[job_id].remove(callback)
                except ValueError:
                    pass

        return unsubscribe

    def _emit(self, job_id: str, event_type: str, data: Dict[str, Any]) -> None:
        """Emit an event to all subscribers and store in history."""
        event = StatusEvent(job_id, event_type, data)

        with self._lock:
            events = self._events[job_id]
            events.append(event)
            if len(events) > self._max_events:
                self._events[job_id] = events[-self._max_events:]
            subscribers = list(self._subscribers.get(job_id, []))

        for callback in subscribers:
            try:
                callback(event)
            except Exception as e:
                logger.warning("Event subscriber error: %s", e)


# Global singleton
_tracker: Optional[JobTracker] = None


def get_tracker() -> JobTracker:
    """Get the global JobTracker singleton."""
    global _tracker
    if _tracker is None:
        _tracker = JobTracker()
    return _tracker
