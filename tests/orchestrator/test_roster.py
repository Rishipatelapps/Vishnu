"""Tests for orchestrator.roster module."""

import pytest

from orchestrator.roster import AgentRoster
from orchestrator.models import AgentDefinition


def test_roster_load_from_directory(temp_roster_dir):
    """Test loading roster from directory with agent markdown files."""
    roster = AgentRoster()
    count = roster.load(temp_roster_dir)

    assert count == 3, "Should load 3 agents from temp directory"
    assert len(roster) == 3


def test_roster_get_agent_by_name(roster):
    """Test retrieving an agent by exact name."""
    agent = roster.get_agent("Frontend Developer")

    assert agent is not None
    assert agent.name == "Frontend Developer"
    assert agent.emoji == "🎨"
    assert agent.division == "engineering"


def test_roster_get_agent_not_found(roster):
    """Test retrieving a non-existent agent returns None."""
    agent = roster.get_agent("Nonexistent Agent")
    assert agent is None


def test_roster_search_by_specialty(roster):
    """Test searching agents by specialty keywords."""
    results = roster.search("react", top_k=10)

    assert len(results) > 0
    assert "Frontend Developer" in [a.name for a in results]


def test_roster_search_by_use_case(roster):
    """Test searching agents by use case."""
    results = roster.search("web apps", top_k=10)

    assert len(results) > 0
    # Should find Frontend Developer which has "Modern web apps" in use_case


def test_roster_search_top_k_limit(roster):
    """Test that search respects top_k limit."""
    results = roster.search("engineering", top_k=1)
    assert len(results) <= 1


def test_roster_search_empty_results(roster):
    """Test search with no matching agents."""
    results = roster.search("xyz_nonexistent_term", top_k=10)
    assert len(results) == 0


def test_roster_list_division(roster):
    """Test listing agents in a specific division."""
    engineering_agents = roster.list_division("engineering")

    assert len(engineering_agents) == 2
    assert all(a.division == "engineering" for a in engineering_agents)


def test_roster_list_division_not_found(roster):
    """Test listing agents in non-existent division."""
    agents = roster.list_division("nonexistent_division")
    assert len(agents) == 0


def test_roster_list_all(roster):
    """Test listing all agents."""
    all_agents = roster.list_all()
    assert len(all_agents) == 3


def test_roster_list_divisions(roster):
    """Test getting all available divisions."""
    divisions = roster.list_divisions()

    assert "engineering" in divisions
    assert "design" in divisions


def test_roster_agent_has_system_prompt(roster):
    """Test that loaded agents have system prompt from markdown."""
    agent = roster.get_agent("Frontend Developer")

    assert agent.system_prompt is not None
    assert len(agent.system_prompt) > 0
    assert "Identity & Personality" in agent.system_prompt


def test_roster_agent_has_metadata(roster):
    """Test that agent metadata is properly parsed."""
    agent = roster.get_agent("Backend Architect")

    assert agent.name == "Backend Architect"
    assert agent.emoji == "🏗️"
    assert agent.division == "engineering"
    assert agent.specialty == "System design, databases, APIs"
    assert agent.use_case == "Scalable backend systems, microservices"
    assert agent.default_model == "anthropic/claude-opus-4-20250514"
    assert "backend" in agent.tags
    assert "architecture" in agent.tags


def test_roster_get_roster_summary(roster):
    """Test generating a roster summary for context injection."""
    summary = roster.get_roster_summary()

    assert len(summary) > 0
    assert "Frontend Developer" in summary
    assert "Backend Architect" in summary
    assert "Engineering" in summary or "engineering" in summary.lower()
    assert "Design" in summary or "design" in summary.lower()


def test_roster_agent_match_score(roster):
    """Test agent relevance scoring."""
    frontend_agent = roster.get_agent("Frontend Developer")

    # Higher score for exact match
    score_frontend = frontend_agent.match_score("react frontend")
    score_random = frontend_agent.match_score("xyz nonexistent")

    assert score_frontend > score_random


def test_roster_agent_division_filtering(roster):
    """Test filtering agents by division."""
    engineering = roster.list_division("engineering")
    design = roster.list_division("design")

    assert all(a.division == "engineering" for a in engineering)
    assert all(a.division == "design" for a in design)
    assert len(engineering) == 2
    assert len(design) == 1


def test_roster_len_operator(roster):
    """Test using len() operator on roster."""
    assert len(roster) == 3


def test_roster_get_all_returns_list(roster):
    """Test that list_all returns a list of agents."""
    agents = roster.list_all()
    assert len(agents) == 3
    assert all(isinstance(a, AgentDefinition) for a in agents)
