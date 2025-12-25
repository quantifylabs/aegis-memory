# Recipe 9: Game World Persistent Memory

**Build a game world that remembers everything—player choices, NPC deaths, destroyed buildings—across sessions and playthroughs.**

| Metric | Value |
|--------|-------|
| Complexity | Intermediate |
| Time to Build | 2-3 hours |
| Agents | 2 (World State Manager, Consequence Engine) |
| Key Patterns | Global memory, Delta updates, Session progress |

---

## The Problem

You want a living world where actions have permanent consequences. The player burns down a village in Act 1—it should still be ash in Act 3. NPCs they befriended should remember them. The economy should react to their choices.

**What breaks in production:**

```
Session 1: Player saves the village elder from bandits
Session 2: Player returns → Elder has no memory of being saved
           "Hello stranger, I've never seen you before."

Session 1: Player destroys the bridge to stop an invasion  
Session 2: Bridge is magically rebuilt
           "Must be that Bethesda bug."

Session 1: Player kills the blacksmith
Session 2: Blacksmith is alive, selling swords
           Player: "I literally watched him die."
```

**Industry struggles:**

- **Skyrim/Fallout**: "Radiant" systems reset, NPCs respawn, consequences are local
- **Witcher 3**: Great narrative memory, but pre-scripted—not emergent
- **No Man's Sky**: 18 quintillion planets, zero persistent memory per planet
- **Live service games**: Separate save files, no cross-session learning

---

## Current Solutions (And Why They Fail)

### Traditional Save Systems
- **How it works**: Serialize game state to file, load on resume
- **The gap**: Saves capture state, not causality. Can't query "why is this village destroyed?" No semantic search.

### Database-Backed Games
- **How it works**: MMOs use SQL databases for persistent state
- **The gap**: Stores facts, not relationships. Can't answer "what events led to this?" No memory decay or relevance scoring.

### Quest/Flag Systems
- **How it works**: Boolean flags track completion (quest_complete = true)
- **The gap**: Binary only. Can't capture nuance ("player helped, but reluctantly"). No emergent consequences.

### Procedural Generation + Seeds
- **How it works**: Generate world from seed, modifications stored as deltas
- **The gap**: Deltas are just state changes. No narrative memory. Can't reconstruct "why."

**The fundamental issue**: Games store **what** the world looks like, not **why** it looks that way. Without causality, there's no emergent storytelling.

---

## The Aegis Approach

Treat the game world as **a collection of memories with consequences**:

```
┌─────────────────────────────────────────────────────────────────┐
│                    WORLD STATE (Traditional)                     │
│                                                                  │
│  village_01_destroyed: true                                     │
│  npc_elder_alive: false                                         │
│  bridge_intact: false                                           │
│                                                                  │
│  Problem: No context. Why? When? By whom?                       │
└─────────────────────────────────────────────────────────────────┘

                              ▼

┌─────────────────────────────────────────────────────────────────┐
│                    WORLD MEMORY (Aegis)                          │
│                                                                  │
│  Memory 1: "Player chose to burn Millbrook village to stop the  │
│            plague from spreading. 47 villagers died. The elder, │
│            Mira, escaped to the mountains." (importance: 0.95)  │
│                                                                  │
│  Memory 2: "The bridge at Thornpass was destroyed by player to  │
│            prevent the Orc army crossing. This trapped 200      │
│            refugees on the wrong side." (importance: 0.9)       │
│                                                                  │
│  Memory 3: "Blacksmith Gorm was killed by player in self-defense│
│            after Gorm discovered player stealing." (importance: │
│            0.85). Consequence: No weapon repairs available.     │
│                                                                  │
│  → Queryable: "What happened to Millbrook?"                     │
│  → Causality: Links events to consequences                      │
│  → Relevance: Scored by importance and recency                  │
└─────────────────────────────────────────────────────────────────┘
```

**Three memory layers:**

1. **Event Memory**: What happened (semantic, queryable)
2. **State Memory**: Current world state (derived from events)
3. **Consequence Memory**: What should happen because of events

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      GAME ENGINE                                 │
│                   (Unity, Unreal, Godot)                        │
└───────────────────────────┬─────────────────────────────────────┘
                            │ Game Events
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                  WORLD STATE MANAGER                             │
│                                                                  │
│  Receives: Player actions, NPC actions, world events            │
│  Creates: Semantic memory of each significant event             │
│  Maintains: Consistent world state derived from memories        │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                   AEGIS MEMORY                                   │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                    GLOBAL SCOPE                          │    │
│  │  World events visible to all (history, geography)        │    │
│  └─────────────────────────────────────────────────────────┘    │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                 LOCATION-SCOPED                          │    │
│  │  Events specific to regions (village history)            │    │
│  └─────────────────────────────────────────────────────────┘    │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                  PLAYER-SCOPED                           │    │
│  │  Player-specific memories (reputation, choices)          │    │
│  └─────────────────────────────────────────────────────────┘    │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                  CONSEQUENCE ENGINE                              │
│                                                                  │
│  Queries: Recent events relevant to current situation           │
│  Determines: What consequences should manifest                   │
│  Applies: State changes, NPC reactions, world modifications     │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                    GAME WORLD                                    │
│                                                                  │
│  NPCs react based on memories of player                         │
│  Locations reflect historical events                            │
│  Economy adapts to past disruptions                             │
│  Quests adjust based on world state                             │
└─────────────────────────────────────────────────────────────────┘
```

---

## Implementation

### Step 1: Project Setup

```python
from aegis_memory import AegisClient
from openai import OpenAI
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict
from enum import Enum
import json

# Initialize
aegis = AegisClient(
    api_key="your-aegis-key",
    base_url="http://localhost:8000"
)
llm = OpenAI()

# Game configuration
GAME_ID = "fantasy-rpg-001"
WORLD_AGENT = "world-state"
CONSEQUENCE_AGENT = "consequence-engine"

class EventType(Enum):
    DESTRUCTION = "destruction"
    DEATH = "death"
    CREATION = "creation"
    INTERACTION = "interaction"
    DISCOVERY = "discovery"
    TRANSACTION = "transaction"
    COMBAT = "combat"
    QUEST = "quest"

@dataclass
class WorldEvent:
    """A significant event in the game world."""
    event_type: EventType
    description: str
    location: str
    actors: List[str]  # NPCs, player, factions involved
    timestamp: datetime
    importance: float = 0.5  # 0.0 - 1.0
    consequences: List[str] = field(default_factory=list)
    reversible: bool = True
```

### Step 2: World State Manager

```python
class WorldStateManager:
    """Manages persistent world state through memories."""
    
    def __init__(self, game_id: str):
        self.game_id = game_id
        self.agent_id = WORLD_AGENT
    
    def record_event(self, event: WorldEvent) -> str:
        """Record a world event as a memory."""
        
        # Create rich semantic description
        event_description = self._enrich_description(event)
        
        # Determine scope based on event type and importance
        scope = self._determine_scope(event)
        
        # Store the event memory
        result = aegis.add(
            content=event_description,
            agent_id=self.agent_id,
            scope=scope,
            memory_type="standard",
            metadata={
                "type": "world_event",
                "event_type": event.event_type.value,
                "location": event.location,
                "actors": event.actors,
                "game_time": event.timestamp.isoformat(),
                "importance": event.importance,
                "consequences": event.consequences,
                "reversible": event.reversible
            }
        )
        
        # If there are consequences, record them too
        for consequence in event.consequences:
            self._record_consequence(event, consequence)
        
        return result.id
    
    def _enrich_description(self, event: WorldEvent) -> str:
        """Create a rich narrative description of the event."""
        
        response = llm.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{
                "role": "system",
                "content": """You are a chronicler recording events in a fantasy world.
Write a concise but complete record of the event, including:
- What happened
- Who was involved
- Where it happened
- Why it matters
- What the immediate aftermath was

Keep it to 2-3 sentences. Be specific and factual."""
            }, {
                "role": "user",
                "content": f"""Event: {event.event_type.value}
Description: {event.description}
Location: {event.location}
Actors: {', '.join(event.actors)}
Importance: {event.importance}"""
            }]
        )
        
        return response.choices[0].message.content
    
    def _determine_scope(self, event: WorldEvent) -> str:
        """Determine memory scope based on event significance."""
        
        if event.importance >= 0.8:
            return "global"  # World-changing events
        elif event.importance >= 0.5:
            return "agent-shared"  # Regional significance
        else:
            return "agent-private"  # Local only
    
    def _record_consequence(self, source_event: WorldEvent, consequence: str):
        """Record a consequence linked to its source event."""
        
        aegis.add(
            content=f"CONSEQUENCE: {consequence}",
            agent_id=self.agent_id,
            scope="global",
            memory_type="reflection",
            metadata={
                "type": "consequence",
                "source_event_type": source_event.event_type.value,
                "source_location": source_event.location,
                "active": True
            }
        )
    
    def query_location_history(self, location: str, top_k: int = 10) -> List:
        """Get the history of events at a location."""
        
        return aegis.query(
            query=f"events at {location}",
            agent_id=self.agent_id,
            filter_metadata={"location": location},
            top_k=top_k
        )
    
    def query_actor_history(self, actor: str, top_k: int = 10) -> List:
        """Get events involving a specific actor."""
        
        return aegis.playbook(
            query=f"events involving {actor}",
            agent_id=self.agent_id,
            top_k=top_k
        )
    
    def get_world_state(self, location: str) -> Dict:
        """Derive current world state from memory."""
        
        # Get all events at this location
        events = self.query_location_history(location, top_k=50)
        
        # Get active consequences
        consequences = aegis.query(
            query=f"consequences affecting {location}",
            agent_id=self.agent_id,
            filter_metadata={"type": "consequence", "active": True},
            top_k=20
        )
        
        # Use LLM to synthesize current state
        events_text = "\n".join([f"- {e.content}" for e in events])
        consequences_text = "\n".join([f"- {c.content}" for c in consequences])
        
        response = llm.chat.completions.create(
            model="gpt-4o",
            messages=[{
                "role": "system",
                "content": """Based on the historical events and active consequences,
describe the current state of this location. Include:
- Physical state (intact, damaged, destroyed)
- Population status
- Notable features or changes
- Ongoing effects

Respond in JSON format."""
            }, {
                "role": "user",
                "content": f"""Location: {location}

Historical events:
{events_text}

Active consequences:
{consequences_text}

What is the current state?"""
            }],
            response_format={"type": "json_object"}
        )
        
        return json.loads(response.choices[0].message.content)


# Usage
world = WorldStateManager(GAME_ID)

# Record a significant event
event = WorldEvent(
    event_type=EventType.DESTRUCTION,
    description="Player burned Millbrook village to stop plague spread",
    location="millbrook_village",
    actors=["player", "villagers", "elder_mira"],
    timestamp=datetime.now(),
    importance=0.95,
    consequences=[
        "Millbrook is now uninhabitable ruins",
        "47 villagers died in the fire",
        "Elder Mira escaped to Thornpass mountains",
        "No merchants available in Millbrook region",
        "Player gained 'Village Burner' reputation"
    ],
    reversible=False
)

event_id = world.record_event(event)
print(f"Recorded event: {event_id}")
```

### Step 3: Consequence Engine

```python
class ConsequenceEngine:
    """Determines and applies consequences based on world memory."""
    
    def __init__(self, world_state: WorldStateManager):
        self.world = world_state
        self.agent_id = CONSEQUENCE_AGENT
    
    def get_consequences_for_action(self, action: str, location: str, actor: str) -> Dict:
        """Determine what consequences should apply to an action."""
        
        # Query relevant world history
        location_history = self.world.query_location_history(location)
        actor_history = self.world.query_actor_history(actor)
        
        # Get player reputation if actor is player
        reputation = self._get_reputation(actor) if actor == "player" else None
        
        # Query for similar past actions and their consequences
        similar_actions = aegis.playbook(
            query=f"{action} consequences",
            agent_id=self.agent_id,
            include_types=["reflection"],
            top_k=5
        )
        
        # Synthesize consequences
        history_text = "\n".join([f"- {h.content}" for h in location_history[:10]])
        similar_text = "\n".join([f"- {s.content}" for s in (similar_actions or [])])
        
        response = llm.chat.completions.create(
            model="gpt-4o",
            messages=[{
                "role": "system",
                "content": """You are a consequence engine for a fantasy RPG.
Given an action and world context, determine realistic consequences.

Consider:
- The location's history and current state
- The actor's past actions and reputation
- Similar situations and their outcomes
- Logical cause and effect

Respond with immediate and long-term consequences."""
            }, {
                "role": "user",
                "content": f"""Action: {action}
Location: {location}
Actor: {actor}
Reputation: {reputation}

Location history:
{history_text}

Similar past situations:
{similar_text}

What are the consequences? Respond in JSON:
{{
    "immediate": ["consequence 1", "consequence 2"],
    "long_term": ["consequence 1", "consequence 2"],
    "reputation_change": float (-1.0 to 1.0),
    "world_state_changes": {{"key": "value"}}
}}"""
            }],
            response_format={"type": "json_object"}
        )
        
        return json.loads(response.choices[0].message.content)
    
    def apply_reputation_change(self, actor: str, faction: str, change: float, reason: str):
        """Update an actor's reputation with a faction."""
        
        # Get current reputation
        rep_memory = aegis.query(
            query=f"reputation {actor} {faction}",
            agent_id=self.agent_id,
            filter_metadata={"type": "reputation", "actor": actor, "faction": faction},
            top_k=1
        )
        
        current_rep = 0.0
        if rep_memory:
            current_rep = rep_memory[0].metadata.get("value", 0.0)
        
        new_rep = max(-1.0, min(1.0, current_rep + change))
        
        # Record reputation change
        if rep_memory:
            aegis.delta([{
                "type": "update",
                "memory_id": rep_memory[0].id,
                "metadata_patch": {
                    "value": new_rep,
                    "last_change": datetime.now().isoformat(),
                    "last_reason": reason
                }
            }])
        else:
            aegis.add(
                content=f"{actor}'s reputation with {faction}: {self._rep_to_text(new_rep)}",
                agent_id=self.agent_id,
                scope="global",
                metadata={
                    "type": "reputation",
                    "actor": actor,
                    "faction": faction,
                    "value": new_rep,
                    "last_change": datetime.now().isoformat(),
                    "last_reason": reason
                }
            )
    
    def _get_reputation(self, actor: str) -> Dict:
        """Get all reputation values for an actor."""
        
        reps = aegis.query(
            query=f"reputation {actor}",
            agent_id=self.agent_id,
            filter_metadata={"type": "reputation", "actor": actor},
            top_k=100
        )
        
        return {
            r.metadata.get("faction"): r.metadata.get("value")
            for r in reps
        }
    
    def _rep_to_text(self, value: float) -> str:
        if value >= 0.8:
            return "Revered"
        elif value >= 0.5:
            return "Honored"
        elif value >= 0.2:
            return "Friendly"
        elif value >= -0.2:
            return "Neutral"
        elif value >= -0.5:
            return "Unfriendly"
        elif value >= -0.8:
            return "Hostile"
        else:
            return "Hated"
    
    def check_npc_reaction(self, npc_id: str, player_id: str, context: str) -> Dict:
        """Determine how an NPC should react to the player."""
        
        # Get NPC's memories of player
        npc_memories = aegis.query(
            query=f"player {player_id}",
            agent_id=f"npc-{npc_id}",
            top_k=10
        )
        
        # Get player's reputation
        reputation = self._get_reputation(player_id)
        
        # Get NPC's faction
        npc_faction = self._get_npc_faction(npc_id)
        faction_rep = reputation.get(npc_faction, 0.0) if npc_faction else 0.0
        
        memories_text = "\n".join([f"- {m.content}" for m in npc_memories])
        
        response = llm.chat.completions.create(
            model="gpt-4o",
            messages=[{
                "role": "system",
                "content": """Determine how an NPC should react to a player based on:
- Their personal memories of the player
- The player's reputation with their faction
- The current context

Respond with the NPC's attitude and behavior."""
            }, {
                "role": "user",
                "content": f"""NPC: {npc_id}
Player reputation with NPC's faction: {self._rep_to_text(faction_rep)} ({faction_rep:.2f})

NPC's memories of player:
{memories_text}

Current context: {context}

How does the NPC react? Respond in JSON:
{{
    "attitude": "friendly/neutral/suspicious/hostile",
    "behavior": "description of behavior",
    "dialogue_tone": "tone for dialogue",
    "will_help": true/false,
    "price_modifier": float (1.0 = normal, 2.0 = double, 0.5 = discount)
}}"""
            }],
            response_format={"type": "json_object"}
        )
        
        return json.loads(response.choices[0].message.content)
    
    def _get_npc_faction(self, npc_id: str) -> Optional[str]:
        """Get the faction an NPC belongs to."""
        npc_data = aegis.query(
            query=f"npc {npc_id} faction",
            agent_id=WORLD_AGENT,
            top_k=1
        )
        if npc_data:
            return npc_data[0].metadata.get("faction")
        return None


# Usage
consequence_engine = ConsequenceEngine(world)

# Check consequences before an action
consequences = consequence_engine.get_consequences_for_action(
    action="Steal from the merchant guild treasury",
    location="capital_city",
    actor="player"
)

print("If you do this:")
print(f"Immediate: {consequences['immediate']}")
print(f"Long-term: {consequences['long_term']}")
print(f"Reputation hit: {consequences['reputation_change']}")
```

### Step 4: Session Persistence

```python
class GameSessionManager:
    """Manages game sessions with full state persistence."""
    
    def __init__(self, game_id: str, player_id: str):
        self.game_id = game_id
        self.player_id = player_id
        self.session_id = f"{game_id}-{player_id}"
    
    def save_session(self, current_location: str, inventory: Dict, quest_state: Dict):
        """Save current session state."""
        
        # Use Aegis session progress for structured state
        aegis.progress.update(
            session_id=self.session_id,
            summary=f"Player at {current_location}",
            status="saved",
            completed=list(quest_state.get("completed", [])),
            in_progress=quest_state.get("active"),
            metadata={
                "player_id": self.player_id,
                "location": current_location,
                "inventory": inventory,
                "quest_state": quest_state,
                "save_time": datetime.now().isoformat()
            }
        )
        
        # Also record as memory for queryable history
        aegis.add(
            content=f"Game saved at {current_location}. Active quest: {quest_state.get('active')}",
            agent_id=f"player-{self.player_id}",
            scope="agent-private",
            metadata={
                "type": "save_point",
                "location": current_location,
                "time": datetime.now().isoformat()
            }
        )
    
    def load_session(self) -> Optional[Dict]:
        """Load the most recent session state."""
        
        progress = aegis.progress.get(self.session_id)
        
        if not progress:
            return None
        
        return {
            "location": progress.metadata.get("location"),
            "inventory": progress.metadata.get("inventory", {}),
            "quest_state": progress.metadata.get("quest_state", {}),
            "completed_quests": progress.completed_items or [],
            "active_quest": progress.in_progress_item
        }
    
    def get_play_history(self) -> List:
        """Get the player's complete play history."""
        
        return aegis.query(
            query="",
            agent_id=f"player-{self.player_id}",
            top_k=1000
        )
    
    def generate_recap(self) -> str:
        """Generate a narrative recap of the player's journey."""
        
        history = self.get_play_history()
        
        # Filter to significant events
        significant = [h for h in history if h.metadata.get("importance", 0) > 0.5]
        
        events_text = "\n".join([f"- {e.content}" for e in significant[:20]])
        
        response = llm.chat.completions.create(
            model="gpt-4o",
            messages=[{
                "role": "system",
                "content": """You are a bard recounting an adventurer's journey.
Based on their significant deeds, create a brief, engaging recap.
Use second person ("You"). Make it feel epic but accurate."""
            }, {
                "role": "user",
                "content": f"The adventurer's deeds:\n{events_text}\n\nRecount their story:"
            }]
        )
        
        return response.choices[0].message.content


# Usage
session = GameSessionManager(GAME_ID, "player_001")

# Save game
session.save_session(
    current_location="thornpass_mountains",
    inventory={"gold": 150, "health_potions": 3, "legendary_sword": 1},
    quest_state={
        "completed": ["find_elder_mira", "investigate_plague"],
        "active": "stop_orc_invasion",
        "failed": ["save_millbrook"]
    }
)

# Later, resume
saved_state = session.load_session()
if saved_state:
    print(f"Welcome back! You were at {saved_state['location']}")
    print(f"Active quest: {saved_state['active_quest']}")

# Get recap
recap = session.generate_recap()
print("\n=== Your Story So Far ===")
print(recap)
```

### Step 5: Dynamic Quest Generation

```python
class DynamicQuestGenerator:
    """Generates quests based on world state and history."""
    
    def __init__(self, world_state: WorldStateManager, consequence_engine: ConsequenceEngine):
        self.world = world_state
        self.consequences = consequence_engine
        self.agent_id = "quest-generator"
    
    def generate_quest(self, player_id: str, location: str) -> Dict:
        """Generate a contextual quest based on world state."""
        
        # Get location history
        location_history = self.world.query_location_history(location)
        
        # Get active consequences
        consequences = aegis.query(
            query=f"consequences {location}",
            agent_id=WORLD_AGENT,
            filter_metadata={"type": "consequence", "active": True},
            top_k=10
        )
        
        # Get player history
        player_history = aegis.query(
            query="",
            agent_id=f"player-{player_id}",
            top_k=20
        )
        
        # Get player reputation
        reputation = self.consequences._get_reputation(player_id)
        
        history_text = "\n".join([f"- {h.content}" for h in location_history[:10]])
        consequences_text = "\n".join([f"- {c.content}" for c in consequences])
        player_text = "\n".join([f"- {p.content}" for p in player_history[:10]])
        
        response = llm.chat.completions.create(
            model="gpt-4o",
            messages=[{
                "role": "system",
                "content": """You are a quest designer for a fantasy RPG.
Create a quest that:
- Emerges naturally from the world's history and state
- Reacts to the player's past choices
- Has meaningful consequences
- Offers interesting moral choices

The quest should feel like a natural consequence of the world, not arbitrary."""
            }, {
                "role": "user",
                "content": f"""Location: {location}

Location history:
{history_text}

Active consequences in this area:
{consequences_text}

Player's recent actions:
{player_text}

Player reputation: {reputation}

Generate a quest. Respond in JSON:
{{
    "title": "Quest name",
    "description": "Brief description",
    "hook": "How player discovers this quest",
    "objectives": ["objective 1", "objective 2"],
    "choices": [
        {{"choice": "Option A", "consequence": "What happens"}},
        {{"choice": "Option B", "consequence": "What happens"}}
    ],
    "rewards": {{"gold": 0, "items": [], "reputation": {{}}}},
    "emerges_from": "What world state/history triggers this quest"
}}"""
            }],
            response_format={"type": "json_object"}
        )
        
        quest = json.loads(response.choices[0].message.content)
        
        # Store quest as memory
        aegis.add(
            content=f"Quest available at {location}: {quest['title']} - {quest['description']}",
            agent_id=self.agent_id,
            scope="global",
            metadata={
                "type": "quest",
                "location": location,
                "quest_data": quest,
                "generated_for": player_id,
                "active": True
            }
        )
        
        return quest


# Usage
quest_gen = DynamicQuestGenerator(world, consequence_engine)

# Generate quest based on current world state
quest = quest_gen.generate_quest("player_001", "thornpass_mountains")

print(f"\n=== New Quest: {quest['title']} ===")
print(f"\n{quest['description']}")
print(f"\nHow you found it: {quest['hook']}")
print(f"\nThis quest exists because: {quest['emerges_from']}")
print(f"\nObjectives:")
for obj in quest['objectives']:
    print(f"  • {obj}")
print(f"\nChoices you'll face:")
for choice in quest['choices']:
    print(f"  • {choice['choice']} → {choice['consequence']}")
```

---

## Production Tips

### 1. Event Importance Auto-Scoring
```python
def auto_score_importance(event: WorldEvent) -> float:
    """Automatically score event importance."""
    
    base_scores = {
        EventType.DEATH: 0.8,
        EventType.DESTRUCTION: 0.85,
        EventType.CREATION: 0.5,
        EventType.DISCOVERY: 0.6,
        EventType.QUEST: 0.7,
        EventType.COMBAT: 0.4,
        EventType.TRANSACTION: 0.2,
        EventType.INTERACTION: 0.3,
    }
    
    score = base_scores.get(event.event_type, 0.5)
    
    # Boost for player involvement
    if "player" in event.actors:
        score += 0.1
    
    # Boost for named NPCs
    named_npcs = [a for a in event.actors if not a.startswith("generic_")]
    score += len(named_npcs) * 0.05
    
    # Boost for irreversible events
    if not event.reversible:
        score += 0.15
    
    return min(1.0, score)
```

### 2. Memory Decay for Less Important Events
```python
def apply_memory_decay():
    """Periodically decay old, unimportant memories."""
    
    old_memories = aegis.query(
        query="",
        agent_id=WORLD_AGENT,
        top_k=1000
    )
    
    for mem in old_memories:
        age_days = (datetime.now() - mem.created_at).days
        importance = mem.metadata.get("importance", 0.5)
        
        # Low importance memories decay faster
        if importance < 0.5 and age_days > 30:
            aegis.delta([{
                "type": "deprecate",
                "memory_id": mem.id,
                "deprecation_reason": "Memory decayed due to low importance and age"
            }])
```

### 3. Efficient World State Queries
```python
# Cache frequently accessed world state
from functools import lru_cache

@lru_cache(maxsize=100)
def get_cached_location_state(location: str, cache_key: str) -> Dict:
    """Cache location state to avoid repeated queries.
    
    cache_key should include timestamp bucket (e.g., hour) to auto-invalidate.
    """
    return world.get_world_state(location)

# Usage
cache_key = datetime.now().strftime("%Y%m%d%H")  # Hourly cache
state = get_cached_location_state("millbrook_village", cache_key)
```

### 4. Debugging World Inconsistencies
```python
def audit_world_consistency(location: str) -> List[str]:
    """Check for inconsistencies in world state."""
    
    issues = []
    
    # Get all events at location
    events = world.query_location_history(location, top_k=100)
    
    # Check for contradictions
    destroyed = any(e.metadata.get("event_type") == "destruction" for e in events)
    created_after = any(
        e.metadata.get("event_type") == "creation" and 
        e.created_at > max(d.created_at for d in events if d.metadata.get("event_type") == "destruction")
        for e in events
    ) if destroyed else False
    
    if destroyed and not created_after:
        # Check if there are interactions at destroyed location
        interactions = [e for e in events if e.metadata.get("event_type") == "interaction"]
        recent_interactions = [i for i in interactions if i.created_at > max(
            d.created_at for d in events if d.metadata.get("event_type") == "destruction"
        )]
        
        if recent_interactions:
            issues.append(f"Interactions at destroyed location: {recent_interactions}")
    
    return issues
```

---

## Expected Outcomes

| Metric | Traditional Save | With Aegis |
|--------|-----------------|------------|
| State persistence | Binary flags | Rich narrative |
| Query capability | None | Full semantic search |
| Consequence tracking | Manual scripting | Automatic |
| Cross-session continuity | Save file only | Memories persist |
| Emergent storytelling | Scripted only | Dynamic |
| Debug capability | State dumps | Queryable history |

---

## Example: Player Returns to Destroyed Village

```
[Player approaches Millbrook, 10 game-days after burning it]

World State Query:
→ Event: "Player burned Millbrook to stop plague" (importance: 0.95)
→ Consequence: "Millbrook is uninhabitable ruins"
→ Consequence: "Elder Mira escaped to mountains"
→ Consequence: "No merchants in region"

Generated Scene:
"You approach what was once Millbrook village. The smell of ash 
still lingers. Charred timbers jut from the ground like broken 
bones. A crow picks at something you'd rather not identify.

Where the market square once bustled, you see a makeshift shrine. 
Someone has placed 47 stones in a circle—one for each villager 
who didn't escape.

A weathered note is pinned to the shrine:
'They died because of YOU. - M'

(Elder Mira knows you're responsible)"

NPC Reaction (when meeting Elder Mira later):
→ Reputation with Millbrook faction: -0.9 (Hated)
→ Attitude: Hostile
→ Will help: false
→ Dialogue: "You! You murdered my people! Guards!"
```

---

## Next Steps

- **Integrate with Unity/Unreal**: Create plugin for native game engine support
- **Add time simulation**: World changes even when player is away
- **Multi-player support**: Shared world state across players
- **Procedural history**: Generate backstory for locations

See [Recipe 10: Support Agent with Customer Memory](./10-support-agent-memory.md) for applying similar persistence to customer service.
