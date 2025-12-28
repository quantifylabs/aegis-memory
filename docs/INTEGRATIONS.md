# Framework Integrations

Aegis Memory provides first-class support for popular AI agent frameworks. This guide explains how to use Aegis with LangChain and CrewAI.

---

## LangChain Integration

Aegis Memory provides a LangChain-compatible memory class that allows you to store conversation history and facts in Aegis, enabling semantic search and cross-session persistence.

### Installation
```bash
pip install "aegis-memory[langchain]"
```

### Basic Usage
Use `AegisMemory` within any LangChain chain:

```python
from aegis_memory.integrations.langchain import AegisMemory
from langchain.chains import ConversationChain
from langchain_openai import ChatOpenAI

# Initialize Aegis Memory
memory = AegisMemory(
    api_key="your-aegis-key",
    agent_id="support-agent",
    namespace="customer-service"
)

# Use in a chain
chain = ConversationChain(
    llm=ChatOpenAI(),
    memory=memory
)

# Memory is handled automatically
response = chain.predict(input="My name is John and I'm a Python developer.")
```

### Advanced Features
- **Scopes**: Control memory visibility using `scope="agent-private"`, `"agent-shared"`, or `"global"`.
- **Semantic Retrieval**: The memory class automatically performs semantic search on the input to retrieve the most relevant context.
- **Message Support**: Set `return_messages=True` to get list of message objects instead of a formatted string.

---

## CrewAI Integration

Aegis provides specialized memory for CrewAI that supports multi-agent coordination and ACE patterns (Agentic Context Engineering).

### Installation
```bash
pip install "aegis-memory[crewai]"
```

### Crew-Level Memory
Use `AegisCrewMemory` to provide shared long-term storage for an entire crew:

```python
from aegis_memory.integrations.crewai import AegisCrewMemory
from crewai import Crew, Agent

# Shared memory for the entire crew
crew_memory = AegisCrewMemory(
    api_key="your-aegis-key",
    namespace="research-project"
)

researcher = Agent(
    role="Researcher",
    goal="Find breakthrough patterns in the data",
    memory=True
)

crew = Crew(
    agents=[researcher],
    memory=crew_memory
)
```

### Agent-Specific Memory (ACE Patterns)
For advanced coordination, use `AegisAgentMemory` to enable scoped memory and self-improvement patterns:

```python
from aegis_memory.integrations.crewai import AegisAgentMemory, AegisCrewMemory

crew_mem = AegisCrewMemory(api_key="...")

# Memory scoped to a specific agent role
researcher_mem = AegisAgentMemory(
    crew_memory=crew_mem,
    agent_id="Researcher",
    scope="agent-shared"
)

# Store a reflection after a task (ACE pattern)
researcher_mem.add_reflection(
    content="Always verify data sources from .gov sites first",
    correct_approach="Start with official government databases"
)

# Handoff state to another agent
baton = researcher_mem.handoff_to("Writer", task_context="Data verified")
```

### Key Capabilities
- **Cross-Agent Queries**: Agents can search for information stored by other agents if the scope allows.
- **Handoffs**: Structured state transfer between agents.
- **Playbooks**: Query for proven strategies and reflections before starting a task.
- **Memory Voting**: Track which memories lead to success vs failure.

---

## Need Support?
If you're using a framework not listed here (like LangGraph or AutoGen), you can use the `AegisClient` directly or [open an issue](https://github.com/quantifylabs/aegis-memory/issues) for a new integration.

