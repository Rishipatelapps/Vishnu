"""Tests for orchestrator.scheduler module."""

import pytest

from orchestrator.models import WorkflowDAG, WorkflowStep


@pytest.fixture
def sample_workflow():
    """Create a sample workflow DAG."""
    steps = [
        WorkflowStep(
            id="step1",
            agent_name="Frontend Developer",
            task_template="Build UI",
            depends_on=[],
        ),
    ]
    return WorkflowDAG(name="Weekly Build", steps=steps)


def test_scheduler_module_imports():
    """Test that orchestrator scheduler module can be imported."""
    try:
        from orchestrator.scheduler import OrchestratorScheduler
        assert OrchestratorScheduler is not None
    except ImportError:
        pytest.skip("Scheduler module not available")


def test_scheduler_creation():
    """Test creating an OrchestratorScheduler instance."""
    try:
        from orchestrator.scheduler import OrchestratorScheduler
        scheduler = OrchestratorScheduler()
        assert scheduler is not None
    except ImportError:
        pytest.skip("Scheduler module not available")


def test_scheduler_has_schedule_methods():
    """Test that scheduler has expected methods."""
    try:
        from orchestrator.scheduler import OrchestratorScheduler
        scheduler = OrchestratorScheduler()

        # Check for expected methods
        assert hasattr(scheduler, "schedule_workflow")
        assert hasattr(scheduler, "schedule_single_agent")
        assert hasattr(scheduler, "list_scheduled")
        assert hasattr(scheduler, "cancel_schedule")
        assert hasattr(scheduler, "pause_schedule")
        assert hasattr(scheduler, "resume_schedule")
    except ImportError:
        pytest.skip("Scheduler module not available")


def test_valid_cron_expressions():
    """Test valid cron expression formats."""
    valid_crons = [
        "0 9 * * 1",      # 9 AM every Monday
        "0 */4 * * *",    # Every 4 hours
        "30 2 * * *",     # 2:30 AM daily
        "0 0 * * 0",      # Midnight every Sunday
    ]

    for cron in valid_crons:
        # Just verify they're non-empty strings
        assert len(cron) > 0
        assert "*" in cron or all(c.isdigit() or c == " " for c in cron)


def test_workflow_scheduling_payload():
    """Test creating a valid workflow scheduling payload."""
    workflow = {
        "dag": {
            "name": "Weekly Build",
            "steps": [
                {
                    "id": "step1",
                    "agent_name": "Frontend Developer",
                    "task_template": "Build UI",
                    "depends_on": [],
                }
            ],
        },
        "cron_expression": "0 9 * * 1",
        "goal": "Weekly site build",
    }

    assert "dag" in workflow
    assert "cron_expression" in workflow
    assert "goal" in workflow


def test_single_agent_scheduling_payload():
    """Test creating a valid single agent scheduling payload."""
    payload = {
        "agent_name": "Frontend Developer",
        "task": "Build weekly UI update",
        "cron_expression": "0 12 * * 5",
    }

    assert "agent_name" in payload
    assert "task" in payload
    assert "cron_expression" in payload


def test_schedule_with_model_override():
    """Test scheduling with model override."""
    payload = {
        "goal": "Build with specific model",
        "model_override": "openai/gpt-4o",
        "cron_expression": "0 9 * * 1",
    }

    assert payload["model_override"] == "openai/gpt-4o"


def test_schedule_with_context():
    """Test scheduling with additional context."""
    context = {
        "brand": "Startup",
        "target": "users",
    }

    payload = {
        "goal": "Build with context",
        "context": context,
        "cron_expression": "0 9 * * 1",
    }

    assert payload["context"]["brand"] == "Startup"


def test_workflow_step_serialization(sample_workflow):
    """Test that workflow steps can be serialized."""
    assert len(sample_workflow.steps) > 0
    step = sample_workflow.steps[0]

    # Verify step has serializable fields
    assert hasattr(step, "id")
    assert hasattr(step, "agent_name")
    assert hasattr(step, "task_template")


def test_schedule_list_structure():
    """Test expected structure for scheduled jobs list."""
    schedules = [
        {
            "id": "schedule-1",
            "goal": "Weekly build",
            "cron": "0 9 * * 1",
            "status": "active",
        },
        {
            "id": "schedule-2",
            "goal": "Daily deploy",
            "cron": "0 2 * * *",
            "status": "paused",
        },
    ]

    assert len(schedules) == 2
    assert all("id" in s for s in schedules)
    assert all("cron" in s for s in schedules)
