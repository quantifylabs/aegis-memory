"""
Aegis Memory - Smart Extractors

LLM-based extraction of valuable memories from conversations.
Contains prompts, extraction logic, and memory categorization.

The philosophy: Extract atomic, reusable facts. Not summaries.
"""

import json
import re
from typing import Any, Dict, List, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum
from abc import ABC, abstractmethod


# =============================================================================
# Data Types
# =============================================================================

@dataclass
class ExtractedMemory:
    """A single extracted memory."""
    content: str
    category: str  # preference, fact, decision, constraint, goal, strategy, mistake
    confidence: float
    memory_type: str  # Maps to Aegis memory_type: standard, strategy, reflection
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass 
class ExtractionResult:
    """Result of memory extraction from a conversation turn."""
    memories: List[ExtractedMemory]
    raw_response: str
    model_used: str
    tokens_used: int = 0


# =============================================================================
# Extraction Prompts
# =============================================================================

class ExtractionPrompts:
    """
    Pre-built extraction prompts for different use cases.
    
    Each prompt is designed to:
    1. Extract atomic facts (not summaries)
    2. Categorize appropriately
    3. Ignore noise
    4. Return structured JSON
    """
    
    # -------------------------------------------------------------------------
    # Core Prompt Template
    # -------------------------------------------------------------------------
    
    BASE_SYSTEM_PROMPT = """You are a memory extraction system. Your job is to extract valuable, 
reusable facts from conversations that would be helpful to remember long-term.

RULES:
1. Extract ATOMIC facts - one clear piece of information per memory
2. Rephrase in third person: "User prefers..." not "I prefer..."
3. Be specific and concrete, not vague
4. Only extract information worth remembering across sessions
5. Return empty array if nothing valuable

CATEGORIES:
- preference: Likes, dislikes, style preferences
- fact: Personal information (name, location, job, family)
- decision: Choices made, directions chosen
- constraint: Limits (budget, deadline, requirements)
- goal: What user wants to achieve
- strategy: What worked, best practices learned
- mistake: What didn't work, things to avoid

OUTPUT FORMAT (JSON only, no markdown):
{
  "memories": [
    {
      "content": "User prefers dark mode for all applications",
      "category": "preference",
      "confidence": 0.9
    }
  ]
}"""

    # -------------------------------------------------------------------------
    # Use-Case Specific Prompts
    # -------------------------------------------------------------------------
    
    CONVERSATIONAL = """You are extracting memories from a casual conversation.

Focus on:
- User preferences (likes, dislikes, habits)
- Personal facts (name, location, job, family, interests)
- Important relationships mentioned
- Recurring topics or concerns

Ignore:
- Greetings and pleasantries
- One-time questions with no lasting relevance
- Temporary states ("I'm tired today")

{base_rules}

CONVERSATION:
User: {user_input}
Assistant: {ai_response}

Extract memories (JSON only):"""

    TASK_ORIENTED = """You are extracting memories from a task-focused conversation.

Focus on:
- Decisions made about the task
- Constraints discovered (budget, deadline, requirements)
- Problems encountered and how they were solved
- Strategies that worked or didn't work
- User's goals and priorities

Ignore:
- Implementation details that won't generalize
- Temporary debugging information
- Questions about syntax or APIs (use docs for that)

{base_rules}

CONVERSATION:
User: {user_input}
Assistant: {ai_response}

Extract memories (JSON only):"""

    RESEARCH = """You are extracting memories from a research conversation.

Focus on:
- Key findings and insights
- Sources mentioned (with credibility notes)
- Contradictions or debates found
- Open questions to explore
- User's research interests and focus areas

Ignore:
- General knowledge the user was just learning
- Temporary search queries
- Information that's easily re-searchable

{base_rules}

CONVERSATION:
User: {user_input}
Assistant: {ai_response}

Extract memories (JSON only):"""

    CODING = """You are extracting memories from a coding/development conversation.

Focus on:
- Tech stack decisions (languages, frameworks, tools)
- Architecture decisions and their rationale
- Bugs encountered and their solutions
- Performance insights
- User's coding preferences and style
- Project constraints and requirements

Ignore:
- Syntax questions (docs are better)
- One-off debugging sessions
- Copy-paste code without context

{base_rules}

CONVERSATION:
User: {user_input}
Assistant: {ai_response}

Extract memories (JSON only):"""

    CREATIVE = """You are extracting memories from a creative conversation (writing, design, art).

Focus on:
- Style preferences (tone, voice, aesthetic)
- Project details (characters, themes, goals)
- Feedback preferences (what kind of critique they want)
- Creative constraints and requirements
- Inspiration sources mentioned

Ignore:
- Draft iterations (save finals only)
- Brainstorm ideas that were rejected
- Generic creative advice

{base_rules}

CONVERSATION:
User: {user_input}
Assistant: {ai_response}

Extract memories (JSON only):"""

    SUPPORT = """You are extracting memories from a customer support conversation.

Focus on:
- User's product/service setup
- Past issues and their resolutions
- User's technical skill level
- Preferences for communication
- Account or subscription details mentioned

Ignore:
- Troubleshooting steps (they're documented)
- Temporary error messages
- Generic support pleasantries

{base_rules}

CONVERSATION:
User: {user_input}
Assistant: {ai_response}

Extract memories (JSON only):"""

    @classmethod
    def get_prompt(cls, use_case: str = "conversational") -> str:
        """Get the appropriate prompt for a use case."""
        prompts = {
            "conversational": cls.CONVERSATIONAL,
            "task": cls.TASK_ORIENTED,
            "research": cls.RESEARCH,
            "coding": cls.CODING,
            "creative": cls.CREATIVE,
            "support": cls.SUPPORT,
        }
        
        base_prompt = prompts.get(use_case, cls.CONVERSATIONAL)
        return base_prompt.replace("{base_rules}", cls.BASE_SYSTEM_PROMPT)


# =============================================================================
# LLM Adapters
# =============================================================================

class LLMAdapter(ABC):
    """Abstract base class for LLM adapters."""
    
    @abstractmethod
    async def complete(self, prompt: str, system: str = None) -> str:
        """Generate completion from prompt."""
        pass
    
    @abstractmethod
    def complete_sync(self, prompt: str, system: str = None) -> str:
        """Synchronous version of complete."""
        pass


class OpenAIAdapter(LLMAdapter):
    """Adapter for OpenAI API."""
    
    def __init__(
        self, 
        api_key: str = None,
        model: str = "gpt-4o-mini",  # Cost-effective for extraction
        temperature: float = 0.1,    # Low temperature for consistency
    ):
        self.model = model
        self.temperature = temperature
        self._client = None
        self._async_client = None
        self._api_key = api_key
    
    @property
    def client(self):
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(api_key=self._api_key)
        return self._client
    
    @property
    def async_client(self):
        if self._async_client is None:
            from openai import AsyncOpenAI
            self._async_client = AsyncOpenAI(api_key=self._api_key)
        return self._async_client
    
    async def complete(self, prompt: str, system: str = None) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        
        response = await self.async_client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
            response_format={"type": "json_object"},
        )
        return response.choices[0].message.content
    
    def complete_sync(self, prompt: str, system: str = None) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
            response_format={"type": "json_object"},
        )
        return response.choices[0].message.content


class AnthropicAdapter(LLMAdapter):
    """Adapter for Anthropic API."""
    
    def __init__(
        self,
        api_key: str = None,
        model: str = "claude-3-haiku-20240307",  # Cost-effective
        temperature: float = 0.1,
    ):
        self.model = model
        self.temperature = temperature
        self._client = None
        self._async_client = None
        self._api_key = api_key
    
    @property
    def client(self):
        if self._client is None:
            from anthropic import Anthropic
            self._client = Anthropic(api_key=self._api_key)
        return self._client
    
    @property
    def async_client(self):
        if self._async_client is None:
            from anthropic import AsyncAnthropic
            self._async_client = AsyncAnthropic(api_key=self._api_key)
        return self._async_client
    
    async def complete(self, prompt: str, system: str = None) -> str:
        response = await self.async_client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=system or "",
            messages=[{"role": "user", "content": prompt + "\n\nRespond with JSON only."}],
        )
        return response.content[0].text
    
    def complete_sync(self, prompt: str, system: str = None) -> str:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=system or "",
            messages=[{"role": "user", "content": prompt + "\n\nRespond with JSON only."}],
        )
        return response.content[0].text


class CustomLLMAdapter(LLMAdapter):
    """Adapter for any custom LLM function."""
    
    def __init__(
        self,
        sync_fn: Callable[[str], str] = None,
        async_fn: Callable[[str], str] = None,
    ):
        """
        Initialize with custom completion functions.
        
        Args:
            sync_fn: Function that takes prompt string, returns completion string
            async_fn: Async version of sync_fn
        """
        self._sync_fn = sync_fn
        self._async_fn = async_fn
    
    async def complete(self, prompt: str, system: str = None) -> str:
        if self._async_fn:
            full_prompt = f"{system}\n\n{prompt}" if system else prompt
            return await self._async_fn(full_prompt)
        else:
            return self.complete_sync(prompt, system)
    
    def complete_sync(self, prompt: str, system: str = None) -> str:
        if self._sync_fn is None:
            raise RuntimeError("No sync completion function provided")
        full_prompt = f"{system}\n\n{prompt}" if system else prompt
        return self._sync_fn(full_prompt)


# =============================================================================
# Memory Extractor
# =============================================================================

class MemoryExtractor:
    """
    Extracts valuable memories from conversations using LLM.
    
    Example:
        extractor = MemoryExtractor(
            llm=OpenAIAdapter(api_key="..."),
            use_case="conversational"
        )
        
        result = extractor.extract(
            user_input="I'm John, a developer from Chennai",
            ai_response="Nice to meet you, John!"
        )
        
        for memory in result.memories:
            print(f"[{memory.category}] {memory.content}")
    """
    
    # Map categories to Aegis memory_type
    CATEGORY_TO_TYPE = {
        "preference": "standard",
        "fact": "standard",
        "decision": "standard",
        "constraint": "standard",
        "goal": "standard",
        "strategy": "strategy",
        "mistake": "reflection",
    }
    
    def __init__(
        self,
        llm: LLMAdapter,
        use_case: str = "conversational",
        custom_prompt: str = None,
        min_confidence: float = 0.5,
    ):
        """
        Initialize memory extractor.
        
        Args:
            llm: LLM adapter for completions
            use_case: One of: conversational, task, research, coding, creative, support
            custom_prompt: Optional custom extraction prompt
            min_confidence: Minimum confidence to include memory
        """
        self.llm = llm
        self.use_case = use_case
        self.min_confidence = min_confidence
        
        if custom_prompt:
            self.prompt_template = custom_prompt
        else:
            self.prompt_template = ExtractionPrompts.get_prompt(use_case)
    
    def extract(
        self,
        user_input: str,
        ai_response: str = "",
    ) -> ExtractionResult:
        """
        Extract memories from a conversation turn (synchronous).
        
        Args:
            user_input: What the user said
            ai_response: What the AI responded (optional)
            
        Returns:
            ExtractionResult with list of extracted memories
        """
        prompt = self.prompt_template.format(
            user_input=user_input,
            ai_response=ai_response or "(no response yet)"
        )
        
        try:
            raw_response = self.llm.complete_sync(prompt)
            return self._parse_response(raw_response)
        except Exception as e:
            # Return empty result on error
            return ExtractionResult(
                memories=[],
                raw_response=str(e),
                model_used="error"
            )
    
    async def extract_async(
        self,
        user_input: str,
        ai_response: str = "",
    ) -> ExtractionResult:
        """
        Extract memories from a conversation turn (async).
        
        Args:
            user_input: What the user said
            ai_response: What the AI responded (optional)
            
        Returns:
            ExtractionResult with list of extracted memories
        """
        prompt = self.prompt_template.format(
            user_input=user_input,
            ai_response=ai_response or "(no response yet)"
        )
        
        try:
            raw_response = await self.llm.complete(prompt)
            return self._parse_response(raw_response)
        except Exception as e:
            return ExtractionResult(
                memories=[],
                raw_response=str(e),
                model_used="error"
            )
    
    def _parse_response(self, raw_response: str) -> ExtractionResult:
        """Parse LLM response into ExtractedMemory objects."""
        memories = []
        
        try:
            # Clean response (remove markdown code blocks if present)
            cleaned = raw_response.strip()
            if cleaned.startswith("```"):
                cleaned = re.sub(r"```json?\n?", "", cleaned)
                cleaned = re.sub(r"```\n?$", "", cleaned)
            
            data = json.loads(cleaned)
            
            for item in data.get("memories", []):
                confidence = item.get("confidence", 0.7)
                
                if confidence >= self.min_confidence:
                    category = item.get("category", "fact")
                    memory = ExtractedMemory(
                        content=item["content"],
                        category=category,
                        confidence=confidence,
                        memory_type=self.CATEGORY_TO_TYPE.get(category, "standard"),
                        metadata={
                            "extracted_by": "smart_memory",
                            "use_case": self.use_case,
                        }
                    )
                    memories.append(memory)
        
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            # Log but don't fail
            pass
        
        return ExtractionResult(
            memories=memories,
            raw_response=raw_response,
            model_used=getattr(self.llm, 'model', 'unknown')
        )
    
    def extract_batch(
        self,
        turns: List[Dict[str, str]],
    ) -> List[ExtractionResult]:
        """
        Extract memories from multiple conversation turns.
        
        Args:
            turns: List of {"user_input": "...", "ai_response": "..."}
            
        Returns:
            List of ExtractionResults
        """
        return [
            self.extract(turn["user_input"], turn.get("ai_response", ""))
            for turn in turns
        ]


# =============================================================================
# Convenience Functions
# =============================================================================

def create_extractor(
    provider: str = "openai",
    api_key: str = None,
    use_case: str = "conversational",
    **kwargs
) -> MemoryExtractor:
    """
    Create a memory extractor with specified provider.
    
    Args:
        provider: "openai", "anthropic", or "custom"
        api_key: API key for the provider
        use_case: Extraction use case
        **kwargs: Additional arguments for the LLM adapter
        
    Returns:
        Configured MemoryExtractor
        
    Example:
        extractor = create_extractor("openai", api_key="sk-...", use_case="coding")
    """
    if provider == "openai":
        llm = OpenAIAdapter(api_key=api_key, **kwargs)
    elif provider == "anthropic":
        llm = AnthropicAdapter(api_key=api_key, **kwargs)
    else:
        raise ValueError(f"Unknown provider: {provider}. Use 'openai' or 'anthropic'")
    
    return MemoryExtractor(llm=llm, use_case=use_case)
