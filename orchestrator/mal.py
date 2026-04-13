"""
Model Abstraction Layer (MAL)

Centralizes LLM provider resolution for all agent executions. Wraps
the existing credential_pool and auth infrastructure to provide a
single point of contact for all LLM communication configuration.

Resolution priority:
  1. Runtime override (from Job or GUI)
  2. Step-level override (from WorkflowStep.model_override)
  3. Agent default (from AgentDefinition.default_model)
  4. Division default (from _defaults.yaml)
  5. Global default (from _defaults.yaml or environment)
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from orchestrator.models import AgentDefinition, LLMConfig

logger = logging.getLogger(__name__)

# Map of provider name -> env var for API key
PROVIDER_KEY_ENV_VARS: Dict[str, List[str]] = {
    "anthropic": ["ANTHROPIC_API_KEY"],
    "openai": ["OPENAI_API_KEY"],
    "openrouter": ["OPENROUTER_API_KEY"],
    "google": ["GEMINI_API_KEY", "GOOGLE_API_KEY"],
    "gemini": ["GEMINI_API_KEY", "GOOGLE_API_KEY"],
    "mistral": ["MISTRAL_API_KEY"],
    "deepseek": ["DEEPSEEK_API_KEY"],
    "groq": ["GROQ_API_KEY"],
    "together": ["TOGETHER_API_KEY"],
    "fireworks": ["FIREWORKS_API_KEY"],
    "cohere": ["COHERE_API_KEY"],
    "xai": ["XAI_API_KEY"],
}

# Default base URLs per provider
PROVIDER_BASE_URLS: Dict[str, str] = {
    "anthropic": "https://api.anthropic.com/v1",
    "openai": "https://api.openai.com/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "google": "https://generativelanguage.googleapis.com/v1beta",
    "gemini": "https://generativelanguage.googleapis.com/v1beta",
    "mistral": "https://api.mistral.ai/v1",
    "deepseek": "https://api.deepseek.com/v1",
    "groq": "https://api.groq.com/openai/v1",
    "together": "https://api.together.xyz/v1",
    "fireworks": "https://api.fireworks.ai/inference/v1",
    "cohere": "https://api.cohere.ai/v1",
    "xai": "https://api.x.ai/v1",
}

# Defaults config file
_DEFAULTS_FILE = Path(__file__).parent.parent / "agency_roster" / "_defaults.yaml"


def _parse_provider_model(model_string: str) -> tuple[str, str]:
    """Parse 'provider/model' format. Falls back to openrouter if no slash."""
    if "/" in model_string:
        parts = model_string.split("/", 1)
        return parts[0], model_string
    return "openrouter", model_string


class ModelAbstractionLayer:
    """Resolves LLM configuration for any agent execution."""

    def __init__(self, defaults_file: Optional[Path] = None):
        self._defaults: Dict[str, Any] = {}
        self._load_defaults(defaults_file or _DEFAULTS_FILE)

    def _load_defaults(self, filepath: Path) -> None:
        """Load _defaults.yaml for global and division-level model defaults."""
        if not filepath.exists():
            logger.debug("No defaults file at %s, using built-in defaults", filepath)
            return
        try:
            with open(filepath, encoding="utf-8") as f:
                self._defaults = yaml.safe_load(f) or {}
            logger.info("Loaded MAL defaults from %s", filepath)
        except Exception as e:
            logger.warning("Failed to load MAL defaults: %s", e)

    def _get_division_default(self, division: str) -> Optional[str]:
        """Get the default model for a division from _defaults.yaml."""
        divisions = self._defaults.get("divisions", {})
        return divisions.get(division, {}).get("default_model")

    def _get_global_default(self) -> str:
        """Get the global default model."""
        return self._defaults.get(
            "global_default_model",
            os.environ.get("ORCHESTRATOR_DEFAULT_MODEL", "anthropic/claude-sonnet-4-20250514"),
        )

    def _resolve_api_key(self, provider: str) -> str:
        """Resolve API key for a provider from environment."""
        # First check provider-specific env vars
        env_vars = PROVIDER_KEY_ENV_VARS.get(provider, [])
        for var in env_vars:
            key = os.environ.get(var)
            if key:
                return key

        # Fall back to credential_pool if available
        try:
            from agent.credential_pool import CredentialPool
            pool = CredentialPool.get_instance()
            cred = pool.acquire(provider)
            if cred and hasattr(cred, "api_key"):
                return cred.api_key
        except Exception:
            pass

        logger.warning("No API key found for provider: %s", provider)
        return ""

    def resolve_config(
        self,
        agent_def: AgentDefinition,
        step_override: Optional[str] = None,
        job_override: Optional[str] = None,
    ) -> LLMConfig:
        """Resolve the full LLM config for an agent execution.

        Priority: job_override > step_override > agent_default > division_default > global
        """
        # Determine model string
        model_string = (
            job_override
            or step_override
            or agent_def.default_model
            or self._get_division_default(agent_def.division)
            or self._get_global_default()
        )

        provider, full_model = _parse_provider_model(model_string)
        api_key = self._resolve_api_key(provider)
        base_url = PROVIDER_BASE_URLS.get(provider, "")

        # For OpenRouter models, use the full provider/model as the model name
        # For direct API calls, strip the provider prefix
        if provider == "openrouter":
            model_id = full_model
        else:
            model_id = full_model.split("/", 1)[-1] if "/" in full_model else full_model

        return LLMConfig(
            provider=provider,
            model=model_id,
            base_url=base_url,
            api_key=api_key,
            api_mode=None,
            max_tokens=None,
        )

    def list_available_providers(self) -> List[str]:
        """List providers that have API keys configured."""
        available = []
        for provider, env_vars in PROVIDER_KEY_ENV_VARS.items():
            for var in env_vars:
                if os.environ.get(var):
                    available.append(provider)
                    break
        return available

    def validate_key(self, provider: str) -> bool:
        """Check if a provider has a valid API key configured."""
        return bool(self._resolve_api_key(provider))
