"""
Manager-specific tools — registered in the Hermes tool system.

These tools give the Orchestrator Manager agent the ability to:
  - query_roster: Search the agency roster for the best agent
  - create_workflow: Build and execute a workflow DAG
  - spawn_single_agent: Quick single-agent delegation
  - check_workflow_status: Poll a running workflow
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# These will be set at initialization by the manager
_roster = None
_mal = None
_engine = None
_tracker = None


def init_manager_tools(roster, mal, engine, tracker):
    """Initialize manager tools with dependencies."""
    global _roster, _mal, _engine, _tracker
    _roster = roster
    _mal = mal
    _engine = engine
    _tracker = tracker


def check_orchestrator_requirements() -> bool:
    """Check if orchestrator tools are available."""
    return _roster is not None and len(_roster) > 0


# ---------------------------------------------------------------------------
# Tool: query_roster
# ---------------------------------------------------------------------------

QUERY_ROSTER_SCHEMA = {
    "type": "function",
    "function": {
        "name": "query_roster",
        "description": (
            "Search the Agency Roster for specialized agents. Returns agents "
            "matching the query, ranked by relevance. Use this to find the best "
            "agent for a sub-task before creating a workflow."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query (e.g., 'frontend react ui', 'database optimization', 'marketing strategy')",
                },
                "division": {
                    "type": "string",
                    "description": "Optional: filter by division (engineering, design, marketing, sales, etc.)",
                },
                "top_k": {
                    "type": "integer",
                    "description": "Max results to return (default: 5)",
                    "default": 5,
                },
            },
            "required": ["query"],
        },
    },
}


async def query_roster(query: str, division: str = None, top_k: int = 5) -> str:
    """Search the roster for matching agents."""
    if not _roster:
        return "Error: Agent roster not loaded."

    if division:
        agents = _roster.list_division(division)
        # Filter by query within division
        scored = [(a, a.match_score(query)) for a in agents]
        scored.sort(key=lambda x: x[1], reverse=True)
        results = [a for a, s in scored[:top_k] if s > 0.0]
    else:
        results = _roster.search(query, top_k=top_k)

    if not results:
        return f"No agents found matching '{query}'. Try broader terms."

    lines = [f"Found {len(results)} matching agents:\n"]
    for agent in results:
        lines.append(
            f"- {agent.emoji} **{agent.name}** [{agent.division}]\n"
            f"  Specialty: {agent.specialty}\n"
            f"  Use: {agent.use_case}\n"
            f"  Default model: {agent.default_model}"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool: create_workflow
# ---------------------------------------------------------------------------

CREATE_WORKFLOW_SCHEMA = {
    "type": "function",
    "function": {
        "name": "create_workflow",
        "description": (
            "Create and execute a multi-step workflow DAG. Each step assigns "
            "a task to a specific agent from the roster. Steps can run in "
            "parallel (no dependencies) or sequentially (with depends_on). "
            "Use {prev_result} or {step_<id>_result} in task templates to "
            "reference prior step outputs."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Human-readable workflow name",
                },
                "steps": {
                    "type": "array",
                    "description": "Ordered list of workflow steps",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {
                                "type": "string",
                                "description": "Unique step ID (e.g., 'research', 'design', 'implement')",
                            },
                            "agent_name": {
                                "type": "string",
                                "description": "Exact agent name from roster (e.g., 'Frontend Developer')",
                            },
                            "task": {
                                "type": "string",
                                "description": "Task description for this agent. May use {prev_result} or {step_<id>_result}",
                            },
                            "depends_on": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Step IDs this step waits for (empty = can run immediately)",
                            },
                            "model_override": {
                                "type": "string",
                                "description": "Optional: override model (e.g., 'anthropic/claude-opus-4-20250514')",
                            },
                        },
                        "required": ["id", "agent_name", "task"],
                    },
                },
                "context": {
                    "type": "string",
                    "description": "Additional context passed to all steps",
                },
            },
            "required": ["name", "steps"],
        },
    },
}


async def create_workflow(
    name: str,
    steps: List[Dict[str, Any]],
    context: str = "",
) -> str:
    """Create and execute a workflow DAG."""
    if not _engine or not _tracker:
        return "Error: Workflow engine not initialized."

    from orchestrator.models import WorkflowDAG, WorkflowStep, Job, JobState

    # Build the DAG
    workflow_steps = []
    for step_data in steps:
        workflow_steps.append(WorkflowStep(
            id=step_data.get("id", ""),
            agent_name=step_data["agent_name"],
            task_template=step_data["task"],
            depends_on=step_data.get("depends_on", []),
            model_override=step_data.get("model_override"),
        ))

    dag = WorkflowDAG(name=name, steps=workflow_steps)

    # Validate
    errors = dag.validate_dag()
    if errors:
        return f"Workflow validation failed:\n" + "\n".join(f"  - {e}" for e in errors)

    # Create and track the job
    job = Job(goal=name, state=JobState.EXECUTING, workflow=dag)
    _tracker.register_job(job)
    _tracker.update_state(job.id, JobState.EXECUTING)

    # Execute
    def _on_step_event(step_id: str, event: str, result=None):
        _tracker.update_step(job.id, step_id, event, result)

    status = _engine.execute(
        dag,
        initial_context=context,
        status_callback=_on_step_event,
    )

    # Complete
    _tracker.complete_job(job.id, status.final_output or "", status.state)

    # Format result
    lines = [f"Workflow '{name}' completed — {status.state.value}"]
    lines.append(f"Steps: {status.steps_completed}/{status.steps_total} completed")
    lines.append(f"Duration: {status.elapsed_seconds}s")
    if status.final_output:
        lines.append(f"\n{status.final_output}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool: spawn_single_agent
# ---------------------------------------------------------------------------

SPAWN_AGENT_SCHEMA = {
    "type": "function",
    "function": {
        "name": "spawn_single_agent",
        "description": (
            "Quickly spawn a single specialized agent from the roster to handle "
            "a task. Use this for simple tasks that don't need a multi-step workflow."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "agent_name": {
                    "type": "string",
                    "description": "Exact agent name from roster (e.g., 'Frontend Developer')",
                },
                "task": {
                    "type": "string",
                    "description": "The task for the agent to complete",
                },
                "context": {
                    "type": "string",
                    "description": "Additional context",
                },
                "model_override": {
                    "type": "string",
                    "description": "Optional: override the agent's default model",
                },
            },
            "required": ["agent_name", "task"],
        },
    },
}


async def spawn_single_agent(
    agent_name: str,
    task: str,
    context: str = "",
    model_override: str = None,
) -> str:
    """Spawn a single worker agent for a task."""
    if not _roster or not _mal:
        return "Error: Roster or MAL not initialized."

    agent_def = _roster.get_agent(agent_name)
    if not agent_def:
        # Try fuzzy search
        results = _roster.search(agent_name, top_k=3)
        if results:
            suggestions = ", ".join(f"'{a.name}'" for a in results)
            return f"Agent '{agent_name}' not found. Did you mean: {suggestions}?"
        return f"Agent '{agent_name}' not found in the roster."

    llm_config = _mal.resolve_config(
        agent_def,
        job_override=model_override,
    )

    from orchestrator.worker import WorkerAgent
    worker = WorkerAgent(agent_def, llm_config)
    result = worker.execute(task, context=context)

    if result.status.value == "completed":
        return (
            f"{agent_def.emoji} {agent_def.name} completed the task "
            f"({result.duration_seconds}s, model: {result.model_used}):\n\n"
            f"{result.output}"
        )
    else:
        return (
            f"{agent_def.emoji} {agent_def.name} failed:\n{result.error}"
        )


# ---------------------------------------------------------------------------
# Tool: check_workflow_status
# ---------------------------------------------------------------------------

CHECK_STATUS_SCHEMA = {
    "type": "function",
    "function": {
        "name": "check_workflow_status",
        "description": "Check the status of a running or completed workflow job.",
        "parameters": {
            "type": "object",
            "properties": {
                "job_id": {
                    "type": "string",
                    "description": "The job ID to check",
                },
            },
            "required": ["job_id"],
        },
    },
}


async def check_workflow_status(job_id: str) -> str:
    """Check the status of a workflow job."""
    if not _tracker:
        return "Error: Status tracker not initialized."

    status = _tracker.get_status(job_id)
    if not status:
        return f"Job '{job_id}' not found."

    lines = [
        f"Job: {job_id}",
        f"State: {status.state.value}",
        f"Steps: {status.steps_completed}/{status.steps_total}",
        f"Duration: {status.elapsed_seconds}s",
        f"Total tokens: {status.total_tokens}",
    ]

    if status.current_step:
        lines.append(f"Current step: {status.current_step}")

    for result in status.step_results:
        icon = "✅" if result.status.value == "completed" else "❌"
        lines.append(f"  {icon} {result.agent_name}: {result.status.value} ({result.duration_seconds}s)")

    if status.final_output:
        lines.append(f"\nOutput preview: {status.final_output[:500]}...")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool registration helpers
# ---------------------------------------------------------------------------

def get_manager_tool_schemas() -> List[Dict]:
    """Return all manager tool schemas for the tool registry."""
    return [
        QUERY_ROSTER_SCHEMA,
        CREATE_WORKFLOW_SCHEMA,
        SPAWN_AGENT_SCHEMA,
        CHECK_STATUS_SCHEMA,
    ]


MANAGER_TOOL_HANDLERS = {
    "query_roster": query_roster,
    "create_workflow": create_workflow,
    "spawn_single_agent": spawn_single_agent,
    "check_workflow_status": check_workflow_status,
}
