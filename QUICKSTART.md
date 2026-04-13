# Vishnu Multi-Agent Orchestrator — Quick Start Guide

## Status
🟢 **LIVE** — Running on http://127.0.0.1:8888

## Start the App
```bash
cd /home/user/Vishnu
BLACKBOX_API_KEY="sk-AeiVFA4s51WsQGyHVqyZfA" python3 /tmp/orchestrator_app.py
```

## Check Health
```bash
curl http://127.0.0.1:8888/health
```

## View Roster (162 agents)
```bash
curl http://127.0.0.1:8888/api/orchestrator/roster | jq
```

## Get Agent Details
```bash
curl 'http://127.0.0.1:8888/api/orchestrator/roster/Frontend%20Developer' | jq
```

## Submit a Job
```bash
curl -X POST http://127.0.0.1:8888/api/orchestrator/jobs \
  -H 'Content-Type: application/json' \
  -d '{
    "goal": "Build a landing page",
    "context": {"brand": "TechCorp"}
  }' | jq
```

## Available Agents by Division
- **engineering** (26): Frontend Dev, Backend Architect, DevOps Engineer, etc.
- **design** (8): UI Designer, UX Researcher, etc.
- **marketing** (30+): Content Creator, SEO Specialist, etc.
- **sales** (8): Sales Strategist, Account Manager, etc.
- **testing** (8): QA Engineer, Test Automation Engineer, etc.
- **product** (5): Product Manager, Product Designer, etc.
- **support** (6): Customer Support Agent, Technical Support, etc.
- **specialized** (30+): Data Scientist, AI Engineer, etc.

## Configuration
- **Primary LLM**: Blackbox AI Minimax 2.5 (`blackbox/minimax-2.5`)
- **Env Var**: `BLACKBOX_API_KEY`
- **Config File**: `agency_roster/_defaults.yaml`
- **Agent Files**: `agency_roster/*/` (162 markdown files)

## Tests (88 tests, all passing)
```bash
BLACKBOX_API_KEY="sk-AeiVFA4s51WsQGyHVqyZfA" pytest tests/orchestrator/ -v
```

## Stop Server
```bash
kill $(cat /tmp/orchestrator.pid)
```

## File Locations
- App Source: `/tmp/orchestrator_app.py`
- Config: `/home/user/Vishnu/agency_roster/_defaults.yaml`
- Agents: `/home/user/Vishnu/agency_roster/`
- Tests: `/home/user/Vishnu/tests/orchestrator/`

---
**System**: Vishnu Multi-Agent Orchestration Framework  
**Status**: ✅ Operational  
**API**: http://127.0.0.1:8888  
**Updated**: 2026-04-13
