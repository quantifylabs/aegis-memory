"""
Aegis Memory - Smart Memory

Intelligent memory that automatically extracts and stores valuable information
from conversations. Zero-config for basic use, fully configurable for power users.

This is the "missing layer" between raw conversation and Aegis storage.

Example (Zero-Config):
    from aegis_memory import SmartMemory
    
    memory = SmartMemory(
        aegis_api_key="your-aegis-key",
        llm_api_key="your-openai-key"
    )
    
    # After each conversation turn:
    memory.process_turn(
        user_input="I'm John, a developer from Chennai. I prefer dark mode.",
        ai_response="Nice to meet you, John!",
        user_id="user_123"
    )
    
    # Before generating response, get relevant context:
    context = memory.get_context(
        query="What theme should I use?",
        user_id="user_123"
    )
    # Returns: "User prefers dark mode"

Example (Configured):
    memory = SmartMemory(
        aegis_api_key="...",
        llm_api_key="...",
        llm_provider="anthropic",
        use_case="coding",
        sensitivity="high",
        auto_store=True
    )
"""

from typing import Any, Dict, List, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime
import asyncio

from .client import AegisClient
from .filters import MessageFilter, FilterResult, SignalType
from .extractors import (
    MemoryExtractor, 
    ExtractedMemory, 
    ExtractionResult,
    OpenAIAdapter,
    AnthropicAdapter,
    CustomLLMAdapter,
    LLMAdapter,
)


# =============================================================================
# Data Types
# =============================================================================

@dataclass
class ProcessResult:
    """Result of processing a conversation turn."""
    extracted: List[ExtractedMemory]
    stored_ids: List[str]
    skipped_reason: Optional[str] = None
    filter_result: Optional[FilterResult] = None
    

@dataclass
class ContextResult:
    """Result of getting context for a query."""
    context_string: str
    memories: List[Dict[str, Any]]
    query_time_ms: float


# =============================================================================
# Smart Memory Class
# =============================================================================

class SmartMemory:
    """
    Intelligent memory that automatically extracts valuable information.
    
    The two-stage process:
    1. FILTER: Fast rule-based check - "Does this look valuable?"
    2. EXTRACT: LLM-based extraction - "What exactly should we remember?"
    
    This avoids expensive LLM calls for obvious non-memories.
    
    Args:
        aegis_api_key: API key for Aegis Memory server
        aegis_base_url: Aegis server URL (default: http://localhost:8000)
        llm_api_key: API key for LLM (OpenAI or Anthropic)
        llm_provider: "openai" or "anthropic" (default: "openai")
        llm_model: Model to use for extraction (default: gpt-4o-mini)
        use_case: Extraction profile - "conversational", "task", "coding", "research", "creative", "support"
        sensitivity: Filter sensitivity - "high", "balanced", "low"
        auto_store: Automatically store extracted memories (default: True)
        namespace: Aegis namespace for memories (default: "default")
        default_agent_id: Default agent ID if not specified per-call
    """
    
    def __init__(
        self,
        aegis_api_key: str,
        aegis_base_url: str = "http://localhost:8000",
        llm_api_key: str = None,
        llm_provider: str = "openai",
        llm_model: str = None,
        use_case: str = "conversational",
        sensitivity: str = "balanced",
        auto_store: bool = True,
        namespace: str = "default",
        default_agent_id: str = "smart-memory",
        custom_llm: LLMAdapter = None,
    ):
        # Aegis client for storage
        self.client = AegisClient(
            api_key=aegis_api_key,
            base_url=aegis_base_url
        )
        
        # Filter for fast pre-checking
        self.filter = MessageFilter(sensitivity=sensitivity)
        
        # LLM for extraction
        if custom_llm:
            self.llm = custom_llm
        elif llm_provider == "openai":
            self.llm = OpenAIAdapter(
                api_key=llm_api_key,
                model=llm_model or "gpt-4o-mini"
            )
        elif llm_provider == "anthropic":
            self.llm = AnthropicAdapter(
                api_key=llm_api_key,
                model=llm_model or "claude-3-haiku-20240307"
            )
        else:
            raise ValueError(
                f"Unknown llm_provider: '{llm_provider}'. "
                f"Supported providers: 'openai', 'anthropic'. "
                f"For other LLMs, pass a custom_llm adapter instead."
            )
        
        # Extractor
        self.extractor = MemoryExtractor(
            llm=self.llm,
            use_case=use_case
        )
        
        # Settings
        self.auto_store = auto_store
        self.namespace = namespace
        self.default_agent_id = default_agent_id
        self.use_case = use_case
        
        # Stats
        self._stats = {
            "turns_processed": 0,
            "turns_filtered_out": 0,
            "memories_extracted": 0,
            "memories_stored": 0,
            "llm_calls": 0,
        }
    
    # =========================================================================
    # Main API
    # =========================================================================
    
    def process_turn(
        self,
        user_input: str,
        ai_response: str = "",
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        force_extract: bool = False,
    ) -> ProcessResult:
        """
        Process a conversation turn and extract/store valuable memories.
        
        This is the main method to call after each conversation turn.
        
        Args:
            user_input: What the user said
            ai_response: What the AI responded
            user_id: User identifier for the memories
            agent_id: Agent identifier (defaults to self.default_agent_id)
            metadata: Additional metadata to attach to memories
            force_extract: Skip filter and always extract (for debugging)
            
        Returns:
            ProcessResult with extracted memories and storage status
            
        Example:
            result = memory.process_turn(
                user_input="I prefer Python over JavaScript",
                ai_response="Python is great for many use cases!",
                user_id="user_123"
            )
            
            print(f"Extracted {len(result.extracted)} memories")
            print(f"Stored IDs: {result.stored_ids}")
        """
        self._stats["turns_processed"] += 1
        agent_id = agent_id or self.default_agent_id
        
        # Stage 1: Filter
        if not force_extract:
            user_filter = self.filter.check(user_input)
            ai_filter = self.filter.check(ai_response) if ai_response else None
            
            should_extract = user_filter.should_extract or (
                ai_filter and ai_filter.should_extract
            )
            
            if not should_extract:
                self._stats["turns_filtered_out"] += 1
                return ProcessResult(
                    extracted=[],
                    stored_ids=[],
                    skipped_reason="No memory signals detected",
                    filter_result=user_filter
                )
        else:
            user_filter = None
        
        # Stage 2: Extract
        self._stats["llm_calls"] += 1
        extraction = self.extractor.extract(user_input, ai_response)
        self._stats["memories_extracted"] += len(extraction.memories)
        
        # Stage 3: Store (if auto_store enabled)
        stored_ids = []
        if self.auto_store and extraction.memories:
            stored_ids = self._store_memories(
                memories=extraction.memories,
                user_id=user_id,
                agent_id=agent_id,
                metadata=metadata
            )
            self._stats["memories_stored"] += len(stored_ids)
        
        return ProcessResult(
            extracted=extraction.memories,
            stored_ids=stored_ids,
            filter_result=user_filter
        )
    
    async def process_turn_async(
        self,
        user_input: str,
        ai_response: str = "",
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        force_extract: bool = False,
    ) -> ProcessResult:
        """Async version of process_turn."""
        self._stats["turns_processed"] += 1
        agent_id = agent_id or self.default_agent_id
        
        # Stage 1: Filter (sync - fast enough)
        if not force_extract:
            user_filter = self.filter.check(user_input)
            ai_filter = self.filter.check(ai_response) if ai_response else None
            
            should_extract = user_filter.should_extract or (
                ai_filter and ai_filter.should_extract
            )
            
            if not should_extract:
                self._stats["turns_filtered_out"] += 1
                return ProcessResult(
                    extracted=[],
                    stored_ids=[],
                    skipped_reason="No memory signals detected",
                    filter_result=user_filter
                )
        else:
            user_filter = None
        
        # Stage 2: Extract (async)
        self._stats["llm_calls"] += 1
        extraction = await self.extractor.extract_async(user_input, ai_response)
        self._stats["memories_extracted"] += len(extraction.memories)
        
        # Stage 3: Store
        stored_ids = []
        if self.auto_store and extraction.memories:
            stored_ids = self._store_memories(
                memories=extraction.memories,
                user_id=user_id,
                agent_id=agent_id,
                metadata=metadata
            )
            self._stats["memories_stored"] += len(stored_ids)
        
        return ProcessResult(
            extracted=extraction.memories,
            stored_ids=stored_ids,
            filter_result=user_filter
        )
    
    def get_context(
        self,
        query: str,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        top_k: int = 5,
        max_tokens: int = 1000,
        include_scores: bool = False,
    ) -> ContextResult:
        """
        Get relevant context for a query.
        
        Call this before generating an AI response to inject relevant memories.
        
        Args:
            query: The current query/task
            user_id: User to get memories for
            agent_id: Agent making the query
            top_k: Maximum number of memories to retrieve
            max_tokens: Approximate token limit for context
            include_scores: Include similarity scores in output
            
        Returns:
            ContextResult with formatted context string and raw memories
            
        Example:
            context = memory.get_context(
                query="What color theme should I use?",
                user_id="user_123"
            )
            
            # Use in your prompt:
            prompt = f'''
            Known about user:
            {context.context_string}
            
            User question: What color theme should I use?
            '''
        """
        import time
        start = time.monotonic()
        
        agent_id = agent_id or self.default_agent_id
        
        # Query Aegis
        memories = self.client.query(
            query=query,
            user_id=user_id,
            agent_id=agent_id,
            namespace=self.namespace,
            top_k=top_k,
            min_score=0.3  # Reasonable threshold
        )
        
        # Format as context string
        if not memories:
            context_string = ""
        else:
            parts = []
            char_count = 0
            char_limit = max_tokens * 4  # Rough token estimate
            
            for mem in memories:
                if include_scores:
                    line = f"- [{mem.score:.2f}] {mem.content}"
                else:
                    line = f"- {mem.content}"
                
                if char_count + len(line) > char_limit:
                    break
                    
                parts.append(line)
                char_count += len(line)
            
            context_string = "\n".join(parts)
        
        elapsed_ms = (time.monotonic() - start) * 1000
        
        return ContextResult(
            context_string=context_string,
            memories=[{
                "content": m.content,
                "score": m.score,
                "memory_type": m.memory_type,
            } for m in memories],
            query_time_ms=round(elapsed_ms, 2)
        )
    
    def store_explicit(
        self,
        content: str,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        category: str = "fact",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Explicitly store a memory (bypass extraction).
        
        Use this when you know exactly what to store.
        
        Args:
            content: Memory content
            user_id: User identifier
            agent_id: Agent identifier
            category: Memory category
            metadata: Additional metadata
            
        Returns:
            Memory ID
        """
        agent_id = agent_id or self.default_agent_id
        
        # Map category to memory_type
        category_map = {
            "preference": "standard",
            "fact": "standard",
            "decision": "standard",
            "constraint": "standard",
            "goal": "standard",
            "strategy": "strategy",
            "mistake": "reflection",
        }
        memory_type = category_map.get(category, "standard")
        
        result = self.client.add(
            content=content,
            user_id=user_id,
            agent_id=agent_id,
            namespace=self.namespace,
            memory_type=memory_type,
            metadata={
                "category": category,
                "source": "explicit",
                **(metadata or {})
            }
        )
        
        return result.id
    
    # =========================================================================
    # Internal Methods
    # =========================================================================
    
    def _store_memories(
        self,
        memories: List[ExtractedMemory],
        user_id: Optional[str],
        agent_id: str,
        metadata: Optional[Dict[str, Any]],
    ) -> List[str]:
        """Store extracted memories to Aegis."""
        stored_ids = []
        
        for mem in memories:
            try:
                result = self.client.add(
                    content=mem.content,
                    user_id=user_id,
                    agent_id=agent_id,
                    namespace=self.namespace,
                    memory_type=mem.memory_type,
                    metadata={
                        "category": mem.category,
                        "confidence": mem.confidence,
                        "extracted_by": "smart_memory",
                        "use_case": self.use_case,
                        **(metadata or {}),
                        **mem.metadata,
                    }
                )
                stored_ids.append(result.id)
            except Exception as e:
                import sys
                print(
                    f"[aegis] Warning: failed to store memory "
                    f"'{mem.content[:50]}...': {e}",
                    file=sys.stderr,
                )
        
        return stored_ids
    
    # =========================================================================
    # Utilities
    # =========================================================================
    
    def get_stats(self) -> Dict[str, Any]:
        """Get processing statistics."""
        stats = self._stats.copy()
        
        # Calculate rates
        if stats["turns_processed"] > 0:
            stats["filter_rate"] = round(
                stats["turns_filtered_out"] / stats["turns_processed"], 3
            )
            stats["extraction_rate"] = round(
                stats["memories_extracted"] / stats["turns_processed"], 3
            )
        
        return stats
    
    def reset_stats(self):
        """Reset statistics counters."""
        self._stats = {
            "turns_processed": 0,
            "turns_filtered_out": 0,
            "memories_extracted": 0,
            "memories_stored": 0,
            "llm_calls": 0,
        }


# =============================================================================
# Smart Agent - Higher Level Wrapper
# =============================================================================

class SmartAgent:
    """
    Complete conversational agent with built-in smart memory.
    
    This is the highest-level abstraction - for users who want memory
    to "just work" with minimal code.
    
    Args:
        aegis_api_key: Aegis Memory API key
        llm_api_key: LLM API key (OpenAI or Anthropic)
        llm_provider: "openai" or "anthropic"
        chat_model: Model for chat responses
        memory_model: Model for memory extraction (cheaper model recommended)
        use_case: Memory extraction profile
        system_prompt: System prompt for the agent
        
    Example:
        agent = SmartAgent(
            aegis_api_key="...",
            llm_api_key="...",
            system_prompt="You are a helpful coding assistant."
        )
        
        # The agent handles memory automatically
        response = agent.chat(
            message="I'm John, I prefer Python over JavaScript",
            user_id="user_123"
        )
        
        # Later conversation automatically has context
        response = agent.chat(
            message="What language should I use for this project?",
            user_id="user_123"
        )
        # Agent knows user prefers Python!
    """
    
    def __init__(
        self,
        aegis_api_key: str,
        llm_api_key: str,
        aegis_base_url: str = "http://localhost:8000",
        llm_provider: str = "openai",
        chat_model: str = None,
        memory_model: str = None,
        use_case: str = "conversational",
        system_prompt: str = "You are a helpful assistant.",
        namespace: str = "default",
    ):
        # Smart memory for extraction/retrieval
        self.memory = SmartMemory(
            aegis_api_key=aegis_api_key,
            aegis_base_url=aegis_base_url,
            llm_api_key=llm_api_key,
            llm_provider=llm_provider,
            llm_model=memory_model,
            use_case=use_case,
            namespace=namespace,
        )
        
        # Chat LLM
        if llm_provider == "openai":
            self._chat_llm = OpenAIAdapter(
                api_key=llm_api_key,
                model=chat_model or "gpt-4o",
                temperature=0.7
            )
        elif llm_provider == "anthropic":
            self._chat_llm = AnthropicAdapter(
                api_key=llm_api_key,
                model=chat_model or "claude-3-sonnet-20240229",
                temperature=0.7
            )
        
        self.system_prompt = system_prompt
        self._conversation_history: Dict[str, List[Dict]] = {}
    
    def chat(
        self,
        message: str,
        user_id: str,
        agent_id: str = "smart-agent",
    ) -> str:
        """
        Send a message and get a response with automatic memory.
        
        Args:
            message: User's message
            user_id: User identifier
            agent_id: Agent identifier
            
        Returns:
            Assistant's response
        """
        # 1. Get relevant context from memory
        context = self.memory.get_context(
            query=message,
            user_id=user_id,
            agent_id=agent_id
        )
        
        # 2. Build prompt with memory context
        system = self.system_prompt
        if context.context_string:
            system += f"\n\nKnown about this user:\n{context.context_string}"
        
        # 3. Get conversation history
        history = self._conversation_history.get(user_id, [])
        
        # 4. Generate response
        prompt = self._build_chat_prompt(history, message)
        response = self._chat_llm.complete_sync(prompt, system=system)
        
        # 5. Update conversation history
        history.append({"role": "user", "content": message})
        history.append({"role": "assistant", "content": response})
        self._conversation_history[user_id] = history[-20:]  # Keep last 20
        
        # 6. Process turn for memory extraction (async in background ideally)
        self.memory.process_turn(
            user_input=message,
            ai_response=response,
            user_id=user_id,
            agent_id=agent_id
        )
        
        return response
    
    async def chat_async(
        self,
        message: str,
        user_id: str,
        agent_id: str = "smart-agent",
    ) -> str:
        """Async version of chat."""
        # 1. Get context
        context = self.memory.get_context(
            query=message,
            user_id=user_id,
            agent_id=agent_id
        )
        
        # 2. Build prompt
        system = self.system_prompt
        if context.context_string:
            system += f"\n\nKnown about this user:\n{context.context_string}"
        
        history = self._conversation_history.get(user_id, [])
        prompt = self._build_chat_prompt(history, message)
        
        # 3. Generate response
        response = await self._chat_llm.complete(prompt, system=system)
        
        # 4. Update history
        history.append({"role": "user", "content": message})
        history.append({"role": "assistant", "content": response})
        self._conversation_history[user_id] = history[-20:]
        
        # 5. Process for memory (async)
        await self.memory.process_turn_async(
            user_input=message,
            ai_response=response,
            user_id=user_id,
            agent_id=agent_id
        )
        
        return response
    
    def _build_chat_prompt(self, history: List[Dict], message: str) -> str:
        """Build chat prompt from history and new message."""
        parts = []
        
        for turn in history[-10:]:  # Last 10 turns
            role = "User" if turn["role"] == "user" else "Assistant"
            parts.append(f"{role}: {turn['content']}")
        
        parts.append(f"User: {message}")
        parts.append("Assistant:")
        
        return "\n\n".join(parts)
    
    def clear_history(self, user_id: str = None):
        """Clear conversation history."""
        if user_id:
            self._conversation_history.pop(user_id, None)
        else:
            self._conversation_history = {}
    
    def get_memory_stats(self) -> Dict[str, Any]:
        """Get memory processing statistics."""
        return self.memory.get_stats()


# =============================================================================
# Convenience Functions
# =============================================================================

def create_smart_memory(
    aegis_api_key: str,
    llm_api_key: str,
    provider: str = "openai",
    use_case: str = "conversational",
    **kwargs
) -> SmartMemory:
    """
    Create a SmartMemory instance with sensible defaults.
    
    Example:
        memory = create_smart_memory(
            aegis_api_key="...",
            llm_api_key="...",
            use_case="coding"
        )
    """
    return SmartMemory(
        aegis_api_key=aegis_api_key,
        llm_api_key=llm_api_key,
        llm_provider=provider,
        use_case=use_case,
        **kwargs
    )
