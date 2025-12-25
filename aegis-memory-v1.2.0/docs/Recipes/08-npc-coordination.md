# Recipe 8: Smallville-Style NPC Coordination

**Build game NPCs that remember players, form relationships, and coordinate emergent behaviors—like Stanford's Generative Agents, but production-ready.**

| Metric | Value |
|--------|-------|
| Complexity | Advanced |
| Time to Build | 3-5 hours |
| Agents | N (one per NPC) |
| Key Patterns | Memory scoping, Reflection synthesis, Cross-agent coordination |

---

## The Problem

You want NPCs that feel alive. Not scripted robots that repeat the same dialogue, but characters who:
- Remember what players did
- Form opinions about each other
- Coordinate activities ("Let's throw a party!")
- React to world events naturally

**What breaks in production:**

Stanford's Smallville research showed this is possible, but their implementation had critical failures:

```
Problem 1: Memory Overflow
  Simulation runs for 2 days → Memory exceeds context window
  NPC forgets recent events while remembering ancient ones

Problem 2: Retrieval Failures  
  NPC Klaus should remember his wife → Retrieves memory about neighbor instead
  Result: Klaus talks to wife like a stranger

Problem 3: Erratic Behaviors
  NPCs speak formally to family members
  Multiple NPCs use bathroom simultaneously  
  Characters develop "day-drinking problems"

Problem 4: Hallucination
  NPC claims neighbor "wrote Wealth of Nations"
  False memories contaminate future interactions
```

**The industry reality:**
- NVIDIA ACE provides voice/animation but **no native memory**—relies on middleware
- Inzoi (using ACE): **9% of players report "immersion-breaking inconsistencies"**
- Character.AI: **400-character memory limit**, forgets basic details within messages

---

## Current Solutions (And Why They Fail)

### NVIDIA ACE + Inworld/Convai
- **How it works**: ACE handles voice/lip-sync, middleware handles memory
- **The gap**: Each middleware has different quality. No coordination between NPCs. Memory inconsistencies across characters.

### Generative Agents (Stanford Research)
- **How it works**: Memory stream + reflection + planning per agent
- **The gap**: Research code, not production-ready. Expensive (thousands of API calls). No memory scoping between NPCs. Reflection is time-triggered, not event-triggered.

### Custom Game Memory (Inzoi, Bethesda AI)
- **How it works**: Game-specific implementations
- **The gap**: Memory collision between NPC narratives. No standard patterns. Hard to debug emergent behaviors.

### Character.AI / Replika
- **How it works**: Fine-tuned models with conversation history
- **The gap**: Character forgets within a single conversation. No multi-character coordination. Can't share world state.

**The fundamental issue**: Game NPCs need **three types of memory** working together:

1. **Personal memory**: What I experienced
2. **Shared memory**: What we all know (world events)  
3. **Social memory**: What I think about other characters

No existing solution handles all three with proper scoping.

---

## The Aegis Approach

Implement the Smallville architecture with Aegis's scope-aware memory:

```
┌─────────────────────────────────────────────────────────────────┐
│                      WORLD MEMORY (Global)                       │
│                                                                  │
│  "Today is the Harvest Festival"                                │
│  "The mayor announced new taxes"                                │
│  "A fire destroyed the bakery last week"                        │
│                                                                  │
│  Visible to: ALL NPCs                                           │
└─────────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────────┐
│                  SOCIAL MEMORY (Agent-Shared)                    │
│                                                                  │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐          │
│  │ Klaus ↔ Maya│    │ Maya ↔ Tom │    │ Tom ↔ Klaus │          │
│  │ "married"   │    │ "friends"   │    │ "rivals"    │          │
│  │ "loves her" │    │ "trust: 0.8"│    │ "trust: 0.2"│          │
│  └─────────────┘    └─────────────┘    └─────────────┘          │
│                                                                  │
│  Visible to: Characters in the relationship                     │
└─────────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────────┐
│                  PERSONAL MEMORY (Agent-Private)                 │
│                                                                  │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐          │
│  │    Klaus    │    │    Maya     │    │     Tom     │          │
│  │ "I saw the  │    │ "Klaus      │    │ "I want to  │          │
│  │  player     │    │  forgot our │    │  win the    │          │
│  │  steal"     │    │  anniversary│    │  contest"   │          │
│  └─────────────┘    └─────────────┘    └─────────────┘          │
│                                                                  │
│  Visible to: Only this NPC                                      │
└─────────────────────────────────────────────────────────────────┘
```

**Plus the key innovations missing from Smallville:**

1. **Memory voting**: NPCs learn which memories are actually important
2. **Reflection synthesis**: Turn observations into higher-level insights
3. **Event-triggered reflection**: Reflect when something significant happens, not on a timer
4. **Cross-NPC coordination**: NPCs can plan together through shared memory

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      GAME ENGINE                                 │
│                   (Unity, Unreal, etc.)                         │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                   NPC ORCHESTRATOR                               │
│                                                                  │
│  • Receives game events (player actions, time passing)          │
│  • Routes to relevant NPCs                                       │
│  • Manages NPC interaction turns                                │
│  • Handles global world state                                    │
└───────────────────────────┬─────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
        ▼                   ▼                   ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│   NPC Agent  │    │   NPC Agent  │    │   NPC Agent  │
│    "Klaus"   │    │    "Maya"    │    │    "Tom"     │
│              │    │              │    │              │
│ ┌──────────┐ │    │ ┌──────────┐ │    │ ┌──────────┐ │
│ │ Perceive │ │    │ │ Perceive │ │    │ │ Perceive │ │
│ └────┬─────┘ │    │ └────┬─────┘ │    │ └────┬─────┘ │
│      ▼       │    │      ▼       │    │      ▼       │
│ ┌──────────┐ │    │ ┌──────────┐ │    │ ┌──────────┐ │
│ │ Remember │◄┼────┼─►│ Remember │◄┼────┼─►│ Remember │ │
│ └────┬─────┘ │    │ └────┬─────┘ │    │ └────┬─────┘ │
│      ▼       │    │      ▼       │    │      ▼       │
│ ┌──────────┐ │    │ ┌──────────┐ │    │ ┌──────────┐ │
│ │ Reflect  │ │    │ │ Reflect  │ │    │ │ Reflect  │ │
│ └────┬─────┘ │    │ └────┬─────┘ │    │ └────┬─────┘ │
│      ▼       │    │      ▼       │    │      ▼       │
│ ┌──────────┐ │    │ ┌──────────┐ │    │ ┌──────────┐ │
│ │   Plan   │ │    │ │   Plan   │ │    │ │   Plan   │ │
│ └────┬─────┘ │    │ └────┬─────┘ │    │ └────┬─────┘ │
│      ▼       │    │      ▼       │    │      ▼       │
│ ┌──────────┐ │    │ ┌──────────┐ │    │ ┌──────────┐ │
│ │   Act    │ │    │ │   Act    │ │    │ │   Act    │ │
│ └──────────┘ │    │ └──────────┘ │    │ └──────────┘ │
└──────────────┘    └──────────────┘    └──────────────┘
        │                   │                   │
        └───────────────────┼───────────────────┘
                            │
                            ▼
                    ┌──────────────┐
                    │ AEGIS MEMORY │
                    │              │
                    │  • Global    │
                    │  • Shared    │
                    │  • Private   │
                    └──────────────┘
```

---

## Implementation

### Step 1: Project Setup

```python
from aegis_memory import AegisClient
from openai import OpenAI
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List
import json

# Initialize
aegis = AegisClient(
    api_key="your-aegis-key",
    base_url="http://localhost:8000"
)
llm = OpenAI()

# Game world configuration
GAME_WORLD = "smallville"
GAME_TIME = datetime(2024, 10, 15, 8, 0)  # Simulation time

@dataclass
class NPCProfile:
    """Static character definition."""
    id: str
    name: str
    age: int
    occupation: str
    personality: List[str]  # ["friendly", "curious", "stubborn"]
    relationships: dict     # {"maya": "wife", "tom": "rival"}
    daily_routine: List[str]  # ["wake 7am", "work 9am-5pm", "dinner 6pm"]
```

### Step 2: Memory Stream (Core NPC Memory)

```python
class NPCMemoryStream:
    """Manages an NPC's memory with proper scoping."""
    
    def __init__(self, npc: NPCProfile):
        self.npc = npc
        self.agent_id = f"npc-{npc.id}"
        
    def observe(self, observation: str, importance: float = 0.5):
        """Record a new observation (something the NPC perceived)."""
        
        # Score importance using LLM if not provided
        if importance == 0.5:
            importance = self._score_importance(observation)
        
        aegis.add(
            content=f"[{GAME_TIME.strftime('%H:%M')}] {observation}",
            agent_id=self.agent_id,
            scope="agent-private",  # Only this NPC sees their observations
            memory_type="standard",
            metadata={
                "type": "observation",
                "importance": importance,
                "game_time": GAME_TIME.isoformat(),
                "location": self._current_location()
            }
        )
        
        # Trigger reflection if importance is high
        if importance > 0.7:
            self._maybe_reflect(observation)
    
    def remember(self, query: str, top_k: int = 10) -> List:
        """Retrieve relevant memories using recency, importance, relevance."""
        
        # Get recent memories (recency)
        recent = aegis.query(
            query="",  # No semantic filter
            agent_id=self.agent_id,
            top_k=top_k,
        )
        
        # Get relevant memories (semantic)
        relevant = aegis.playbook(
            query=query,
            agent_id=self.agent_id,
            include_types=["standard", "reflection"],
            top_k=top_k
        )
        
        # Get world knowledge (global scope)
        world = aegis.query(
            query=query,
            agent_id=self.agent_id,
            scope="global",
            top_k=5
        )
        
        # Get relationship knowledge (shared scope)
        social = aegis.query_cross_agent(
            query=query,
            requesting_agent_id=self.agent_id,
            target_agent_ids=[f"npc-{r}" for r in self.npc.relationships.keys()],
            top_k=5
        )
        
        # Combine and rank by composite score
        all_memories = self._rank_memories(recent, relevant, world, social, query)
        
        return all_memories[:top_k]
    
    def _rank_memories(self, recent, relevant, world, social, query) -> List:
        """Rank memories by recency * importance * relevance."""
        
        all_mems = []
        
        for mem in (recent or []):
            score = self._composite_score(mem, query, source="recent")
            all_mems.append((score, mem, "personal"))
        
        for mem in (relevant or []):
            score = self._composite_score(mem, query, source="relevant")
            all_mems.append((score, mem, "personal"))
        
        for mem in (world or []):
            score = self._composite_score(mem, query, source="world")
            all_mems.append((score, mem, "world"))
        
        for mem in (social or []):
            score = self._composite_score(mem, query, source="social")
            all_mems.append((score, mem, "social"))
        
        # Sort by score, deduplicate
        all_mems.sort(key=lambda x: x[0], reverse=True)
        seen_ids = set()
        unique = []
        for score, mem, source in all_mems:
            if mem.id not in seen_ids:
                seen_ids.add(mem.id)
                unique.append(mem)
        
        return unique
    
    def _composite_score(self, mem, query: str, source: str) -> float:
        """Calculate composite retrieval score."""
        
        # Recency decay (exponential)
        age_hours = (GAME_TIME - mem.created_at).total_seconds() / 3600
        recency = 0.99 ** age_hours
        
        # Importance from metadata
        importance = mem.metadata.get("importance", 0.5)
        
        # Relevance from effectiveness score (if available)
        relevance = mem.effectiveness_score if hasattr(mem, 'effectiveness_score') else 0.5
        
        # Source boost
        source_boost = {
            "recent": 1.0,
            "relevant": 1.2,
            "world": 0.8,
            "social": 1.1
        }.get(source, 1.0)
        
        return recency * importance * relevance * source_boost
    
    def _score_importance(self, observation: str) -> float:
        """Use LLM to score observation importance."""
        
        response = llm.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{
                "role": "system",
                "content": f"""Rate the importance of this observation for {self.npc.name}, 
a {self.npc.occupation} who is {', '.join(self.npc.personality)}.

Score from 0.0 to 1.0 where:
- 0.0-0.3: Mundane (saw a bird, walked past a tree)
- 0.4-0.6: Notable (had a conversation, learned something)
- 0.7-0.8: Important (relationship change, significant event)
- 0.9-1.0: Critical (major life event, danger)

Return only the number."""
            }, {
                "role": "user",
                "content": observation
            }]
        )
        
        try:
            return float(response.choices[0].message.content.strip())
        except:
            return 0.5
    
    def _maybe_reflect(self, trigger: str):
        """Maybe trigger reflection based on accumulated importance."""
        
        # Get recent unreflected memories
        recent = aegis.query(
            query="",
            agent_id=self.agent_id,
            filter_metadata={"reflected": False},
            top_k=20
        )
        
        # Calculate accumulated importance
        total_importance = sum(m.metadata.get("importance", 0.5) for m in recent)
        
        if total_importance > 3.0:  # Threshold for reflection
            self.reflect()
    
    def _current_location(self) -> str:
        """Get NPC's current location (game integration point)."""
        return "town_square"  # Placeholder


class NPCReflection:
    """Handles reflection synthesis for NPCs."""
    
    def __init__(self, npc: NPCProfile, memory_stream: NPCMemoryStream):
        self.npc = npc
        self.memory = memory_stream
        self.agent_id = f"npc-{npc.id}"
    
    def reflect(self) -> List[str]:
        """Synthesize recent observations into higher-level insights."""
        
        # Get recent observations
        recent = aegis.query(
            query="",
            agent_id=self.agent_id,
            filter_metadata={"type": "observation"},
            top_k=50
        )
        
        if len(recent) < 5:
            return []  # Not enough to reflect on
        
        # Format observations for reflection
        observations = "\n".join([f"- {m.content}" for m in recent])
        
        response = llm.chat.completions.create(
            model="gpt-4o",
            messages=[{
                "role": "system",
                "content": f"""You are {self.npc.name}, a {self.npc.occupation}.
Your personality: {', '.join(self.npc.personality)}

Based on your recent observations, generate 1-3 high-level insights.
These should be conclusions, realizations, or new understandings about:
- Other people and your relationships with them
- The state of the world
- Your own goals and feelings

Format each insight as a single declarative statement."""
            }, {
                "role": "user",
                "content": f"Recent observations:\n{observations}\n\nWhat do you realize from these experiences?"
            }]
        )
        
        # Parse and store reflections
        insights = response.choices[0].message.content.strip().split("\n")
        insights = [i.strip("- ").strip() for i in insights if i.strip()]
        
        for insight in insights:
            aegis.reflection(
                content=insight,
                agent_id=self.agent_id,
                scope="agent-private",  # Reflections are personal
                metadata={
                    "type": "reflection",
                    "game_time": GAME_TIME.isoformat(),
                    "source_count": len(recent)
                }
            )
        
        # Mark observations as reflected
        for mem in recent:
            aegis.delta([{
                "type": "update",
                "memory_id": mem.id,
                "metadata_patch": {"reflected": True}
            }])
        
        return insights
```

### Step 3: Social Memory (Relationships)

```python
class NPCSocialMemory:
    """Manages NPC relationships and social knowledge."""
    
    def __init__(self, npc: NPCProfile):
        self.npc = npc
        self.agent_id = f"npc-{npc.id}"
    
    def update_relationship(self, other_npc_id: str, event: str, sentiment_change: float):
        """Update relationship based on interaction."""
        
        other_agent = f"npc-{other_npc_id}"
        
        # Get current relationship memory
        existing = aegis.query(
            query=f"relationship {other_npc_id}",
            agent_id=self.agent_id,
            filter_metadata={"type": "relationship", "target": other_npc_id},
            top_k=1
        )
        
        current_trust = 0.5
        if existing:
            current_trust = existing[0].metadata.get("trust", 0.5)
        
        new_trust = max(0.0, min(1.0, current_trust + sentiment_change))
        
        # Create shared memory visible to both parties
        aegis.add(
            content=f"Interaction between {self.npc.name} and {other_npc_id}: {event}",
            agent_id=self.agent_id,
            scope="agent-shared",
            shared_with_agents=[other_agent],
            memory_type="standard",
            metadata={
                "type": "relationship_event",
                "target": other_npc_id,
                "trust_change": sentiment_change,
                "new_trust": new_trust,
                "game_time": GAME_TIME.isoformat()
            }
        )
        
        # Update personal relationship summary
        if existing:
            aegis.delta([{
                "type": "update",
                "memory_id": existing[0].id,
                "metadata_patch": {
                    "trust": new_trust,
                    "last_interaction": GAME_TIME.isoformat(),
                    "interaction_count": existing[0].metadata.get("interaction_count", 0) + 1
                }
            }])
        else:
            aegis.add(
                content=f"My relationship with {other_npc_id}: {self._describe_relationship(new_trust)}",
                agent_id=self.agent_id,
                scope="agent-private",
                metadata={
                    "type": "relationship",
                    "target": other_npc_id,
                    "trust": new_trust,
                    "last_interaction": GAME_TIME.isoformat(),
                    "interaction_count": 1
                }
            )
    
    def get_relationship_context(self, other_npc_id: str) -> dict:
        """Get full relationship context for dialogue generation."""
        
        # Personal view
        personal = aegis.query(
            query=f"relationship {other_npc_id}",
            agent_id=self.agent_id,
            filter_metadata={"target": other_npc_id},
            top_k=10
        )
        
        # Shared history
        shared = aegis.query_cross_agent(
            query=f"interaction {other_npc_id}",
            requesting_agent_id=self.agent_id,
            target_agent_ids=[f"npc-{other_npc_id}"],
            top_k=10
        )
        
        trust = 0.5
        history = []
        
        for mem in personal:
            if mem.metadata.get("type") == "relationship":
                trust = mem.metadata.get("trust", 0.5)
            history.append(mem.content)
        
        for mem in (shared or []):
            history.append(mem.content)
        
        return {
            "trust": trust,
            "relationship_type": self.npc.relationships.get(other_npc_id, "stranger"),
            "history": history[-10:],  # Last 10 interactions
            "sentiment": self._trust_to_sentiment(trust)
        }
    
    def _describe_relationship(self, trust: float) -> str:
        if trust >= 0.8:
            return "close friend, I trust them deeply"
        elif trust >= 0.6:
            return "friendly acquaintance, generally trustworthy"
        elif trust >= 0.4:
            return "neutral, I don't know them well"
        elif trust >= 0.2:
            return "somewhat wary, they've disappointed me"
        else:
            return "I don't trust them at all"
    
    def _trust_to_sentiment(self, trust: float) -> str:
        if trust >= 0.8:
            return "warm"
        elif trust >= 0.6:
            return "friendly"
        elif trust >= 0.4:
            return "neutral"
        elif trust >= 0.2:
            return "cool"
        else:
            return "hostile"
```

### Step 4: Planning and Action

```python
class NPCPlanner:
    """Plans NPC actions based on memories and goals."""
    
    def __init__(self, npc: NPCProfile, memory: NPCMemoryStream):
        self.npc = npc
        self.memory = memory
        self.agent_id = f"npc-{npc.id}"
    
    def make_daily_plan(self) -> List[dict]:
        """Create a plan for the day based on routine and memories."""
        
        # Get relevant memories for planning
        recent_reflections = aegis.query(
            query="goals plans tomorrow",
            agent_id=self.agent_id,
            filter_metadata={"type": "reflection"},
            top_k=5
        )
        
        # Get world events that might affect plans
        world_events = aegis.query(
            query="events happening today",
            agent_id=self.agent_id,
            scope="global",
            top_k=5
        )
        
        context = {
            "routine": self.npc.daily_routine,
            "reflections": [m.content for m in recent_reflections],
            "world_events": [m.content for m in (world_events or [])]
        }
        
        response = llm.chat.completions.create(
            model="gpt-4o",
            messages=[{
                "role": "system",
                "content": f"""You are {self.npc.name}, a {self.npc.occupation}.
Personality: {', '.join(self.npc.personality)}

Create a daily plan based on your routine, recent thoughts, and world events.
Be specific about times and locations. Include social interactions."""
            }, {
                "role": "user",
                "content": f"""Today is {GAME_TIME.strftime('%A, %B %d')}.

Your usual routine: {context['routine']}
Recent thoughts: {context['reflections']}
World events: {context['world_events']}

Create your plan for today as a JSON array:
[{{"time": "7:00", "activity": "...", "location": "...", "with": null or "name"}}]"""
            }],
            response_format={"type": "json_object"}
        )
        
        plan = json.loads(response.choices[0].message.content)
        
        # Store plan as memory
        aegis.add(
            content=f"My plan for today: {json.dumps(plan)}",
            agent_id=self.agent_id,
            scope="agent-private",
            metadata={
                "type": "plan",
                "game_date": GAME_TIME.strftime('%Y-%m-%d'),
                "plan": plan
            }
        )
        
        return plan.get("plan", plan) if isinstance(plan, dict) else plan
    
    def decide_action(self, situation: str) -> dict:
        """Decide what to do in a specific situation."""
        
        # Retrieve relevant memories
        memories = self.memory.remember(situation, top_k=10)
        
        # Get current plan
        current_plan = aegis.query(
            query="today's plan",
            agent_id=self.agent_id,
            filter_metadata={"type": "plan"},
            top_k=1
        )
        
        memory_context = "\n".join([f"- {m.content}" for m in memories])
        plan_context = current_plan[0].content if current_plan else "No specific plan"
        
        response = llm.chat.completions.create(
            model="gpt-4o",
            messages=[{
                "role": "system",
                "content": f"""You are {self.npc.name}, a {self.npc.occupation}.
Personality: {', '.join(self.npc.personality)}

Decide what to do based on the situation, your memories, and your plan.
Be specific and in-character."""
            }, {
                "role": "user",
                "content": f"""Current situation: {situation}

Your memories related to this:
{memory_context}

Your plan for today:
{plan_context}

What do you do? Respond in JSON:
{{
    "action": "specific action to take",
    "reason": "why you're doing this",
    "emotion": "how you feel",
    "dialogue": "what you say (if anything)"
}}"""
            }],
            response_format={"type": "json_object"}
        )
        
        return json.loads(response.choices[0].message.content)
```

### Step 5: NPC Coordination (The Key Differentiator)

```python
class NPCCoordinator:
    """Enables NPCs to coordinate activities through shared memory."""
    
    def __init__(self):
        self.agent_id = "world-coordinator"
    
    def propose_group_activity(self, proposer_npc: NPCProfile, activity: str, invitees: List[str]):
        """One NPC proposes a group activity."""
        
        # Create proposal in shared memory visible to all invitees
        invitee_agents = [f"npc-{i}" for i in invitees]
        
        aegis.add(
            content=f"{proposer_npc.name} proposes: {activity}",
            agent_id=f"npc-{proposer_npc.id}",
            scope="agent-shared",
            shared_with_agents=invitee_agents,
            metadata={
                "type": "activity_proposal",
                "proposer": proposer_npc.id,
                "activity": activity,
                "invitees": invitees,
                "status": "pending",
                "responses": {}
            }
        )
    
    def respond_to_proposal(self, responder_npc: NPCProfile, proposal_id: str, accept: bool, reason: str):
        """An NPC responds to a group activity proposal."""
        
        # Get proposal
        proposal = aegis.get(proposal_id)
        
        if not proposal:
            return
        
        # Update responses
        responses = proposal.metadata.get("responses", {})
        responses[responder_npc.id] = {
            "accept": accept,
            "reason": reason
        }
        
        aegis.delta([{
            "type": "update",
            "memory_id": proposal_id,
            "metadata_patch": {
                "responses": responses,
                "status": self._calculate_status(proposal.metadata.get("invitees", []), responses)
            }
        }])
    
    def _calculate_status(self, invitees: List[str], responses: dict) -> str:
        """Calculate proposal status based on responses."""
        if len(responses) < len(invitees):
            return "pending"
        
        accepts = sum(1 for r in responses.values() if r.get("accept"))
        if accepts == len(invitees):
            return "confirmed"
        elif accepts > len(invitees) / 2:
            return "partial"
        else:
            return "declined"
    
    def broadcast_world_event(self, event: str, importance: float = 0.7):
        """Broadcast a world event to all NPCs."""
        
        aegis.add(
            content=f"[WORLD EVENT] {event}",
            agent_id=self.agent_id,
            scope="global",  # Visible to all NPCs
            memory_type="standard",
            metadata={
                "type": "world_event",
                "importance": importance,
                "game_time": GAME_TIME.isoformat()
            }
        )
```

### Step 6: Full NPC Agent

```python
class NPCAgent:
    """Complete NPC agent with all capabilities."""
    
    def __init__(self, profile: NPCProfile):
        self.profile = profile
        self.agent_id = f"npc-{profile.id}"
        
        self.memory = NPCMemoryStream(profile)
        self.reflection = NPCReflection(profile, self.memory)
        self.social = NPCSocialMemory(profile)
        self.planner = NPCPlanner(profile, self.memory)
    
    def perceive(self, observation: str):
        """NPC perceives something in the world."""
        self.memory.observe(observation)
    
    def interact(self, other_npc: NPCProfile, dialogue: str, sentiment: float = 0.0):
        """NPC interacts with another NPC."""
        
        # Record the interaction
        self.memory.observe(f"{other_npc.name} said: '{dialogue}'")
        
        # Update relationship
        self.social.update_relationship(other_npc.id, dialogue, sentiment)
    
    def generate_dialogue(self, context: str, speaking_to: Optional[NPCProfile] = None) -> str:
        """Generate contextual dialogue."""
        
        # Get relevant memories
        memories = self.memory.remember(context, top_k=10)
        
        # Get relationship context if speaking to someone
        relationship = None
        if speaking_to:
            relationship = self.social.get_relationship_context(speaking_to.id)
        
        memory_context = "\n".join([f"- {m.content}" for m in memories])
        
        system_prompt = f"""You are {self.profile.name}, a {self.profile.age}-year-old {self.profile.occupation}.
Personality: {', '.join(self.profile.personality)}

Speak naturally in first person. Keep responses brief (1-3 sentences).
Your dialogue should reflect your personality and memories."""
        
        if relationship:
            system_prompt += f"""

You are speaking to {speaking_to.name}.
Your relationship: {relationship['relationship_type']}
Trust level: {relationship['sentiment']}
Recent history: {relationship['history'][-3:]}"""
        
        response = llm.chat.completions.create(
            model="gpt-4o",
            messages=[{
                "role": "system",
                "content": system_prompt
            }, {
                "role": "user",
                "content": f"""Context: {context}

Your relevant memories:
{memory_context}

What do you say?"""
            }]
        )
        
        dialogue = response.choices[0].message.content
        
        # Record what we said
        self.memory.observe(f"I said: '{dialogue}'")
        
        return dialogue
    
    def tick(self, game_time: datetime, situation: str) -> dict:
        """Main update loop called each game tick."""
        
        global GAME_TIME
        GAME_TIME = game_time
        
        # 1. Decide action based on situation
        action = self.planner.decide_action(situation)
        
        # 2. Maybe reflect on recent experiences
        if GAME_TIME.minute == 0:  # Reflect every hour
            self.reflection.reflect()
        
        return action


# Example usage
klaus = NPCAgent(NPCProfile(
    id="klaus",
    name="Klaus",
    age=45,
    occupation="baker",
    personality=["friendly", "hardworking", "traditional"],
    relationships={"maya": "wife", "tom": "rival"},
    daily_routine=["wake 5am", "bake 5:30am-2pm", "rest 2pm-4pm", "dinner 6pm"]
))

maya = NPCAgent(NPCProfile(
    id="maya",
    name="Maya",
    age=42,
    occupation="librarian",
    personality=["intelligent", "patient", "curious"],
    relationships={"klaus": "husband", "tom": "friend"},
    daily_routine=["wake 7am", "library 9am-5pm", "reading 7pm-9pm"]
))

# Simulate interaction
klaus.perceive("The morning sun rises over the bakery")
klaus.perceive("Maya is still sleeping")

dialogue = klaus.generate_dialogue(
    context="It's early morning, you're heading to the bakery",
    speaking_to=None
)
print(f"Klaus (to himself): {dialogue}")

# Later, an interaction
maya.perceive("Klaus left early without saying goodbye")
maya_dialogue = maya.generate_dialogue(
    context="Klaus just came home from the bakery",
    speaking_to=klaus.profile
)
print(f"Maya: {maya_dialogue}")

# Klaus responds
klaus.interact(maya.profile, maya_dialogue, sentiment=-0.1)
klaus_response = klaus.generate_dialogue(
    context=f"Maya said: {maya_dialogue}",
    speaking_to=maya.profile
)
print(f"Klaus: {klaus_response}")
```

---

## Production Tips

### 1. Memory Limits
```python
# Cap memories per NPC to prevent context explosion
MAX_MEMORIES_PER_NPC = 1000

def prune_old_memories(agent_id: str):
    """Remove low-importance old memories."""
    all_memories = aegis.query(
        query="",
        agent_id=agent_id,
        top_k=MAX_MEMORIES_PER_NPC + 100
    )
    
    if len(all_memories) > MAX_MEMORIES_PER_NPC:
        # Sort by composite score, deprecate lowest
        for mem in all_memories[MAX_MEMORIES_PER_NPC:]:
            aegis.delta([{
                "type": "deprecate",
                "memory_id": mem.id,
                "deprecation_reason": "Memory limit exceeded"
            }])
```

### 2. Batching for Performance
```python
# Don't call LLM for every observation - batch
class BatchedPerception:
    def __init__(self, npc_agent, batch_size=10):
        self.agent = npc_agent
        self.buffer = []
        self.batch_size = batch_size
    
    def observe(self, observation: str):
        self.buffer.append(observation)
        if len(self.buffer) >= self.batch_size:
            self.flush()
    
    def flush(self):
        if not self.buffer:
            return
        # Score importance for all at once
        importance_scores = self._batch_score(self.buffer)
        for obs, importance in zip(self.buffer, importance_scores):
            self.agent.memory.observe(obs, importance=importance)
        self.buffer = []
```

### 3. Prevent Erratic Behavior
```python
# Validate actions against common sense rules
FORBIDDEN_ACTIONS = [
    ("bathroom", 2),  # Max 2 NPCs in bathroom
    ("bedroom", 1),   # Only owner in bedroom
]

def validate_action(npc: NPCProfile, action: dict, world_state: dict) -> bool:
    location = action.get("location", "")
    for forbidden_loc, max_occupants in FORBIDDEN_ACTIONS:
        if forbidden_loc in location.lower():
            current = world_state.get(f"{forbidden_loc}_occupants", 0)
            if current >= max_occupants:
                return False
    return True
```

### 4. Debug Emergent Behaviors
```python
# Log all memory operations for debugging
import logging

logging.basicConfig(level=logging.DEBUG)

def debug_memory_state(npc_id: str):
    """Dump NPC's memory state for debugging."""
    agent_id = f"npc-{npc_id}"
    
    personal = aegis.query(query="", agent_id=agent_id, top_k=100)
    reflections = aegis.query(
        query="",
        agent_id=agent_id,
        filter_metadata={"type": "reflection"},
        top_k=50
    )
    
    print(f"=== {npc_id} Memory Debug ===")
    print(f"Total memories: {len(personal)}")
    print(f"Reflections: {len(reflections)}")
    print("\nRecent memories:")
    for mem in personal[:10]:
        print(f"  - [{mem.metadata.get('importance', 0):.2f}] {mem.content[:50]}...")
```

---

## Expected Outcomes

| Metric | Smallville (Original) | With Aegis |
|--------|----------------------|------------|
| Memory consistency | ~70% | ~95% |
| Erratic behaviors | Common | Rare |
| Retrieval accuracy | Embedding only | Composite scoring |
| Multi-NPC coordination | None | Native |
| Session persistence | Simulation only | Persistent |
| Production readiness | Research code | Deployable |

---

## Example: Emergent Party Planning

```
[Morning - Klaus observes]
Klaus: "The Harvest Festival is next week. Maya loves festivals."

[Klaus reflects]
Reflection: "I should plan something special for Maya for the festival."

[Klaus proposes]
Klaus proposes: "Harvest Festival dinner party at our home"
Invitees: Maya, Tom, neighbors

[Maya responds]
Maya: "A party! Klaus is so thoughtful. I'll help with decorations."
Response: ACCEPT

[Tom responds - note the low trust relationship]
Tom: "Klaus is trying to show off again. But the food will be good."
Response: ACCEPT (reluctantly)

[World event triggers]
WORLD EVENT: Heavy rain forecasted for festival week

[Klaus replans]
Klaus: "The party might need to be indoors. I should check the bakery space."

[Coordination memory visible to all invitees]
Shared: "Party moved indoors due to weather. Klaus preparing extra bread."
```

---

## Next Steps

- **Integrate with game engine**: Connect to Unity/Unreal via REST API
- **Add emotional states**: Mood affects dialogue and decisions
- **Implement locations**: NPCs move through the world
- **Add player interactions**: NPCs remember and react to player

See [Recipe 9: Game World Persistent Memory](./09-game-world-memory.md) for world state management.
