"""Shared fixtures and utilities for orchestrator tests."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from orchestrator.models import AgentDefinition, LLMConfig
from orchestrator.roster import AgentRoster
from orchestrator.mal import ModelAbstractionLayer
from orchestrator.status import JobTracker


@pytest.fixture
def temp_roster_dir():
    """Create a temporary directory with sample agent definitions."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)

        # Create engineering division
        (tmppath / "engineering").mkdir()
        (tmppath / "engineering" / "frontend_developer.md").write_text(
            """---
name: "Frontend Developer"
emoji: "🎨"
division: "engineering"
specialty: "React, Vue, Angular, UI implementation"
use_case: "Modern web apps, responsive design"
default_model: "anthropic/claude-sonnet-4-20250514"
tags: ["frontend", "react", "ui"]
role: "specialist"
---

# 🎨 Frontend Developer

## Identity & Personality
You are a senior frontend developer with expertise in modern web frameworks.

## Core Mission
Build beautiful, performant, accessible web interfaces.

## Critical Rules
1. Always write semantic HTML
2. Optimize for performance
3. Test accessibility

## Workflow
1. Analyze requirements
2. Design component structure
3. Implement with best practices
4. Test thoroughly
"""
        )

        (tmppath / "engineering" / "backend_architect.md").write_text(
            """---
name: "Backend Architect"
emoji: "🏗️"
division: "engineering"
specialty: "System design, databases, APIs"
use_case: "Scalable backend systems, microservices"
default_model: "anthropic/claude-opus-4-20250514"
tags: ["backend", "architecture", "database"]
role: "specialist"
---

# 🏗️ Backend Architect

## Identity & Personality
You are a backend architect with deep expertise in distributed systems.

## Core Mission
Design scalable, reliable backend infrastructure.

## Critical Rules
1. Design for scalability
2. Plan for failure
3. Document thoroughly

## Workflow
1. Understand requirements
2. Design architecture
3. Plan database schema
4. Define API contracts
"""
        )

        # Create design division
        (tmppath / "design").mkdir()
        (tmppath / "design" / "ui_designer.md").write_text(
            """---
name: "UI Designer"
emoji: "✨"
division: "design"
specialty: "UI design, prototyping, design systems"
use_case: "User interfaces, design systems"
default_model: "anthropic/claude-sonnet-4-20250514"
tags: ["design", "ui", "prototyping"]
role: "specialist"
---

# ✨ UI Designer

## Identity & Personality
You are a talented UI designer with a keen eye for detail.

## Core Mission
Create beautiful, intuitive user interfaces.

## Critical Rules
1. Design with purpose
2. Consider accessibility
3. Maintain consistency

## Workflow
1. Understand user needs
2. Sketch concepts
3. Create high-fidelity designs
4. Document design system
"""
        )

        yield tmppath


@pytest.fixture
def sample_agent_def():
    """Create a sample agent definition."""
    return AgentDefinition(
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


@pytest.fixture
def sample_llm_config():
    """Create a sample LLM configuration."""
    return LLMConfig(
        provider="anthropic",
        model="claude-sonnet-4-20250514",
        base_url="https://api.anthropic.com",
        api_key="test-key-123",
        api_mode=None,
        max_tokens=4096,
    )


@pytest.fixture
def roster(temp_roster_dir):
    """Create a roster loaded with sample agents."""
    r = AgentRoster()
    r.load(temp_roster_dir)
    return r


@pytest.fixture
def mal():
    """Create a ModelAbstractionLayer instance."""
    with patch.dict(
        "os.environ",
        {
            "ANTHROPIC_API_KEY": "test-anthropic-key",
            "OPENAI_API_KEY": "test-openai-key",
        },
    ):
        return ModelAbstractionLayer()


@pytest.fixture
def tracker():
    """Create a JobTracker instance."""
    return JobTracker()


@pytest.fixture
def mock_worker_agent():
    """Create a mock WorkerAgent."""
    from orchestrator.models import WorkerResult, StepStatus

    agent = MagicMock()
    agent.execute.return_value = WorkerResult(
        status=StepStatus.COMPLETED,
        output="Mock output",
        error=None,
        duration_seconds=1.5,
        tokens_used=150,
        model_used="claude-sonnet-4-20250514",
    )
    return agent


@pytest.fixture
def mock_orchestrator_manager():
    """Create a mock OrchestratorManager."""
    manager = MagicMock()
    manager.roster = MagicMock(spec=AgentRoster)
    manager.mal = MagicMock(spec=ModelAbstractionLayer)
    return manager
