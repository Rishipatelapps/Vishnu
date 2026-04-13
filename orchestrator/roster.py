"""
Agent Roster — loader and registry for agency_roster/ Markdown definitions.

Parses YAML frontmatter + Markdown body from each agent .md file into
AgentDefinition objects. Provides search, filtering, and summary generation
for the orchestrator Manager.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Dict, List, Optional

import yaml

from orchestrator.models import AgentDefinition

logger = logging.getLogger(__name__)

# Default roster directory relative to project root
_DEFAULT_ROSTER_DIR = Path(__file__).parent.parent / "agency_roster"

# Frontmatter regex: matches --- ... --- at the start of a file
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _parse_agent_file(filepath: Path) -> Optional[AgentDefinition]:
    """Parse a single agent Markdown file into an AgentDefinition."""
    try:
        content = filepath.read_text(encoding="utf-8")
    except Exception as e:
        logger.warning("Failed to read agent file %s: %s", filepath, e)
        return None

    # Extract YAML frontmatter
    frontmatter: Dict = {}
    body = content
    match = _FRONTMATTER_RE.match(content)
    if match:
        try:
            frontmatter = yaml.safe_load(match.group(1)) or {}
        except yaml.YAMLError as e:
            logger.warning("Bad YAML frontmatter in %s: %s", filepath, e)
        body = content[match.end():]

    # Derive division from parent directory name
    division = filepath.parent.name

    # Build AgentDefinition from frontmatter + body
    return AgentDefinition(
        name=frontmatter.get("name", filepath.stem.replace("_", " ").title()),
        emoji=frontmatter.get("emoji", "🤖"),
        division=frontmatter.get("division", division),
        specialty=frontmatter.get("specialty", ""),
        use_case=frontmatter.get("use_case", ""),
        default_model=frontmatter.get(
            "default_model", "anthropic/claude-sonnet-4-20250514"
        ),
        tags=frontmatter.get("tags", []),
        system_prompt=body.strip(),
        source_file=str(filepath),
        role=frontmatter.get("role", "worker"),
    )


class AgentRoster:
    """Registry of all available agent definitions loaded from agency_roster/."""

    def __init__(self) -> None:
        self._agents: Dict[str, AgentDefinition] = {}  # keyed by normalized name
        self._by_division: Dict[str, List[AgentDefinition]] = {}

    @staticmethod
    def _normalize_name(name: str) -> str:
        """Normalize agent name for lookup (lowercase, stripped)."""
        return name.lower().strip()

    def load(self, roster_dir: Optional[Path] = None) -> int:
        """Load all agent .md files from roster_dir. Returns count loaded."""
        roster_dir = Path(roster_dir or _DEFAULT_ROSTER_DIR)
        if not roster_dir.is_dir():
            logger.warning("Roster directory not found: %s", roster_dir)
            return 0

        count = 0
        for md_file in sorted(roster_dir.rglob("*.md")):
            # Skip _defaults.yaml and other non-agent files
            if md_file.name.startswith("_"):
                continue
            agent = _parse_agent_file(md_file)
            if agent:
                key = self._normalize_name(agent.name)
                self._agents[key] = agent
                self._by_division.setdefault(agent.division, []).append(agent)
                count += 1
                logger.debug("Loaded agent: %s (%s)", agent.name, agent.division)

        logger.info("Loaded %d agents from %s", count, roster_dir)
        return count

    def get_agent(self, name: str) -> Optional[AgentDefinition]:
        """Get an agent by exact name (case-insensitive)."""
        return self._agents.get(self._normalize_name(name))

    def search(self, query: str, top_k: int = 10) -> List[AgentDefinition]:
        """Search agents by relevance to a query string."""
        scored = [
            (agent, agent.match_score(query))
            for agent in self._agents.values()
        ]
        scored.sort(key=lambda x: x[1], reverse=True)
        return [agent for agent, score in scored[:top_k] if score > 0.0]

    def list_division(self, division: str) -> List[AgentDefinition]:
        """List all agents in a specific division."""
        return self._by_division.get(division, [])

    def list_all(self) -> List[AgentDefinition]:
        """List all loaded agents."""
        return list(self._agents.values())

    def list_divisions(self) -> List[str]:
        """List all division names."""
        return sorted(self._by_division.keys())

    def get_roster_summary(self) -> str:
        """Generate a compact text summary for the Manager's system prompt context."""
        lines = []
        for division in sorted(self._by_division.keys()):
            agents = self._by_division[division]
            div_display = division.replace("_", " ").title()
            lines.append(f"\n## {div_display} Division ({len(agents)} agents)")
            for agent in agents:
                use = f" | Use: {agent.use_case}" if agent.use_case else ""
                lines.append(f"  - {agent.emoji} {agent.name}: {agent.specialty}{use}")
        return "\n".join(lines)

    def __len__(self) -> int:
        return len(self._agents)

    def __contains__(self, name: str) -> bool:
        return self._normalize_name(name) in self._agents
