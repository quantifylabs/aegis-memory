"""
Aegis Python SDK

A production-ready Python client for Aegis Memory API.

Includes ACE (Agentic Context Engineering) features:
- Memory voting (helpful/harmful)
- Incremental delta updates
- Session progress tracking
- Feature status tracking
- Playbook queries
"""

from ._models import (
    AddResult,
    AgentInteractionsResult,
    ConsolidationCandidate,
    ContentScanResult,
    CurationEntry,
    CurationResult,
    DeltaResult,
    DeltaResultItem,
    EventWithChainResult,
    Feature,
    FeatureList,
    HandoffBaton,
    IntegrityCheckResult,
    InteractionEvent,
    InteractionEventResult,
    InteractionSearchResult,
    InteractionSearchResultItem,
    Memory,
    PlaybookEntry,
    PlaybookResult,
    RunResult,
    SecurityAuditEvent,
    SessionProgress,
    SessionTimelineResult,
    VoteResult,
)
from ._async import AsyncAegisClient
from ._parsers import (
    _parse_curation_data,
    _parse_feature_data,
    _parse_interaction_event,
    _parse_memory_data,
    _parse_run_data,
    _parse_session_data,
)
from ._sync import AegisClient

__all__ = [
    # Clients
    "AegisClient",
    "AsyncAegisClient",
    # Models
    "AddResult",
    "AgentInteractionsResult",
    "ConsolidationCandidate",
    "ContentScanResult",
    "CurationEntry",
    "CurationResult",
    "DeltaResult",
    "DeltaResultItem",
    "EventWithChainResult",
    "Feature",
    "FeatureList",
    "HandoffBaton",
    "IntegrityCheckResult",
    "InteractionEvent",
    "InteractionEventResult",
    "InteractionSearchResult",
    "InteractionSearchResultItem",
    "Memory",
    "PlaybookEntry",
    "PlaybookResult",
    "RunResult",
    "SecurityAuditEvent",
    "SessionProgress",
    "SessionTimelineResult",
    "VoteResult",
]
