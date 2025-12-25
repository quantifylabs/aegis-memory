"""
Aegis Memory Framework Integrations

Integrations for popular AI/ML frameworks:
- LangChain: aegis_memory.integrations.langchain
- CrewAI: aegis_memory.integrations.crewai

Install with extras:
    pip install aegis-memory[langchain]
    pip install aegis-memory[crewai]
    pip install aegis-memory[all]
"""

# Lazy imports to avoid requiring all frameworks
def __getattr__(name):
    if name == "langchain":
        from aegis_memory.integrations import langchain
        return langchain
    elif name == "crewai":
        from aegis_memory.integrations import crewai
        return crewai
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
