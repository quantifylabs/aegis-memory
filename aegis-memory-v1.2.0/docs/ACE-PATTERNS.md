# Aegis ACE Patterns Guide

## Executive Summary

This guide documents how Aegis implements patterns from two breakthrough research papers:

1. **ACE Paper** (Stanford/SambaNova): "Agentic Context Engineering" - treats contexts as evolving playbooks that accumulate strategies over time
2. **Anthropic's Long-Running Agent Harnesses**: Solving the multi-context-window problem for agents that work across sessions

**Key Insight**: Both papers demonstrate that **structured, incremental context evolution** dramatically outperforms static prompts or monolithic rewrites. ACE achieved +17.1% improvement on agent benchmarks by structuring how memory accumulates.

---

## The Problems These Patterns Solve

### Problem 1: Context Collapse

When an LLM rewrites its entire context, it can collapse valuable accumulated knowledge:

```
Step 60: 18,282 tokens → Accuracy 66.7%
Step 61: 122 tokens → Accuracy 57.1% (COLLAPSED!)
```

**Aegis Solution**: Incremental delta updates that never rewrite the full context.

### Problem 2: Brevity Bias

Prompt optimizers compress away domain-specific heuristics for "concise" instructions, losing critical task-specific knowledge.

**Aegis Solution**: Memory types (reflection, strategy) that preserve detailed insights.

### Problem 3: Premature Victory

Agents declare tasks complete without proper verification.

**Aegis Solution**: Feature tracking with explicit pass/fail status.

### Problem 4: Lost Progress Between Sessions

Each new context window starts fresh with no memory of previous work.

**Aegis Solution**: Session progress tracking that persists between context windows.

---

## Pattern 1: Memory Voting (Self-Improvement)

ACE's key insight: track which memories were helpful vs harmful for completing tasks.

### Why It Works

The paper found that memories with positive effectiveness scores (`helpful - harmful / total`) consistently improve task performance. By voting on memories, agents learn what strategies actually work.

### Implementation

```python
from aegis_memory import AegisClient

client = AegisClient(api_key="...")

# After successfully using a strategy
client.vote(
    memory_id=strategy.id,
    vote="helpful",
    voter_agent_id="executor",
    context="Successfully paginated through all API results",
    task_id="task-12345"
)

# After a strategy caused an error
client.vote(
    memory_id=strategy.id,
    vote="harmful",
    voter_agent_id="executor",
    context="Caused infinite loop - range(10) wasn't enough pages",
    task_id="task-12345"
)
```

### Querying by Effectiveness

```python
# Only get well-rated strategies
strategies = client.playbook(
    query="API pagination handling",
    agent_id="executor",
    min_effectiveness=0.3  # Filter by (helpful-harmful)/(total+1) > 0.3
)
```

### Best Practices

1. **Vote immediately after task completion** - context is fresh
2. **Include context** - explains why it was helpful/harmful
3. **Vote from the executing agent** - the one that actually used the memory
4. **Set min_effectiveness thresholds** - filter out low-quality strategies

---

## Pattern 2: Incremental Delta Updates

ACE's breakthrough: never rewrite the full context. Use atomic, localized updates.

### Why It Works

The paper showed that monolithic rewrites cause "context collapse" where an LLM accidentally compresses away valuable information. Delta updates:
- Only modify what needs to change
- Preserve accumulated knowledge
- Enable parallel updates
- Reduce latency by 86.9%

### Implementation

```python
# Apply multiple atomic updates
result = client.delta([
    # Add a new strategy
    {
        "type": "add",
        "content": "For pagination, always use while True loop instead of range(n)",
        "memory_type": "strategy",
        "agent_id": "reflector",
        "scope": "global"
    },
    # Update metadata on existing memory
    {
        "type": "update",
        "memory_id": "abc123",
        "metadata_patch": {
            "last_used": "2024-01-15",
            "use_count": 5
        }
    },
    # Deprecate outdated strategy (soft delete)
    {
        "type": "deprecate",
        "memory_id": "old-pagination-strategy",
        "superseded_by": None,  # Will link to new strategy
        "deprecation_reason": "Caused incomplete data collection"
    }
])
```

### Operation Types

| Operation | Purpose | Key Fields |
|-----------|---------|------------|
| `add` | Create new memory | content, memory_type, agent_id, scope |
| `update` | Modify metadata | memory_id, metadata_patch |
| `deprecate` | Soft-delete (preserve history) | memory_id, superseded_by, deprecation_reason |

### Best Practices

1. **Never delete, always deprecate** - preserves learning history
2. **Link superseded memories** - shows evolution of understanding
3. **Batch related updates** - atomic operations
4. **Use appropriate memory types** - strategy, reflection, standard

---

## Pattern 3: Reflection Memories

ACE Reflector pattern: extract actionable insights from task trajectories.

### Why It Works

The ACE paper's Reflector component analyzes success/failure trajectories and extracts reusable lessons. These become high-value memories that prevent future mistakes.

### Reflection Structure

```python
client.reflection(
    # What was learned
    content="When identifying roommates, always use Phone app contacts via "
            "apis.phone.search_contacts(). Never rely on Venmo transaction "
            "descriptions - they are unreliable and cause incorrect totals.",
    
    agent_id="reflector",
    
    # Link to the source task
    source_trajectory_id="task-12345",
    
    # Categorize the error type
    error_pattern="identity_resolution",
    
    # The correct approach
    correct_approach="First authenticate with Phone app, use search_contacts() "
                     "to find contacts with 'roommate' relationship, then filter "
                     "Venmo transactions by those specific emails.",
    
    # When this applies
    applicable_contexts=["financial_tasks", "contact_tasks", "venmo_queries"],
    
    # Make available to all agents
    scope="global"
)
```

### Error Pattern Taxonomy

Define consistent error patterns for your domain:

```python
ERROR_PATTERNS = {
    "identity_resolution": "Wrong source used to identify entities",
    "pagination_incomplete": "Fixed iteration instead of while-True loop",
    "auth_missing": "Forgot to authenticate before API call",
    "filter_wrong": "Incorrect filter (timeframe/direction/identity)",
    "format_mismatch": "Output format didn't match API schema",
}
```

### Workflow: Reflector Agent

```python
async def reflect_on_task(task_id: str, success: bool, trajectory: str, error: str = None):
    """
    Called after each task to extract learnings.
    """
    if success:
        # Extract what worked well
        prompt = f"""
        Task completed successfully. Extract reusable strategies.
        
        Trajectory:
        {trajectory}
        
        What specific techniques made this work? Focus on:
        - API usage patterns
        - Data handling approaches
        - Verification steps
        """
    else:
        # Diagnose what went wrong
        prompt = f"""
        Task failed. Analyze and extract lessons.
        
        Trajectory:
        {trajectory}
        
        Error:
        {error}
        
        Identify:
        - error_pattern: What category of mistake?
        - root_cause: Why did this happen?
        - correct_approach: What should be done instead?
        """
    
    analysis = await llm.complete(prompt)
    
    # Create reflection memory
    client.reflection(
        content=analysis.key_insight,
        agent_id="reflector",
        source_trajectory_id=task_id,
        error_pattern=analysis.error_pattern,
        correct_approach=analysis.correct_approach,
        applicable_contexts=analysis.contexts
    )
```

---

## Pattern 4: Session Progress Tracking

Anthropic's `claude-progress.txt` pattern, structured and queryable.

### Why It Works

When an agent starts with a fresh context window, it needs to quickly understand:
- What's been completed
- What's in progress
- What's blocked
- What's next

Without this, agents waste tokens rediscovering state.

### Implementation

```python
# Create session at start of project
session = client.progress.create(
    session_id="build-dashboard-v2",
    agent_id="coding-agent",
    namespace="project-alpha"
)

# Update as work progresses
client.progress.update(
    session_id="build-dashboard-v2",
    completed=["auth", "routing", "api-client"],
    in_progress="dashboard-components",
    next=["data-visualization", "testing", "deployment"],
    blocked=[
        {"item": "payment-integration", "reason": "Waiting for Stripe API keys"}
    ],
    last_action="Implemented JWT token refresh logic in api-client module",
    summary="Core infrastructure complete. Starting UI components."
)
```

### Session Start Protocol

Every new context window should:

```python
async def initialize_session(session_id: str):
    """
    Standard initialization for new context window.
    Matches Anthropic's recommended flow.
    """
    # 1. Get current working directory
    cwd = os.getcwd()
    
    # 2. Read progress
    progress = client.progress.get(session_id)
    print(f"Status: {progress.status}")
    print(f"Completed: {progress.completed_count}/{progress.total_items}")
    print(f"In Progress: {progress.in_progress_item}")
    print(f"Last Action: {progress.last_action}")
    
    # 3. Get relevant strategies
    if progress.in_progress_item:
        strategies = client.playbook(
            query=progress.in_progress_item,
            agent_id="coding-agent"
        )
    
    # 4. Run verification test
    await run_basic_tests()
    
    # 5. Continue work
    if progress.in_progress_item:
        await work_on(progress.in_progress_item)
    elif progress.next_items:
        next_task = progress.next_items[0]
        client.progress.update(session_id, in_progress=next_task)
        await work_on(next_task)
```

---

## Pattern 5: Feature Tracking

Anthropic's feature list pattern to prevent premature victory.

### Why It Works

The paper found that agents often declare tasks complete without proper verification. A structured feature list with explicit pass/fail status forces verification.

### Implementation

```python
# Initialize features at project start
features = [
    {
        "feature_id": "new-chat",
        "description": "User can create a new chat, type a message, and receive AI response",
        "category": "functional",
        "test_steps": [
            "Navigate to main interface",
            "Click 'New Chat' button",
            "Verify new conversation created",
            "Type message and press Enter",
            "Verify AI response appears"
        ]
    },
    {
        "feature_id": "dark-mode",
        "description": "User can toggle dark mode in settings",
        "category": "ui",
        "test_steps": [
            "Navigate to settings",
            "Toggle dark mode switch",
            "Verify UI colors change",
            "Refresh page and verify persistence"
        ]
    }
]

for f in features:
    client.features.create(**f)

# After implementing, don't just mark complete!
# Run the test steps first
async def verify_and_complete(feature_id: str, verifier_agent: str):
    feature = client.features.get(feature_id)
    
    for step in feature.test_steps:
        result = await run_test_step(step)
        if not result.passed:
            client.features.mark_failed(
                feature_id,
                reason=f"Failed at: {step}. Error: {result.error}"
            )
            return False
    
    # All steps passed
    client.features.mark_complete(feature_id, verified_by=verifier_agent)
    return True
```

### Feature Status Flow

```
NOT_STARTED → IN_PROGRESS → TESTING → COMPLETE
                    ↓           ↓
                 BLOCKED     FAILED
```

### Checking Progress

```python
# Get status summary
status = client.features.list(session_id="build-dashboard-v2")

print(f"Total: {status['total']}")
print(f"Passing: {status['passing']}")
print(f"Failing: {status['failing']}")
print(f"In Progress: {status['in_progress']}")

# Get incomplete features
incomplete = [f for f in status['features'] if not f.passes]
for f in incomplete:
    print(f"❌ {f.feature_id}: {f.status}")
```

---

## Pattern 6: Playbook Queries

ACE's evolving playbook pattern for context retrieval.

### Why It Works

Instead of fixed prompts, ACE treats context as an "evolving playbook" that accumulates strategies. The playbook query retrieves relevant entries ranked by:
- Semantic similarity to current task
- Effectiveness score from voting history
- Recency

### Implementation

```python
# Before starting a task, query for relevant strategies
strategies = client.playbook(
    query="Split bill among roommates using Venmo",
    agent_id="executor",
    include_types=["strategy", "reflection"],
    top_k=10,
    min_effectiveness=0.2
)

# Format for prompt injection
playbook_text = "\n\n".join([
    f"[{s.effectiveness_score:.2f}] {s.content}"
    for s in strategies
])

prompt = f"""
PLAYBOOK - Apply these proven strategies:
{playbook_text}

Task: {task_description}
"""
```

### Playbook in Agent Loop

```python
async def agent_loop(task: str):
    # 1. Query playbook before starting
    strategies = client.playbook(task, agent_id="executor")
    
    # 2. Execute with playbook context
    result = await execute_with_playbook(task, strategies)
    
    # 3. Vote on which strategies helped
    for s in strategies:
        if s.id in result.helpful_strategy_ids:
            client.vote(s.id, "helpful", voter_agent_id="executor")
        elif s.id in result.harmful_strategy_ids:
            client.vote(s.id, "harmful", voter_agent_id="executor",
                       context=result.error_context)
    
    # 4. Extract new reflections if failed
    if not result.success:
        client.reflection(
            content=result.lesson_learned,
            agent_id="reflector",
            error_pattern=result.error_pattern
        )
```

---

## Complete Workflow: ACE-Enhanced Agent

Here's how all patterns work together:

```python
from aegis_memory import AegisClient

client = AegisClient(api_key="...")

class ACEAgent:
    def __init__(self, agent_id: str, session_id: str):
        self.agent_id = agent_id
        self.session_id = session_id
    
    async def initialize(self):
        """Called at start of each context window."""
        # 1. Load session progress
        progress = client.progress.get(self.session_id)
        print(f"Resuming: {progress.summary}")
        print(f"Last action: {progress.last_action}")
        
        # 2. Check feature status
        features = client.features.list(session_id=self.session_id)
        incomplete = [f for f in features['features'] if not f.passes]
        print(f"Incomplete features: {len(incomplete)}/{features['total']}")
        
        # 3. Run verification tests
        if not await self.run_basic_tests():
            print("⚠️ Basic tests failing - fixing first")
            await self.fix_broken_state()
        
        # 4. Continue work
        if progress.in_progress_item:
            await self.work_on(progress.in_progress_item)
        elif incomplete:
            next_feature = incomplete[0].feature_id
            await self.work_on(next_feature)
    
    async def work_on(self, task: str):
        """Work on a single task with playbook support."""
        # Update progress
        client.progress.update(
            self.session_id,
            in_progress=task,
            last_action=f"Starting work on {task}"
        )
        
        # Query playbook for relevant strategies
        strategies = client.playbook(task, agent_id=self.agent_id)
        
        try:
            # Execute task with strategies
            result = await self.execute(task, strategies)
            
            # Vote on strategies
            for s in strategies:
                if s.id in result.used_strategies:
                    client.vote(s.id, "helpful", voter_agent_id=self.agent_id)
            
            # Update progress
            client.progress.update(
                self.session_id,
                completed=[task],
                in_progress=None,
                last_action=f"Completed {task}"
            )
            
            # Mark feature complete if applicable
            await self.verify_feature(task)
            
        except Exception as e:
            # Record failure
            client.progress.update(
                self.session_id,
                last_action=f"Failed on {task}: {str(e)}"
            )
            
            # Create reflection from failure
            client.reflection(
                content=f"Task '{task}' failed: {str(e)}",
                agent_id="reflector",
                error_pattern=self.classify_error(e),
                correct_approach=self.suggest_fix(e)
            )
            
            # Vote harmful on strategies that didn't help
            for s in strategies:
                client.vote(s.id, "harmful", voter_agent_id=self.agent_id,
                           context=str(e))
    
    async def verify_feature(self, feature_id: str):
        """Verify feature with test steps before marking complete."""
        feature = client.features.get(feature_id)
        if not feature:
            return
        
        for step in feature.test_steps:
            if not await self.run_test(step):
                client.features.update(
                    feature_id,
                    status="testing",
                    failure_reason=f"Failed: {step}"
                )
                return
        
        client.features.mark_complete(feature_id, verified_by=self.agent_id)
    
    async def finalize_session(self):
        """Called at end of context window."""
        progress = client.progress.get(self.session_id)
        
        # Write summary for next session
        client.progress.update(
            self.session_id,
            summary=await self.generate_summary(),
            last_action="Session ended cleanly"
        )
        
        # Commit any pending work to git
        await self.git_commit("Session checkpoint")
```

---

## Performance Impact

Based on the ACE paper's benchmarks:

| Metric | Without ACE | With ACE | Improvement |
|--------|-------------|----------|-------------|
| Agent Tasks (AppWorld) | 42.4% | 59.5% | **+17.1%** |
| Financial Analysis | 70.7% | 78.3% | **+7.6%** |
| Adaptation Latency | Baseline | -86.9% | **86.9% faster** |
| Token Cost | Baseline | -83.6% | **83.6% cheaper** |

---

## Quick Reference

### Endpoints

| Endpoint | Purpose |
|----------|---------|
| `POST /ace/vote/{id}` | Vote on memory usefulness |
| `POST /ace/delta` | Apply incremental updates |
| `POST /ace/reflection` | Create reflection memory |
| `POST /ace/playbook` | Query strategies/reflections |
| `POST /ace/session` | Create session |
| `PATCH /ace/session/{id}` | Update progress |
| `POST /ace/feature` | Create feature |
| `PATCH /ace/feature/{id}` | Update feature status |

### Memory Types

| Type | Purpose | Scope Default |
|------|---------|---------------|
| `standard` | Facts, preferences | agent-private |
| `strategy` | Reusable patterns | global |
| `reflection` | Lessons from failures | global |
| `progress` | Session state | agent-private |
| `feature` | Feature tracking | global |

### Effectiveness Score

```python
score = (helpful - harmful) / (helpful + harmful + 1)
# Range: -1.0 to 1.0
# Positive = net helpful
# Negative = net harmful
```

---

## References

1. **ACE Paper**: Zhang et al. "Agentic Context Engineering: Evolving Contexts for Self-Improving Language Models" (arXiv:2510.04618, Oct 2025)

2. **Anthropic Blog**: "Effective Harnesses for Long-Running Agents" (anthropic.com/engineering, 2025)

3. **Dynamic Cheatsheet**: Suzgun et al. "Dynamic Cheatsheet: Test-Time Learning with Adaptive Memory" (2025)
