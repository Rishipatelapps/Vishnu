"""
Pydantic data models for the orchestration framework.

Defines the core data structures shared across all layers:
- AgentDefinition: Parsed agent personality from roster Markdown files
- LLMConfig: Provider/model/key configuration for a single agent execution
- Job: A user-submitted orchestration request
- WorkflowStep / WorkflowDAG: n8n-style workflow definitions
- WorkerResult / JobStatus: Execution results and status tracking
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Agent Roster Models
# ---------------------------------------------------------------------------

class AgentDefinition(BaseModel):
    """A single agent personality parsed from an agency_roster Markdown file."""

    name: str = Field(..., description="Display name (e.g. 'Frontend Developer')")
    emoji: str = Field("🤖", description="Agent emoji identifier")
    division: str = Field(..., description="Division slug (e.g. 'engineering')")
    specialty: str = Field("", description="Core competency summary")
    use_case: str = Field("", description="When to use this agent")
    default_model: str = Field(
        "anthropic/claude-sonnet-4-20250514",
        description="Default LLM model in provider/model format",
    )
    tags: List[str] = Field(default_factory=list, description="Searchable tags")
    system_prompt: str = Field("", description="Full Markdown body as system prompt")
    source_file: str = Field("", description="Path to the source .md file")
    role: str = Field("worker", description="'manager' or 'worker'")

    def summary_line(self) -> str:
        """Compact one-line summary for the manager's roster context."""
        return f"{self.emoji} {self.name} [{self.division}] — {self.specialty}"

    def match_score(self, query: str) -> float:
        """Simple relevance score against a search query (0.0–1.0)."""
        query_lower = query.lower()
        tokens = query_lower.split()
        searchable = (
            f"{self.name} {self.specialty} {self.use_case} "
            f"{self.division} {' '.join(self.tags)}"
        ).lower()

        if not tokens:
            return 0.0

        hits = sum(1 for t in tokens if t in searchable)
        return hits / len(tokens)


# ---------------------------------------------------------------------------
# LLM Configuration
# ---------------------------------------------------------------------------

class LLMConfig(BaseModel):
    """Resolved LLM configuration for a single agent execution."""

    provider: str = Field(..., description="Provider name (anthropic, openai, openrouter, etc.)")
    model: str = Field(..., description="Model identifier (e.g. claude-sonnet-4-20250514)")
    base_url: str = Field("", description="API base URL")
    api_key: str = Field("", description="Resolved API key")
    api_mode: Optional[str] = Field(None, description="API mode override")
    max_tokens: Optional[int] = Field(None, description="Max output tokens")

    class Config:
        # Don't expose api_key in repr/logs
        json_schema_extra = {"sensitive_fields": ["api_key"]}

    def __repr__(self) -> str:
        return (
            f"LLMConfig(provider={self.provider!r}, model={self.model!r}, "
            f"base_url={self.base_url!r}, api_key='***')"
        )


# ---------------------------------------------------------------------------
# Job & Status Models
# ---------------------------------------------------------------------------

class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class JobState(str, Enum):
    SUBMITTED = "submitted"
    PLANNING = "planning"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WorkerResult(BaseModel):
    """Result from a single worker agent execution."""

    step_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    agent_name: str = ""
    task: str = ""
    status: StepStatus = StepStatus.COMPLETED
    output: str = ""
    error: Optional[str] = None
    model_used: str = ""
    tokens_used: int = 0
    duration_seconds: float = 0.0
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class WorkflowStep(BaseModel):
    """Single step in a workflow DAG."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    agent_name: str = Field(..., description="Agent name from roster")
    task_template: str = Field(
        ...,
        description="Task description; may use {prev_result}, {step_<id>_result} placeholders",
    )
    depends_on: List[str] = Field(
        default_factory=list,
        description="Step IDs this step waits for before executing",
    )
    condition: Optional[str] = Field(
        None,
        description="Optional condition expression; step is skipped if evaluates to False",
    )
    model_override: Optional[str] = Field(
        None, description="Override the agent's default model for this step"
    )
    toolsets: Optional[List[str]] = Field(
        None, description="Override toolsets for this step's worker"
    )
    max_iterations: int = Field(50, description="Max tool-calling iterations for worker")


class WorkflowDAG(BaseModel):
    """Directed Acyclic Graph of workflow steps."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = Field("", description="Human-readable workflow name")
    steps: List[WorkflowStep] = Field(default_factory=list)

    def get_ready_steps(self, completed: set[str]) -> List[WorkflowStep]:
        """Return steps whose dependencies are all satisfied."""
        return [
            step for step in self.steps
            if step.id not in completed
            and all(dep in completed for dep in step.depends_on)
        ]

    def validate_dag(self) -> List[str]:
        """Check for cycles, missing dependencies, duplicate IDs. Returns error list."""
        errors = []
        step_ids = {s.id for s in self.steps}

        # Check for duplicate IDs
        if len(step_ids) != len(self.steps):
            seen = set()
            for s in self.steps:
                if s.id in seen:
                    errors.append(f"Duplicate step ID: {s.id}")
                seen.add(s.id)

        # Check for missing dependencies
        for step in self.steps:
            for dep in step.depends_on:
                if dep not in step_ids:
                    errors.append(f"Step {step.id} depends on unknown step: {dep}")

        # Check for cycles using DFS
        adjacency = {s.id: s.depends_on for s in self.steps}
        visited: set[str] = set()
        in_stack: set[str] = set()

        def _dfs(node: str) -> bool:
            if node in in_stack:
                return True  # cycle
            if node in visited:
                return False
            visited.add(node)
            in_stack.add(node)
            for neighbor in adjacency.get(node, []):
                if _dfs(neighbor):
                    return True
            in_stack.discard(node)
            return False

        for sid in step_ids:
            if _dfs(sid):
                errors.append(f"Cycle detected involving step: {sid}")
                break

        return errors

    def topological_layers(self) -> List[List[WorkflowStep]]:
        """Return steps grouped into parallel-executable layers."""
        layers = []
        completed: set[str] = set()
        remaining = set(s.id for s in self.steps)
        step_map = {s.id: s for s in self.steps}

        while remaining:
            layer = [
                step_map[sid] for sid in remaining
                if all(dep in completed for dep in step_map[sid].depends_on)
            ]
            if not layer:
                break  # stuck — cycle or error
            layers.append(layer)
            for s in layer:
                completed.add(s.id)
                remaining.discard(s.id)

        return layers


class Job(BaseModel):
    """A user-submitted orchestration request."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    goal: str = Field(..., description="High-level user goal")
    state: JobState = Field(default=JobState.SUBMITTED)
    workflow: Optional[WorkflowDAG] = Field(
        None, description="Pre-defined workflow DAG; if None, manager auto-generates"
    )
    model_override: Optional[str] = Field(
        None, description="Force all agents to use this model"
    )
    context: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional context passed to agents",
    )
    schedule: Optional[str] = Field(
        None, description="Cron expression for recurring execution"
    )
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None


class JobStatus(BaseModel):
    """Real-time status snapshot for a running job."""

    job_id: str
    state: JobState
    current_step: Optional[str] = None
    steps_completed: int = 0
    steps_total: int = 0
    step_results: List[WorkerResult] = Field(default_factory=list)
    final_output: Optional[str] = None
    elapsed_seconds: float = 0.0
    total_tokens: int = 0
