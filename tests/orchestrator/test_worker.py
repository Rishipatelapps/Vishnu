"""Tests for orchestrator.worker module."""

import pytest

from orchestrator.models import AgentDefinition, LLMConfig, StepStatus, WorkerResult


@pytest.fixture
def test_agent_def():
    """Create a test agent definition."""
    return AgentDefinition(
        name="Test Agent",
        emoji="🤖",
        division="testing",
        specialty="Testing and validation",
        use_case="For unit tests",
        default_model="anthropic/claude-sonnet-4-20250514",
        tags=["test", "unit"],
        role="specialist",
        system_prompt="You are a test agent for unit testing purposes.",
    )


@pytest.fixture
def test_llm_config():
    """Create a test LLM configuration."""
    return LLMConfig(
        provider="anthropic",
        model="claude-sonnet-4-20250514",
        base_url="https://api.anthropic.com",
        api_key="test-key-123",
        api_mode=None,
        max_tokens=4096,
    )


def test_agent_definition_structure(test_agent_def):
    """Test that AgentDefinition has all required fields."""
    assert test_agent_def.name == "Test Agent"
    assert test_agent_def.emoji == "🤖"
    assert test_agent_def.division == "testing"
    assert test_agent_def.specialty is not None
    assert test_agent_def.use_case is not None
    assert test_agent_def.default_model is not None
    assert test_agent_def.system_prompt is not None


def test_llm_config_structure(test_llm_config):
    """Test that LLMConfig has all required fields."""
    assert test_llm_config.provider == "anthropic"
    assert test_llm_config.model == "claude-sonnet-4-20250514"
    assert test_llm_config.base_url is not None
    assert test_llm_config.api_key == "test-key-123"
    assert test_llm_config.max_tokens == 4096


def test_worker_result_creation():
    """Test creating a WorkerResult."""
    result = WorkerResult(
        status=StepStatus.COMPLETED,
        output="Test output",
        error=None,
        duration_seconds=1.5,
        tokens_used=100,
        model_used="test-model",
    )

    assert result.status == StepStatus.COMPLETED
    assert result.output == "Test output"
    assert result.error is None
    assert result.duration_seconds == 1.5
    assert result.tokens_used == 100
    assert result.model_used == "test-model"


def test_worker_result_failure():
    """Test creating a failed WorkerResult."""
    result = WorkerResult(
        status=StepStatus.FAILED,
        output="",
        error="Something went wrong",
        duration_seconds=0.5,
        tokens_used=0,
        model_used="test-model",
    )

    assert result.status == StepStatus.FAILED
    assert result.error == "Something went wrong"


def test_worker_result_pending():
    """Test creating a pending WorkerResult."""
    result = WorkerResult(
        status=StepStatus.PENDING,
        output="",
        error=None,
        duration_seconds=0.0,
        tokens_used=0,
        model_used="pending-model",
    )

    assert result.status == StepStatus.PENDING
    assert result.duration_seconds == 0.0


def test_agent_def_has_system_prompt(test_agent_def):
    """Test that agent definition system prompt is set."""
    assert len(test_agent_def.system_prompt) > 0


def test_agent_def_tags(test_agent_def):
    """Test agent definition tags."""
    assert len(test_agent_def.tags) > 0
    assert "test" in test_agent_def.tags


def test_llm_config_has_api_key(test_llm_config):
    """Test that LLM config has API key."""
    assert len(test_llm_config.api_key) > 0


def test_llm_config_base_url_format(test_llm_config):
    """Test that base URL is properly formatted."""
    assert test_llm_config.base_url.startswith("https://")


def test_step_status_enum():
    """Test StepStatus enum values."""
    assert StepStatus.PENDING.value == "pending"
    assert StepStatus.RUNNING.value == "running"
    assert StepStatus.COMPLETED.value == "completed"
    assert StepStatus.FAILED.value == "failed"


def test_worker_result_status_options():
    """Test that WorkerResult can be created with different statuses."""
    statuses = [StepStatus.PENDING, StepStatus.COMPLETED, StepStatus.FAILED]

    for status in statuses:
        result = WorkerResult(
            status=status,
            output="",
            error=None,
            duration_seconds=0.0,
            tokens_used=0,
            model_used="model",
        )
        assert result.status == status
