"""
Aegis Memory LangChain Integration

Provides a LangChain-compatible memory class that uses Aegis Memory
as the backend for persistent, multi-agent memory.

Usage:
    from aegis_memory.integrations.langchain import AegisMemory
    from langchain.chains import ConversationChain
    from langchain_openai import ChatOpenAI
    
    memory = AegisMemory(
        api_key="your-aegis-key",
        base_url="http://localhost:8000",
        agent_id="conversational-agent",
        namespace="customer-support"
    )
    
    chain = ConversationChain(
        llm=ChatOpenAI(),
        memory=memory
    )
    
    response = chain.predict(input="Hello!")
"""

from typing import Any, Dict, List, Optional

try:
    from langchain_core.memory import BaseMemory
    from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
    LANGCHAIN_AVAILABLE = True
except ImportError:
    LANGCHAIN_AVAILABLE = False
    BaseMemory = object

from aegis_memory.client import AegisClient


class AegisMemory(BaseMemory if LANGCHAIN_AVAILABLE else object):
    """
    LangChain Memory backed by Aegis Memory.
    
    This memory class stores conversation history and facts in Aegis Memory,
    enabling persistent, cross-session, and multi-agent memory capabilities.
    
    Features:
    - Persistent memory across sessions
    - Multi-agent memory sharing via scopes
    - Semantic search over memory
    - ACE patterns (voting, reflections) available
    
    Args:
        api_key: Aegis Memory API key
        base_url: Aegis Memory server URL
        agent_id: Identifier for this agent
        user_id: Optional user identifier for user-specific memory
        namespace: Memory namespace (default: "default")
        memory_key: Key used in chain's input/output (default: "history")
        input_key: Key for human input (default: "input")
        output_key: Key for AI output (default: "output")
        return_messages: Return as Message objects vs string (default: False)
        scope: Memory scope ("agent-private", "agent-shared", "global")
        k: Number of recent memories to retrieve (default: 10)
    """
    
    # LangChain memory properties
    memory_key: str = "history"
    input_key: str = "input"
    output_key: str = "output"
    return_messages: bool = False
    
    def __init__(
        self,
        api_key: str,
        base_url: str = "http://localhost:8000",
        agent_id: str = "langchain-agent",
        user_id: Optional[str] = None,
        namespace: str = "default",
        memory_key: str = "history",
        input_key: str = "input",
        output_key: str = "output",
        return_messages: bool = False,
        scope: str = "agent-private",
        k: int = 10,
    ):
        if not LANGCHAIN_AVAILABLE:
            raise ImportError(
                "LangChain is not installed. Install with: "
                "pip install aegis-memory[langchain]"
            )
        
        super().__init__()
        
        self.client = AegisClient(api_key=api_key, base_url=base_url)
        self.agent_id = agent_id
        self.user_id = user_id
        self.namespace = namespace
        self.memory_key = memory_key
        self.input_key = input_key
        self.output_key = output_key
        self.return_messages = return_messages
        self.scope = scope
        self.k = k
    
    @property
    def memory_variables(self) -> List[str]:
        """Return memory variables."""
        return [self.memory_key]
    
    def load_memory_variables(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Load memory variables from Aegis Memory.
        
        Performs semantic search based on the input to find relevant memories.
        """
        # Get the input text for semantic search
        input_text = inputs.get(self.input_key, "")
        
        if not input_text:
            # If no input, return empty or recent memories
            return {self.memory_key: "" if not self.return_messages else []}
        
        # Query Aegis Memory for relevant context
        memories = self.client.query(
            query=input_text,
            agent_id=self.agent_id,
            user_id=self.user_id,
            namespace=self.namespace,
            top_k=self.k,
        )
        
        if self.return_messages:
            # Convert to LangChain messages
            messages = []
            for mem in memories:
                metadata = mem.metadata or {}
                if metadata.get("role") == "human":
                    messages.append(HumanMessage(content=mem.content))
                elif metadata.get("role") == "ai":
                    messages.append(AIMessage(content=mem.content))
            return {self.memory_key: messages}
        else:
            # Return as formatted string
            history_str = "\n".join([
                f"[{mem.metadata.get('role', 'memory')}]: {mem.content}"
                for mem in memories
            ])
            return {self.memory_key: history_str}
    
    def save_context(self, inputs: Dict[str, Any], outputs: Dict[str, str]) -> None:
        """
        Save context from this conversation turn to Aegis Memory.
        """
        input_text = inputs.get(self.input_key, "")
        output_text = outputs.get(self.output_key, "")
        
        # Save human input
        if input_text:
            self.client.add(
                content=input_text,
                agent_id=self.agent_id,
                user_id=self.user_id,
                namespace=self.namespace,
                scope=self.scope,
                metadata={"role": "human", "type": "conversation"},
            )
        
        # Save AI output
        if output_text:
            self.client.add(
                content=output_text,
                agent_id=self.agent_id,
                user_id=self.user_id,
                namespace=self.namespace,
                scope=self.scope,
                metadata={"role": "ai", "type": "conversation"},
            )
    
    def clear(self) -> None:
        """
        Clear memory.
        
        Note: This is a no-op for Aegis Memory as we prefer soft-delete
        via TTL or explicit deletion. Use the client directly if you
        need to delete specific memories.
        """
        pass
    
    def add_memory(
        self,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        scope: Optional[str] = None,
    ) -> str:
        """
        Add a standalone memory (not conversation history).
        
        Useful for storing facts, preferences, or other information
        that should be retrieved semantically.
        
        Returns:
            Memory ID
        """
        result = self.client.add(
            content=content,
            agent_id=self.agent_id,
            user_id=self.user_id,
            namespace=self.namespace,
            scope=scope or self.scope,
            metadata=metadata or {},
        )
        return result["id"]
    
    def search(
        self,
        query: str,
        top_k: Optional[int] = None,
        min_score: float = 0.0,
    ) -> List[Any]:
        """
        Search memories semantically.
        
        Args:
            query: Search query
            top_k: Number of results (default: self.k)
            min_score: Minimum similarity score
            
        Returns:
            List of Memory objects
        """
        return self.client.query(
            query=query,
            agent_id=self.agent_id,
            user_id=self.user_id,
            namespace=self.namespace,
            top_k=top_k or self.k,
            min_score=min_score,
        )


class AegisConversationMemory(AegisMemory):
    """
    Convenience class for conversation memory.
    
    Pre-configured for typical conversation chain use.
    """
    
    def __init__(
        self,
        api_key: str,
        base_url: str = "http://localhost:8000",
        agent_id: str = "conversational-agent",
        user_id: Optional[str] = None,
        namespace: str = "conversations",
        k: int = 5,
        **kwargs
    ):
        super().__init__(
            api_key=api_key,
            base_url=base_url,
            agent_id=agent_id,
            user_id=user_id,
            namespace=namespace,
            k=k,
            return_messages=True,
            **kwargs
        )
