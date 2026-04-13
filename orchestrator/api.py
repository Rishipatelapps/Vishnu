"""
REST API for the Orchestrator — enables Hermes-Workspace GUI integration.

Provides endpoints for job submission, status polling, roster browsing,
and SSE event streaming. Designed to be mounted on the existing
Hermes gateway HTTP server.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Lazy-initialized singleton
_manager = None


def _get_manager():
    """Get or create the OrchestratorManager singleton."""
    global _manager
    if _manager is None:
        from orchestrator.manager import OrchestratorManager
        _manager = OrchestratorManager()
    return _manager


def _get_tracker():
    """Get the global JobTracker."""
    from orchestrator.status import get_tracker
    return get_tracker()


# ---------------------------------------------------------------------------
# Request/Response helpers
# ---------------------------------------------------------------------------

def _json_response(data: Any, status: int = 200) -> Dict[str, Any]:
    """Build a JSON response dict."""
    return {"status": status, "body": data}


def _error_response(message: str, status: int = 400) -> Dict[str, Any]:
    """Build an error response dict."""
    return {"status": status, "body": {"error": message}}


# ---------------------------------------------------------------------------
# API Handlers (called by gateway or standalone server)
# ---------------------------------------------------------------------------

def handle_submit_job(body: Dict[str, Any]) -> Dict[str, Any]:
    """POST /api/orchestrator/jobs — Submit a new orchestration job."""
    goal = body.get("goal")
    if not goal:
        return _error_response("Missing required field: 'goal'")

    manager = _get_manager()

    # Parse optional workflow
    workflow = None
    if body.get("workflow"):
        from orchestrator.models import WorkflowDAG, WorkflowStep
        try:
            steps_data = body["workflow"].get("steps", [])
            steps = [WorkflowStep(**s) for s in steps_data]
            workflow = WorkflowDAG(
                name=body["workflow"].get("name", goal[:50]),
                steps=steps,
            )
        except Exception as e:
            return _error_response(f"Invalid workflow: {e}")

    # Submit the job
    job = manager.submit_job(
        goal=goal,
        workflow=workflow,
        model_override=body.get("model_override"),
        context=body.get("context", {}),
        schedule=body.get("schedule"),
    )

    # Handle scheduled jobs
    if job.schedule:
        from orchestrator.scheduler import OrchestratorScheduler
        scheduler = OrchestratorScheduler()
        schedule_id = scheduler.schedule_workflow(
            name=goal[:50],
            goal=goal,
            cron_expression=job.schedule,
            model_override=body.get("model_override"),
            context=body.get("context"),
        )
        return _json_response({
            "job_id": job.id,
            "state": "scheduled",
            "schedule_id": schedule_id,
            "schedule": job.schedule,
        }, 201)

    # Execute in background thread
    def _run():
        manager.execute_job(job)

    thread = threading.Thread(target=_run, name=f"orchestrator-job-{job.id}", daemon=True)
    thread.start()

    return _json_response({
        "job_id": job.id,
        "state": job.state.value,
        "message": "Job submitted and executing",
    }, 201)


def handle_get_job(job_id: str) -> Dict[str, Any]:
    """GET /api/orchestrator/jobs/{id} — Get job status and results."""
    tracker = _get_tracker()
    status = tracker.get_status(job_id)
    if not status:
        return _error_response(f"Job '{job_id}' not found", 404)

    return _json_response({
        "job_id": status.job_id,
        "state": status.state.value,
        "current_step": status.current_step,
        "steps_completed": status.steps_completed,
        "steps_total": status.steps_total,
        "elapsed_seconds": status.elapsed_seconds,
        "total_tokens": status.total_tokens,
        "step_results": [
            {
                "step_id": r.step_id,
                "agent_name": r.agent_name,
                "status": r.status.value,
                "output": r.output[:1000] if r.output else None,
                "error": r.error,
                "duration_seconds": r.duration_seconds,
                "model_used": r.model_used,
            }
            for r in status.step_results
        ],
        "final_output": status.final_output,
    })


def handle_list_jobs(state: Optional[str] = None) -> Dict[str, Any]:
    """GET /api/orchestrator/jobs — List all jobs."""
    tracker = _get_tracker()

    state_filter = None
    if state:
        from orchestrator.models import JobState
        try:
            state_filter = JobState(state)
        except ValueError:
            return _error_response(f"Invalid state: {state}")

    jobs = tracker.list_jobs(state=state_filter)
    return _json_response({
        "jobs": [
            {
                "id": j.id,
                "goal": j.goal[:200],
                "state": j.state.value,
                "created_at": j.created_at.isoformat() if j.created_at else None,
            }
            for j in jobs
        ],
        "total": len(jobs),
    })


def handle_cancel_job(job_id: str) -> Dict[str, Any]:
    """DELETE /api/orchestrator/jobs/{id} — Cancel a running job."""
    tracker = _get_tracker()
    job = tracker.get_job(job_id)
    if not job:
        return _error_response(f"Job '{job_id}' not found", 404)

    from orchestrator.models import JobState
    tracker.update_state(job_id, JobState.CANCELLED)
    return _json_response({"job_id": job_id, "state": "cancelled"})


def handle_list_roster(division: Optional[str] = None) -> Dict[str, Any]:
    """GET /api/orchestrator/roster — List all agents."""
    manager = _get_manager()

    if division:
        agents = manager.roster.list_division(division)
    else:
        agents = manager.roster.list_all()

    return _json_response({
        "agents": [
            {
                "name": a.name,
                "emoji": a.emoji,
                "division": a.division,
                "specialty": a.specialty,
                "use_case": a.use_case,
                "default_model": a.default_model,
                "tags": a.tags,
                "role": a.role,
            }
            for a in agents
        ],
        "total": len(agents),
        "divisions": manager.roster.list_divisions(),
    })


def handle_get_agent(agent_name: str) -> Dict[str, Any]:
    """GET /api/orchestrator/roster/{name} — Get agent details."""
    manager = _get_manager()
    agent = manager.roster.get_agent(agent_name)
    if not agent:
        return _error_response(f"Agent '{agent_name}' not found", 404)

    return _json_response({
        "name": agent.name,
        "emoji": agent.emoji,
        "division": agent.division,
        "specialty": agent.specialty,
        "use_case": agent.use_case,
        "default_model": agent.default_model,
        "tags": agent.tags,
        "role": agent.role,
        "system_prompt": agent.system_prompt,
        "source_file": agent.source_file,
    })


def handle_search_roster(query: str, top_k: int = 10) -> Dict[str, Any]:
    """GET /api/orchestrator/roster/search?q=... — Search agents."""
    manager = _get_manager()
    results = manager.roster.search(query, top_k=top_k)

    return _json_response({
        "query": query,
        "results": [
            {
                "name": a.name,
                "emoji": a.emoji,
                "division": a.division,
                "specialty": a.specialty,
                "use_case": a.use_case,
                "score": a.match_score(query),
            }
            for a in results
        ],
        "total": len(results),
    })


def handle_sse_stream(job_id: str):
    """GET /api/orchestrator/status/stream?job_id=... — SSE event stream.

    Returns a generator of SSE-formatted strings for real-time updates.
    """
    tracker = _get_tracker()
    event_queue = []
    done = threading.Event()

    def _on_event(event):
        event_queue.append(event)
        if event.event_type in ("job.completed", "job.failed"):
            done.set()

    unsubscribe = tracker.subscribe(job_id, _on_event)

    def _generate():
        try:
            # Send existing events first
            for event in tracker.get_events(job_id):
                yield event.to_sse()

            # Stream new events
            while not done.is_set():
                while event_queue:
                    event = event_queue.pop(0)
                    yield event.to_sse()
                time.sleep(0.5)

            # Flush remaining
            while event_queue:
                yield event_queue.pop(0).to_sse()

        finally:
            unsubscribe()

    return _generate()


# ---------------------------------------------------------------------------
# Route table for integration with gateway/run.py
# ---------------------------------------------------------------------------

ORCHESTRATOR_ROUTES = {
    ("POST", "/api/orchestrator/jobs"): handle_submit_job,
    ("GET", "/api/orchestrator/jobs"): handle_list_jobs,
    ("GET", "/api/orchestrator/jobs/{id}"): handle_get_job,
    ("DELETE", "/api/orchestrator/jobs/{id}"): handle_cancel_job,
    ("GET", "/api/orchestrator/roster"): handle_list_roster,
    ("GET", "/api/orchestrator/roster/search"): handle_search_roster,
    ("GET", "/api/orchestrator/roster/{name}"): handle_get_agent,
    ("GET", "/api/orchestrator/status/stream"): handle_sse_stream,
}
