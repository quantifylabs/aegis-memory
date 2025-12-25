# Recipe 7: Codebase Onboarding Agent

**Build an AI assistant that gives new developers instant context—no more "ask Sarah, she's been here 5 years."**

| Metric | Value |
|--------|-------|
| Complexity | Beginner |
| Time to Build | 30-60 minutes |
| Agents | 1 (Onboarding Assistant) |
| Key Patterns | Cross-agent queries, Playbook retrieval, Memory scoping |

---

## The Problem

A new developer joins your team. They need to understand:
- Why is the code structured this way?
- What are the unwritten rules?
- Where are the landmines?
- Who knows what?

**What happens in reality:**

```
Day 1:   "Read the docs" (docs are 2 years outdated)
Week 1:  "Ask around" (everyone's in meetings)
Week 2:  Makes changes → breaks things → gets told "we don't do it that way"
Week 3:  Finally finds the tribal knowledge holder → absorbs context
Week 4:  Finally productive
```

**The cost is staggering:**
- Average onboarding time: 3-6 months to full productivity
- Senior engineer time spent answering repeat questions: 5+ hours/week
- Knowledge loss when employees leave: unquantifiable
- "Tribal knowledge" = single points of failure

---

## Current Solutions (And Why They Fail)

### Confluence/Notion Documentation
- **How it works**: Write everything down, hope people read it
- **The gap**: Docs go stale instantly. No one updates them. Can't answer "why" questions. No context about recent decisions.

### README Files
- **How it works**: Each repo has setup instructions
- **The gap**: Covers "what" not "why." Doesn't capture architecture decisions, team conventions, or history.

### Recorded Onboarding Sessions
- **How it works**: Record a senior engineer explaining the codebase
- **The gap**: Can't ask follow-up questions. Out of date within months. Passive learning.

### GitHub Copilot/Cursor
- **How it works**: AI suggests code based on context
- **The gap**: No memory of your team's specific patterns. Doesn't know "we tried X and it failed." No organizational context.

### Slack Search
- **How it works**: Search past conversations for answers
- **The gap**: Noise-to-signal ratio is terrible. Context scattered across 100 threads. Key decisions buried in DMs.

**The fundamental issue**: Onboarding knowledge is fragmented, outdated, and trapped in human brains. No system captures the living, evolving understanding of your codebase.

---

## The Aegis Approach

Create an **always-available AI assistant** that:

1. **Knows your codebase history** via memories from other agents (architect, engineer, reviewer)
2. **Understands recent decisions** via cross-agent queries
3. **Learns from every question** by storing Q&A as new memories
4. **Improves over time** via voting on answer usefulness

```
┌─────────────────────────────────────────────────────────────────┐
│                    NEW DEVELOPER ASKS                            │
│        "Why do we use Redis instead of Memcached?"               │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                  ONBOARDING AGENT                                │
│                                                                  │
│  Step 1: Query playbook for "Redis Memcached decision"          │
│          → Found: Architect memory from 6 months ago             │
│          → "Chose Redis for pub/sub + persistence needs"         │
│                                                                  │
│  Step 2: Query cross-agent for recent context                    │
│          → Found: Engineer memory from last week                 │
│          → "Redis cluster migration completed, 3x throughput"    │
│                                                                  │
│  Step 3: Generate contextual answer                              │
│          → Combines historical decision + recent updates         │
│                                                                  │
│  Step 4: Store this Q&A for future new hires                     │
│          → Memory: "Why Redis? Pub/sub + persistence + recent    │
│             migration gave 3x throughput"                        │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    ANSWER TO DEVELOPER                           │
│                                                                  │
│  "We chose Redis over Memcached 6 months ago because:            │
│   1. We needed pub/sub for real-time notifications               │
│   2. Persistence was required for session data                   │
│   3. Our architect evaluated both under load                     │
│                                                                  │
│   Recent update: Last week we migrated to Redis Cluster,         │
│   which gave us 3x throughput improvement.                       │
│                                                                  │
│   Related memories: [Architecture Decision Doc] [Migration PR]"  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     MEMORY SOURCES                               │
├───────────────┬───────────────┬───────────────┬─────────────────┤
│   Architect   │   Engineer    │   Reviewer    │   Past Q&A      │
│   Decisions   │   Learnings   │   Standards   │   Sessions      │
│               │               │               │                 │
│ "Why Redis"   │ "Migration    │ "Code style   │ "Prev new hire  │
│ "API design"  │  gotchas"     │  rules"       │  questions"     │
│ "DB schema"   │ "Perf tips"   │ "Review       │                 │
│               │               │  checklist"   │                 │
└───────┬───────┴───────┬───────┴───────┬───────┴────────┬────────┘
        │               │               │                │
        └───────────────┴───────────────┴────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                  ONBOARDING AGENT                                │
│                                                                  │
│  • Queries ALL agent memories (cross-agent access)              │
│  • Synthesizes answers from multiple sources                    │
│  • Stores new Q&A pairs for future queries                      │
│  • Collects feedback to improve answers                         │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      INTERFACES                                  │
├─────────────────┬─────────────────┬─────────────────────────────┤
│   Slack Bot     │   CLI Tool      │   IDE Extension             │
│   @onboard      │   onboard ask   │   Right-click → Ask         │
│   "why Redis?"  │   "why Redis?"  │   "Why this pattern?"       │
└─────────────────┴─────────────────┴─────────────────────────────┘
```

---

## Implementation

### Step 1: Basic Setup

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

# Configuration
NAMESPACE = "mycompany/backend"
ONBOARDING_AGENT = "onboarding-assistant"

# Agents this assistant can read from
SOURCE_AGENTS = ["architect", "engineer", "reviewer", "tech-lead", "devops"]
```

### Step 2: Core Onboarding Agent

```python
class OnboardingAgent:
    """AI assistant that answers codebase questions using team memory."""
    
    def __init__(self):
        self.agent_id = ONBOARDING_AGENT
    
    def answer(self, question: str, context: dict = None) -> dict:
        """Answer a question about the codebase."""
        
        # Step 1: Gather relevant memories from all sources
        memories = self._gather_context(question)
        
        # Step 2: Generate answer using LLM + memories
        answer = self._generate_answer(question, memories, context)
        
        # Step 3: Store this Q&A for future reference
        qa_memory_id = self._store_qa(question, answer, memories)
        
        return {
            "answer": answer["response"],
            "sources": answer["sources"],
            "confidence": answer["confidence"],
            "memory_id": qa_memory_id,  # For feedback
            "follow_up_questions": answer.get("follow_ups", [])
        }
    
    def _gather_context(self, question: str) -> dict:
        """Query all memory sources for relevant context."""
        
        context = {
            "playbook": [],
            "cross_agent": [],
            "past_qa": []
        }
        
        # 1. Query global playbook (strategies + reflections from all agents)
        playbook = aegis.playbook(
            query=question,
            agent_id=self.agent_id,
            include_types=["strategy", "reflection", "standard"],
            min_effectiveness=0.0,  # Include all, we'll synthesize
            top_k=10
        )
        context["playbook"] = playbook or []
        
        # 2. Query cross-agent for recent context
        cross_agent = aegis.query_cross_agent(
            query=question,
            requesting_agent_id=self.agent_id,
            target_agent_ids=SOURCE_AGENTS,
            top_k=10
        )
        context["cross_agent"] = cross_agent or []
        
        # 3. Query past Q&A sessions (our own memories)
        past_qa = aegis.query(
            query=question,
            agent_id=self.agent_id,
            top_k=5
        )
        context["past_qa"] = past_qa or []
        
        return context
    
    def _generate_answer(self, question: str, memories: dict, user_context: dict) -> dict:
        """Use LLM to synthesize answer from memories."""
        
        # Format memories for prompt
        memory_text = self._format_memories(memories)
        
        # User context (e.g., which file they're looking at)
        context_text = ""
        if user_context:
            context_text = f"\nUser is currently working on: {user_context.get('file', 'unknown')}\n"
        
        response = llm.chat.completions.create(
            model="gpt-4o",
            messages=[{
                "role": "system",
                "content": """You are a senior engineer helping onboard new team members.
                
Your job is to answer questions about the codebase using the team's collective memory.
Be specific and actionable. Cite your sources when possible.
If you're not sure, say so—don't make things up.

For each answer, provide:
1. A clear, direct answer
2. The reasoning/history behind it
3. Any caveats or recent changes
4. Suggested follow-up questions"""
            }, {
                "role": "user",
                "content": f"""Question: {question}
{context_text}
Available team memories:
{memory_text}

Respond in JSON format:
{{
    "response": "Your answer here",
    "sources": ["memory_id_1", "memory_id_2"],
    "confidence": 0.0-1.0,
    "follow_ups": ["Related question 1", "Related question 2"]
}}"""
            }],
            response_format={"type": "json_object"}
        )
        
        return json.loads(response.choices[0].message.content)
    
    def _format_memories(self, memories: dict) -> str:
        """Format memories for LLM prompt."""
        sections = []
        
        if memories["playbook"]:
            sections.append("## Team Playbook (Proven Strategies)")
            for mem in memories["playbook"]:
                score = f"[{mem.effectiveness_score:.1f}]" if hasattr(mem, 'effectiveness_score') else ""
                agent = mem.agent_id if hasattr(mem, 'agent_id') else "unknown"
                sections.append(f"- {score} ({agent}): {mem.content[:300]}...")
                sections.append(f"  ID: {mem.id}")
        
        if memories["cross_agent"]:
            sections.append("\n## Recent Team Knowledge")
            for mem in memories["cross_agent"]:
                agent = mem.agent_id if hasattr(mem, 'agent_id') else "unknown"
                date = mem.created_at.strftime("%Y-%m-%d") if hasattr(mem, 'created_at') else "unknown"
                sections.append(f"- ({agent}, {date}): {mem.content[:300]}...")
                sections.append(f"  ID: {mem.id}")
        
        if memories["past_qa"]:
            sections.append("\n## Previous Q&A Sessions")
            for mem in memories["past_qa"]:
                sections.append(f"- {mem.content[:300]}...")
                sections.append(f"  ID: {mem.id}")
        
        return "\n".join(sections) if sections else "No relevant memories found."
    
    def _store_qa(self, question: str, answer: dict, sources: dict) -> str:
        """Store Q&A for future reference."""
        
        # Create a memory of this Q&A session
        source_ids = answer.get("sources", [])
        
        result = aegis.add(
            content=f"""Q: {question}

A: {answer['response'][:500]}

Sources: {', '.join(source_ids)}
Confidence: {answer['confidence']}""",
            agent_id=self.agent_id,
            scope="global",  # Share with all future queries
            memory_type="standard",
            metadata={
                "type": "qa_session",
                "question": question,
                "source_memory_ids": source_ids,
                "confidence": answer["confidence"]
            }
        )
        
        return result.id if result else None
    
    def record_feedback(self, memory_id: str, helpful: bool, feedback: str = None):
        """Record whether an answer was helpful."""
        
        vote = "helpful" if helpful else "harmful"
        aegis.vote(
            memory_id=memory_id,
            vote=vote,
            voter_agent_id="human-feedback",
            context=feedback or f"User rated answer as {'helpful' if helpful else 'not helpful'}"
        )


# Usage
onboarding = OnboardingAgent()

# New developer asks a question
result = onboarding.answer(
    question="Why do we use Redis instead of Memcached?",
    context={"file": "src/cache/redis_client.py"}
)

print(result["answer"])
print(f"\nConfidence: {result['confidence']:.0%}")
print(f"\nYou might also want to know:")
for q in result["follow_up_questions"]:
    print(f"  - {q}")
```

### Step 3: Slack Bot Integration

```python
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

app = App(token="xoxb-your-bot-token")
onboarding = OnboardingAgent()

@app.event("app_mention")
def handle_mention(event, say):
    """Handle @onboard mentions in Slack."""
    
    question = event["text"].replace("<@YOUR_BOT_ID>", "").strip()
    
    if not question:
        say("👋 Hi! Ask me anything about the codebase. For example:\n"
            "• Why do we use Redis?\n"
            "• What's the authentication flow?\n"
            "• Where should I put new API endpoints?")
        return
    
    # Get answer
    result = onboarding.answer(question)
    
    # Format for Slack
    blocks = [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": result["answer"]}
        },
        {
            "type": "context",
            "elements": [{
                "type": "mrkdwn",
                "text": f"Confidence: {result['confidence']:.0%} • Sources: {len(result['sources'])} memories"
            }]
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "👍 Helpful"},
                    "action_id": f"helpful_{result['memory_id']}"
                },
                {
                    "type": "button", 
                    "text": {"type": "plain_text", "text": "👎 Not Helpful"},
                    "action_id": f"not_helpful_{result['memory_id']}"
                }
            ]
        }
    ]
    
    if result["follow_up_questions"]:
        follow_ups = "\n".join([f"• {q}" for q in result["follow_up_questions"]])
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Related questions:*\n{follow_ups}"}
        })
    
    say(blocks=blocks)


@app.action("helpful_*")
def handle_helpful(ack, body, action):
    ack()
    memory_id = action["action_id"].replace("helpful_", "")
    onboarding.record_feedback(memory_id, helpful=True)


@app.action("not_helpful_*")
def handle_not_helpful(ack, body, respond):
    ack()
    memory_id = action["action_id"].replace("not_helpful_", "")
    onboarding.record_feedback(memory_id, helpful=False)
    respond("Thanks for the feedback! I'll improve. What was wrong with the answer?")


if __name__ == "__main__":
    handler = SocketModeHandler(app, "xapp-your-app-token")
    handler.start()
```

### Step 4: CLI Tool

```python
#!/usr/bin/env python3
"""
CLI tool for codebase onboarding.

Usage:
    onboard ask "Why do we use Redis?"
    onboard ask "What's the auth flow?" --file src/auth/login.py
    onboard search "database migrations"
"""

import argparse
import sys
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

console = Console()
onboarding = OnboardingAgent()


def ask(question: str, file: str = None):
    """Ask a question about the codebase."""
    
    context = {"file": file} if file else None
    
    with console.status("Searching team memory..."):
        result = onboarding.answer(question, context)
    
    # Display answer
    console.print(Panel(
        Markdown(result["answer"]),
        title="Answer",
        subtitle=f"Confidence: {result['confidence']:.0%}"
    ))
    
    # Display sources
    if result["sources"]:
        console.print(f"\n[dim]Sources: {len(result['sources'])} memories referenced[/dim]")
    
    # Display follow-ups
    if result["follow_up_questions"]:
        console.print("\n[bold]You might also want to know:[/bold]")
        for q in result["follow_up_questions"]:
            console.print(f"  • {q}")
    
    # Feedback
    console.print(f"\n[dim]Was this helpful? Run: onboard feedback {result['memory_id']} --helpful[/dim]")


def search(query: str):
    """Search team memories directly."""
    
    with console.status("Searching..."):
        results = aegis.playbook(
            query=query,
            agent_id=ONBOARDING_AGENT,
            top_k=10
        )
    
    if not results:
        console.print("[yellow]No memories found for that query.[/yellow]")
        return
    
    console.print(f"\n[bold]Found {len(results)} relevant memories:[/bold]\n")
    
    for i, mem in enumerate(results, 1):
        score = f"[{mem.effectiveness_score:.1f}]" if hasattr(mem, 'effectiveness_score') else ""
        agent = mem.agent_id if hasattr(mem, 'agent_id') else "unknown"
        
        console.print(Panel(
            mem.content[:500] + ("..." if len(mem.content) > 500 else ""),
            title=f"#{i} {score} from {agent}",
        ))


def feedback(memory_id: str, helpful: bool):
    """Record feedback on an answer."""
    onboarding.record_feedback(memory_id, helpful)
    console.print("[green]Thanks for the feedback![/green]")


def main():
    parser = argparse.ArgumentParser(description="Codebase onboarding assistant")
    subparsers = parser.add_subparsers(dest="command")
    
    # ask command
    ask_parser = subparsers.add_parser("ask", help="Ask a question")
    ask_parser.add_argument("question", help="Your question")
    ask_parser.add_argument("--file", "-f", help="File you're working on")
    
    # search command
    search_parser = subparsers.add_parser("search", help="Search memories")
    search_parser.add_argument("query", help="Search query")
    
    # feedback command
    fb_parser = subparsers.add_parser("feedback", help="Provide feedback")
    fb_parser.add_argument("memory_id", help="Memory ID from previous answer")
    fb_parser.add_argument("--helpful", action="store_true")
    fb_parser.add_argument("--not-helpful", action="store_true")
    
    args = parser.parse_args()
    
    if args.command == "ask":
        ask(args.question, args.file)
    elif args.command == "search":
        search(args.query)
    elif args.command == "feedback":
        feedback(args.memory_id, args.helpful)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
```

### Step 5: Seeding Initial Knowledge

```python
def seed_initial_knowledge():
    """Seed the onboarding agent with essential knowledge.
    
    Run this once when setting up a new project.
    """
    
    essential_knowledge = [
        {
            "content": """Architecture Overview:
Our backend is a monolithic Python FastAPI application with the following layers:
- API Layer (src/api/): HTTP endpoints, request validation
- Service Layer (src/services/): Business logic
- Repository Layer (src/repositories/): Database access
- Models (src/models/): SQLAlchemy ORM models

Key principle: Dependencies flow inward. API depends on Services, Services depend on Repositories.""",
            "type": "standard",
            "metadata": {"category": "architecture", "priority": "high"}
        },
        {
            "content": """Database Conventions:
- All tables have id (UUID), created_at, updated_at columns
- Use SQLAlchemy migrations via Alembic
- Never write raw SQL in application code
- Foreign keys are named: {table}_{column}_fkey
- Indexes are named: ix_{table}_{column}""",
            "type": "standard",
            "metadata": {"category": "database", "priority": "high"}
        },
        {
            "content": """Code Style Rules:
- Type hints required on all function signatures
- Docstrings required on public functions
- Max line length: 100 characters
- Import order: stdlib, third-party, local (enforced by isort)
- Use dataclasses or Pydantic models, not plain dicts""",
            "type": "standard",
            "metadata": {"category": "style", "priority": "medium"}
        },
        {
            "content": """Testing Conventions:
- Unit tests in tests/unit/, integration tests in tests/integration/
- Use pytest fixtures, not setUp/tearDown
- Mock external services, never hit real APIs in tests
- Test file naming: test_{module}.py
- Minimum coverage: 80%""",
            "type": "standard",
            "metadata": {"category": "testing", "priority": "high"}
        },
        {
            "content": """Git Workflow:
- Branch naming: {type}/{ticket}-{description} (e.g., feat/PROJ-123-add-auth)
- Commits: conventional commits format (feat:, fix:, docs:, etc.)
- PRs require 1 approval minimum
- Squash merge to main
- Delete branches after merge""",
            "type": "standard",
            "metadata": {"category": "workflow", "priority": "medium"}
        },
        {
            "content": """Common Gotchas:
1. Don't use datetime.now() - use datetime.utcnow() for consistency
2. Redis connections must be closed explicitly in tests
3. The /health endpoint is excluded from authentication
4. File uploads go to S3, not local storage
5. Rate limiting is per-user, tracked in Redis""",
            "type": "reflection",
            "metadata": {"category": "gotchas", "priority": "high"}
        }
    ]
    
    for knowledge in essential_knowledge:
        aegis.add(
            content=knowledge["content"],
            agent_id=ONBOARDING_AGENT,
            scope="global",
            memory_type=knowledge["type"],
            metadata=knowledge["metadata"]
        )
    
    print(f"Seeded {len(essential_knowledge)} essential memories")


# Run once
# seed_initial_knowledge()
```

---

## Production Tips

### 1. Encourage Memory Creation from Other Agents
```python
# In your other agents (architect, engineer, etc.), 
# explicitly create memories that will help onboarding

# In architect agent:
aegis.add(
    content=f"""Architecture Decision: {decision_title}
    
Context: {why_we_needed_to_decide}
Options Considered: {options}
Decision: {chosen_option}
Rationale: {why_this_option}
Date: {date}""",
    agent_id="architect",
    scope="global",  # Make visible to onboarding agent
    memory_type="strategy",
    metadata={"type": "architecture_decision", "area": "caching"}
)
```

### 2. Track Popular Questions
```python
def get_popular_questions(limit: int = 10):
    """Find the most frequently asked questions."""
    
    qa_memories = aegis.query(
        query="",
        agent_id=ONBOARDING_AGENT,
        filter_metadata={"type": "qa_session"},
        top_k=1000
    )
    
    # Group by question similarity
    # (In production, use embeddings for clustering)
    questions = [m.metadata.get("question") for m in qa_memories]
    # ... cluster and count
    
    return top_questions


# Use this to create FAQ document or seed new hires
```

### 3. Confidence Calibration
```python
# Adjust confidence based on source quality
def calibrate_confidence(base_confidence: float, memories: dict) -> float:
    confidence = base_confidence
    
    # Boost if multiple sources agree
    if len(memories["cross_agent"]) > 3:
        confidence += 0.1
    
    # Boost if from high-trust agents
    trusted_agents = ["architect", "tech-lead"]
    trusted_sources = [m for m in memories["cross_agent"] 
                       if m.agent_id in trusted_agents]
    if trusted_sources:
        confidence += 0.1
    
    # Reduce if sources are old
    recent_threshold = datetime.now() - timedelta(days=90)
    old_sources = [m for m in memories["cross_agent"] 
                   if m.created_at < recent_threshold]
    if len(old_sources) == len(memories["cross_agent"]):
        confidence -= 0.2
    
    return min(max(confidence, 0.0), 1.0)
```

### 4. Handle "I Don't Know"
```python
def answer_with_uncertainty(question: str, memories: dict) -> dict:
    """Be honest when we don't have enough information."""
    
    if not memories["playbook"] and not memories["cross_agent"]:
        return {
            "response": f"""I don't have information about this in team memory yet.

Here's what you can do:
1. Ask in #engineering Slack channel
2. Check the codebase for comments/docs
3. Look at recent PRs related to this area

Once you find the answer, let me know and I'll remember it for future new hires!""",
            "confidence": 0.0,
            "sources": [],
            "follow_ups": []
        }
    
    # ... normal answer generation
```

---

## Expected Outcomes

| Metric | Before Aegis | After Aegis |
|--------|--------------|-------------|
| Time to first PR | 5-7 days | 1-2 days |
| Questions to senior engineers | 10+/week | 2-3/week |
| Repeat questions (same question, different person) | High | Near zero |
| Knowledge captured when employees leave | ~10% | ~80% |
| Onboarding satisfaction score | 3.2/5 | 4.6/5 |

---

## Example Interaction

```
Developer: @onboard Why do we have both User and Account models?

Onboarding Agent: Great question! This is a common source of confusion.

**The Short Answer:**
- `User` = authentication identity (email, password hash, OAuth tokens)
- `Account` = business entity (billing, subscription, settings)

**The History:**
This separation was an architecture decision made in Q2 2024 (ADR-015). 
Originally we had a single User model, but we needed to support:
1. Multiple users per account (teams)
2. SSO where one person has multiple identities
3. Separate billing from authentication

**In Practice:**
- Login/signup → User model
- Billing, settings, team management → Account model
- Every User belongs_to one Account
- An Account has_many Users

**Gotcha:**
Don't store business data on User. If you need to track something 
per-organization, it goes on Account.

Confidence: 92% • Sources: architect decision, engineer learnings

---
*Related questions:*
• How does SSO work with this model?
• Where do team permissions live?
• How do I add a new field to Account?

[👍 Helpful] [👎 Not Helpful]
```

---

## Next Steps

- **VS Code Extension**: Right-click on any code → "Ask about this"
- **Auto-capture from PRs**: Extract knowledge from PR descriptions and reviews
- **Personalization**: Track what each new hire has already learned
- **Knowledge gaps**: Identify questions that have no good answers

See [Recipe 8: Smallville-Style NPC Coordination](./08-npc-coordination.md) for applying similar memory patterns to game AI.
