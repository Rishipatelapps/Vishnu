"""
Workflow Engine — DAG-based execution of multi-agent workflows.

Supports sequential, parallel, and conditional step execution following
an n8n-style directed acyclic graph. Each step maps to a worker agent
from the agency roster.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Set

from orchestrator.models import (
    AgentDefinition,
    Job,
    JobState,
    JobStatus,
    LLMConfig,
    StepStatus,
    WorkerResult,
    WorkflowDAG,
    WorkflowStep,
)
from orchestrator.roster import AgentRoster
from orchestrator.mal import ModelAbstractionLayer
from orchestrator.worker import WorkerAgent

logger = logging.getLogger(__name__)


def _render_task_template(
    template: str,
    step_results: Dict[str, WorkerResult],
    initial_context: str = "",
) -> str:
    """Render a task template with results from prior steps.

    Supports placeholders:
      {prev_result} — output from the most recently completed step
      {step_<id>_result} — output from a specific step by ID
      {initial_context} — the original job context
    """
    rendered = template

    # Replace {initial_context}
    rendered = rendered.replace("{initial_context}", initial_context)

    # Replace {step_<id>_result} placeholders
    for step_id, result in step_results.items():
        placeholder = "{step_" + step_id + "_result}"
        rendered = rendered.replace(placeholder, result.output or "")

    # Replace {prev_result} with the last completed step's output
    if step_results:
        last_result = list(step_results.values())[-1]
        rendered = rendered.replace("{prev_result}", last_result.output or "")

    return rendered


def _evaluate_condition(
    condition: str,
    step_results: Dict[str, WorkerResult],
) -> bool:
    """Evaluate a step's condition expression.

    The condition has access to step_results dict and can reference
    individual step outputs.
    """
    if not condition:
        return True

    try:
        # Build a safe evaluation context
        eval_context = {
            "step_results": step_results,
            "any_failed": any(
                r.status == StepStatus.FAILED for r in step_results.values()
            ),
            "all_passed": all(
                r.status == StepStatus.COMPLETED for r in step_results.values()
            ),
        }
        # Add individual step outputs as variables
        for step_id, result in step_results.items():
            eval_context[f"step_{step_id}"] = result.output or ""
            eval_context[f"step_{step_id}_status"] = result.status.value

        return bool(eval(condition, {"__builtins__": {}}, eval_context))
    except Exception as e:
        logger.warning("Condition evaluation failed for '%s': %s", condition, e)
        return True  # Default to executing on eval failure


class WorkflowEngine:
    """Executes a WorkflowDAG using WorkerAgents from the roster."""

    def __init__(
        self,
        roster: AgentRoster,
        mal: ModelAbstractionLayer,
        max_concurrent_workers: int = 3,
    ):
        self.roster = roster
        self.mal = mal
        self.max_concurrent = max_concurrent_workers

    def execute(
        self,
        dag: WorkflowDAG,
        initial_context: str = "",
        job_model_override: Optional[str] = None,
        status_callback: Optional[Callable[[str, str, Optional[WorkerResult]], None]] = None,
    ) -> JobStatus:
        """Execute a workflow DAG step-by-step.

        Args:
            dag: The workflow DAG to execute
            initial_context: Context string passed to all steps
            job_model_override: Force all agents to use this model
            status_callback: Optional callback(step_id, event, result)

        Returns:
            JobStatus with all step results and final output
        """
        start_time = time.monotonic()

        # Validate the DAG
        errors = dag.validate_dag()
        if errors:
            return JobStatus(
                job_id=dag.id,
                state=JobState.FAILED,
                steps_total=len(dag.steps),
                final_output=f"DAG validation failed: {'; '.join(errors)}",
            )

        # Get execution layers (topologically sorted)
        layers = dag.topological_layers()
        if not layers:
            return JobStatus(
                job_id=dag.id,
                state=JobState.COMPLETED,
                steps_total=0,
                final_output="Empty workflow — nothing to execute.",
            )

        step_results: Dict[str, WorkerResult] = {}
        completed_ids: Set[str] = set()
        all_results: List[WorkerResult] = []

        # Execute layer by layer
        for layer_idx, layer in enumerate(layers):
            logger.info(
                "Executing workflow layer %d/%d (%d steps)",
                layer_idx + 1, len(layers), len(layer),
            )

            # Prepare workers for this layer
            workers_and_tasks = []
            step_map: Dict[int, WorkflowStep] = {}

            for step in layer:
                # Check condition
                if step.condition and not _evaluate_condition(step.condition, step_results):
                    logger.info("Skipping step %s: condition not met", step.id)
                    skip_result = WorkerResult(
                        step_id=step.id,
                        agent_name=step.agent_name,
                        task=step.task_template,
                        status=StepStatus.SKIPPED,
                        output="Skipped: condition not met",
                    )
                    step_results[step.id] = skip_result
                    completed_ids.add(step.id)
                    all_results.append(skip_result)
                    if status_callback:
                        status_callback(step.id, "skipped", skip_result)
                    continue

                # Resolve agent from roster
                agent_def = self.roster.get_agent(step.agent_name)
                if not agent_def:
                    logger.error("Agent not found in roster: %s", step.agent_name)
                    fail_result = WorkerResult(
                        step_id=step.id,
                        agent_name=step.agent_name,
                        task=step.task_template,
                        status=StepStatus.FAILED,
                        error=f"Agent '{step.agent_name}' not found in roster",
                    )
                    step_results[step.id] = fail_result
                    completed_ids.add(step.id)
                    all_results.append(fail_result)
                    if status_callback:
                        status_callback(step.id, "failed", fail_result)
                    continue

                # Resolve LLM config
                llm_config = self.mal.resolve_config(
                    agent_def,
                    step_override=step.model_override,
                    job_override=job_model_override,
                )

                # Render task template with prior results
                rendered_task = _render_task_template(
                    step.task_template, step_results, initial_context
                )

                # Create worker
                worker = WorkerAgent(agent_def, llm_config)
                idx = len(workers_and_tasks)
                step_map[idx] = step
                workers_and_tasks.append((worker, rendered_task, initial_context))

                if status_callback:
                    status_callback(step.id, "started", None)

            # Execute this layer's workers in parallel
            if workers_and_tasks:
                batch_results = WorkerAgent.execute_batch(
                    workers_and_tasks,
                    max_concurrent=self.max_concurrent,
                )

                # Map results back to steps
                for idx, result in enumerate(batch_results):
                    step = step_map[idx]
                    result.step_id = step.id
                    step_results[step.id] = result
                    completed_ids.add(step.id)
                    all_results.append(result)

                    event = "completed" if result.status == StepStatus.COMPLETED else "failed"
                    if status_callback:
                        status_callback(step.id, event, result)

        # Build final output by combining all completed results
        elapsed = time.monotonic() - start_time
        total_tokens = sum(r.tokens_used for r in all_results)

        # Synthesize final output
        output_parts = []
        for result in all_results:
            if result.status == StepStatus.COMPLETED and result.output:
                output_parts.append(
                    f"## {result.agent_name} (Step {result.step_id})\n{result.output}"
                )
            elif result.status == StepStatus.FAILED:
                output_parts.append(
                    f"## {result.agent_name} (Step {result.step_id}) — FAILED\n{result.error}"
                )

        any_failed = any(r.status == StepStatus.FAILED for r in all_results)
        final_state = JobState.COMPLETED if not any_failed else JobState.FAILED

        return JobStatus(
            job_id=dag.id,
            state=final_state,
            steps_completed=len([r for r in all_results if r.status == StepStatus.COMPLETED]),
            steps_total=len(dag.steps),
            step_results=all_results,
            final_output="\n\n".join(output_parts) if output_parts else "No output produced.",
            elapsed_seconds=round(elapsed, 2),
            total_tokens=total_tokens,
        )
