"""
Aegis Memory - Smart Filters

Fast rule-based pre-filtering to determine if a message MIGHT contain
valuable information worth extracting. This avoids expensive LLM calls
for obvious non-memories like greetings and confirmations.

The philosophy: Be generous in what passes the filter (false positives OK),
but catch obvious non-memories (false negatives bad).
"""

import re
from typing import List, Tuple, Set
from dataclasses import dataclass
from enum import Enum


class SignalType(Enum):
    """Types of signals that suggest valuable memory content."""
    PREFERENCE = "preference"
    PERSONAL_FACT = "personal_fact"
    DECISION = "decision"
    CONSTRAINT = "constraint"
    GOAL = "goal"
    PROBLEM = "problem"
    STRATEGY = "strategy"
    MISTAKE = "mistake"
    TEMPORAL = "temporal"
    RELATIONSHIP = "relationship"


@dataclass
class FilterResult:
    """Result of pre-filtering a message."""
    should_extract: bool
    signals: List[SignalType]
    confidence: float  # 0.0 to 1.0
    reason: str


class MessageFilter:
    """
    Fast rule-based filter to identify messages worth extracting memories from.
    
    Two-stage approach:
    1. Check for definite NON-memories (skip immediately)
    2. Check for memory SIGNALS (if found, worth extracting)
    
    Example:
        filter = MessageFilter()
        result = filter.check("I'm a software engineer in Chennai")
        # result.should_extract = True
        # result.signals = [SignalType.PERSONAL_FACT]
        
        result = filter.check("Thanks!")
        # result.should_extract = False
        # result.reason = "Short acknowledgment"
    """
    
    # =========================================================================
    # Stage 1: Definite NON-memories (skip these)
    # =========================================================================
    
    # Messages that are definitely not worth storing
    SKIP_PATTERNS: List[Tuple[str, str]] = [
        # Greetings
        (r"^(hi|hello|hey|greetings|good morning|good afternoon|good evening)[\s!.]*$", "greeting"),
        (r"^(bye|goodbye|see you|take care|later)[\s!.]*$", "farewell"),
        
        # Acknowledgments
        (r"^(ok|okay|sure|yes|no|yeah|yep|nope|alright|got it|understood|thanks|thank you|thx|ty)[\s!.]*$", "acknowledgment"),
        (r"^(great|good|nice|cool|awesome|perfect|sounds good)[\s!.]*$", "acknowledgment"),
        
        # Meta-conversation
        (r"^(what|huh|sorry|pardon|come again|repeat that|say again)\?*$", "clarification_request"),
        (r"^(please|pls) (continue|go on|proceed)[\s.]*$", "continuation_request"),
        
        # Filler
        (r"^(um+|uh+|hmm+|er+|ah+)[\s.]*$", "filler"),
        (r"^[.!?]+$", "punctuation_only"),
    ]
    
    # Very short messages are usually not memories
    MIN_MEANINGFUL_LENGTH = 15
    
    # =========================================================================
    # Stage 2: Memory SIGNALS (these suggest valuable content)
    # =========================================================================
    
    # Preference signals
    PREFERENCE_PATTERNS: List[str] = [
        r"\b(i prefer|i like|i love|i hate|i dislike|i enjoy|i don't like)\b",
        r"\b(my favorite|my preferred|i always|i never|i usually)\b",
        r"\b(rather than|instead of|better than|worse than)\b",
        r"\b(fan of|not a fan|into|not into)\b",
    ]
    
    # Personal fact signals
    PERSONAL_FACT_PATTERNS: List[str] = [
        r"\b(i am|i'm|i work|i live|i have|i've been|i was)\b",
        r"\b(my name|my job|my role|my title|my company|my team)\b",
        r"\b(my (wife|husband|partner|kids|children|family|dog|cat))\b",
        r"\b(i'm (a|an) \w+)\b",  # "I'm a developer", "I'm an engineer"
        r"\b(based in|located in|live in|from|born in)\b",
        r"\b(years? (old|of experience)|experience in)\b",
    ]
    
    # Decision signals
    DECISION_PATTERNS: List[str] = [
        r"\b(i('ve)? decided|i('ll| will) go with|i('m| am) going to)\b",
        r"\b(let's (go with|use|do)|we('ll| will) use)\b",
        r"\b(chosen|selected|picked|opted for|settled on)\b",
        r"\b(the plan is|we agreed|final decision)\b",
    ]
    
    # Constraint signals
    CONSTRAINT_PATTERNS: List[str] = [
        r"\b(budget|cost|price|afford|spend|max(imum)?|limit)\b",
        r"\b(deadline|due (date|by)|by (monday|tuesday|wednesday|thursday|friday|saturday|sunday))\b",
        r"\b(must|have to|need to|required|requirement|can't|cannot|unable)\b",
        r"\b(only|just|at most|at least|no more than|minimum)\b",
        r"\$[\d,]+|\d+\s*(dollars|usd|inr|rupees|euros|pounds)",  # Money amounts
    ]
    
    # Goal/Problem signals
    GOAL_PROBLEM_PATTERNS: List[str] = [
        r"\b(i want|i need|i'm trying|i wish|i hope|my goal)\b",
        r"\b(looking for|searching for|hoping to|planning to)\b",
        r"\b(problem|issue|challenge|struggling|stuck|help with)\b",
        r"\b(achieve|accomplish|complete|finish|build|create|make)\b",
    ]
    
    # Strategy signals (things that worked)
    STRATEGY_PATTERNS: List[str] = [
        r"\b(worked|works|effective|successful|solved|fixed)\b",
        r"\b(trick|tip|approach|method|way to|how to)\b",
        r"\b(best practice|pro tip|lesson learned|key insight)\b",
        r"\b(remember to|don't forget|make sure|always|never)\b",
    ]
    
    # Mistake signals (things that didn't work)
    MISTAKE_PATTERNS: List[str] = [
        r"\b(didn't work|doesn't work|failed|mistake|error|wrong)\b",
        r"\b(shouldn't|should not|bad idea|avoid|don't do)\b",
        r"\b(broke|broken|crashed|bug|issue|problem)\b",
        r"\b(learned (the hard way|that)|won't .* again)\b",
    ]
    
    # Temporal signals (important dates/times)
    TEMPORAL_PATTERNS: List[str] = [
        r"\b(january|february|march|april|may|june|july|august|september|october|november|december)\b",
        r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
        r"\b(next week|this week|last week|tomorrow|yesterday)\b",
        r"\b(meeting|appointment|call|event|launch|release)\b.*(at|on|scheduled)",
        r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}",  # Date patterns
    ]
    
    # Relationship signals
    RELATIONSHIP_PATTERNS: List[str] = [
        r"\b(my (boss|manager|colleague|coworker|client|customer|friend))\b",
        r"\b(works? (with|for|under)|reports? to|manages?)\b",
        r"\b(team|department|company|organization)\b",
    ]
    
    def __init__(self, sensitivity: str = "balanced"):
        """
        Initialize filter with sensitivity level.
        
        Args:
            sensitivity: "high" (extract more), "balanced", or "low" (extract less)
        """
        self.sensitivity = sensitivity
        
        # Compile regex patterns for speed
        self._skip_patterns = [(re.compile(p, re.IGNORECASE), reason) 
                               for p, reason in self.SKIP_PATTERNS]
        
        self._signal_patterns = {
            SignalType.PREFERENCE: [re.compile(p, re.IGNORECASE) for p in self.PREFERENCE_PATTERNS],
            SignalType.PERSONAL_FACT: [re.compile(p, re.IGNORECASE) for p in self.PERSONAL_FACT_PATTERNS],
            SignalType.DECISION: [re.compile(p, re.IGNORECASE) for p in self.DECISION_PATTERNS],
            SignalType.CONSTRAINT: [re.compile(p, re.IGNORECASE) for p in self.CONSTRAINT_PATTERNS],
            SignalType.GOAL: [re.compile(p, re.IGNORECASE) for p in self.GOAL_PROBLEM_PATTERNS],
            SignalType.STRATEGY: [re.compile(p, re.IGNORECASE) for p in self.STRATEGY_PATTERNS],
            SignalType.MISTAKE: [re.compile(p, re.IGNORECASE) for p in self.MISTAKE_PATTERNS],
            SignalType.TEMPORAL: [re.compile(p, re.IGNORECASE) for p in self.TEMPORAL_PATTERNS],
            SignalType.RELATIONSHIP: [re.compile(p, re.IGNORECASE) for p in self.RELATIONSHIP_PATTERNS],
        }
        
        # Sensitivity thresholds
        self._thresholds = {
            "high": 0,      # Any signal passes
            "balanced": 1,  # At least 1 signal
            "low": 2,       # At least 2 signals
        }
    
    def check(self, message: str) -> FilterResult:
        """
        Check if a message might contain valuable memory content.
        
        Args:
            message: The message to check
            
        Returns:
            FilterResult with should_extract, signals, confidence, and reason
        """
        message = message.strip()
        
        # Stage 1: Check for definite skips
        skip_result = self._check_skip_patterns(message)
        if skip_result:
            return skip_result
        
        # Stage 2: Check for memory signals
        signals = self._detect_signals(message)
        
        # Determine if we should extract
        threshold = self._thresholds.get(self.sensitivity, 1)
        should_extract = len(signals) > threshold
        
        # Calculate confidence based on number and type of signals
        confidence = self._calculate_confidence(signals, message)
        
        if should_extract:
            signal_names = [s.value for s in signals]
            return FilterResult(
                should_extract=True,
                signals=signals,
                confidence=confidence,
                reason=f"Detected signals: {', '.join(signal_names)}"
            )
        else:
            return FilterResult(
                should_extract=False,
                signals=signals,
                confidence=confidence,
                reason="No strong memory signals detected"
            )
    
    def _check_skip_patterns(self, message: str) -> FilterResult | None:
        """Check if message matches any skip pattern."""
        
        # Too short
        if len(message) < self.MIN_MEANINGFUL_LENGTH:
            return FilterResult(
                should_extract=False,
                signals=[],
                confidence=0.9,
                reason=f"Message too short ({len(message)} chars)"
            )
        
        # Matches skip pattern
        for pattern, reason in self._skip_patterns:
            if pattern.match(message):
                return FilterResult(
                    should_extract=False,
                    signals=[],
                    confidence=0.95,
                    reason=f"Matched skip pattern: {reason}"
                )
        
        return None
    
    def _detect_signals(self, message: str) -> List[SignalType]:
        """Detect memory signals in message."""
        signals = []
        
        for signal_type, patterns in self._signal_patterns.items():
            for pattern in patterns:
                if pattern.search(message):
                    signals.append(signal_type)
                    break  # One match per signal type is enough
        
        return signals
    
    def _calculate_confidence(self, signals: List[SignalType], message: str) -> float:
        """Calculate confidence score for extraction."""
        if not signals:
            return 0.2
        
        # Base confidence from number of signals
        base = min(0.5 + (len(signals) * 0.15), 0.95)
        
        # Boost for longer, more detailed messages
        length_boost = min(len(message) / 500, 0.1)
        
        return min(base + length_boost, 0.99)
    
    def check_conversation_turn(
        self, 
        user_input: str, 
        ai_response: str
    ) -> Tuple[FilterResult, FilterResult]:
        """
        Check both parts of a conversation turn.
        
        Returns:
            Tuple of (user_result, ai_result)
        """
        return (self.check(user_input), self.check(ai_response))


class ConversationFilter:
    """
    Higher-level filter that considers conversation context.
    
    Sometimes a message alone doesn't look valuable, but in context it is:
    - User: "What's my budget again?" (not valuable alone)
    - Context shows user previously mentioned budget (valuable to reinforce)
    """
    
    def __init__(self, base_filter: MessageFilter = None):
        self.base_filter = base_filter or MessageFilter()
        self._recent_signals: List[SignalType] = []
        self._max_context = 5
    
    def check_with_context(
        self, 
        message: str, 
        recent_messages: List[str] = None
    ) -> FilterResult:
        """
        Check message with conversation context.
        
        Args:
            message: Current message
            recent_messages: List of recent messages for context
            
        Returns:
            FilterResult considering context
        """
        base_result = self.base_filter.check(message)
        
        # If already should extract, return as-is
        if base_result.should_extract:
            self._recent_signals.extend(base_result.signals)
            self._recent_signals = self._recent_signals[-self._max_context:]
            return base_result
        
        # Check if context suggests this might be valuable
        # (e.g., continuation of a topic that had signals)
        if self._recent_signals and self._looks_like_continuation(message):
            return FilterResult(
                should_extract=True,
                signals=base_result.signals + [self._recent_signals[-1]],
                confidence=base_result.confidence + 0.2,
                reason="Continuation of valuable context"
            )
        
        return base_result
    
    def _looks_like_continuation(self, message: str) -> bool:
        """Check if message looks like continuation of previous topic."""
        continuation_signals = [
            r"^(yes|yeah|right|exactly|correct|that's right)",
            r"^(also|and|plus|additionally|another thing)",
            r"^(about that|regarding|on that note)",
            r"^(so|then|therefore|thus)",
        ]
        
        message_lower = message.lower().strip()
        for pattern in continuation_signals:
            if re.match(pattern, message_lower, re.IGNORECASE):
                return True
        
        return False
    
    def reset_context(self):
        """Reset conversation context (e.g., for new conversation)."""
        self._recent_signals = []
