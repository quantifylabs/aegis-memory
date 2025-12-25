# Recipe 3: Cross-Repository Knowledge Sharing

**Learn once, apply everywhere. Stop re-discovering the same patterns across codebases.**

| Metric | Value |
|--------|-------|
| Complexity | Intermediate |
| Time to Build | 1-2 hours |
| Key Patterns | Global scope, Playbook queries, Memory voting |

---

## The Problem

Your AI coding assistant helps you build a pagination system in Project A:

```python
# Project A: Learned the hard way
# ✗ range(10) misses pages → ✓ while True with break
# ✗ offset pagination on large tables → ✓ cursor-based
# ✗ no rate limiting → ✓ exponential backoff
```

Next week, you start Project B. Same assistant. Same pagination task.

**It makes all the same mistakes again.**

Every codebase is an island. Your agents learn nothing from past projects. The pattern you spent hours debugging? Gone. The edge case that caused production issues? Forgotten.

---

## Current Solutions (And Why They Fail)

### Project-Specific RAG
- **Approach**: Index each codebase separately
- **Fails because**: Knowledge doesn't transfer. Project A's learnings don't help Project B.

### Shared Vector Database
- **Approach**: One big index across all projects
- **Fails because**: Context pollution. Project A's Django patterns contaminate Project B's FastAPI queries.

### Fine-Tuning
- **Approach**: Train on your codebase patterns
- **Fails because**: Expensive, slow iteration, can't capture recent learnings.

### Global Prompt Engineering
- **Approach**: Massive system prompt with all patterns
- **Fails because**: Context window limits. Can't fit everything. No prioritization.

**The core issue**: No mechanism to capture learnings at the right scope—some patterns are project-specific, some are team-wide, some are universal.

---

## The Aegis Approach

Aegis uses **scope hierarchy** with **effectiveness voting**:

```
┌─────────────────────────────────────────────────────────────────┐
│                         GLOBAL SCOPE                             │
│  "Always use cursor-based pagination for large datasets"         │
│  "Add retry logic with exponential backoff for external APIs"    │
│  Effectiveness: 0.8+ (proven across many projects)               │
├─────────────────────────────────────────────────────────────────┤
│                      TEAM/ORG SCOPE                              │
│  "Our REST APIs use camelCase for JSON keys"                     │
│  "Authentication goes through api.internal/auth"                 │
│  Effectiveness: Varies by team                                   │
├─────────────────────────────────────────────────────────────────┤
│                       PROJECT SCOPE                              │
│  "This project uses SQLAlchemy 2.0 async patterns"               │
│  "User model is in app/models/user.py"                           │
│  Effectiveness: Project-specific                                 │
└─────────────────────────────────────────────────────────────────┘
```

When an agent starts work, it queries all relevant scopes:

```python
# Agent working on Project B pagination
strategies = aegis.playbook(
    query="pagination implementation",
    agent_id="coder",
    min_effectiveness=0.3  # Only proven strategies
)

# Returns:
# [0.85] "Use cursor-based pagination for tables > 10K rows"  (GLOBAL)
# [0.72] "Our API uses 'next_cursor' field in responses"       (TEAM)
# [0.45] "This project's Cursor class is in utils/pagination"  (PROJECT)
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    KNOWLEDGE FLOW                                │
│                                                                  │
│   PROJECT A          PROJECT B          PROJECT C                │
│   ┌───────┐          ┌───────┐          ┌───────┐               │
│   │ Learn │          │ Learn │          │ Learn │               │
│   │pattern│          │pattern│          │pattern│               │
│   └───┬───┘          └───┬───┘          └───┬───┘               │
│       │                  │                  │                    │
│       ▼                  ▼                  ▼                    │
│   ┌─────────────────────────────────────────────────┐           │
│   │              VOTING & PROMOTION                  │           │
│   │  • Project learns pattern → votes "helpful"      │           │
│   │  • Multiple projects confirm → promote to TEAM   │           │
│   │  • Universal patterns → promote to GLOBAL        │           │
│   └─────────────────────────────────────────────────┘           │
│                          │                                       │
│                          ▼                                       │
│   ┌─────────────────────────────────────────────────┐           │
│   │              PLAYBOOK QUERIES                    │           │
│   │  • New project queries GLOBAL first              │           │
│   │  • Filters by min_effectiveness                  │           │
│   │  • Gets proven patterns immediately              │           │
│   └─────────────────────────────────────────────────┘           │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Implementation

### Step 1: Knowledge Extraction Agent

```python
from aegis_memory import AegisClient
from openai import OpenAI
from typing import List, Dict
import json

aegis = AegisClient(api_key="your-key", base_url="http://localhost:8000")
llm = OpenAI()

class KnowledgeExtractor:
    """Extracts reusable patterns from coding sessions."""
    
    def __init__(self, agent_id: str, project_id: str, team_id: str = "default"):
        self.agent_id = agent_id
        self.project_id = project_id
        self.team_id = team_id
    
    def extract_from_task(self, 
                          task: str, 
                          solution: str, 
                          outcome: str,
                          errors_encountered: List[str] = None) -> List[Dict]:
        """Extract learnings from a completed task."""
        
        prompt = f"""Analyze this coding task and extract reusable patterns.

TASK: {task}

SOLUTION:
{solution}

OUTCOME: {outcome}

ERRORS ENCOUNTERED:
{json.dumps(errors_encountered or [], indent=2)}

Extract patterns at three levels:
1. UNIVERSAL: Patterns that apply to any codebase (language-agnostic best practices)
2. TECH-SPECIFIC: Patterns specific to the technology stack used
3. PROJECT-SPECIFIC: Patterns unique to this project's structure

For each pattern, provide:
- content: The actionable insight (imperative, specific)
- level: "universal", "tech_specific", or "project_specific"  
- category: e.g., "pagination", "error_handling", "authentication"
- confidence: 0.0-1.0 based on how certain you are this is a good pattern

Output JSON array of patterns."""

        response = llm.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are a senior engineer extracting reusable patterns from code."},
                {"role": "user", "content": prompt}
            ]
        )
        
        patterns = json.loads(response.choices[0].message.content)
        
        # Store each pattern at appropriate scope
        stored_patterns = []
        for pattern in patterns:
            memory_id = self._store_pattern(pattern)
            stored_patterns.append({**pattern, "memory_id": memory_id})
        
        return stored_patterns
    
    def _store_pattern(self, pattern: dict) -> str:
        """Store pattern at appropriate scope."""
        
        level = pattern["level"]
        
        if level == "universal":
            scope = "global"
            namespace = "global-patterns"
        elif level == "tech_specific":
            scope = "global"  # Global but namespaced by team
            namespace = f"team-{self.team_id}"
        else:  # project_specific
            scope = "agent-shared"
            namespace = f"project-{self.project_id}"
        
        memory = aegis.add(
            content=pattern["content"],
            agent_id=self.agent_id,
            scope=scope,
            namespace=namespace,
            memory_type="strategy",
            metadata={
                "category": pattern["category"],
                "level": level,
                "initial_confidence": pattern["confidence"],
                "source_project": self.project_id,
                "source_team": self.team_id
            }
        )
        
        return memory.id
    
    def extract_from_error(self, 
                           error: str, 
                           root_cause: str,
                           fix: str) -> str:
        """Create reflection from error resolution."""
        
        content = f"""Error: {error}
Root cause: {root_cause}
Fix: {fix}"""
        
        # Reflections are always global - everyone should learn from errors
        memory = aegis.reflection(
            content=content,
            agent_id=self.agent_id,
            error_pattern=self._categorize_error(error),
            correct_approach=fix,
            scope="global"
        )
        
        return memory.id
    
    def _categorize_error(self, error: str) -> str:
        """Categorize error type."""
        error_lower = error.lower()
        
        if "timeout" in error_lower or "connection" in error_lower:
            return "network_error"
        elif "permission" in error_lower or "auth" in error_lower:
            return "auth_error"
        elif "null" in error_lower or "none" in error_lower:
            return "null_reference"
        elif "type" in error_lower:
            return "type_error"
        elif "memory" in error_lower or "oom" in error_lower:
            return "resource_error"
        else:
            return "general_error"
```

### Step 2: Cross-Project Query Agent

```python
class CrossProjectAgent:
    """Coding agent that leverages knowledge across projects."""
    
    def __init__(self, agent_id: str, project_id: str, team_id: str = "default"):
        self.agent_id = agent_id
        self.project_id = project_id
        self.team_id = team_id
        self.extractor = KnowledgeExtractor(agent_id, project_id, team_id)
    
    def get_relevant_knowledge(self, task: str) -> Dict:
        """Query knowledge at all relevant scopes."""
        
        knowledge = {
            "global_patterns": [],
            "team_patterns": [],
            "project_patterns": [],
            "reflections": []
        }
        
        # 1. Query global patterns (proven across all projects)
        global_patterns = aegis.playbook(
            query=task,
            agent_id=self.agent_id,
            namespace="global-patterns",
            min_effectiveness=0.3,
            include_types=["strategy"],
            top_k=5
        )
        knowledge["global_patterns"] = [
            {
                "content": m.content,
                "effectiveness": m.effectiveness_score,
                "category": m.metadata.get("category"),
                "id": m.id
            }
            for m in global_patterns
        ]
        
        # 2. Query team patterns
        team_patterns = aegis.playbook(
            query=task,
            agent_id=self.agent_id,
            namespace=f"team-{self.team_id}",
            min_effectiveness=0.2,
            include_types=["strategy"],
            top_k=5
        )
        knowledge["team_patterns"] = [
            {
                "content": m.content,
                "effectiveness": m.effectiveness_score,
                "category": m.metadata.get("category"),
                "id": m.id
            }
            for m in team_patterns
        ]
        
        # 3. Query project-specific patterns
        project_patterns = aegis.query(
            query=task,
            agent_id=self.agent_id,
            namespace=f"project-{self.project_id}",
            top_k=5
        )
        knowledge["project_patterns"] = [
            {
                "content": m.content,
                "category": m.metadata.get("category"),
                "id": m.id
            }
            for m in project_patterns
        ]
        
        # 4. Query relevant reflections (lessons from errors)
        reflections = aegis.playbook(
            query=task,
            agent_id=self.agent_id,
            include_types=["reflection"],
            min_effectiveness=0.0,  # All reflections are valuable
            top_k=5
        )
        knowledge["reflections"] = [
            {
                "content": m.content,
                "error_pattern": m.metadata.get("error_pattern"),
                "id": m.id
            }
            for m in reflections
        ]
        
        return knowledge
    
    def build_context_prompt(self, task: str) -> str:
        """Build prompt with cross-project knowledge."""
        
        knowledge = self.get_relevant_knowledge(task)
        
        sections = []
        
        if knowledge["global_patterns"]:
            sections.append("## Universal Best Practices (Proven Across Projects)")
            for p in knowledge["global_patterns"]:
                sections.append(f"[{p['effectiveness']:.1f}] {p['content']}")
        
        if knowledge["team_patterns"]:
            sections.append("\n## Team Standards")
            for p in knowledge["team_patterns"]:
                sections.append(f"[{p['effectiveness']:.1f}] {p['content']}")
        
        if knowledge["project_patterns"]:
            sections.append("\n## Project-Specific Context")
            for p in knowledge["project_patterns"]:
                sections.append(f"- {p['content']}")
        
        if knowledge["reflections"]:
            sections.append("\n## Lessons from Past Errors (Don't Repeat These)")
            for r in knowledge["reflections"]:
                sections.append(f"⚠️ [{r['error_pattern']}] {r['content']}")
        
        # Store which patterns we're using for later voting
        self._current_patterns = knowledge
        
        return "\n".join(sections)
    
    def execute_task(self, task: str) -> Dict:
        """Execute task with cross-project knowledge."""
        
        context = self.build_context_prompt(task)
        
        response = llm.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": f"""You are a coding agent with knowledge from past projects.

{context}

Apply these proven patterns to the task. Note which patterns you used."""},
                {"role": "user", "content": task}
            ]
        )
        
        solution = response.choices[0].message.content
        
        return {
            "solution": solution,
            "knowledge_used": self._current_patterns
        }
    
    def report_outcome(self, task: str, solution: str, success: bool, 
                       errors: List[str] = None, patterns_that_helped: List[str] = None):
        """Report task outcome, vote on patterns, extract new learnings."""
        
        # 1. Vote on patterns that were helpful/harmful
        for pattern_type in ["global_patterns", "team_patterns"]:
            for pattern in self._current_patterns.get(pattern_type, []):
                helpful = pattern["id"] in (patterns_that_helped or [])
                aegis.vote(
                    memory_id=pattern["id"],
                    vote="helpful" if helpful else ("harmful" if not success else "neutral"),
                    voter_agent_id=self.agent_id,
                    context=f"Task: {task[:100]}..."
                )
        
        # 2. Extract new patterns from this task
        new_patterns = self.extractor.extract_from_task(
            task=task,
            solution=solution,
            outcome="success" if success else "failure",
            errors_encountered=errors
        )
        
        # 3. Create reflections from errors
        if errors:
            for error in errors:
                self.extractor.extract_from_error(
                    error=error,
                    root_cause="See solution",
                    fix=solution[:500]
                )
        
        return {"new_patterns": new_patterns}
```

### Step 3: Pattern Promotion System

```python
class PatternPromoter:
    """Promotes patterns based on cross-project validation."""
    
    def __init__(self, team_id: str):
        self.team_id = team_id
    
    def analyze_for_promotion(self) -> List[Dict]:
        """Find patterns ready for promotion to higher scope."""
        
        candidates = []
        
        # Find team patterns that could be promoted to global
        team_patterns = aegis.playbook(
            query="*",  # All patterns
            agent_id="system",
            namespace=f"team-{self.team_id}",
            min_effectiveness=0.7,  # High effectiveness
            top_k=100
        )
        
        for pattern in team_patterns:
            # Check if pattern has been validated across multiple projects
            votes = self._get_vote_breakdown(pattern.id)
            
            if votes["unique_projects"] >= 3 and votes["helpful_ratio"] >= 0.75:
                candidates.append({
                    "pattern": pattern,
                    "current_scope": "team",
                    "recommended_scope": "global",
                    "evidence": votes
                })
        
        # Find project patterns that could be promoted to team
        # (Would iterate through projects similarly)
        
        return candidates
    
    def _get_vote_breakdown(self, memory_id: str) -> Dict:
        """Get voting statistics for a pattern."""
        # This would query the vote_history table
        # Simplified for example
        return {
            "helpful": 10,
            "harmful": 2,
            "helpful_ratio": 0.83,
            "unique_projects": 4,
            "unique_agents": 7
        }
    
    def promote_pattern(self, memory_id: str, to_scope: str):
        """Promote a pattern to a higher scope."""
        
        # Get original pattern
        pattern = aegis.get(memory_id)
        
        # Create new pattern at higher scope
        new_namespace = "global-patterns" if to_scope == "global" else f"team-{self.team_id}"
        
        new_memory = aegis.add(
            content=pattern.content,
            agent_id="system",
            scope="global",
            namespace=new_namespace,
            memory_type="strategy",
            metadata={
                **pattern.metadata,
                "promoted_from": memory_id,
                "promotion_reason": "High effectiveness across multiple projects"
            }
        )
        
        # Deprecate original (keep history)
        aegis.delta([{
            "type": "deprecate",
            "memory_id": memory_id,
            "superseded_by": new_memory.id,
            "deprecation_reason": f"Promoted to {to_scope} scope"
        }])
        
        return new_memory.id
```

### Step 4: Usage Example

```python
# === Project A: Learning pagination patterns ===

agent_a = CrossProjectAgent(
    agent_id="coder",
    project_id="ecommerce-api",
    team_id="backend-team"
)

# Execute task
result = agent_a.execute_task(
    "Implement pagination for the products endpoint. We have 1M+ products."
)

# Report outcome with learnings
agent_a.report_outcome(
    task="Implement pagination",
    solution=result["solution"],
    success=True,
    patterns_that_helped=["cursor_pagination_pattern"]
)

# === Project B: Automatically gets Project A's learnings ===

agent_b = CrossProjectAgent(
    agent_id="coder",
    project_id="inventory-service",
    team_id="backend-team"
)

# This query now returns the pagination patterns learned in Project A!
knowledge = agent_b.get_relevant_knowledge("paginate inventory items")
print(knowledge["team_patterns"])
# [{"content": "Use cursor-based pagination for tables > 10K rows", ...}]

# === Periodic: Promote validated patterns ===

promoter = PatternPromoter(team_id="backend-team")
candidates = promoter.analyze_for_promotion()

for candidate in candidates:
    if candidate["evidence"]["helpful_ratio"] >= 0.8:
        promoter.promote_pattern(
            candidate["pattern"].id,
            to_scope=candidate["recommended_scope"]
        )
```

---

## Production Tips

### 1. Namespace Strategy
```python
# Recommended namespace hierarchy
NAMESPACES = {
    "global": "global-patterns",           # Universal patterns
    "team": f"team-{team_id}",             # Team standards
    "project": f"project-{project_id}",    # Project specifics
    "agent": f"agent-{agent_id}"           # Agent private
}
```

### 2. Cold Start with Genesis Playbook
```python
# Seed new teams with proven patterns
def seed_team(team_id: str):
    genesis_patterns = load_json("playbooks/genesis.json")
    
    for pattern in genesis_patterns:
        aegis.add(
            content=pattern["content"],
            agent_id="system",
            scope="global",
            namespace=f"team-{team_id}",
            memory_type="strategy",
            metadata={"source": "genesis", "category": pattern["category"]}
        )
```

### 3. Pattern Quality Gates
```python
# Don't promote patterns too quickly
PROMOTION_CRITERIA = {
    "project_to_team": {
        "min_effectiveness": 0.5,
        "min_votes": 5,
        "min_age_days": 7
    },
    "team_to_global": {
        "min_effectiveness": 0.7,
        "min_votes": 15,
        "min_unique_projects": 3,
        "min_age_days": 30
    }
}
```

### 4. Conflict Resolution
```python
# Handle conflicting patterns
def resolve_conflicts(patterns: List) -> List:
    """Keep highest-effectiveness pattern when conflicts exist."""
    by_category = defaultdict(list)
    for p in patterns:
        by_category[p.metadata.get("category")].append(p)
    
    resolved = []
    for category, group in by_category.items():
        # Sort by effectiveness, keep top
        group.sort(key=lambda x: x.effectiveness_score, reverse=True)
        resolved.append(group[0])
        
        # Deprecate lower-ranked conflicting patterns
        for p in group[1:]:
            if p.effectiveness_score < group[0].effectiveness_score - 0.3:
                aegis.delta([{
                    "type": "deprecate",
                    "memory_id": p.id,
                    "superseded_by": group[0].id
                }])
    
    return resolved
```

---

## Expected Outcomes

| Metric | Without Aegis | With Aegis |
|--------|---------------|------------|
| Pattern rediscovery | Every project | Once ever |
| Error repetition | Common | Rare (reflections prevent) |
| Onboarding time | Days | Hours |
| Cross-team learning | Manual | Automatic |
| Pattern quality | Unknown | Measured (effectiveness) |

---

## Next Steps

- [Recipe 4: Code Review Swarm](./04-code-review-swarm.md) - Multiple reviewers with shared knowledge
- [Recipe 6: Debugging Agent](./06-debugging-agent-reflection.md) - Self-improving error resolution
- [Recipe 7: Codebase Onboarding](./07-codebase-onboarding.md) - Instant context for new agents
