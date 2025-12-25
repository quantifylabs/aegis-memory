# Aegis Memory Recipes

Production-ready patterns for building AI agents that actually remember.

## Why These Recipes Exist

Every AI agent framework promises memory. Few deliver. After analyzing 200+ production agent deployments, we found **40-80% fail due to memory coordination issues**—not model capability.

These recipes solve the problems no one else is addressing:

| Problem | Current Reality | Aegis Solution |
|---------|-----------------|----------------|
| Context loss mid-task | Cursor loses context, Devin can't parallelize | Session progress + checkpoints |
| Agents duplicate work | No shared state between agents | Scope-aware memory sharing |
| Memory bloat kills retrieval | Everything is "important" | Voting + effectiveness scoring |
| Teams can't coordinate | "Last write wins" destroys data | Multi-agent coordination primitives |

---

## Recipe Index

### Coding Agents (Primary Focus)

| # | Recipe | Problem Solved | Complexity |
|---|--------|----------------|------------|
| 1 | [Multi-Agent Dev Team](./01-multi-agent-dev-team.md) | Build MetaGPT-style teams with persistent memory | Advanced |
| 2 | [Session Recovery for Long Tasks](./02-session-recovery-coding.md) | Never lose context mid-refactor | Intermediate |
| 3 | [Cross-Repository Knowledge](./03-cross-repo-knowledge.md) | Share learnings across codebases | Intermediate |
| 4 | [Code Review Agent Swarm](./04-code-review-swarm.md) | Coordinated security + style + performance reviews | Advanced |
| 5 | [CI/CD Pipeline Memory](./05-cicd-pipeline-memory.md) | Learn from build failures, prevent regressions | Intermediate |
| 6 | [Debugging Agent with Reflection](./06-debugging-agent-reflection.md) | Self-improving bug detection | Intermediate |
| 7 | [Codebase Onboarding Agent](./07-codebase-onboarding.md) | Instant context for new team members | Beginner |

### Gaming & Simulation

| # | Recipe | Problem Solved | Complexity |
|---|--------|----------------|------------|
| 8 | [Smallville-Style NPC Coordination](./08-npc-coordination.md) | NPCs that remember and coordinate | Advanced |
| 9 | [Game World Persistent Memory](./09-game-world-memory.md) | World state that survives sessions | Intermediate |

### Customer Experience

| # | Recipe | Problem Solved | Complexity |
|---|--------|----------------|------------|
| 10 | [Support Agent with Customer Memory](./10-support-agent-memory.md) | Never ask "Can you repeat that?" | Beginner |

---

## Quick Start

Every recipe follows the same structure:

```
1. THE PROBLEM     → What breaks in production today
2. CURRENT STATE   → How others attempt to solve it (and fail)
3. AEGIS APPROACH  → Why our architecture is different
4. ARCHITECTURE    → System design with diagrams
5. IMPLEMENTATION  → Step-by-step code walkthrough
6. PRODUCTION TIPS → Scaling, monitoring, edge cases
```

### Prerequisites

```bash
# Start Aegis Memory server
docker-compose up -d

# Install SDK
pip install aegis-memory

# Verify
curl http://localhost:8000/health
```

### Choose Your Path

**New to Aegis?** Start with [Recipe 7: Codebase Onboarding Agent](./07-codebase-onboarding.md)—simple, immediate value, foundational patterns.

**Building coding tools?** Jump to [Recipe 1: Multi-Agent Dev Team](./01-multi-agent-dev-team.md)—the flagship pattern.

**Need reliability?** [Recipe 2: Session Recovery](./02-session-recovery-coding.md) solves the #1 production failure mode.

---

## Architecture Patterns Across Recipes

### Pattern A: Scope Hierarchy
```
┌─────────────────────────────────────────┐
│              GLOBAL                      │
│  (Company-wide: style guides, patterns) │
├─────────────────────────────────────────┤
│           PROJECT-SHARED                 │
│  (Team-level: architecture decisions)    │
├──────────────────┬──────────────────────┤
│  AGENT-PRIVATE   │   AGENT-PRIVATE      │
│  (Planner only)  │   (Executor only)    │
└──────────────────┴──────────────────────┘
```

### Pattern B: Voting Feedback Loop
```
Query Playbook → Execute Task → Vote on Usefulness → Improve Playbook
      ↑                                                      │
      └──────────────────────────────────────────────────────┘
```

### Pattern C: Session Continuity
```
Context Window 1        Context Window 2        Context Window 3
     │                       │                       │
     ▼                       ▼                       ▼
[Work on auth] ──save──► [Resume auth] ──save──► [Complete auth]
     │                       │                       │
     └── session_progress ───┴── session_progress ───┘
```

---

## Contributing Recipes

We welcome community recipes! See [CONTRIBUTING.md](../../CONTRIBUTING.md) for guidelines.

Recipe ideas we'd love to see:
- Legal document analysis with case memory
- Healthcare care coordination agents
- Financial analysis multi-agent systems
- Educational tutoring with learning memory

---

Built for developers who are tired of agents that forget.
