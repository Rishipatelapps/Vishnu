"""Tests for orchestrator.workflow module."""

import pytest

from orchestrator.models import WorkflowStep, WorkflowDAG, JobState
from orchestrator.workflow import WorkflowEngine


def test_workflow_step_creation():
    """Test creating a workflow step."""
    step = WorkflowStep(
        id="step1",
        agent_name="Frontend Developer",
        task_template="Build a landing page",
        depends_on=[],
    )

    assert step.id == "step1"
    assert step.agent_name == "Frontend Developer"
    assert step.task_template == "Build a landing page"
    assert step.depends_on == []


def test_workflow_step_with_dependencies():
    """Test creating a step with dependencies."""
    step = WorkflowStep(
        id="step2",
        agent_name="Backend Developer",
        task_template="Build API",
        depends_on=["step1"],
    )

    assert step.depends_on == ["step1"]


def test_workflow_dag_creation():
    """Test creating a workflow DAG."""
    steps = [
        WorkflowStep(
            id="design",
            agent_name="UI Designer",
            task_template="Design the UI",
            depends_on=[],
        ),
        WorkflowStep(
            id="frontend",
            agent_name="Frontend Developer",
            task_template="Implement the UI based on design",
            depends_on=["design"],
        ),
    ]

    dag = WorkflowDAG(name="Build Website", steps=steps)

    assert dag.name == "Build Website"
    assert len(dag.steps) == 2


def test_workflow_dag_validation_success():
    """Test validating a correct DAG."""
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

    dag = WorkflowDAG(name="Test", steps=steps)
    errors = dag.validate_dag()

    assert len(errors) == 0


def test_workflow_dag_validation_missing_dependency():
    """Test validation fails for missing dependency."""
    steps = [
        WorkflowStep(
            id="step2",
            agent_name="Agent B",
            task_template="Task 2",
            depends_on=["nonexistent"],
        ),
    ]

    dag = WorkflowDAG(name="Test", steps=steps)
    errors = dag.validate_dag()

    assert len(errors) > 0
    assert any("nonexistent" in e for e in errors)


def test_workflow_dag_validation_circular_dependency():
    """Test validation detects circular dependencies."""
    steps = [
        WorkflowStep(
            id="step1",
            agent_name="Agent A",
            task_template="Task 1",
            depends_on=["step2"],
        ),
        WorkflowStep(
            id="step2",
            agent_name="Agent B",
            task_template="Task 2",
            depends_on=["step1"],
        ),
    ]

    dag = WorkflowDAG(name="Test", steps=steps)
    errors = dag.validate_dag()

    assert len(errors) > 0


def test_workflow_dag_topological_sorting():
    """Test topological sorting of DAG steps."""
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
        WorkflowStep(
            id="step3",
            agent_name="Agent C",
            task_template="Task 3",
            depends_on=["step1"],
        ),
    ]

    dag = WorkflowDAG(name="Test", steps=steps)
    layers = dag.topological_layers()

    assert len(layers) == 2
    assert len(layers[0]) == 1  # step1 runs first
    assert len(layers[1]) == 2  # step2, step3 run together


def test_workflow_dag_get_ready_steps():
    """Test identifying steps ready for execution."""
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

    dag = WorkflowDAG(name="Test", steps=steps)
    ready = dag.get_ready_steps(completed=set())

    assert len(ready) == 1
    assert ready[0].id == "step1"


def test_workflow_dag_get_ready_steps_after_completion():
    """Test identifying ready steps after one completes."""
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

    dag = WorkflowDAG(name="Test", steps=steps)
    ready = dag.get_ready_steps(completed={"step1"})

    assert len(ready) == 1
    assert ready[0].id == "step2"


def test_workflow_dag_parallel_execution_no_dependencies():
    """Test that independent steps can execute in parallel."""
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
            depends_on=[],
        ),
        WorkflowStep(
            id="step3",
            agent_name="Agent C",
            task_template="Task 3",
            depends_on=[],
        ),
    ]

    dag = WorkflowDAG(name="Test", steps=steps)
    ready = dag.get_ready_steps(completed=set())

    assert len(ready) == 3  # All can run in parallel


def test_workflow_step_with_model_override():
    """Test step with model override."""
    step = WorkflowStep(
        id="step1",
        agent_name="Frontend Developer",
        task_template="Build UI",
        depends_on=[],
        model_override="openai/gpt-4o",
    )

    assert step.model_override == "openai/gpt-4o"


def test_workflow_step_with_condition():
    """Test step with conditional execution."""
    step = WorkflowStep(
        id="step1",
        agent_name="Agent A",
        task_template="Task 1",
        depends_on=[],
        condition="prev_result and 'success' in prev_result",
    )

    assert step.condition is not None


def test_workflow_dag_empty_steps():
    """Test DAG with no steps."""
    dag = WorkflowDAG(name="Empty", steps=[])

    assert len(dag.steps) == 0
    errors = dag.validate_dag()
    # Empty DAG should be valid
    assert len(errors) == 0


def test_workflow_dag_single_step():
    """Test DAG with a single step."""
    steps = [
        WorkflowStep(
            id="only",
            agent_name="Agent A",
            task_template="Only task",
            depends_on=[],
        ),
    ]

    dag = WorkflowDAG(name="Single", steps=steps)
    errors = dag.validate_dag()

    assert len(errors) == 0
    assert len(dag.steps) == 1


def test_workflow_dag_complex_dependencies():
    """Test DAG with complex dependency graph."""
    steps = [
        WorkflowStep(id="a", agent_name="A", task_template="A", depends_on=[]),
        WorkflowStep(id="b", agent_name="B", task_template="B", depends_on=[]),
        WorkflowStep(id="c", agent_name="C", task_template="C", depends_on=["a", "b"]),
        WorkflowStep(id="d", agent_name="D", task_template="D", depends_on=["c"]),
    ]

    dag = WorkflowDAG(name="Complex", steps=steps)
    errors = dag.validate_dag()

    assert len(errors) == 0

    # Check topological layers
    layers = dag.topological_layers()
    assert len(layers) == 3
    assert len(layers[0]) == 2  # a, b
    assert len(layers[1]) == 1  # c
    assert len(layers[2]) == 1  # d
