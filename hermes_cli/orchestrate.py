"""
CLI integration for the orchestrator — `hermes orchestrate` subcommand.

Usage:
    hermes orchestrate "Build a landing page for our SaaS product"
    hermes orchestrate --roster
    hermes orchestrate --roster --division engineering
    hermes orchestrate --status <job_id>
    hermes orchestrate --search "frontend react"
    hermes orchestrate --workflow workflow.yaml
    hermes orchestrate --schedule "0 9 * * 1" --workflow weekly.yaml
"""

from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def _print_table(headers: list, rows: list, max_col_width: int = 50):
    """Simple table printer."""
    if not rows:
        print("  (no results)")
        return

    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            if i < len(col_widths):
                col_widths[i] = max(col_widths[i], min(len(str(cell)), max_col_width))

    header_line = "  ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers))
    print(header_line)
    print("  ".join("-" * w for w in col_widths))
    for row in rows:
        cells = []
        for i, cell in enumerate(row):
            text = str(cell)
            if len(text) > max_col_width:
                text = text[:max_col_width - 3] + "..."
            cells.append(text.ljust(col_widths[i]) if i < len(col_widths) else text)
        print("  ".join(cells))


def cmd_orchestrate(
    goal: Optional[str] = None,
    roster: bool = False,
    division: Optional[str] = None,
    search: Optional[str] = None,
    status: Optional[str] = None,
    workflow: Optional[str] = None,
    schedule: Optional[str] = None,
    model: Optional[str] = None,
    agent: Optional[str] = None,
):
    """Main orchestrate CLI handler."""
    from orchestrator.manager import OrchestratorManager
    from orchestrator.roster import AgentRoster

    # --- Roster listing ---
    if roster:
        _cmd_roster(division)
        return

    # --- Search ---
    if search:
        _cmd_search(search)
        return

    # --- Status check ---
    if status:
        _cmd_status(status)
        return

    # --- Single agent spawn ---
    if agent and goal:
        _cmd_spawn_agent(agent, goal, model)
        return

    # --- Workflow execution ---
    if workflow:
        _cmd_workflow(workflow, schedule, model, goal)
        return

    # --- Auto-orchestrate a goal ---
    if goal:
        _cmd_auto_orchestrate(goal, model)
        return

    # No valid command
    print("Usage: hermes orchestrate <goal>")
    print("       hermes orchestrate --roster [--division <name>]")
    print("       hermes orchestrate --search <query>")
    print("       hermes orchestrate --status <job_id>")
    print("       hermes orchestrate --agent <name> <goal>")
    print("       hermes orchestrate --workflow <file.yaml> [--schedule <cron>]")


def _cmd_roster(division: Optional[str] = None):
    """List the agent roster."""
    from orchestrator.roster import AgentRoster

    roster = AgentRoster()
    count = roster.load()
    print(f"\nAgency Roster — {count} agents loaded\n")

    if division:
        agents = roster.list_division(division)
        if not agents:
            print(f"No agents found in division: {division}")
            print(f"Available divisions: {', '.join(roster.list_divisions())}")
            return
        print(f"Division: {division.replace('_', ' ').title()}\n")
    else:
        agents = roster.list_all()
        # Group by division
        by_div = {}
        for a in agents:
            by_div.setdefault(a.division, []).append(a)

        for div_name in sorted(by_div.keys()):
            div_agents = by_div[div_name]
            print(f"\n{div_name.replace('_', ' ').title()} ({len(div_agents)} agents)")
            for a in div_agents:
                print(f"  {a.emoji} {a.name}: {a.specialty[:60]}")
        return

    headers = ["Agent", "Specialty", "Default Model"]
    rows = [
        (f"{a.emoji} {a.name}", a.specialty[:50], a.default_model)
        for a in agents
    ]
    _print_table(headers, rows)


def _cmd_search(query: str):
    """Search the roster."""
    from orchestrator.roster import AgentRoster

    roster = AgentRoster()
    roster.load()
    results = roster.search(query, top_k=10)

    print(f"\nSearch results for '{query}' — {len(results)} matches\n")
    for agent in results:
        score = agent.match_score(query)
        print(f"  {agent.emoji} {agent.name} [{agent.division}] (score: {score:.2f})")
        print(f"    {agent.specialty}")
        print(f"    Use: {agent.use_case}\n")


def _cmd_status(job_id: str):
    """Check job status."""
    from orchestrator.status import get_tracker

    tracker = get_tracker()
    status = tracker.get_status(job_id)
    if not status:
        print(f"Job '{job_id}' not found.")
        return

    print(f"\nJob: {status.job_id}")
    print(f"State: {status.state.value}")
    print(f"Steps: {status.steps_completed}/{status.steps_total}")
    print(f"Duration: {status.elapsed_seconds}s")
    print(f"Tokens: {status.total_tokens}")

    if status.step_results:
        print("\nStep Results:")
        for r in status.step_results:
            icon = "+" if r.status.value == "completed" else "x"
            print(f"  [{icon}] {r.agent_name}: {r.status.value} ({r.duration_seconds}s)")

    if status.final_output:
        print(f"\nOutput:\n{status.final_output[:2000]}")


def _cmd_spawn_agent(agent_name: str, task: str, model_override: Optional[str] = None):
    """Spawn a single agent."""
    from orchestrator.manager import OrchestratorManager

    print(f"\nSpawning agent: {agent_name}")
    print(f"Task: {task[:100]}\n")

    manager = OrchestratorManager()
    agent_def = manager.roster.get_agent(agent_name)
    if not agent_def:
        results = manager.roster.search(agent_name, top_k=3)
        if results:
            print(f"Agent '{agent_name}' not found. Did you mean:")
            for a in results:
                print(f"  - {a.emoji} {a.name}")
        else:
            print(f"Agent '{agent_name}' not found in roster.")
        return

    from orchestrator.worker import WorkerAgent

    llm_config = manager.mal.resolve_config(agent_def, job_override=model_override)
    worker = WorkerAgent(agent_def, llm_config)

    print(f"Using model: {llm_config.model} ({llm_config.provider})")
    print("Executing...\n")

    result = worker.execute(task)
    print(f"Status: {result.status.value}")
    print(f"Duration: {result.duration_seconds}s")
    if result.output:
        print(f"\n{result.output}")
    if result.error:
        print(f"\nError: {result.error}")


def _cmd_auto_orchestrate(goal: str, model_override: Optional[str] = None):
    """Auto-orchestrate a goal."""
    from orchestrator.manager import OrchestratorManager

    print(f"\nOrchestrating: {goal}\n")

    manager = OrchestratorManager()
    print(f"Roster: {len(manager.roster)} agents across {len(manager.roster.list_divisions())} divisions")
    if model_override:
        print(f"Model override: {model_override}")
    print("Executing...\n")

    output = manager.run_interactive(goal, model_override=model_override)
    print(output)


def _cmd_workflow(
    workflow_path: str,
    schedule: Optional[str] = None,
    model_override: Optional[str] = None,
    goal: Optional[str] = None,
):
    """Execute or schedule a workflow from YAML file."""
    import yaml

    path = Path(workflow_path)
    if not path.exists():
        print(f"Workflow file not found: {workflow_path}")
        return

    with open(path, encoding="utf-8") as f:
        wf_data = yaml.safe_load(f)

    if not wf_data or "steps" not in wf_data:
        print("Invalid workflow file: must contain 'steps' key")
        return

    if schedule:
        # Schedule for recurring execution
        from orchestrator.scheduler import OrchestratorScheduler

        scheduler = OrchestratorScheduler()
        wf_yaml = path.read_text(encoding="utf-8")
        schedule_id = scheduler.schedule_workflow(
            name=wf_data.get("name", path.stem),
            goal=goal or wf_data.get("name", "Workflow execution"),
            cron_expression=schedule,
            workflow_yaml=wf_yaml,
            model_override=model_override,
        )
        if schedule_id:
            print(f"Workflow scheduled: {schedule_id}")
            print(f"Schedule: {schedule}")
        else:
            print("Failed to schedule workflow.")
        return

    # Execute immediately
    from orchestrator.models import WorkflowDAG, WorkflowStep
    from orchestrator.manager import OrchestratorManager

    steps = [WorkflowStep(**s) for s in wf_data["steps"]]
    dag = WorkflowDAG(name=wf_data.get("name", path.stem), steps=steps)

    errors = dag.validate_dag()
    if errors:
        print("Workflow validation errors:")
        for e in errors:
            print(f"  - {e}")
        return

    print(f"\nExecuting workflow: {dag.name}")
    print(f"Steps: {len(dag.steps)}\n")

    manager = OrchestratorManager()
    from orchestrator.models import Job, JobState

    job = manager.submit_job(
        goal=goal or dag.name,
        workflow=dag,
        model_override=model_override,
    )

    status = manager.execute_job(job)
    print(f"\nState: {status.state.value}")
    print(f"Steps completed: {status.steps_completed}/{status.steps_total}")
    print(f"Duration: {status.elapsed_seconds}s")
    if status.final_output:
        print(f"\n{status.final_output}")
