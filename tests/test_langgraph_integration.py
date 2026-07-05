"""
Network-free unit tests for the LangGraph integration adapter.

The adapter is duck-typed over AegisClient, so we drive it with a MagicMock client
and assert it calls the right client methods with the right arguments. No server,
no Postgres, no network.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from aegis_memory.integrations.langgraph import AegisLangGraphMemory


def _mem(content, *, score=0.9, agent_id="a", metadata=None):
    return SimpleNamespace(
        content=content, score=score, agent_id=agent_id, metadata=metadata or {}
    )


@pytest.fixture
def client():
    c = MagicMock()
    c.query.return_value = [_mem("m1", score=0.8), _mem("m2", score=0.7)]
    c.query_cross_agent.return_value = [_mem("x1", score=0.6, agent_id="other")]
    c.add.return_value = SimpleNamespace(id="mem-123")
    return c


@pytest.fixture
def memory(client):
    return AegisLangGraphMemory(client=client, namespace="ns")


def test_requires_client_or_api_key():
    with pytest.raises(ValueError):
        AegisLangGraphMemory()


def test_retrieve_uses_plain_query_without_agent(memory, client):
    out = memory.retrieve("hello", top_k=5)
    client.query.assert_called_once_with(
        query="hello", namespace="ns", top_k=5, min_score=0.0
    )
    client.query_cross_agent.assert_not_called()
    assert out == [
        {"content": "m1", "metadata": {}, "score": 0.8, "agent_id": "a"},
        {"content": "m2", "metadata": {}, "score": 0.7, "agent_id": "a"},
    ]


def test_retrieve_uses_cross_agent_with_agent(memory, client):
    out = memory.retrieve("hello", agent_id="me", top_k=3)
    client.query_cross_agent.assert_called_once_with(
        query="hello", requesting_agent_id="me", namespace="ns", top_k=3, min_score=0.0
    )
    client.query.assert_not_called()
    assert out[0]["agent_id"] == "other"


def test_remember_calls_add_with_source_tag(memory, client):
    mem_id = memory.remember("a fact", agent_id="me", metadata={"k": "v"})
    assert mem_id == "mem-123"
    client.add.assert_called_once()
    kwargs = client.add.call_args.kwargs
    assert kwargs["content"] == "a fact"
    assert kwargs["agent_id"] == "me"
    assert kwargs["namespace"] == "ns"
    assert kwargs["scope"] == "agent-shared"  # default_scope when an agent is given
    assert kwargs["metadata"] == {"source": "langgraph", "k": "v"}


def test_remember_agentless_defaults_to_global(memory, client):
    # Agentless writes must land in a scope the agentless retrieve() path can read
    # (only global), so the simple remember()/retrieve() round-trip works.
    memory.remember("a fact")
    assert client.add.call_args.kwargs["agent_id"] is None
    assert client.add.call_args.kwargs["scope"] == "global"


def test_remember_respects_scope_override(memory, client):
    # An explicit scope always wins, even agentless.
    memory.remember("x", scope="agent-private")
    assert client.add.call_args.kwargs["scope"] == "agent-private"
    memory.remember("y", agent_id="me", scope="global")
    assert client.add.call_args.kwargs["scope"] == "global"


def test_load_into_state_writes_default_key(memory):
    state = {"question": "q"}
    out = memory.load_into_state(state, "q")
    assert out is state  # mutated in place and returned
    assert state["aegis_memories"] == [
        {"content": "m1", "metadata": {}, "score": 0.8, "agent_id": "a"},
        {"content": "m2", "metadata": {}, "score": 0.7, "agent_id": "a"},
    ]


def test_load_into_state_custom_key(memory):
    state = memory.load_into_state({}, "q", key="mem")
    assert "mem" in state and "aegis_memories" not in state


def test_persist_from_state_stores_content_and_metadata(memory, client):
    state = {"answer": "the answer", "meta": {"q": "why"}}
    mem_id = memory.persist_from_state(
        state, "answer", agent_id="me", metadata_key="meta"
    )
    assert mem_id == "mem-123"
    kwargs = client.add.call_args.kwargs
    assert kwargs["content"] == "the answer"
    assert kwargs["metadata"] == {"source": "langgraph", "q": "why"}


def test_persist_from_state_noops_on_missing_content(memory, client):
    assert memory.persist_from_state({}, "answer") is None
    client.add.assert_not_called()
