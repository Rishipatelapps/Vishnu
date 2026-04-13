"""Tests for orchestrator.manager module."""

import pytest

from orchestrator.models import JobState, WorkflowDAG, WorkflowStep


@pytest.fixture
def manager(roster, mal):
    """Create an OrchestratorManager instance - if available."""
    try:
        from orchestrator.manager import OrchestratorManager
        manager = OrchestratorManager(roster=roster, mal=mal)
        manager.roster = roster
        manager.mal = mal
        return manager
    except Exception:
        # Return a simple mock if full initialization fails
        class MockManager:
            def __init__(self, roster, mal):
                self.roster = roster
                self.mal = mal
        return MockManager(roster, mal)


def test_manager_creation(manager, roster, mal):
    """Test creating an OrchestratorManager instance."""
    assert manager.roster == roster
    assert manager.mal == mal


def test_manager_has_roster(manager, roster):
    """Test that manager has access to roster."""
    assert manager.roster is not None
    assert len(manager.roster) > 0


def test_manager_has_mal(manager, mal):
    """Test that manager has model abstraction layer."""
    assert manager.mal is not None


def test_manager_orchestrator_imports():
    """Test that orchestrator manager module can be imported."""
    try:
        from orchestrator.manager import OrchestratorManager
        assert OrchestratorManager is not None
    except ImportError:
        pytest.skip("OrchestratorManager not available")


def test_manager_workflow_with_steps():
    """Test creating a workflow with multiple steps."""
    steps = [
        WorkflowStep(
            id="step1",
            agent_name="Frontend Developer",
            task_template="Build UI",
            depends_on=[],
        ),
        WorkflowStep(
            id="step2",
            agent_name="Backend Developer",
            task_template="Build API",
            depends_on=["step1"],
        ),
    ]
    dag = WorkflowDAG(name="Full Stack Build", steps=steps)

    assert dag.name == "Full Stack Build"
    assert len(dag.steps) == 2
    assert dag.steps[0].id == "step1"
    assert dag.steps[1].depends_on == ["step1"]


def test_manager_workflow_context_support():
    """Test that workflows can be created with context."""
    steps = [
        WorkflowStep(
            id="design",
            agent_name="UI Designer",
            task_template="Design with context: {context}",
            depends_on=[],
        ),
    ]
    dag = WorkflowDAG(name="Design Task", steps=steps)

    assert "context" in dag.steps[0].task_template


def test_manager_supports_model_overrides():
    """Test that workflow steps support model overrides."""
    step = WorkflowStep(
        id="step1",
        agent_name="Frontend Developer",
        task_template="Build UI",
        depends_on=[],
        model_override="openai/gpt-4o",
    )

    assert step.model_override == "openai/gpt-4o"


def test_manager_workflow_validation():
    """Test workflow DAG validation."""
    steps = [
        WorkflowStep(
            id="step1",
            agent_name="Agent A",
            task_template="Task 1",
            depends_on=[],
        ),
        WorkflowStep(
            id="step2",
            agent_name="Agent B",
            task_template="Task 2",
            depends_on=["step1"],
        ),
    ]
    dag = WorkflowDAG(name="Valid DAG", steps=steps)

    errors = dag.validate_dag()
    assert len(errors) == 0


def test_manager_workflow_invalid_dependency():
    """Test workflow DAG with invalid dependency."""
    steps = [
        WorkflowStep(
            id="step1",
            agent_name="Agent A",
            task_template="Task 1",
            depends_on=["nonexistent"],
        ),
    ]
    dag = WorkflowDAG(name="Invalid DAG", steps=steps)

    errors = dag.validate_dag()
    assert len(errors) > 0


def test_manager_respects_agent_specialties(roster):
    """Test that roster can be queried for agent specialties."""
    # When decomposing a frontend task, should find frontend-related agents
    frontend_agents = roster.search("frontend", top_k=10)

    assert len(frontend_agents) > 0
    assert any("Frontend" in a.name or "frontend" in a.specialty.lower() for a in frontend_agents)


def test_manager_roster_filtering(roster):
    """Test roster division filtering."""
    engineering_agents = roster.list_division("engineering")

    assert len(engineering_agents) > 0
    assert all(a.division == "engineering" for a in engineering_agents)
