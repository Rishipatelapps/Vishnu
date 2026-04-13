"""
Worker Agent — spawns specialized AIAgent instances with roster personalities.

Adapts the _build_child_agent() pattern from tools/delegate_tool.py but
injects the full agency roster system prompt instead of a generic subagent prompt.
Workers are stateless: they receive a task, execute it, and return a result.
"""

from __future__ import annotations

import logging
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

from orchestrator.models import (
    AgentDefinition,
    LLMConfig,
    StepStatus,
    WorkerResult,
)

logger = logging.getLogger(__name__)

MAX_CONCURRENT_WORKERS = 3
DEFAULT_MAX_ITERATIONS = 50

# Tools blocked for worker agents (same philosophy as delegate_tool.py)
WORKER_BLOCKED_TOOLSETS = frozenset([
    "delegation",   # no recursive delegation from workers
    "clarify",      # no user interaction from workers
    "memory",       # no shared memory writes
    "send_message", # no cross-platform side effects
])


def _build_worker_system_prompt(
    agent_def: AgentDefinition,
    task: str,
    context: str = "",
    workspace_path: Optional[str] = None,
) -> str:
    """Build the system prompt for a worker agent.

    Combines the agent's roster personality with the specific task and context.
    """
    parts = []

    # Agent personality from roster
    if agent_def.system_prompt:
        parts.append(agent_def.system_prompt)
        parts.append("")

    # Task assignment
    parts.append("---")
    parts.append(f"YOUR CURRENT TASK:\n{task}")

    if context and context.strip():
        parts.append(f"\nCONTEXT:\n{context}")

    if workspace_path:
        parts.append(f"\nWORKSPACE PATH:\n{workspace_path}")

    parts.append(
        "\nComplete this task using the tools available to you. "
        "When finished, provide a clear, concise summary of:\n"
        "- What you did\n"
        "- What you found or accomplished\n"
        "- Any files you created or modified\n"
        "- Any issues encountered\n\n"
        "Be thorough but concise — your response is returned to the "
        "orchestrator for synthesis with other agents' work."
    )

    return "\n".join(parts)


def _resolve_workspace_path() -> Optional[str]:
    """Best-effort workspace path resolution."""
    import os
    candidates = [
        os.getenv("TERMINAL_CWD"),
        os.getcwd(),
    ]
    for candidate in candidates:
        if candidate and os.path.isabs(candidate) and os.path.isdir(candidate):
            return candidate
    return None


class WorkerAgent:
    """Spawns and runs a specialized AIAgent as a worker."""

    def __init__(
        self,
        agent_def: AgentDefinition,
        llm_config: LLMConfig,
    ):
        self.agent_def = agent_def
        self.llm_config = llm_config

    def execute(
        self,
        task: str,
        context: str = "",
        toolsets: Optional[List[str]] = None,
        max_iterations: int = DEFAULT_MAX_ITERATIONS,
        progress_callback: Optional[Callable] = None,
    ) -> WorkerResult:
        """Spawn an AIAgent with the roster personality and run the task.

        Returns a WorkerResult with the output text, status, and metadata.
        """
        started_at = datetime.utcnow()
        start_time = time.monotonic()

        try:
            from run_agent import AIAgent

            # Build the specialized system prompt
            workspace = _resolve_workspace_path()
            system_prompt = _build_worker_system_prompt(
                self.agent_def, task, context, workspace
            )

            # Resolve toolsets: use provided or defaults, strip blocked
            effective_toolsets = toolsets or ["terminal", "file", "web"]
            effective_toolsets = [
                t for t in effective_toolsets
                if t not in WORKER_BLOCKED_TOOLSETS
            ]

            # Create the child AIAgent
            child = AIAgent(
                base_url=self.llm_config.base_url,
                api_key=self.llm_config.api_key,
                model=self.llm_config.model,
                provider=self.llm_config.provider,
                api_mode=self.llm_config.api_mode,
                max_iterations=max_iterations,
                max_tokens=self.llm_config.max_tokens,
                enabled_toolsets=effective_toolsets,
                system_prompt=system_prompt,
                skip_memory=True,
                skip_context_files=True,
            )

            # Run the conversation
            result_text = child.run_conversation(task)

            elapsed = time.monotonic() - start_time
            return WorkerResult(
                agent_name=self.agent_def.name,
                task=task,
                status=StepStatus.COMPLETED,
                output=result_text or "",
                model_used=self.llm_config.model,
                duration_seconds=round(elapsed, 2),
                started_at=started_at,
                completed_at=datetime.utcnow(),
            )

        except Exception as e:
            elapsed = time.monotonic() - start_time
            logger.error(
                "Worker %s failed on task: %s — %s",
                self.agent_def.name, task[:80], e,
            )
            return WorkerResult(
                agent_name=self.agent_def.name,
                task=task,
                status=StepStatus.FAILED,
                output="",
                error=str(e),
                model_used=self.llm_config.model,
                duration_seconds=round(elapsed, 2),
                started_at=started_at,
                completed_at=datetime.utcnow(),
            )

    @staticmethod
    def execute_batch(
        workers_and_tasks: List[Tuple["WorkerAgent", str, str]],
        max_concurrent: int = MAX_CONCURRENT_WORKERS,
        progress_callback: Optional[Callable] = None,
    ) -> List[WorkerResult]:
        """Run multiple workers in parallel.

        Args:
            workers_and_tasks: List of (WorkerAgent, task, context) tuples
            max_concurrent: Max parallel workers
            progress_callback: Optional callback(agent_name, status, result)

        Returns:
            List of WorkerResult in the same order as input
        """
        results: Dict[int, WorkerResult] = {}

        def _run_one(idx: int, worker: WorkerAgent, task: str, ctx: str) -> Tuple[int, WorkerResult]:
            if progress_callback:
                progress_callback(worker.agent_def.name, "started", None)
            result = worker.execute(task, context=ctx)
            if progress_callback:
                progress_callback(worker.agent_def.name, "completed", result)
            return idx, result

        with ThreadPoolExecutor(max_workers=max_concurrent) as executor:
            futures = {
                executor.submit(_run_one, i, w, t, c): i
                for i, (w, t, c) in enumerate(workers_and_tasks)
            }
            for future in as_completed(futures):
                idx, result = future.result()
                results[idx] = result

        # Return in original order
        return [results[i] for i in range(len(workers_and_tasks))]
