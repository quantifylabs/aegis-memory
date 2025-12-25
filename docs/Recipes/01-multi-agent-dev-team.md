# Recipe 1: Multi-Agent Development Team

**Build a MetaGPT-style autonomous dev team where agents actually coordinate.**

| Metric | Value |
|--------|-------|
| Complexity | Advanced |
| Time to Build | 2-4 hours |
| Agents | 5 (Planner, Architect, Engineer, Reviewer, Tester) |
| Key Patterns | Scope hierarchy, Memory voting, Cross-agent queries |

---

## The Problem

You want to build an autonomous coding team like MetaGPT or ChatDev. Five agents—Planner, Architect, Engineer, Reviewer, Tester—working together to build software.

**What breaks in production:**

```
Hour 1: Planner creates task breakdown
Hour 2: Architect designs system... but queries Planner's old context
Hour 3: Engineer starts coding... unaware Architect changed the design
Hour 4: Reviewer flags issues... that were already fixed
Hour 5: Tester writes tests... for the wrong implementation
```

The result? **Cascading inconsistencies**, duplicated work, and agents operating on stale reality.

---

## Current Solutions (And Why They Fail)

### MetaGPT Approach
- **How it works**: Message subscription system, structured outputs (PRDs, design docs)
- **The gap**: Memory is conversation history only. No persistent learning across projects. Roles can't share private reasoning.

### ChatDev Approach  
- **How it works**: "Chat chains" decompose work into atomic conversations
- **The gap**: Per-session memory. Next project starts from zero. No cross-project experiential learning.

### AutoGen Approach
- **How it works**: Agents converse in group chats
- **The gap**: No memory isolation. Every agent sees everything. No way to scope "Architect-only" insights.

### LangGraph + mem0
- **How it works**: State machine + external memory
- **The gap**: mem0 provides user/agent scoping but no native coordination. You build everything yourself.

**The fundamental issue**: All these frameworks assume memory is either fully shared or fully private. Real teams need **graduated visibility**—some knowledge is role-specific, some is team-wide, some is organizational.

---

## The Aegis Approach

Aegis provides **scope-aware memory** with three levels:

```
┌─────────────────────────────────────────────────────────┐
│                     GLOBAL SCOPE                         │
│  "Always use type hints in Python"                       │
│  "Our API follows REST conventions"                      │
│  Visible to: ALL agents, ALL projects                    │
├─────────────────────────────────────────────────────────┤
│                  AGENT-SHARED SCOPE                      │
│  "Current task: Build user authentication"               │
│  "Architecture decision: Use JWT tokens"                 │
│  Visible to: Specified agents in this project            │
├──────────────┬──────────────┬───────────────────────────┤
│ AGENT-PRIVATE│ AGENT-PRIVATE│ AGENT-PRIVATE             │
│   Planner    │   Architect  │   Engineer                │
│ "User seems  │ "Considered  │ "This pattern            │
│  to want     │  microservices│  worked well             │
│  simplicity" │  but too     │  last time"              │
│              │  complex"    │                           │
└──────────────┴──────────────┴───────────────────────────┘
```

Plus **memory voting** so agents learn which strategies actually work:

```python
# After Engineer successfully uses a pattern
client.vote(memory_id, "helpful", voter_agent_id="engineer")

# After a strategy causes bugs
client.vote(memory_id, "harmful", voter_agent_id="tester", 
           context="Caused race condition in auth flow")
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         USER REQUEST                             │
│                    "Build a login system"                        │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                          PLANNER                                 │
│  • Breaks down into tasks                                        │
│  • Queries global patterns: client.playbook("task breakdown")    │
│  • Stores plan in SHARED scope                                   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                         ARCHITECT                                │
│  • Queries Planner's shared memories                             │
│  • Designs system architecture                                   │
│  • Stores decisions in SHARED scope                              │
│  • Private: "Rejected approaches" (so others don't retry)        │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                          ENGINEER                                │
│  • Queries Architect + Planner memories                          │
│  • Implements code                                               │
│  • Stores implementation notes in SHARED                         │
│  • Votes on which patterns from playbook helped                  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                          REVIEWER                                │
│  • Queries all shared memories for context                       │
│  • Reviews code against architecture decisions                   │
│  • Creates GLOBAL reflections for org-wide learnings             │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                           TESTER                                 │
│  • Queries implementation details                                │
│  • Writes tests based on actual implementation                   │
│  • Votes on strategy effectiveness                               │
│  • Failures become GLOBAL reflections                            │
└─────────────────────────────────────────────────────────────────┘
```

---

## Implementation

### Step 1: Project Setup

```python
from aegis_memory import AegisClient
from openai import OpenAI
import json

# Initialize clients
aegis = AegisClient(
    api_key="your-aegis-key",
    base_url="http://localhost:8000"
)
llm = OpenAI()

# Project configuration
PROJECT_ID = "login-system-v1"
NAMESPACE = "dev-team"

# Agent definitions
AGENTS = {
    "planner": {
        "role": "Planner",
        "can_read_from": [],  # Starts fresh, queries playbook
        "shares_with": ["architect", "engineer", "reviewer", "tester"]
    },
    "architect": {
        "role": "Architect", 
        "can_read_from": ["planner"],
        "shares_with": ["engineer", "reviewer", "tester"]
    },
    "engineer": {
        "role": "Engineer",
        "can_read_from": ["planner", "architect"],
        "shares_with": ["reviewer", "tester"]
    },
    "reviewer": {
        "role": "Reviewer",
        "can_read_from": ["planner", "architect", "engineer"],
        "shares_with": ["engineer", "tester"]  # Feedback loop
    },
    "tester": {
        "role": "Tester",
        "can_read_from": ["planner", "architect", "engineer"],
        "shares_with": ["engineer"]  # Bug reports
    }
}
```

### Step 2: Base Agent Class

```python
class DevTeamAgent:
    def __init__(self, agent_id: str, config: dict):
        self.agent_id = agent_id
        self.role = config["role"]
        self.can_read_from = config["can_read_from"]
        self.shares_with = config["shares_with"]
    
    def get_context(self, task: str) -> str:
        """Gather all relevant context for this agent."""
        context_parts = []
        
        # 1. Query global playbook for proven strategies
        playbook = aegis.playbook(
            query=task,
            agent_id=self.agent_id,
            min_effectiveness=0.3,  # Only well-rated strategies
            top_k=5
        )
        if playbook:
            context_parts.append("## Proven Strategies (from past successes)\n")
            for memory in playbook:
                score = f"[{memory.effectiveness_score:.1f}]"
                context_parts.append(f"{score} {memory.content}\n")
        
        # 2. Query cross-agent memories from collaborators
        if self.can_read_from:
            cross_agent = aegis.query_cross_agent(
                query=task,
                requesting_agent_id=self.agent_id,
                target_agent_ids=self.can_read_from,
                top_k=10
            )
            if cross_agent:
                context_parts.append("\n## Context from Team Members\n")
                for memory in cross_agent:
                    context_parts.append(
                        f"[{memory.agent_id}] {memory.content}\n"
                    )
        
        # 3. Query own private memories
        own_memories = aegis.query(
            query=task,
            agent_id=self.agent_id,
            top_k=5
        )
        if own_memories:
            context_parts.append("\n## Your Previous Insights\n")
            for memory in own_memories:
                context_parts.append(f"- {memory.content}\n")
        
        return "".join(context_parts)
    
    def store_output(self, content: str, scope: str = "agent-shared", 
                     memory_type: str = "standard"):
        """Store agent output with appropriate scoping."""
        aegis.add(
            content=content,
            agent_id=self.agent_id,
            scope=scope,
            shared_with_agents=self.shares_with if scope == "agent-shared" else [],
            memory_type=memory_type,
            metadata={
                "project_id": PROJECT_ID,
                "role": self.role
            }
        )
    
    def vote_on_strategy(self, memory_id: str, helpful: bool, context: str = ""):
        """Vote on whether a playbook strategy helped."""
        aegis.vote(
            memory_id=memory_id,
            vote="helpful" if helpful else "harmful",
            voter_agent_id=self.agent_id,
            context=context
        )
    
    def create_reflection(self, content: str, error_pattern: str = None):
        """Create a reflection from success or failure."""
        aegis.reflection(
            content=content,
            agent_id=self.agent_id,
            error_pattern=error_pattern,
            scope="global"  # Reflections benefit everyone
        )
```

### Step 3: Specialized Agents

```python
class PlannerAgent(DevTeamAgent):
    def __init__(self):
        super().__init__("planner", AGENTS["planner"])
    
    def plan(self, user_request: str) -> dict:
        context = self.get_context(user_request)
        
        response = llm.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": f"""You are a software planning agent.
                
{context}

Break down the user's request into clear, actionable tasks.
Output JSON with: tasks (list), dependencies (dict), priority_order (list)"""},
                {"role": "user", "content": user_request}
            ]
        )
        
        plan = json.loads(response.choices[0].message.content)
        
        # Store plan for other agents
        self.store_output(
            content=f"Task breakdown for '{user_request}':\n" + 
                    json.dumps(plan, indent=2),
            scope="agent-shared"
        )
        
        return plan


class ArchitectAgent(DevTeamAgent):
    def __init__(self):
        super().__init__("architect", AGENTS["architect"])
    
    def design(self, plan: dict) -> dict:
        context = self.get_context(str(plan))
        
        response = llm.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": f"""You are a software architect.

{context}

Design the system architecture for this plan.
Output JSON with: components (list), interfaces (dict), 
technology_choices (dict), rationale (dict)"""},
                {"role": "user", "content": json.dumps(plan)}
            ]
        )
        
        design = json.loads(response.choices[0].message.content)
        
        # Store architecture decisions (shared)
        self.store_output(
            content=f"Architecture design:\n{json.dumps(design, indent=2)}",
            scope="agent-shared"
        )
        
        # Store rejected alternatives (private - prevents others retrying)
        self.store_output(
            content=f"Rejected approaches: {design.get('rationale', {})}",
            scope="agent-private"
        )
        
        return design


class EngineerAgent(DevTeamAgent):
    def __init__(self):
        super().__init__("engineer", AGENTS["engineer"])
        self.used_strategies = []  # Track for voting
    
    def implement(self, design: dict, task: str) -> str:
        context = self.get_context(task)
        
        # Track which playbook strategies we're using
        playbook = aegis.playbook(task, agent_id=self.agent_id, top_k=3)
        self.used_strategies = [(m.id, m.content) for m in playbook]
        
        response = llm.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": f"""You are a software engineer.

{context}

Implement the following based on the architecture design.
Write clean, well-documented code."""},
                {"role": "user", "content": f"Design: {json.dumps(design)}\nTask: {task}"}
            ]
        )
        
        code = response.choices[0].message.content
        
        # Store implementation
        self.store_output(
            content=f"Implementation for {task}:\n```\n{code}\n```",
            scope="agent-shared"
        )
        
        return code
    
    def report_outcome(self, success: bool, error_msg: str = ""):
        """Report task outcome and vote on strategies."""
        for strategy_id, strategy_content in self.used_strategies:
            self.vote_on_strategy(
                memory_id=strategy_id,
                helpful=success,
                context=error_msg if not success else "Task completed successfully"
            )
        
        if not success:
            self.create_reflection(
                content=f"Implementation failed: {error_msg}",
                error_pattern="implementation_failure"
            )


class ReviewerAgent(DevTeamAgent):
    def __init__(self):
        super().__init__("reviewer", AGENTS["reviewer"])
    
    def review(self, code: str, design: dict) -> dict:
        context = self.get_context("code review security performance")
        
        response = llm.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": f"""You are a code reviewer.

{context}

Review the code against the architecture design.
Check for: correctness, security, performance, maintainability.
Output JSON with: approved (bool), issues (list), suggestions (list)"""},
                {"role": "user", "content": f"Design: {json.dumps(design)}\n\nCode:\n{code}"}
            ]
        )
        
        review = json.loads(response.choices[0].message.content)
        
        # Store review results
        self.store_output(
            content=f"Code review results:\n{json.dumps(review, indent=2)}",
            scope="agent-shared"
        )
        
        # Create global reflections for important findings
        if review.get("issues"):
            for issue in review["issues"]:
                if issue.get("severity") == "high":
                    self.create_reflection(
                        content=f"Code review finding: {issue['description']}. "
                               f"Fix: {issue.get('fix', 'See review')}",
                        error_pattern=issue.get("category", "code_quality")
                    )
        
        return review


class TesterAgent(DevTeamAgent):
    def __init__(self):
        super().__init__("tester", AGENTS["tester"])
    
    def write_tests(self, code: str, design: dict) -> str:
        context = self.get_context("testing test cases edge cases")
        
        response = llm.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": f"""You are a test engineer.

{context}

Write comprehensive tests for this code.
Include: unit tests, integration tests, edge cases."""},
                {"role": "user", "content": f"Design: {json.dumps(design)}\n\nCode:\n{code}"}
            ]
        )
        
        tests = response.choices[0].message.content
        
        self.store_output(
            content=f"Test suite:\n```\n{tests}\n```",
            scope="agent-shared"
        )
        
        return tests
    
    def report_test_results(self, passed: bool, failures: list = None):
        """Report test results and create reflections."""
        if not passed and failures:
            for failure in failures:
                self.create_reflection(
                    content=f"Test failure: {failure['test']}. "
                           f"Expected: {failure['expected']}. "
                           f"Got: {failure['actual']}",
                    error_pattern="test_failure"
                )
```

### Step 4: Orchestrator

```python
class DevTeamOrchestrator:
    def __init__(self):
        self.planner = PlannerAgent()
        self.architect = ArchitectAgent()
        self.engineer = EngineerAgent()
        self.reviewer = ReviewerAgent()
        self.tester = TesterAgent()
    
    def build(self, user_request: str) -> dict:
        """Orchestrate the full development workflow."""
        results = {"request": user_request, "stages": {}}
        
        # Stage 1: Planning
        print("📋 Planning...")
        plan = self.planner.plan(user_request)
        results["stages"]["plan"] = plan
        
        # Stage 2: Architecture
        print("🏗️ Designing architecture...")
        design = self.architect.design(plan)
        results["stages"]["design"] = design
        
        # Stage 3: Implementation (iterate over tasks)
        print("💻 Implementing...")
        implementations = {}
        for task in plan.get("priority_order", plan.get("tasks", [])):
            code = self.engineer.implement(design, task)
            implementations[task] = code
        results["stages"]["implementation"] = implementations
        
        # Stage 4: Review
        print("🔍 Reviewing...")
        all_code = "\n\n".join(implementations.values())
        review = self.reviewer.review(all_code, design)
        results["stages"]["review"] = review
        
        # Stage 5: Handle review feedback
        if not review.get("approved", False):
            print("🔄 Addressing review feedback...")
            # Engineer addresses issues
            for issue in review.get("issues", []):
                fixed_code = self.engineer.implement(
                    design, 
                    f"Fix: {issue['description']}"
                )
                implementations["fix_" + issue.get("id", "unknown")] = fixed_code
        
        # Stage 6: Testing
        print("🧪 Testing...")
        tests = self.tester.write_tests(all_code, design)
        results["stages"]["tests"] = tests
        
        # Stage 7: Final status
        print("✅ Complete!")
        results["status"] = "complete"
        
        return results


# Run the team
if __name__ == "__main__":
    team = DevTeamOrchestrator()
    result = team.build("Build a user authentication system with JWT tokens")
    print(json.dumps(result, indent=2))
```

### Step 5: Session Progress for Long Tasks

```python
class DevTeamOrchestratorWithRecovery(DevTeamOrchestrator):
    def __init__(self, session_id: str):
        super().__init__()
        self.session_id = session_id
    
    def build_with_recovery(self, user_request: str) -> dict:
        """Build with session recovery for long-running tasks."""
        
        # Check if resuming existing session
        try:
            progress = aegis.progress.get(self.session_id)
            if progress and progress.status == "active":
                print(f"🔄 Resuming from: {progress.last_action}")
                return self._resume(progress, user_request)
        except:
            pass  # New session
        
        # Initialize session
        aegis.progress.update(
            session_id=self.session_id,
            summary=f"Building: {user_request}",
            status="active",
            completed=[],
            in_progress="planning"
        )
        
        try:
            # Planning
            self._update_progress("planning")
            plan = self.planner.plan(user_request)
            self._mark_complete("planning")
            
            # Architecture
            self._update_progress("architecture")
            design = self.architect.design(plan)
            self._mark_complete("architecture")
            
            # Implementation (task by task with checkpoints)
            for i, task in enumerate(plan.get("tasks", [])):
                task_id = f"implement_{i}"
                self._update_progress(task_id)
                self.engineer.implement(design, task)
                self._mark_complete(task_id)
            
            # Review
            self._update_progress("review")
            # ... rest of workflow
            
            aegis.progress.update(
                session_id=self.session_id,
                status="completed"
            )
            
        except Exception as e:
            aegis.progress.update(
                session_id=self.session_id,
                status="failed",
                last_action=f"Failed: {str(e)}"
            )
            raise
    
    def _update_progress(self, stage: str):
        aegis.progress.update(
            session_id=self.session_id,
            in_progress=stage,
            last_action=f"Starting {stage}"
        )
    
    def _mark_complete(self, stage: str):
        progress = aegis.progress.get(self.session_id)
        completed = progress.completed_items or []
        completed.append(stage)
        aegis.progress.update(
            session_id=self.session_id,
            completed=completed,
            in_progress=None,
            last_action=f"Completed {stage}"
        )
    
    def _resume(self, progress, user_request: str):
        """Resume from last checkpoint."""
        completed = set(progress.completed_items or [])
        
        if "planning" not in completed:
            return self.build_with_recovery(user_request)
        
        # Load existing plan from memory
        plan_memory = aegis.query(
            query="task breakdown",
            agent_id="planner",
            top_k=1
        )
        # ... continue from checkpoint
```

---

## Production Tips

### 1. Namespace by Project
```python
# Keep project memories isolated
aegis = AegisClient(
    namespace=f"project-{project_id}",
    # ...
)
```

### 2. Effectiveness Thresholds
```python
# Start permissive, tighten as playbook grows
EARLY_PROJECT_THRESHOLD = 0.0   # Accept all strategies
MATURE_PROJECT_THRESHOLD = 0.3  # Only proven strategies
```

### 3. Memory Cleanup
```python
# Deprecate outdated strategies instead of deleting
aegis.delta([{
    "type": "deprecate",
    "memory_id": old_strategy_id,
    "deprecation_reason": "Superseded by new approach",
    "superseded_by": new_strategy_id
}])
```

### 4. Monitoring
```python
# Track agent coordination health
metrics = {
    "cross_agent_queries": count_cross_agent_queries(),
    "voting_rate": votes_cast / memories_used,
    "reflection_rate": reflections_created / tasks_completed,
    "playbook_hit_rate": playbook_queries_with_results / total_queries
}
```

---

## Expected Outcomes

| Metric | Without Aegis | With Aegis |
|--------|---------------|------------|
| Context consistency | ~60% | ~95% |
| Duplicate work | High | Near zero |
| Cross-project learning | None | Automatic |
| Recovery from crashes | Manual | Automatic |
| Strategy improvement | Static | Continuous |

---

## Next Steps

- **Add more agents**: Security auditor, documentation writer, DevOps
- **Integrate with git**: Store memories alongside code commits
- **Add human-in-the-loop**: Approval gates at critical stages
- **Scale horizontally**: Run multiple teams on different projects

See [Recipe 2: Session Recovery](./02-session-recovery-coding.md) for robust failure handling.
