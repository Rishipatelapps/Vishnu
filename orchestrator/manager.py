"""
Orchestrator Manager — the "AI Chief of Staff" (HiClaw Manager pattern).

A specialized AIAgent instance that decomposes complex tasks, selects
the best worker agents from the roster, builds workflow DAGs, and
synthesizes results. This is the 🎭 Agents Orchestrator.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from orchestrator.models import (
    AgentDefinition,
    Job,
    JobState,
    JobStatus,
    WorkflowDAG,
    WorkflowStep,
)
from orchestrator.roster import AgentRoster
from orchestrator.mal import ModelAbstractionLayer
from orchestrator.workflow import WorkflowEngine
from orchestrator.status import JobTracker, get_tracker
from orchestrator import manager_tools

logger = logging.getLogger(__name__)


# The Manager's system prompt template
MANAGER_SYSTEM_PROMPT = """You are the 🎭 Agents Orchestrator — an AI Chief of Staff responsible for decomposing complex tasks and delegating them to specialized worker agents.

You have access to a roster of {agent_count} specialized agents across {division_count} divisions. Your job is to:

1. **ANALYZE** the user's goal and break it into discrete sub-tasks
2. **SELECT** the best agent from the roster for each sub-task
3. **PLAN** the execution order — parallel where possible, sequential where dependencies exist
4. **EXECUTE** using the create_workflow tool to run the plan
5. **SYNTHESIZE** the results into a unified, high-quality response

## Available Tools

- **query_roster**: Search for agents by specialty, division, or keywords
- **create_workflow**: Build and execute a multi-step workflow DAG
- **spawn_single_agent**: Quick single-agent task (for simple requests)
- **check_workflow_status**: Monitor running workflows

## Decision Framework

For SIMPLE tasks (single domain, straightforward):
→ Use spawn_single_agent with the most relevant specialist

For COMPLEX tasks (multi-domain, multi-step):
→ Use query_roster to find the best agents
→ Use create_workflow to build a DAG with proper dependencies

## AVAILABLE AGENT ROSTER
{roster_summary}

## Critical Rules

1. ALWAYS search the roster before assigning agents — don't guess agent names
2. Prefer PARALLEL execution when steps are independent
3. Use {prev_result} in task templates to pass output between sequential steps
4. Choose the MOST SPECIALIZED agent for each sub-task — a Frontend Developer for UI work, not a generic Senior Developer
5. Your final response should SYNTHESIZE all agent outputs, not just concatenate them
6. If a task truly requires only one agent, use spawn_single_agent — don't over-engineer with workflows
"""


class OrchestratorManager:
    """The main orchestration manager that coordinates all agent operations."""

    def __init__(
        self,
        roster: Optional[AgentRoster] = None,
        mal: Optional[ModelAbstractionLayer] = None,
        max_concurrent_workers: int = 3,
    ):
        # Initialize components
        self.roster = roster or AgentRoster()
        if not len(self.roster):
            self.roster.load()

        self.mal = mal or ModelAbstractionLayer()
        self.engine = WorkflowEngine(self.roster, self.mal, max_concurrent_workers)
        self.tracker = get_tracker()

        # Initialize manager tools with dependencies
        manager_tools.init_manager_tools(
            self.roster, self.mal, self.engine, self.tracker
        )

        logger.info(
            "OrchestratorManager initialized with %d agents across %d divisions",
            len(self.roster),
            len(self.roster.list_divisions()),
        )

    def get_manager_system_prompt(self) -> str:
        """Build the full system prompt for the manager agent."""
        return MANAGER_SYSTEM_PROMPT.format(
            agent_count=len(self.roster),
            division_count=len(self.roster.list_divisions()),
            roster_summary=self.roster.get_roster_summary(),
        )

    def submit_job(self, goal: str, **kwargs) -> Job:
        """Submit a new orchestration job.

        Args:
            goal: High-level user goal
            **kwargs: Optional: workflow, model_override, context, schedule

        Returns:
            The created Job object
        """
        job = Job(goal=goal, **kwargs)
        self.tracker.register_job(job)
        logger.info("Job submitted: %s — %s", job.id, goal[:100])
        return job

    def execute_job(self, job: Job) -> JobStatus:
        """Execute a job synchronously.

        If the job has a pre-defined workflow, execute it directly.
        Otherwise, use the manager agent to auto-decompose and execute.
        """
        self.tracker.update_state(job.id, JobState.EXECUTING)

        try:
            if job.workflow:
                # Direct workflow execution
                status = self._execute_workflow(job)
            else:
                # Auto-decompose using the manager agent
                status = self._auto_orchestrate(job)

            self.tracker.complete_job(
                job.id,
                status.final_output or "",
                status.state,
            )
            return status

        except Exception as e:
            logger.error("Job %s failed: %s", job.id, e)
            self.tracker.complete_job(job.id, str(e), JobState.FAILED)
            return JobStatus(
                job_id=job.id,
                state=JobState.FAILED,
                final_output=f"Orchestration failed: {e}",
            )

    def _execute_workflow(self, job: Job) -> JobStatus:
        """Execute a pre-defined workflow DAG."""
        assert job.workflow is not None

        def _on_event(step_id, event, result=None):
            self.tracker.update_step(job.id, step_id, event, result)

        context_str = ""
        if job.context:
            import json
            context_str = json.dumps(job.context, indent=2)

        return self.engine.execute(
            job.workflow,
            initial_context=context_str,
            job_model_override=job.model_override,
            status_callback=_on_event,
        )

    def _auto_orchestrate(self, job: Job) -> JobStatus:
        """Use the manager AIAgent to auto-decompose and execute a task.

        The manager agent has tools for roster querying, workflow creation,
        and single-agent spawning. It decides the best approach.
        """
        try:
            from run_agent import AIAgent

            # Resolve manager's own LLM config
            manager_def = self.roster.get_agent("Agents Orchestrator")
            if manager_def:
                llm_config = self.mal.resolve_config(
                    manager_def,
                    job_override=job.model_override,
                )
            else:
                # Fallback to global default
                llm_config = self.mal.resolve_config(
                    AgentDefinition(
                        name="Agents Orchestrator",
                        division="specialized",
                        default_model="anthropic/claude-sonnet-4-20250514",
                    ),
                    job_override=job.model_override,
                )

            system_prompt = self.get_manager_system_prompt()

            # Build context string
            context_parts = [f"USER GOAL: {job.goal}"]
            if job.context:
                import json
                context_parts.append(f"ADDITIONAL CONTEXT:\n{json.dumps(job.context, indent=2)}")

            agent = AIAgent(
                base_url=llm_config.base_url,
                api_key=llm_config.api_key,
                model=llm_config.model,
                provider=llm_config.provider,
                api_mode=llm_config.api_mode,
                max_iterations=90,
                system_prompt=system_prompt,
                skip_memory=True,
                skip_context_files=True,
            )

            result_text = agent.run_conversation("\n".join(context_parts))

            return JobStatus(
                job_id=job.id,
                state=JobState.COMPLETED,
                final_output=result_text or "No output produced.",
            )

        except Exception as e:
            logger.error("Auto-orchestration failed: %s", e)
            return JobStatus(
                job_id=job.id,
                state=JobState.FAILED,
                final_output=f"Auto-orchestration failed: {e}",
            )

    def run_interactive(self, goal: str, **kwargs) -> str:
        """Convenience method: submit + execute + return output."""
        job = self.submit_job(goal, **kwargs)
        status = self.execute_job(job)
        return status.final_output or ""
