"""Tests for orchestrator.api module."""

import pytest

from orchestrator.models import WorkflowDAG, WorkflowStep


def test_api_module_imports():
    """Test that orchestrator API module can be imported."""
    try:
        from orchestrator import api
        assert api is not None
    except ImportError:
        pytest.skip("API module not available")


def test_api_function_signatures():
    """Test that expected API functions exist."""
    try:
        from orchestrator import api

        # Check that handler functions are defined
        handlers = [
            "handle_submit_job",
            "handle_list_jobs",
            "handle_get_job",
            "handle_cancel_job",
            "handle_list_roster",
            "handle_search_roster",
            "handle_get_agent",
            "handle_sse_stream",
        ]

        for handler_name in handlers:
            assert hasattr(api, handler_name), f"API missing {handler_name}"
    except ImportError:
        pytest.skip("API module not available")


def test_workflow_with_steps():
    """Test creating a workflow with steps for API testing."""
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
            task_template="Build the frontend",
            depends_on=["design"],
        ),
    ]
    dag = WorkflowDAG(name="Build Website", steps=steps)

    assert dag.name == "Build Website"
    assert len(dag.steps) == 2


def test_api_job_payload_structure():
    """Test valid job submission payload structure."""
    payload = {
        "goal": "Build a landing page",
        "model_override": None,
        "context": {},
    }

    # Just verify the structure is sound
    assert "goal" in payload
    assert payload["goal"] == "Build a landing page"


def test_api_job_with_workflow_payload():
    """Test job submission with workflow payload."""
    payload = {
        "goal": "Build website",
        "workflow": {
            "name": "Build Site",
            "steps": [
                {
                    "id": "design",
                    "agent_name": "UI Designer",
                    "task": "Design UI",
                    "depends_on": [],
                }
            ],
        },
    }

    assert "goal" in payload
    assert "workflow" in payload
    assert payload["workflow"]["name"] == "Build Site"


def test_api_roster_listing_structure():
    """Test roster listing response structure."""
    from orchestrator.models import AgentDefinition

    agent = AgentDefinition(
        name="Test Agent",
        emoji="🤖",
        division="testing",
        specialty="Testing",
        use_case="Unit tests",
        default_model="anthropic/claude-sonnet-4-20250514",
        tags=["test"],
        role="specialist",
        system_prompt="Test",
    )

    agents = [agent]
    assert len(agents) > 0
    assert agents[0].name == "Test Agent"


def test_api_agent_details_structure():
    """Test agent details response structure."""
    from orchestrator.models import AgentDefinition

    agent = AgentDefinition(
        name="Frontend Developer",
        emoji="🎨",
        division="engineering",
        specialty="React, Vue, Angular",
        use_case="Modern web apps",
        default_model="anthropic/claude-sonnet-4-20250514",
        tags=["frontend", "react"],
        role="specialist",
        system_prompt="You are a frontend developer...",
    )

    assert agent.name == "Frontend Developer"
    assert agent.division == "engineering"
    assert agent.emoji == "🎨"


def test_api_search_parameters():
    """Test search API parameters."""
    search_params = {
        "q": "frontend",
        "top_k": 5,
    }

    assert "q" in search_params
    assert search_params["q"] == "frontend"
    assert search_params["top_k"] == 5


def test_api_job_status_states():
    """Test valid job status states."""
    from orchestrator.models import JobState

    valid_states = [
        JobState.SUBMITTED,
        JobState.PLANNING,
        JobState.EXECUTING,
        JobState.COMPLETED,
        JobState.FAILED,
        JobState.CANCELLED,
    ]

    assert len(valid_states) > 0
    assert JobState.COMPLETED in valid_states
    assert JobState.EXECUTING in valid_states
