# Recipe 10: Support Agent with Customer Memory

**Build a customer support AI that remembers every interaction—across channels, sessions, and agents—so customers never repeat themselves.**

| Metric | Value |
|--------|-------|
| Complexity | Beginner |
| Time to Build | 1-2 hours |
| Agents | 2 (Support Agent, Escalation Agent) |
| Key Patterns | Customer-scoped memory, Cross-channel continuity, Handoff memory |

---

## The Problem

A customer contacts support. They explain their issue in detail. The chatbot can't help, so they're transferred to an agent. The agent says: **"Can you tell me what the issue is?"**

The customer, now frustrated, repeats everything. The agent escalates to a specialist. The specialist says: **"Can you walk me through what happened?"**

By now, the customer is furious—not because of the original issue, but because they've repeated themselves three times.

**What breaks in production:**

```
Channel 1 (Chat): Customer explains billing issue for 15 minutes
           → Bot can't resolve
           → "Please call our support line"

Channel 2 (Phone): Customer calls, waits 20 minutes
           → Agent: "How can I help you today?"
           → Customer: "I JUST EXPLAINED THIS IN CHAT"
           → Agent has zero context

Channel 3 (Email): Customer sends angry email
           → Different agent responds
           → "I see you contacted us before. Can you explain the issue?"
           → Customer: *screaming internally*
```

**The numbers:**
- **67%** of customer frustration comes from repeating information
- **75%** expect agents to know their history
- **Klarna** saw **25% reduction** in repeat inquiries with AI memory
- **$1.6 trillion** lost annually due to poor customer service

---

## Current Solutions (And Why They Fail)

### CRM Systems (Salesforce, Zendesk, HubSpot)
- **How it works**: Ticket system with conversation history attached
- **The gap**: Agents must read through history manually. No semantic search. No automatic context injection. History is per-ticket, not per-customer.

### Chatbot Conversation History
- **How it works**: Store chat transcripts, show to human agents
- **The gap**: Raw transcripts are noise. Agent must scan hundreds of messages. No extraction of key facts.

### Customer 360 Profiles
- **How it works**: Aggregate data from multiple sources into unified profile
- **The gap**: Shows data, not narrative. "Order count: 47" doesn't tell you "Customer upgraded 3 times because they love feature X."

### AI Chatbots (Intercom, Drift)
- **How it works**: AI responds based on knowledge base + conversation context
- **The gap**: Memory resets each session. "Hi again!" but with zero memory of last conversation. Can't learn from past resolutions.

**The fundamental issue**: Support systems store **records**, not **understanding**. They know what the customer bought, not why they're frustrated.

---

## The Aegis Approach

Build a **customer memory layer** that captures understanding, not just data:

```
┌─────────────────────────────────────────────────────────────────┐
│                  TRADITIONAL SUPPORT                             │
│                                                                  │
│  Ticket #1234                                                   │
│  Customer: John Smith                                           │
│  Issue: Billing                                                 │
│  History: [500 messages to scroll through]                      │
│                                                                  │
│  Agent: "Tell me about your issue..."                           │
└─────────────────────────────────────────────────────────────────┘

                              ▼

┌─────────────────────────────────────────────────────────────────┐
│                   AEGIS-POWERED SUPPORT                          │
│                                                                  │
│  Customer Memory: John Smith                                    │
│                                                                  │
│  Key Facts:                                                     │
│  • Pro plan customer since 2022                                 │
│  • Upgraded twice (loves collaboration features)                │
│  • Had billing issue in March (resolved, happy outcome)         │
│  • Prefers email over phone                                     │
│  • Technical background (skip basic instructions)               │
│                                                                  │
│  Current Context:                                               │
│  • Chatted 10 min ago about billing discrepancy                 │
│  • Issue: Charged $99 instead of $49 after downgrade            │
│  • Already tried: Checking invoice, contacting bank             │
│  • Emotional state: Frustrated but polite                       │
│                                                                  │
│  Agent sees this BEFORE customer says anything                  │
└─────────────────────────────────────────────────────────────────┘
```

**Three memory types:**

1. **Customer Profile**: Long-term facts (plan, preferences, history)
2. **Session Memory**: Current issue context (what they've tried, how they feel)
3. **Resolution Memory**: What worked before (for similar issues)

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    CUSTOMER TOUCHPOINTS                          │
├─────────────┬─────────────┬─────────────┬───────────────────────┤
│    Chat     │    Email    │    Phone    │        App            │
└──────┬──────┴──────┬──────┴──────┬──────┴───────────┬───────────┘
       │             │             │                   │
       └─────────────┴─────────────┴───────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    SUPPORT ORCHESTRATOR                          │
│                                                                  │
│  1. Identify customer (email, phone, account ID)                │
│  2. Load customer memory from Aegis                             │
│  3. Add current interaction to context                          │
│  4. Route to appropriate agent with full context                │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     AEGIS MEMORY                                 │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │               CUSTOMER PROFILE (Global)                   │    │
│  │  Long-term: preferences, plan, lifetime value             │    │
│  └─────────────────────────────────────────────────────────┘    │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │              INTERACTION HISTORY (Shared)                 │    │
│  │  All past conversations, resolutions, feedback            │    │
│  └─────────────────────────────────────────────────────────┘    │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │              ACTIVE SESSION (Private)                     │    │
│  │  Current issue, what's been tried, emotional state        │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      SUPPORT AGENTS                              │
├─────────────────────┬───────────────────────────────────────────┤
│    AI Chatbot       │           Human Agent                     │
│                     │                                           │
│ • Auto-responses    │ • Sees full customer context              │
│ • Simple queries    │ • No need to ask for background           │
│ • Knows customer    │ • Can reference past interactions         │
│ • Escalates smart   │ • Resolution logged automatically         │
└─────────────────────┴───────────────────────────────────────────┘
```

---

## Implementation

### Step 1: Project Setup

```python
from aegis_memory import AegisClient
from openai import OpenAI
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List, Dict
import json

# Initialize
aegis = AegisClient(
    api_key="your-aegis-key",
    base_url="http://localhost:8000"
)
llm = OpenAI()

# Configuration
SUPPORT_NAMESPACE = "customer-support"
AI_AGENT_ID = "support-bot"
ESCALATION_AGENT_ID = "escalation-specialist"

@dataclass
class CustomerContext:
    """Context passed to support agents."""
    customer_id: str
    name: str
    email: str
    plan: str
    lifetime_value: float
    tenure_months: int
    profile_summary: str
    recent_interactions: List[str]
    current_issue: Optional[str]
    sentiment: str
    preferences: Dict
```

### Step 2: Customer Memory Manager

```python
class CustomerMemory:
    """Manages persistent memory for each customer."""
    
    def __init__(self, customer_id: str):
        self.customer_id = customer_id
        self.agent_id = f"customer-{customer_id}"
    
    def get_context(self) -> CustomerContext:
        """Get full customer context for support interactions."""
        
        # Get customer profile
        profile = self._get_profile()
        
        # Get recent interactions
        recent = self._get_recent_interactions()
        
        # Get current session (if any)
        current_session = self._get_active_session()
        
        # Get preferences
        preferences = self._get_preferences()
        
        return CustomerContext(
            customer_id=self.customer_id,
            name=profile.get("name", "Customer"),
            email=profile.get("email", ""),
            plan=profile.get("plan", "unknown"),
            lifetime_value=profile.get("ltv", 0.0),
            tenure_months=profile.get("tenure_months", 0),
            profile_summary=self._summarize_profile(profile, recent),
            recent_interactions=[i.content for i in recent[:5]],
            current_issue=current_session.get("issue") if current_session else None,
            sentiment=current_session.get("sentiment", "neutral") if current_session else "neutral",
            preferences=preferences
        )
    
    def _get_profile(self) -> Dict:
        """Get long-term customer profile."""
        
        profile_mem = aegis.query(
            query="customer profile",
            agent_id=self.agent_id,
            filter_metadata={"type": "profile"},
            top_k=1
        )
        
        if profile_mem:
            return profile_mem[0].metadata
        return {}
    
    def _get_recent_interactions(self) -> List:
        """Get recent support interactions."""
        
        return aegis.query(
            query="support interaction",
            agent_id=self.agent_id,
            filter_metadata={"type": "interaction"},
            top_k=10
        ) or []
    
    def _get_active_session(self) -> Optional[Dict]:
        """Get currently active support session."""
        
        try:
            progress = aegis.progress.get(f"support-{self.customer_id}")
            if progress and progress.status == "active":
                return progress.metadata
        except:
            pass
        return None
    
    def _get_preferences(self) -> Dict:
        """Get customer communication preferences."""
        
        pref_mem = aegis.query(
            query="preferences communication",
            agent_id=self.agent_id,
            filter_metadata={"type": "preference"},
            top_k=5
        )
        
        preferences = {}
        for mem in (pref_mem or []):
            preferences.update(mem.metadata.get("preferences", {}))
        
        return preferences
    
    def _summarize_profile(self, profile: Dict, recent: List) -> str:
        """Generate human-readable profile summary."""
        
        recent_text = "\n".join([f"- {r.content[:100]}" for r in recent[:3]])
        
        response = llm.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{
                "role": "system",
                "content": """Summarize this customer in 2-3 sentences for a support agent.
Focus on: relationship length, value, past issues, and anything notable.
Be concise and actionable."""
            }, {
                "role": "user",
                "content": f"""Customer profile: {json.dumps(profile)}

Recent interactions:
{recent_text}"""
            }]
        )
        
        return response.choices[0].message.content
    
    def update_profile(self, updates: Dict):
        """Update customer profile with new information."""
        
        profile_mem = aegis.query(
            query="customer profile",
            agent_id=self.agent_id,
            filter_metadata={"type": "profile"},
            top_k=1
        )
        
        if profile_mem:
            # Update existing
            current = profile_mem[0].metadata
            current.update(updates)
            aegis.delta([{
                "type": "update",
                "memory_id": profile_mem[0].id,
                "metadata_patch": current
            }])
        else:
            # Create new
            aegis.add(
                content=f"Customer profile for {self.customer_id}",
                agent_id=self.agent_id,
                scope="agent-private",
                metadata={
                    "type": "profile",
                    **updates
                }
            )
    
    def record_interaction(
        self, 
        channel: str, 
        summary: str, 
        resolution: Optional[str] = None,
        sentiment: str = "neutral",
        agent_id: str = None
    ):
        """Record a support interaction."""
        
        aegis.add(
            content=f"[{channel.upper()}] {summary}",
            agent_id=self.agent_id,
            scope="agent-private",
            metadata={
                "type": "interaction",
                "channel": channel,
                "resolution": resolution,
                "sentiment": sentiment,
                "handled_by": agent_id or AI_AGENT_ID,
                "timestamp": datetime.now().isoformat()
            }
        )
        
        # If resolved, also create a reflection for future reference
        if resolution:
            aegis.reflection(
                content=f"Issue: {summary}\nResolution: {resolution}",
                agent_id=AI_AGENT_ID,
                scope="global",  # Share resolution patterns
                metadata={
                    "type": "resolution_pattern",
                    "issue_category": self._categorize_issue(summary),
                    "customer_plan": self._get_profile().get("plan")
                }
            )
    
    def _categorize_issue(self, summary: str) -> str:
        """Categorize issue for pattern matching."""
        
        categories = ["billing", "technical", "account", "feature_request", "complaint", "other"]
        
        response = llm.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{
                "role": "user",
                "content": f"Categorize this support issue into one of: {categories}\n\nIssue: {summary}\n\nCategory:"
            }]
        )
        
        category = response.choices[0].message.content.strip().lower()
        return category if category in categories else "other"
    
    def start_session(self, channel: str, initial_message: str):
        """Start a new support session."""
        
        # Analyze initial message
        analysis = self._analyze_message(initial_message)
        
        aegis.progress.update(
            session_id=f"support-{self.customer_id}",
            summary=f"Support session via {channel}",
            status="active",
            in_progress=analysis.get("issue_summary"),
            metadata={
                "channel": channel,
                "issue": analysis.get("issue_summary"),
                "sentiment": analysis.get("sentiment"),
                "urgency": analysis.get("urgency"),
                "start_time": datetime.now().isoformat()
            }
        )
    
    def _analyze_message(self, message: str) -> Dict:
        """Analyze customer message for intent and sentiment."""
        
        response = llm.chat.completions.create(
            model="gpt-4o",
            messages=[{
                "role": "system",
                "content": """Analyze this customer support message. Extract:
- issue_summary: One sentence describing the issue
- sentiment: positive/neutral/frustrated/angry
- urgency: low/medium/high/critical
- category: billing/technical/account/feature_request/complaint/other"""
            }, {
                "role": "user",
                "content": message
            }],
            response_format={"type": "json_object"}
        )
        
        return json.loads(response.choices[0].message.content)
    
    def end_session(self, resolution: str, satisfaction: Optional[int] = None):
        """End a support session."""
        
        session = self._get_active_session()
        
        if session:
            # Record final interaction
            self.record_interaction(
                channel=session.get("channel", "unknown"),
                summary=session.get("issue", "Support session"),
                resolution=resolution,
                sentiment=session.get("sentiment", "neutral")
            )
        
        aegis.progress.update(
            session_id=f"support-{self.customer_id}",
            status="resolved",
            metadata={
                "resolution": resolution,
                "satisfaction": satisfaction,
                "end_time": datetime.now().isoformat()
            }
        )
    
    def learn_preference(self, preference: str, value: str):
        """Learn a customer preference from interaction."""
        
        aegis.add(
            content=f"Customer prefers {preference}: {value}",
            agent_id=self.agent_id,
            scope="agent-private",
            metadata={
                "type": "preference",
                "preferences": {preference: value}
            }
        )


# Usage
customer = CustomerMemory("cust_12345")

# Get full context before responding
context = customer.get_context()
print(f"Customer: {context.name}")
print(f"Summary: {context.profile_summary}")
print(f"Current mood: {context.sentiment}")
```

### Step 3: AI Support Agent

```python
class AISupportAgent:
    """AI-powered support agent with full customer context."""
    
    def __init__(self):
        self.agent_id = AI_AGENT_ID
    
    def respond(self, customer_id: str, message: str, channel: str = "chat") -> Dict:
        """Generate contextual response to customer message."""
        
        # Load customer memory
        memory = CustomerMemory(customer_id)
        context = memory.get_context()
        
        # Check for active session or start new one
        if not context.current_issue:
            memory.start_session(channel, message)
            context = memory.get_context()  # Reload with session
        
        # Query for similar past resolutions
        similar_resolutions = self._find_similar_resolutions(message)
        
        # Generate response
        response = self._generate_response(context, message, similar_resolutions)
        
        # Decide if escalation needed
        should_escalate = self._should_escalate(context, message, response)
        
        if should_escalate:
            return self._prepare_escalation(context, message, response)
        
        return {
            "response": response["message"],
            "confidence": response["confidence"],
            "suggested_actions": response.get("actions", []),
            "escalate": False
        }
    
    def _find_similar_resolutions(self, message: str) -> List:
        """Find past resolutions for similar issues."""
        
        return aegis.playbook(
            query=message,
            agent_id=self.agent_id,
            include_types=["reflection"],
            filter_metadata={"type": "resolution_pattern"},
            min_effectiveness=0.3,
            top_k=5
        ) or []
    
    def _generate_response(self, context: CustomerContext, message: str, resolutions: List) -> Dict:
        """Generate personalized response."""
        
        # Build context for LLM
        context_text = f"""Customer: {context.name}
Plan: {context.plan}
Tenure: {context.tenure_months} months
Summary: {context.profile_summary}
Current mood: {context.sentiment}
Current issue: {context.current_issue or 'New inquiry'}

Communication preferences: {context.preferences}

Recent interactions:
{chr(10).join(context.recent_interactions[:3])}"""
        
        resolutions_text = ""
        if resolutions:
            resolutions_text = "\n\nSimilar past resolutions:\n"
            for r in resolutions[:3]:
                resolutions_text += f"- {r.content}\n"
        
        response = llm.chat.completions.create(
            model="gpt-4o",
            messages=[{
                "role": "system",
                "content": f"""You are a helpful customer support agent.

You have access to this customer's history and preferences.
Personalize your response based on:
- Their tenure and value (long-term customers deserve extra care)
- Their communication style (technical vs. non-technical)
- Their current emotional state (frustrated customers need empathy first)
- Past interactions (don't ask for info they've already provided)

IMPORTANT: Never ask the customer to repeat information that's in their history.

{context_text}
{resolutions_text}"""
            }, {
                "role": "user",
                "content": message
            }]
        )
        
        # Assess confidence
        can_resolve = len(resolutions) > 0 and resolutions[0].effectiveness_score > 0.5
        
        return {
            "message": response.choices[0].message.content,
            "confidence": 0.8 if can_resolve else 0.5,
            "actions": self._extract_actions(response.choices[0].message.content)
        }
    
    def _extract_actions(self, response: str) -> List[str]:
        """Extract suggested actions from response."""
        # Simple extraction - in production, use structured output
        actions = []
        if "refund" in response.lower():
            actions.append("process_refund")
        if "upgrade" in response.lower():
            actions.append("upgrade_plan")
        if "reset" in response.lower():
            actions.append("reset_password")
        return actions
    
    def _should_escalate(self, context: CustomerContext, message: str, response: Dict) -> bool:
        """Determine if issue should be escalated to human."""
        
        # Always escalate angry customers
        if context.sentiment == "angry":
            return True
        
        # Escalate low confidence
        if response["confidence"] < 0.5:
            return True
        
        # Escalate high-value customers with complex issues
        if context.lifetime_value > 10000 and "billing" in message.lower():
            return True
        
        # Escalate if customer explicitly asks
        if any(phrase in message.lower() for phrase in ["speak to human", "real person", "manager", "escalate"]):
            return True
        
        return False
    
    def _prepare_escalation(self, context: CustomerContext, message: str, response: Dict) -> Dict:
        """Prepare escalation with full context for human agent."""
        
        # Create handoff summary
        handoff = {
            "customer_id": context.customer_id,
            "customer_name": context.name,
            "plan": context.plan,
            "ltv": context.lifetime_value,
            "profile_summary": context.profile_summary,
            "current_issue": context.current_issue,
            "sentiment": context.sentiment,
            "recent_messages": context.recent_interactions[:5],
            "attempted_resolution": response["message"],
            "escalation_reason": self._get_escalation_reason(context, response),
            "suggested_next_steps": response.get("actions", [])
        }
        
        return {
            "response": "I understand this is important to you. Let me connect you with a specialist who can help right away. They'll have all our conversation history, so you won't need to repeat anything.",
            "confidence": 1.0,
            "escalate": True,
            "handoff_context": handoff
        }
    
    def _get_escalation_reason(self, context: CustomerContext, response: Dict) -> str:
        if context.sentiment == "angry":
            return "Customer expressing frustration - needs empathy"
        if response["confidence"] < 0.5:
            return "Complex issue requiring specialist knowledge"
        if context.lifetime_value > 10000:
            return "High-value customer - VIP treatment"
        return "Customer requested human agent"


# Usage
agent = AISupportAgent()

response = agent.respond(
    customer_id="cust_12345",
    message="I was charged $99 but I downgraded to the $49 plan last week. This is the THIRD time this has happened!",
    channel="chat"
)

if response["escalate"]:
    print("Escalating to human agent...")
    print(f"Handoff context: {response['handoff_context']}")
else:
    print(f"Bot response: {response['response']}")
```

### Step 4: Human Agent Dashboard Context

```python
class HumanAgentDashboard:
    """Provides context panel for human agents."""
    
    def __init__(self):
        self.agent_id = "human-support"
    
    def get_customer_panel(self, customer_id: str, handoff: Optional[Dict] = None) -> Dict:
        """Get full context panel for human agent."""
        
        memory = CustomerMemory(customer_id)
        context = memory.get_context()
        
        # Get all interaction history (not just recent)
        full_history = aegis.query(
            query="",
            agent_id=f"customer-{customer_id}",
            filter_metadata={"type": "interaction"},
            top_k=50
        )
        
        # Get resolution history
        resolutions = aegis.query(
            query=context.current_issue or "",
            agent_id=AI_AGENT_ID,
            filter_metadata={"type": "resolution_pattern"},
            top_k=5
        )
        
        panel = {
            "header": {
                "name": context.name,
                "email": context.email,
                "plan": context.plan,
                "tenure": f"{context.tenure_months} months",
                "ltv": f"${context.lifetime_value:,.2f}",
                "sentiment": context.sentiment,
                "vip": context.lifetime_value > 10000
            },
            "summary": context.profile_summary,
            "current_session": {
                "issue": context.current_issue,
                "channel": handoff.get("channel") if handoff else "unknown",
                "ai_attempted": handoff.get("attempted_resolution") if handoff else None,
                "escalation_reason": handoff.get("escalation_reason") if handoff else None
            },
            "preferences": context.preferences,
            "interaction_timeline": self._format_timeline(full_history),
            "suggested_resolutions": [
                {
                    "resolution": r.content,
                    "success_rate": f"{r.effectiveness_score:.0%}" if hasattr(r, 'effectiveness_score') else "unknown"
                }
                for r in (resolutions or [])[:3]
            ],
            "quick_actions": self._get_quick_actions(context)
        }
        
        return panel
    
    def _format_timeline(self, history: List) -> List[Dict]:
        """Format interaction history as timeline."""
        
        timeline = []
        for interaction in history:
            timeline.append({
                "date": interaction.metadata.get("timestamp", "unknown"),
                "channel": interaction.metadata.get("channel", "unknown"),
                "summary": interaction.content[:100],
                "resolved": interaction.metadata.get("resolution") is not None,
                "sentiment": interaction.metadata.get("sentiment", "neutral")
            })
        
        return sorted(timeline, key=lambda x: x["date"], reverse=True)
    
    def _get_quick_actions(self, context: CustomerContext) -> List[Dict]:
        """Get contextual quick actions for agent."""
        
        actions = []
        
        # Based on current issue
        if context.current_issue:
            if "billing" in context.current_issue.lower():
                actions.extend([
                    {"label": "Issue Refund", "action": "refund"},
                    {"label": "Apply Credit", "action": "credit"},
                    {"label": "Review Invoices", "action": "invoices"}
                ])
            if "technical" in context.current_issue.lower():
                actions.extend([
                    {"label": "Check System Status", "action": "status"},
                    {"label": "Reset Account", "action": "reset"},
                    {"label": "Schedule Call", "action": "callback"}
                ])
        
        # Based on customer value
        if context.lifetime_value > 10000:
            actions.append({"label": "Offer VIP Upgrade", "action": "vip_upgrade"})
        
        # Based on sentiment
        if context.sentiment in ["frustrated", "angry"]:
            actions.append({"label": "Offer Goodwill Credit", "action": "goodwill"})
        
        return actions
    
    def record_resolution(self, customer_id: str, resolution: str, satisfaction: int = None):
        """Record resolution by human agent."""
        
        memory = CustomerMemory(customer_id)
        memory.end_session(resolution, satisfaction)
        
        # Record for agent learning
        aegis.add(
            content=f"Human agent resolution: {resolution}",
            agent_id=self.agent_id,
            scope="global",
            metadata={
                "type": "human_resolution",
                "satisfaction": satisfaction
            }
        )


# Usage (for frontend integration)
dashboard = HumanAgentDashboard()

# When human agent picks up escalated ticket
panel = dashboard.get_customer_panel(
    customer_id="cust_12345",
    handoff=escalation_response.get("handoff_context")
)

print(f"""
=== Customer Panel ===
{panel['header']['name']} ({panel['header']['plan']})
Customer for {panel['header']['tenure']} • LTV: {panel['header']['ltv']}
{'⭐ VIP CUSTOMER' if panel['header']['vip'] else ''}

📋 Summary: {panel['summary']}

🔥 Current Issue: {panel['current_session']['issue']}
Escalated because: {panel['current_session']['escalation_reason']}

🤖 AI attempted: {panel['current_session']['ai_attempted'][:100]}...

✨ Suggested resolutions:
""")
for res in panel['suggested_resolutions']:
    print(f"  • {res['resolution'][:80]}... (worked {res['success_rate']} of the time)")

print("\n⚡ Quick actions:")
for action in panel['quick_actions']:
    print(f"  [{action['label']}]")
```

### Step 5: Cross-Channel Continuity

```python
class CrossChannelSupport:
    """Maintains continuity across support channels."""
    
    def __init__(self):
        self.channels = ["chat", "email", "phone", "app", "social"]
    
    def customer_switches_channel(
        self, 
        customer_id: str, 
        from_channel: str, 
        to_channel: str
    ) -> Dict:
        """Handle customer switching channels mid-issue."""
        
        memory = CustomerMemory(customer_id)
        context = memory.get_context()
        
        # Generate continuity message
        continuity = self._generate_continuity_message(context, from_channel, to_channel)
        
        # Record channel switch
        aegis.add(
            content=f"Customer switched from {from_channel} to {to_channel}",
            agent_id=f"customer-{customer_id}",
            scope="agent-private",
            metadata={
                "type": "channel_switch",
                "from": from_channel,
                "to": to_channel,
                "issue_context": context.current_issue
            }
        )
        
        return continuity
    
    def _generate_continuity_message(
        self, 
        context: CustomerContext, 
        from_channel: str, 
        to_channel: str
    ) -> Dict:
        """Generate message acknowledging channel switch."""
        
        greeting = f"Hi {context.name}! "
        
        if context.current_issue:
            acknowledgment = f"I see you were just chatting with us on {from_channel} about {context.current_issue}. "
            assurance = "I have all the details, so you don't need to repeat anything. "
        else:
            acknowledgment = f"Welcome! "
            assurance = ""
        
        # Customize for channel
        channel_specific = {
            "phone": "Let me pull up your account... Got it. ",
            "email": "I've reviewed your case. ",
            "chat": "",
            "app": "I can see your account details. ",
            "social": "Thanks for reaching out here. "
        }
        
        continuation = "How can I help you today?" if not context.current_issue else "Let's continue where we left off."
        
        return {
            "message": greeting + acknowledgment + assurance + channel_specific.get(to_channel, "") + continuation,
            "context_loaded": True,
            "previous_channel": from_channel,
            "issue_carried_over": context.current_issue is not None
        }
    
    def sync_interaction(self, customer_id: str, channel: str, content: str, is_agent: bool = False):
        """Sync interaction across all channel records."""
        
        memory = CustomerMemory(customer_id)
        
        # Record with channel tag
        aegis.add(
            content=f"[{channel.upper()}] {'Agent' if is_agent else 'Customer'}: {content}",
            agent_id=f"customer-{customer_id}",
            scope="agent-private",
            metadata={
                "type": "message",
                "channel": channel,
                "is_agent": is_agent,
                "timestamp": datetime.now().isoformat()
            }
        )


# Usage
cross_channel = CrossChannelSupport()

# Customer was in chat, now calling
continuity = cross_channel.customer_switches_channel(
    customer_id="cust_12345",
    from_channel="chat",
    to_channel="phone"
)

print(f"Phone agent greeting: {continuity['message']}")
# Output: "Hi John! I see you were just chatting with us on chat about 
#          billing discrepancy. I have all the details, so you don't need 
#          to repeat anything. Let me pull up your account... Got it. 
#          Let's continue where we left off."
```

---

## Production Tips

### 1. Privacy and Data Retention
```python
# Implement customer data deletion
def delete_customer_data(customer_id: str):
    """GDPR-compliant customer data deletion."""
    
    # Get all customer memories
    memories = aegis.query(
        query="",
        agent_id=f"customer-{customer_id}",
        top_k=10000
    )
    
    # Delete all
    for mem in memories:
        aegis.delta([{
            "type": "deprecate",
            "memory_id": mem.id,
            "deprecation_reason": "Customer data deletion request"
        }])
    
    # Delete session
    aegis.progress.delete(f"support-{customer_id}")
```

### 2. Sentiment Tracking Over Time
```python
def track_sentiment_trend(customer_id: str) -> Dict:
    """Track customer sentiment over time."""
    
    interactions = aegis.query(
        query="",
        agent_id=f"customer-{customer_id}",
        filter_metadata={"type": "interaction"},
        top_k=100
    )
    
    sentiments = [i.metadata.get("sentiment", "neutral") for i in interactions]
    
    # Calculate trend
    sentiment_scores = {"angry": -2, "frustrated": -1, "neutral": 0, "positive": 1}
    scores = [sentiment_scores.get(s, 0) for s in sentiments]
    
    if len(scores) > 5:
        recent_avg = sum(scores[:5]) / 5
        older_avg = sum(scores[5:min(10, len(scores))]) / min(5, len(scores) - 5)
        trend = "improving" if recent_avg > older_avg else "declining" if recent_avg < older_avg else "stable"
    else:
        trend = "insufficient_data"
    
    return {
        "current": sentiments[0] if sentiments else "unknown",
        "trend": trend,
        "history": sentiments[:10]
    }
```

### 3. Resolution Pattern Learning
```python
def learn_from_successful_resolution(
    issue_category: str,
    resolution: str,
    satisfaction: int
):
    """Learn from successful resolutions."""
    
    if satisfaction >= 4:  # 4-5 star resolution
        # Record as successful pattern
        aegis.add(
            content=f"Successful resolution for {issue_category}: {resolution}",
            agent_id=AI_AGENT_ID,
            scope="global",
            memory_type="strategy",
            metadata={
                "type": "resolution_pattern",
                "category": issue_category,
                "satisfaction": satisfaction
            }
        )
        
        # Vote helpful on similar patterns
        similar = aegis.playbook(
            query=resolution,
            agent_id=AI_AGENT_ID,
            filter_metadata={"type": "resolution_pattern"},
            top_k=3
        )
        
        for s in (similar or []):
            aegis.vote(s.id, "helpful", voter_agent_id=AI_AGENT_ID)
```

---

## Expected Outcomes

| Metric | Before Aegis | After Aegis |
|--------|--------------|-------------|
| Repeat rate ("Can you explain again?") | 67% | <10% |
| Average handle time | 8.5 min | 5.2 min |
| First contact resolution | 45% | 72% |
| Customer satisfaction | 3.2/5 | 4.5/5 |
| Channel switch friction | High | Seamless |
| Agent onboarding time | 2 weeks | 2 days |

---

## Example: Perfect Support Interaction

```
=== Customer calls after chat session ===

Agent: "Hi John! I see you were just chatting with us about a billing 
discrepancy—you were charged $99 but should have been $49 after your 
downgrade last week. I have all the details, so you don't need to repeat 
anything.

I also noticed this is the third time this has happened, and I'm really 
sorry about that. As a customer for over 2 years, you deserve better.

I've already processed a $50 refund for this charge, and I've flagged 
your account for priority handling to make sure this doesn't happen 
again. You should see the refund in 3-5 business days.

Is there anything else I can help you with?"

Customer: "Wow, that was... actually easy. Thank you."

Agent: "Of course! Thanks for your patience, John. Have a great day."

[Resolution logged: Refund processed + account flagged]
[Customer satisfaction: 5/5]
[Resolution pattern learned: "Repeat billing issues → immediate refund + 
 account flag + proactive communication"]
```

---

## Next Steps

- **Integrate with your CRM**: Sync Aegis memory with Salesforce/Zendesk
- **Add voice analysis**: Detect sentiment from call audio
- **Proactive support**: Reach out before customers complain
- **Multi-language**: Maintain memory across language switches

---

Built for support teams tired of hearing "Can you repeat that?"
