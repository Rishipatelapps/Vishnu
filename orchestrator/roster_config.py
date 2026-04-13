"""
Roster Configuration — loads and manages _defaults.yaml for model assignments.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

logger = logging.getLogger(__name__)

_DEFAULTS_PATH = Path(__file__).parent.parent / "agency_roster" / "_defaults.yaml"


def load_roster_defaults(path: Optional[Path] = None) -> Dict[str, Any]:
    """Load the roster defaults configuration."""
    filepath = path or _DEFAULTS_PATH
    if not filepath.exists():
        return {}
    try:
        with open(filepath, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        logger.warning("Failed to load roster defaults: %s", e)
        return {}


def get_division_model(division: str, defaults: Optional[Dict] = None) -> Optional[str]:
    """Get the default model for a specific division."""
    if defaults is None:
        defaults = load_roster_defaults()
    return defaults.get("divisions", {}).get(division, {}).get("default_model")


def get_global_model(defaults: Optional[Dict] = None) -> str:
    """Get the global default model."""
    if defaults is None:
        defaults = load_roster_defaults()
    return defaults.get("global_default_model", "anthropic/claude-sonnet-4-20250514")
