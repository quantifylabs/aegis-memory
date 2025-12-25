# Recipe 6: Self-Improving Debugging Agent

**An AI debugger that learns from every bug it fixes.**

| Metric | Value |
|--------|-------|
| Complexity | Intermediate |
| Time to Build | 1-2 hours |
| Key Patterns | Reflections, Playbook queries, Error pattern taxonomy |

---

## The Problem

You have an AI debugging assistant. It helps you fix a tricky async race condition. Great!

Two months later, similar bug. Same assistant. **It doesn't remember the fix.**

```
Developer: "There's a race condition in the order processing"

AI (Today): "Let me analyze... [spends 20 minutes] ...you need a mutex!"

AI (2 months ago): [Already figured this out. Knowledge lost.]
```

**Problems:**
- Every debugging session starts from zero
- Same error patterns require re-discovery
- No accumulation of debugging expertise
- No transfer between team members

---

## Current Solutions (And Why They Fail)

### RAG over Documentation
- **Approach**: Index docs, retrieve relevant sections
- **Fails because**: Docs describe how things *should* work, not how they *actually* break.

### Conversation History
- **Approach**: Keep chat history, reference past sessions
- **Fails because**: Finding the right past session is needle-in-haystack. No semantic indexing.

### Fine-Tuning
- **Approach**: Train on debugging examples
- **Fails because**: Expensive, slow, can't adapt to new bug types quickly.

### Stack Overflow Search
- **Approach**: Search SO for similar errors
- **Fails because**: Generic solutions, not tailored to your codebase. Misses org-specific patterns.

**The core issue**: Debugging expertise is experiential. You need to capture *what was tried*, *what worked*, and *why*—not just error/fix pairs.

---

## The Aegis Approach

Aegis enables **experiential learning** through structured reflections:

```python
# After successfully debugging a race condition
aegis.reflection(
    content="""
    Race condition in async order processing.
    
    SYMPTOMS: Intermittent 'duplicate order' errors under load.
    
    ROOT CAUSE: Two coroutines reading order status before either 
    could write the 'processing' flag.
    
    FIX: Added asyncio.Lock() around the read-check-write sequence.
    
    KEY INSIGHT: Always look for read-check-write patterns in async 
    code. The time between check and write is the danger zone.
    """,
    agent_id="debugger",
    error_pattern="race_condition",
    correct_approach="Use locks for read-check-write in async code",
    applicable_contexts=["async", "concurrent", "order_processing"],
    scope="global"
)
```

Next time a similar bug appears:

```python
# Agent queries for relevant debugging experience
reflections = aegis.playbook(
    query="race condition async duplicate",
    agent_id="debugger",
    include_types=["reflection"],
    min_effectiveness=0.3
)

# Returns the reflection with KEY INSIGHT ready to apply
```

---

## Implementation

### Step 1: Debugging Session Manager

```python
from aegis_memory import AegisClient
from openai import OpenAI
from dataclasses import dataclass, field
from typing import List, Dict, Optional
import json

aegis = AegisClient(api_key="your-key", base_url="http://localhost:8000")
llm = OpenAI()

@dataclass
class DebuggingAttempt:
    hypothesis: str
    action: str
    result: str
    successful: bool

@dataclass
class DebuggingSession:
    session_id: str
    initial_problem: str
    error_message: Optional[str] = None
    stack_trace: Optional[str] = None
    attempts: List[DebuggingAttempt] = field(default_factory=list)
    root_cause: Optional[str] = None
    solution: Optional[str] = None
    key_insight: Optional[str] = None

class DebuggingAgent:
    """Self-improving debugging agent."""
    
    def __init__(self, project_id: str = "default"):
        self.project_id = project_id
        self.agent_id = "debugger"
        self.current_session: Optional[DebuggingSession] = None
    
    def start_session(self, problem: str, error: str = None, 
                      stack_trace: str = None) -> Dict:
        """Start a new debugging session."""
        
        session_id = f"debug-{int(time.time())}"
        self.current_session = DebuggingSession(
            session_id=session_id,
            initial_problem=problem,
            error_message=error,
            stack_trace=stack_trace
        )
        
        # Query for relevant past debugging experience
        context = self._gather_context(problem, error)
        
        # Generate initial analysis
        analysis = self._analyze(problem, error, stack_trace, context)
        
        # Store session start
        aegis.add(
            content=f"Debugging session started: {problem[:200]}",
            agent_id=self.agent_id,
            scope="agent-private",
            metadata={
                "session_id": session_id,
                "type": "session_start"
            }
        )
        
        return {
            "session_id": session_id,
            "analysis": analysis,
            "similar_past_bugs": context.get("reflections", []),
            "suggested_hypotheses": analysis.get("hypotheses", [])
        }
    
    def _gather_context(self, problem: str, error: str = None) -> Dict:
        """Gather relevant debugging context from memory."""
        
        query = f"{problem} {error or ''}"
        
        # Get relevant reflections (past debugging insights)
        reflections = aegis.playbook(
            query=query,
            agent_id=self.agent_id,
            include_types=["reflection"],
            min_effectiveness=0.2,
            top_k=5
        )
        
        # Get debugging strategies
        strategies = aegis.playbook(
            query=query,
            agent_id=self.agent_id,
            include_types=["strategy"],
            min_effectiveness=0.3,
            top_k=5
        )
        
        return {
            "reflections": [
                {
                    "id": r.id,
                    "content": r.content,
                    "error_pattern": r.metadata.get("error_pattern"),
                    "effectiveness": r.effectiveness_score
                }
                for r in reflections
            ],
            "strategies": [
                {
                    "id": s.id,
                    "content": s.content,
                    "effectiveness": s.effectiveness_score
                }
                for s in strategies
            ]
        }
    
    def _analyze(self, problem: str, error: str, 
                 stack_trace: str, context: Dict) -> Dict:
        """Generate initial analysis using LLM + context."""
        
        # Format past experience
        past_experience = ""
        if context["reflections"]:
            past_experience = "## Similar bugs I've debugged before:\n"
            for r in context["reflections"]:
                past_experience += f"\n[{r['error_pattern']}] {r['content'][:300]}...\n"
        
        if context["strategies"]:
            past_experience += "\n## Debugging strategies that worked:\n"
            for s in context["strategies"]:
                past_experience += f"- {s['content']}\n"
        
        response = llm.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": f"""You are an expert debugger.

{past_experience}

Analyze the problem and generate hypotheses to test.
Output JSON:
{{
    "category": "<bug category>",
    "hypotheses": [
        {{
            "hypothesis": "<what might be wrong>",
            "test": "<how to verify>",
            "confidence": 0.0-1.0
        }}
    ],
    "recommended_first_step": "<what to try first>"
}}"""},
                {"role": "user", "content": f"""
Problem: {problem}
Error: {error or 'N/A'}
Stack trace: {stack_trace or 'N/A'}
"""}
            ]
        )
        
        return json.loads(response.choices[0].message.content)
    
    def record_attempt(self, hypothesis: str, action: str, 
                       result: str, successful: bool) -> Dict:
        """Record a debugging attempt."""
        
        if not self.current_session:
            raise ValueError("No active debugging session")
        
        attempt = DebuggingAttempt(
            hypothesis=hypothesis,
            action=action,
            result=result,
            successful=successful
        )
        self.current_session.attempts.append(attempt)
        
        # Store attempt in memory
        aegis.add(
            content=json.dumps({
                "hypothesis": hypothesis,
                "action": action,
                "result": result,
                "successful": successful
            }),
            agent_id=self.agent_id,
            scope="agent-private",
            metadata={
                "session_id": self.current_session.session_id,
                "type": "attempt"
            }
        )
        
        if successful:
            return {"status": "success", "message": "Great! Ready to record the solution."}
        else:
            # Generate next hypothesis
            next_steps = self._generate_next_steps()
            return {
                "status": "continue",
                "message": f"That didn't work. Here's what to try next:",
                "next_hypotheses": next_steps
            }
    
    def _generate_next_steps(self) -> List[Dict]:
        """Generate next hypotheses based on failed attempts."""
        
        failed_attempts = "\n".join([
            f"- Tried: {a.hypothesis} → {a.result}"
            for a in self.current_session.attempts if not a.successful
        ])
        
        response = llm.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": """Generate new debugging hypotheses.
Avoid repeating what's already been tried.
Output JSON array of hypotheses."""},
                {"role": "user", "content": f"""
Original problem: {self.current_session.initial_problem}
Error: {self.current_session.error_message}

Already tried (didn't work):
{failed_attempts}

What else could be wrong?
"""}
            ]
        )
        
        return json.loads(response.choices[0].message.content)
    
    def resolve_session(self, root_cause: str, solution: str, 
                        key_insight: str = None) -> Dict:
        """Complete the debugging session and create reflection."""
        
        if not self.current_session:
            raise ValueError("No active debugging session")
        
        self.current_session.root_cause = root_cause
        self.current_session.solution = solution
        self.current_session.key_insight = key_insight
        
        # Determine error pattern category
        error_pattern = self._categorize_error(root_cause)
        
        # Create reflection from this session
        reflection_content = self._compose_reflection()
        
        reflection = aegis.reflection(
            content=reflection_content,
            agent_id=self.agent_id,
            error_pattern=error_pattern,
            correct_approach=solution,
            source_trajectory_id=self.current_session.session_id,
            applicable_contexts=self._extract_contexts(),
            scope="global"
        )
        
        # Vote on any patterns that helped
        self._vote_on_helpful_patterns()
        
        # Clear session
        session_summary = {
            "session_id": self.current_session.session_id,
            "reflection_id": reflection.id,
            "attempts_count": len(self.current_session.attempts),
            "error_pattern": error_pattern
        }
        self.current_session = None
        
        return session_summary
    
    def _compose_reflection(self) -> str:
        """Compose a structured reflection from the session."""
        
        session = self.current_session
        
        # Format failed attempts as "what not to do"
        failed_attempts = [a for a in session.attempts if not a.successful]
        what_didnt_work = "\n".join([
            f"- {a.hypothesis}: {a.result}"
            for a in failed_attempts[:3]  # Top 3 failed attempts
        ])
        
        reflection = f"""
PROBLEM: {session.initial_problem}

ERROR SIGNATURE: {session.error_message[:200] if session.error_message else 'N/A'}

ROOT CAUSE: {session.root_cause}

SOLUTION: {session.solution}

WHAT DIDN'T WORK:
{what_didnt_work}

KEY INSIGHT: {session.key_insight or 'See solution.'}
"""
        return reflection.strip()
    
    def _categorize_error(self, root_cause: str) -> str:
        """Categorize the error type."""
        
        cause_lower = root_cause.lower()
        
        patterns = {
            "race_condition": ["race", "concurrent", "mutex", "lock", "async"],
            "null_reference": ["null", "none", "undefined", "optional"],
            "type_error": ["type", "cast", "convert"],
            "resource_leak": ["leak", "memory", "connection", "file handle"],
            "configuration": ["config", "environment", "setting"],
            "integration": ["api", "timeout", "connection", "network"],
            "logic_error": ["logic", "algorithm", "calculation"],
            "state_management": ["state", "cache", "stale"],
        }
        
        for pattern, keywords in patterns.items():
            if any(kw in cause_lower for kw in keywords):
                return pattern
        
        return "general"
    
    def _extract_contexts(self) -> List[str]:
        """Extract applicable contexts from the session."""
        
        # Use LLM to extract relevant contexts
        response = llm.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "Extract 3-5 context tags for when this debugging insight applies. Output JSON array of strings."},
                {"role": "user", "content": f"Problem: {self.current_session.initial_problem}\nSolution: {self.current_session.solution}"}
            ]
        )
        
        return json.loads(response.choices[0].message.content)
    
    def _vote_on_helpful_patterns(self):
        """Vote on patterns that helped in this session."""
        
        # Query what patterns we retrieved at session start
        context = self._gather_context(
            self.current_session.initial_problem,
            self.current_session.error_message
        )
        
        # Vote helpful on reflections that matched our solution
        for reflection in context["reflections"]:
            if self._is_relevant(reflection["content"], self.current_session.solution):
                aegis.vote(
                    memory_id=reflection["id"],
                    vote="helpful",
                    voter_agent_id=self.agent_id,
                    context=f"Helped debug {self.current_session.session_id}"
                )
    
    def _is_relevant(self, pattern_content: str, solution: str) -> bool:
        """Check if a pattern was relevant to the solution."""
        # Simple keyword overlap check
        pattern_words = set(pattern_content.lower().split())
        solution_words = set(solution.lower().split())
        overlap = len(pattern_words & solution_words)
        return overlap > 5
```

### Step 2: Interactive CLI

```python
def debug_cli():
    """Interactive debugging CLI."""
    
    agent = DebuggingAgent()
    
    print("🐛 Debugging Agent")
    print("=" * 50)
    
    problem = input("Describe the bug: ")
    error = input("Error message (or press Enter): ") or None
    
    # Start session
    result = agent.start_session(problem, error)
    
    print(f"\n📊 Analysis:")
    print(f"Category: {result['analysis']['category']}")
    print(f"Recommended first step: {result['analysis']['recommended_first_step']}")
    
    if result["similar_past_bugs"]:
        print(f"\n💡 Similar bugs I've seen before:")
        for bug in result["similar_past_bugs"][:3]:
            print(f"  [{bug['error_pattern']}] {bug['content'][:100]}...")
    
    print(f"\n🔍 Hypotheses to test:")
    for i, h in enumerate(result["analysis"]["hypotheses"], 1):
        print(f"  {i}. {h['hypothesis']} (confidence: {h['confidence']:.0%})")
    
    # Interactive debugging loop
    while True:
        print("\n" + "-" * 50)
        hypothesis = input("What are you testing? (or 'solved' if fixed): ")
        
        if hypothesis.lower() == "solved":
            break
        
        action = input("What did you do? ")
        result = input("What happened? ")
        success = input("Did it fix the bug? (y/n): ").lower() == "y"
        
        response = agent.record_attempt(hypothesis, action, result, success)
        
        if response["status"] == "success":
            break
        else:
            print(f"\n{response['message']}")
            for i, h in enumerate(response["next_hypotheses"], 1):
                print(f"  {i}. {h['hypothesis']}")
    
    # Record solution
    print("\n" + "=" * 50)
    print("🎉 Bug fixed! Let's record what we learned.")
    
    root_cause = input("Root cause: ")
    solution = input("Solution: ")
    insight = input("Key insight (what should we remember?): ")
    
    summary = agent.resolve_session(root_cause, solution, insight)
    
    print(f"\n✅ Session complete!")
    print(f"Reflection saved: {summary['reflection_id']}")
    print(f"This will help debug similar {summary['error_pattern']} bugs in the future.")

if __name__ == "__main__":
    debug_cli()
```

### Step 3: IDE Integration

```python
# VS Code extension example (pseudocode)
class DebuggingExtension:
    def __init__(self):
        self.agent = DebuggingAgent()
    
    def on_exception(self, exception: Exception, stack_trace: str):
        """Called when debugger hits an exception."""
        
        # Check memory for known fixes
        matches = aegis.playbook(
            query=f"{type(exception).__name__} {str(exception)}",
            agent_id="debugger",
            include_types=["reflection"],
            top_k=3
        )
        
        if matches and matches[0].effectiveness_score > 0.5:
            # Show inline suggestion
            self.show_suggestion(
                title="💡 Known Issue",
                body=f"I've seen this before:\n\n{matches[0].content}",
                confidence=matches[0].effectiveness_score
            )
        else:
            # Offer to start debugging session
            self.show_suggestion(
                title="🐛 Start Debugging Session?",
                body="I can help analyze this. Would you like to start a session?",
                action=lambda: self.start_session(exception, stack_trace)
            )
```

---

## Production Tips

### 1. Reflection Quality
```python
# Ensure reflections have minimum structure
def validate_reflection(content: str) -> bool:
    required_sections = ["ROOT CAUSE:", "SOLUTION:"]
    return all(section in content for section in required_sections)
```

### 2. Cross-Team Learning
```python
# Share high-value reflections across teams
def promote_reflection(reflection_id: str):
    reflection = aegis.get(reflection_id)
    
    if reflection.effectiveness_score > 0.7:
        # Copy to global namespace
        aegis.add(
            content=reflection.content,
            agent_id="system",
            scope="global",
            namespace="org-wide-debugging",
            memory_type="reflection",
            metadata={
                "promoted_from": reflection_id,
                "original_team": reflection.metadata.get("team")
            }
        )
```

### 3. Feedback Loop
```python
# Track if suggested fixes actually work
def track_fix_outcome(reflection_id: str, worked: bool):
    aegis.vote(
        memory_id=reflection_id,
        vote="helpful" if worked else "harmful",
        voter_agent_id="user-feedback"
    )
```

---

## Expected Outcomes

| Metric | Without Aegis | With Aegis |
|--------|---------------|------------|
| Time to first hypothesis | 10-30 min | 1-2 min |
| Repeat bug resolution | Full re-debug | Instant recall |
| Team knowledge sharing | Tribal | Systematic |
| Debugging expertise | Linear | Compounding |

---

## Next Steps

- [Recipe 5: CI/CD Memory](./05-cicd-pipeline-memory.md) - Catch bugs before they reach you
- [Recipe 3: Cross-Repo Knowledge](./03-cross-repo-knowledge.md) - Share debugging expertise across projects
