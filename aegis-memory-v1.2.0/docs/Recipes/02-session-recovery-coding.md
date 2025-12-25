# Recipe 2: Session Recovery for Long-Running Coding Tasks

**Never lose context mid-refactor again.**

| Metric | Value |
|--------|-------|
| Complexity | Intermediate |
| Time to Build | 1-2 hours |
| Key Patterns | Session progress, Feature tracking, Checkpoint/resume |

---

## The Problem

Your AI coding agent is 3 hours into a complex refactoring task:

```
✓ Analyzed 47 files
✓ Updated 23 imports  
✓ Refactored 12 functions
→ Working on authentication module...

ERROR: Request timeout. Connection reset.
```

**Everything is gone.** The agent restarts with zero memory of what was completed.

This isn't theoretical. Production data from Intellyx identifies **state management as the #1 challenge for agentic AI**. Cursor users report "AI chat abruptly loses all context in the middle of a chat." Devin sessions can't share context—"parallelization of tasks would not work here."

---

## Current Solutions (And Why They Fail)

### Conversation History
- **Approach**: Store chat messages, replay on resume
- **Fails because**: Context windows overflow. 3 hours of work = 100K+ tokens. You can't replay it all.

### File-Based Checkpoints
- **Approach**: Write progress to JSON files
- **Fails because**: No semantic understanding. "What was I trying to accomplish?" requires re-analysis.

### LangGraph Persistence
- **Approach**: Checkpoint graph state to database
- **Fails because**: Stores raw state, not semantic progress. Resuming means re-executing nodes, not understanding context.

### TapeAgents
- **Approach**: Structured tape of all agent actions
- **Fails because**: Tape grows unboundedly. No summarization. Resume = replay entire tape.

**The core issue**: These solutions persist *data* but not *understanding*. When an agent resumes, it needs to know: What was I doing? What's done? What's left? What did I learn?

---

## The Aegis Approach

Aegis provides **session progress tracking** that persists semantic understanding:

```python
# What Aegis stores (semantic, resumable)
{
    "session_id": "refactor-auth-v2",
    "summary": "Refactoring authentication to use JWT. 60% complete.",
    "completed_items": ["analyze_codebase", "update_imports", "user_model"],
    "in_progress_item": "auth_middleware",
    "next_items": ["token_validation", "refresh_flow", "tests"],
    "blocked_items": [
        {"item": "oauth_integration", "reason": "Waiting for API credentials"}
    ],
    "last_action": "Updated auth_middleware.py lines 45-89",
    "status": "active"
}
```

Plus **feature tracking** that prevents premature completion:

```python
# Agent can't declare "done" until tests pass
{
    "feature_id": "jwt_authentication",
    "status": "in_progress",
    "test_steps": [
        "Token generation returns valid JWT",
        "Expired tokens are rejected",
        "Refresh flow extends session"
    ],
    "passes": false,  # Can't mark complete until true
    "verified_by": null
}
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      CODING SESSION                              │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                   SESSION PROGRESS                        │   │
│  │  • What's done (completed_items)                          │   │
│  │  • What's active (in_progress_item)                       │   │
│  │  • What's next (next_items)                               │   │
│  │  • What's blocked (blocked_items)                         │   │
│  │  • Human-readable summary                                 │   │
│  └──────────────────────────────────────────────────────────┘   │
│                              │                                   │
│                              ▼                                   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                   FEATURE TRACKER                         │   │
│  │  • Feature definitions with test criteria                 │   │
│  │  • Pass/fail status                                       │   │
│  │  • Prevents premature "done" declarations                 │   │
│  └──────────────────────────────────────────────────────────┘   │
│                              │                                   │
│                              ▼                                   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                   MEMORY REPOSITORY                       │   │
│  │  • Code changes made                                      │   │
│  │  • Decisions and rationale                                │   │
│  │  • Errors encountered and solutions                       │   │
│  │  • Reflections for future sessions                        │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    [CRASH / TIMEOUT]
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      NEW CONTEXT WINDOW                          │
│                                                                  │
│  1. Load session progress → Know what's done                     │
│  2. Load feature tracker → Know success criteria                 │
│  3. Query memories → Get full context                            │
│  4. Resume from in_progress_item → Continue work                 │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Implementation

### Step 1: Session Manager

```python
from aegis_memory import AegisClient
from dataclasses import dataclass, field
from typing import List, Optional
import json

aegis = AegisClient(api_key="your-key", base_url="http://localhost:8000")

@dataclass
class CodingSession:
    session_id: str
    task_description: str
    agent_id: str = "coding-agent"
    
    def initialize(self, subtasks: List[str], features: List[dict]):
        """Initialize a new coding session with task breakdown."""
        
        # Create session progress
        aegis.progress.update(
            session_id=self.session_id,
            summary=f"Starting: {self.task_description}",
            status="active",
            completed=[],
            in_progress=subtasks[0] if subtasks else None,
            next_items=subtasks[1:] if len(subtasks) > 1 else [],
            blocked=[],
            last_action="Session initialized"
        )
        
        # Create feature trackers for success criteria
        for feature in features:
            aegis.features.create(
                feature_id=feature["id"],
                session_id=self.session_id,
                description=feature["description"],
                test_steps=feature["test_steps"],
                status="not_started"
            )
        
        # Store initial context
        aegis.add(
            content=f"Session goal: {self.task_description}\n"
                   f"Subtasks: {json.dumps(subtasks)}\n"
                   f"Success criteria: {json.dumps(features)}",
            agent_id=self.agent_id,
            scope="agent-private",
            metadata={"session_id": self.session_id, "type": "session_init"}
        )
        
        return self
    
    def resume(self) -> dict:
        """Resume an existing session - returns context for agent."""
        progress = aegis.progress.get(self.session_id)
        
        if not progress:
            raise ValueError(f"No session found: {self.session_id}")
        
        if progress.status == "completed":
            return {"status": "completed", "message": "Session already finished"}
        
        # Get feature status
        features = aegis.features.list(session_id=self.session_id)
        
        # Get relevant memories from this session
        memories = aegis.query(
            query=progress.in_progress_item or progress.summary,
            agent_id=self.agent_id,
            top_k=20,
            filter_metadata={"session_id": self.session_id}
        )
        
        # Build resume context
        context = {
            "status": "resuming",
            "summary": progress.summary,
            "completed": progress.completed_items or [],
            "in_progress": progress.in_progress_item,
            "next": progress.next_items or [],
            "blocked": progress.blocked_items or [],
            "last_action": progress.last_action,
            "features": {
                "total": features["total"],
                "passing": features["passing"],
                "incomplete": [
                    f for f in features["features"] if not f.passes
                ]
            },
            "relevant_memories": [
                {"content": m.content, "type": m.metadata.get("type")}
                for m in memories
            ]
        }
        
        return context
    
    def checkpoint(self, 
                   completed_task: str = None,
                   started_task: str = None,
                   action_description: str = None,
                   memories_to_store: List[dict] = None):
        """Save progress checkpoint."""
        
        progress = aegis.progress.get(self.session_id)
        completed = progress.completed_items or []
        next_items = progress.next_items or []
        
        # Update completed
        if completed_task:
            if completed_task not in completed:
                completed.append(completed_task)
            if completed_task in next_items:
                next_items.remove(completed_task)
        
        # Update in-progress
        in_progress = started_task or progress.in_progress_item
        if started_task and started_task in next_items:
            next_items.remove(started_task)
        
        aegis.progress.update(
            session_id=self.session_id,
            completed=completed,
            in_progress=in_progress,
            next_items=next_items,
            last_action=action_description or f"Checkpoint at {completed_task or started_task}",
            summary=f"{self.task_description} - {len(completed)}/{len(completed)+len(next_items)+1} tasks"
        )
        
        # Store any memories
        if memories_to_store:
            for memory in memories_to_store:
                aegis.add(
                    content=memory["content"],
                    agent_id=self.agent_id,
                    scope=memory.get("scope", "agent-private"),
                    memory_type=memory.get("type", "standard"),
                    metadata={
                        "session_id": self.session_id,
                        "task": completed_task or started_task,
                        **memory.get("metadata", {})
                    }
                )
    
    def mark_blocked(self, task: str, reason: str):
        """Mark a task as blocked."""
        progress = aegis.progress.get(self.session_id)
        blocked = progress.blocked_items or []
        blocked.append({"item": task, "reason": reason})
        
        # Move to next task if current is blocked
        next_items = progress.next_items or []
        in_progress = next_items[0] if next_items else None
        
        aegis.progress.update(
            session_id=self.session_id,
            blocked=blocked,
            in_progress=in_progress,
            next_items=next_items[1:] if next_items else [],
            last_action=f"Blocked on {task}: {reason}"
        )
    
    def update_feature(self, feature_id: str, passed: bool, notes: str = None):
        """Update feature test status."""
        aegis.features.update(
            feature_id=feature_id,
            status="complete" if passed else "failing",
            passes=passed,
            failure_reason=notes if not passed else None
        )
        
        if passed:
            aegis.features.mark_complete(
                feature_id=feature_id,
                verified_by=self.agent_id
            )
    
    def complete(self, final_summary: str = None):
        """Mark session as complete."""
        # Verify all features pass
        features = aegis.features.list(session_id=self.session_id)
        if features["failing"] > 0:
            raise ValueError(
                f"Cannot complete: {features['failing']} features still failing"
            )
        
        aegis.progress.update(
            session_id=self.session_id,
            status="completed",
            summary=final_summary or f"Completed: {self.task_description}",
            last_action="Session completed successfully"
        )
        
        # Create reflection for future sessions
        aegis.reflection(
            content=f"Successfully completed '{self.task_description}'. "
                   f"Key learnings stored in session memories.",
            agent_id=self.agent_id,
            scope="global"
        )
```

### Step 2: Recoverable Coding Agent

```python
from openai import OpenAI

llm = OpenAI()

class RecoverableCodingAgent:
    def __init__(self, session: CodingSession):
        self.session = session
        self.agent_id = session.agent_id
    
    def run(self, user_task: str):
        """Main agent loop with automatic recovery."""
        
        # Try to resume existing session
        try:
            context = self.session.resume()
            if context["status"] == "completed":
                print("✅ Session already completed")
                return
            elif context["status"] == "resuming":
                print(f"🔄 Resuming session...")
                print(f"   Completed: {len(context['completed'])} tasks")
                print(f"   In progress: {context['in_progress']}")
                print(f"   Remaining: {len(context['next'])} tasks")
                self._continue_work(context)
                return
        except ValueError:
            pass  # New session
        
        # Start new session
        print(f"🆕 Starting new session: {user_task}")
        self._start_fresh(user_task)
    
    def _start_fresh(self, user_task: str):
        """Initialize and run new session."""
        
        # Step 1: Plan the work
        plan = self._create_plan(user_task)
        
        # Step 2: Initialize session with plan
        self.session.initialize(
            subtasks=plan["subtasks"],
            features=plan["features"]
        )
        
        # Step 3: Execute with checkpoints
        self._execute_plan(plan)
    
    def _create_plan(self, user_task: str) -> dict:
        """Use LLM to create task breakdown."""
        
        # Get relevant playbook strategies
        playbook = aegis.playbook(
            query=user_task,
            agent_id=self.agent_id,
            top_k=5
        )
        playbook_context = "\n".join([
            f"- {m.content}" for m in playbook
        ]) if playbook else "No prior strategies available."
        
        response = llm.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": f"""You are a coding agent planner.
                
Proven strategies from past sessions:
{playbook_context}

Break down the task into subtasks and define success criteria.
Output JSON:
{{
    "subtasks": ["task1", "task2", ...],
    "features": [
        {{
            "id": "feature_id",
            "description": "What this feature does",
            "test_steps": ["Test 1", "Test 2"]
        }}
    ]
}}"""},
                {"role": "user", "content": user_task}
            ]
        )
        
        return json.loads(response.choices[0].message.content)
    
    def _continue_work(self, context: dict):
        """Resume work from checkpoint."""
        
        # Build prompt with full context
        resume_prompt = f"""You are resuming a coding session.

SESSION SUMMARY: {context['summary']}

COMPLETED TASKS:
{json.dumps(context['completed'], indent=2)}

CURRENT TASK: {context['in_progress']}

REMAINING TASKS:
{json.dumps(context['next'], indent=2)}

BLOCKED TASKS:
{json.dumps(context['blocked'], indent=2)}

LAST ACTION: {context['last_action']}

FEATURE STATUS:
- Total: {context['features']['total']}
- Passing: {context['features']['passing']}
- Incomplete: {[f.feature_id for f in context['features']['incomplete']]}

RELEVANT CONTEXT FROM THIS SESSION:
{json.dumps(context['relevant_memories'], indent=2)}

Continue from where you left off. Start with: {context['in_progress']}"""

        # Execute remaining work
        self._execute_from_context(resume_prompt, context)
    
    def _execute_plan(self, plan: dict):
        """Execute plan with checkpoints after each task."""
        
        for i, task in enumerate(plan["subtasks"]):
            print(f"\n📌 Task {i+1}/{len(plan['subtasks'])}: {task}")
            
            try:
                # Execute task
                result = self._execute_task(task)
                
                # Checkpoint progress
                self.session.checkpoint(
                    completed_task=task,
                    started_task=plan["subtasks"][i+1] if i+1 < len(plan["subtasks"]) else None,
                    action_description=f"Completed: {task}",
                    memories_to_store=[
                        {
                            "content": f"Task '{task}' result: {result[:500]}",
                            "type": "task_result",
                            "metadata": {"task_index": i}
                        }
                    ]
                )
                
                print(f"   ✓ Completed and checkpointed")
                
            except Exception as e:
                print(f"   ✗ Failed: {e}")
                
                # Store failure for recovery
                self.session.checkpoint(
                    action_description=f"Failed on {task}: {str(e)}",
                    memories_to_store=[
                        {
                            "content": f"Task '{task}' failed: {str(e)}",
                            "type": "task_failure",
                            "scope": "agent-private"
                        }
                    ]
                )
                
                # Create reflection
                aegis.reflection(
                    content=f"Task '{task}' failed with: {str(e)}. "
                           "Consider alternative approach on retry.",
                    agent_id=self.agent_id,
                    error_pattern="task_failure"
                )
                
                raise  # Re-raise to stop execution
        
        # Verify features before completing
        self._verify_features(plan["features"])
        
        # Complete session
        self.session.complete(
            final_summary=f"Successfully completed all {len(plan['subtasks'])} tasks"
        )
        print("\n✅ Session completed!")
    
    def _execute_task(self, task: str) -> str:
        """Execute a single task using LLM."""
        
        # Get context for this specific task
        context = aegis.query(
            query=task,
            agent_id=self.agent_id,
            top_k=5
        )
        
        response = llm.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": f"""You are a coding agent executing a task.

Relevant context:
{chr(10).join([m.content for m in context])}

Execute the task and return the result."""},
                {"role": "user", "content": task}
            ]
        )
        
        return response.choices[0].message.content
    
    def _verify_features(self, features: List[dict]):
        """Verify all features pass before completing."""
        
        for feature in features:
            # Run verification (simplified - in practice, run actual tests)
            print(f"\n🧪 Verifying: {feature['id']}")
            
            for step in feature["test_steps"]:
                # Simulate test execution
                passed = self._run_test(step)
                
                if not passed:
                    self.session.update_feature(
                        feature_id=feature["id"],
                        passed=False,
                        notes=f"Failed: {step}"
                    )
                    raise ValueError(f"Feature {feature['id']} failed: {step}")
            
            self.session.update_feature(
                feature_id=feature["id"],
                passed=True
            )
            print(f"   ✓ {feature['id']} verified")
    
    def _run_test(self, test_step: str) -> bool:
        """Run a test step (simplified)."""
        # In practice: execute actual test code
        return True  # Placeholder


# Usage
if __name__ == "__main__":
    session = CodingSession(
        session_id="refactor-auth-jwt-001",
        task_description="Refactor authentication system to use JWT tokens"
    )
    
    agent = RecoverableCodingAgent(session)
    agent.run("Refactor the user authentication system to use JWT tokens instead of session cookies")
```

### Step 3: CLI for Session Management

```python
import argparse
import sys

def main():
    parser = argparse.ArgumentParser(description="Recoverable Coding Agent")
    subparsers = parser.add_subparsers(dest="command")
    
    # Start new session
    start_parser = subparsers.add_parser("start", help="Start new coding session")
    start_parser.add_argument("task", help="Task description")
    start_parser.add_argument("--session-id", help="Custom session ID")
    
    # Resume session
    resume_parser = subparsers.add_parser("resume", help="Resume existing session")
    resume_parser.add_argument("session_id", help="Session ID to resume")
    
    # Check status
    status_parser = subparsers.add_parser("status", help="Check session status")
    status_parser.add_argument("session_id", help="Session ID")
    
    # List sessions
    list_parser = subparsers.add_parser("list", help="List all sessions")
    
    args = parser.parse_args()
    
    if args.command == "start":
        session_id = args.session_id or f"session-{int(time.time())}"
        session = CodingSession(session_id=session_id, task_description=args.task)
        agent = RecoverableCodingAgent(session)
        agent.run(args.task)
        
    elif args.command == "resume":
        session = CodingSession(session_id=args.session_id, task_description="")
        context = session.resume()
        session.task_description = context["summary"]
        agent = RecoverableCodingAgent(session)
        agent._continue_work(context)
        
    elif args.command == "status":
        session = CodingSession(session_id=args.session_id, task_description="")
        context = session.resume()
        print(json.dumps(context, indent=2, default=str))
        
    elif args.command == "list":
        # Query all sessions (would need additional Aegis API)
        print("Session listing not yet implemented")

if __name__ == "__main__":
    main()
```

---

## Production Tips

### 1. Checkpoint Frequency
```python
# Checkpoint after meaningful work units, not every line
CHECKPOINT_TRIGGERS = [
    "file_modified",
    "test_passed",
    "feature_complete",
    "error_recovered",
    "5_minutes_elapsed"
]
```

### 2. Memory Pruning for Long Sessions
```python
# Summarize old memories to prevent bloat
def prune_session_memories(session_id: str, keep_recent: int = 50):
    memories = aegis.query(
        query="*",
        filter_metadata={"session_id": session_id},
        top_k=1000
    )
    
    if len(memories) > keep_recent:
        old_memories = memories[keep_recent:]
        summary = summarize_memories(old_memories)
        
        # Store summary
        aegis.add(
            content=f"Session history summary: {summary}",
            agent_id="system",
            metadata={"session_id": session_id, "type": "history_summary"}
        )
        
        # Deprecate old memories
        for m in old_memories:
            aegis.delta([{
                "type": "deprecate",
                "memory_id": m.id,
                "deprecation_reason": "Summarized into history"
            }])
```

### 3. Graceful Degradation
```python
# Handle partial state corruption
def safe_resume(session_id: str):
    try:
        return full_resume(session_id)
    except CorruptedStateError:
        # Fall back to memory-only recovery
        memories = aegis.query(
            query="session progress",
            filter_metadata={"session_id": session_id}
        )
        return reconstruct_state_from_memories(memories)
```

### 4. Multi-Agent Session Sharing
```python
# Allow handoff between agents
def handoff_session(session_id: str, from_agent: str, to_agent: str):
    # Store handoff context
    aegis.add(
        content=f"Session handed off from {from_agent} to {to_agent}",
        agent_id=from_agent,
        scope="agent-shared",
        shared_with_agents=[to_agent],
        metadata={"session_id": session_id, "type": "handoff"}
    )
    
    # Update session with new agent
    aegis.progress.update(
        session_id=session_id,
        last_action=f"Handed off to {to_agent}"
    )
```

---

## Expected Outcomes

| Scenario | Without Aegis | With Aegis |
|----------|---------------|------------|
| 3-hour task, timeout at 2h | Restart from zero | Resume in 30 seconds |
| Context window overflow | Lost context | Semantic compression |
| "Is this done?" | Unknown | Feature tracker knows |
| Agent crash | Manual recovery | Automatic checkpoint |
| Team handoff | Re-explain everything | Instant context |

---

## Next Steps

- [Recipe 1: Multi-Agent Dev Team](./01-multi-agent-dev-team.md) - Add more agents
- [Recipe 3: Cross-Repository Knowledge](./03-cross-repo-knowledge.md) - Share learnings across projects
- [Recipe 5: CI/CD Pipeline Memory](./05-cicd-pipeline-memory.md) - Integrate with your build system
