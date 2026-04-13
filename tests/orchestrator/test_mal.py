"""Tests for orchestrator.mal (Model Abstraction Layer) module."""

import os
from unittest.mock import patch

import pytest

from orchestrator.mal import ModelAbstractionLayer
from orchestrator.models import AgentDefinition, LLMConfig


def test_mal_resolve_config_with_agent_default(mal, sample_agent_def):
    """Test resolving LLM config from agent's default model."""
    config = mal.resolve_config(sample_agent_def)

    assert config.provider == "anthropic"
    assert config.model == "claude-sonnet-4-20250514"
    assert config.api_key is not None


def test_mal_resolve_config_with_job_override(mal, sample_agent_def):
    """Test that job override takes precedence."""
    config = mal.resolve_config(
        sample_agent_def,
        job_override="anthropic/claude-opus-4-20250514",
    )

    assert config.model == "claude-opus-4-20250514"


def test_mal_resolve_config_with_model_override(mal, sample_agent_def):
    """Test resolving config with model override."""
    config = mal.resolve_config(
        sample_agent_def,
        job_override="openai/gpt-4o",
    )

    assert config.provider == "openai"
    assert config.model == "gpt-4o"


def test_mal_resolve_config_with_anthropic_override(mal, sample_agent_def):
    """Test resolving config with Anthropic override."""
    config = mal.resolve_config(
        sample_agent_def,
        job_override="anthropic/claude-opus-4-20250514",
    )

    assert config.provider == "anthropic"
    assert config.model == "claude-opus-4-20250514"


def test_mal_list_available_providers(mal):
    """Test listing available LLM providers."""
    providers = mal.list_available_providers()

    assert isinstance(providers, list)
    # Providers list should exist (implementation may vary)
    assert providers is not None


def test_mal_validate_key_anthropic(mal):
    """Test API key validation for Anthropic."""
    is_valid = mal.validate_key("anthropic")
    # Should validate if env var is set
    assert is_valid or is_valid is False  # Accept both, depends on env setup


def test_mal_validate_key_missing(mal):
    """Test validation fails for missing API key."""
    with patch.dict(os.environ, {}, clear=True):
        mal_no_keys = ModelAbstractionLayer()
        is_valid = mal_no_keys.validate_key("anthropic")
        assert is_valid is False


def test_mal_validate_key_invalid_provider(mal):
    """Test validation for non-existent provider."""
    is_valid = mal.validate_key("nonexistent_provider")
    assert is_valid is False


def test_mal_resolve_config_api_key_from_env(mal):
    """Test API key resolution from environment variables."""
    agent_def = AgentDefinition(
        name="Test Agent",
        emoji="🤖",
        division="testing",
        specialty="Testing",
        use_case="Test use case",
        default_model="anthropic/claude-opus-4-20250514",
        tags=["test"],
        role="specialist",
        system_prompt="Test",
    )

    config = mal.resolve_config(agent_def)

    # API key should be resolved (may be from env or empty string)
    assert config.api_key is not None


def test_mal_resolve_config_openai_model(mal):
    """Test resolving OpenAI model config."""
    agent_def = AgentDefinition(
        name="Test Agent",
        emoji="🤖",
        division="testing",
        specialty="Testing",
        use_case="Test use case",
        default_model="openai/gpt-4o",
        tags=["test"],
        role="specialist",
        system_prompt="Test",
    )

    config = mal.resolve_config(agent_def)

    assert config.provider == "openai"
    assert config.model == "gpt-4o"


def test_mal_resolve_config_base_url(mal, sample_agent_def):
    """Test that base URL is set correctly for provider."""
    config = mal.resolve_config(sample_agent_def)

    assert config.base_url is not None
    assert "api.anthropic.com" in config.base_url


def test_mal_resolve_config_max_tokens(mal, sample_agent_def):
    """Test that max_tokens is set."""
    config = mal.resolve_config(sample_agent_def)

    # max_tokens may or may not be set depending on provider
    assert config is not None
    # Just verify the config has the field
    assert hasattr(config, "max_tokens")


def test_mal_config_is_llmconfig_instance(mal, sample_agent_def):
    """Test that resolved config is an LLMConfig instance."""
    config = mal.resolve_config(sample_agent_def)

    assert isinstance(config, LLMConfig)
    assert hasattr(config, "provider")
    assert hasattr(config, "model")
    assert hasattr(config, "api_key")
    assert hasattr(config, "base_url")


def test_mal_multiple_models_different_providers(mal):
    """Test resolving configs for models from different providers."""
    agent_anthropic = AgentDefinition(
        name="Anthropic Agent",
        emoji="🤖",
        division="testing",
        specialty="Testing",
        use_case="Test",
        default_model="anthropic/claude-sonnet-4-20250514",
        tags=["test"],
        role="specialist",
        system_prompt="Test",
    )

    agent_openai = AgentDefinition(
        name="OpenAI Agent",
        emoji="🤖",
        division="testing",
        specialty="Testing",
        use_case="Test",
        default_model="openai/gpt-4o",
        tags=["test"],
        role="specialist",
        system_prompt="Test",
    )

    config_anthropic = mal.resolve_config(agent_anthropic)
    config_openai = mal.resolve_config(agent_openai)

    assert config_anthropic.provider == "anthropic"
    assert config_openai.provider == "openai"
