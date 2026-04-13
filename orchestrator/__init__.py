"""
Multi-Agent Orchestration Framework

Modular Three-Tier Agent Orchestration combining:
- Layer 1: Hermes-Workspace GUI (Presentation)
- Layer 2: HiClaw-style Manager-Workers orchestration (Business Logic)
- Layer 3: Agency Roster + Model Abstraction Layer (Execution)

This package provides the orchestration engine (Layers 2 & 3).
"""

__version__ = "0.1.0"

from orchestrator.models import (
    AgentDefinition,
    Job,
    JobStatus,
    LLMConfig,
    WorkerResult,
    WorkflowDAG,
    WorkflowStep,
)
from orchestrator.roster import AgentRoster
from orchestrator.mal import ModelAbstractionLayer
from orchestrator.worker import WorkerAgent
from orchestrator.workflow import WorkflowEngine
from orchestrator.manager import OrchestratorManager

__all__ = [
    "AgentDefinition",
    "AgentRoster",
    "Job",
    "JobStatus",
    "LLMConfig",
    "ModelAbstractionLayer",
    "OrchestratorManager",
    "WorkerAgent",
    "WorkerResult",
    "WorkflowDAG",
    "WorkflowEngine",
    "WorkflowStep",
]
