"""
Regression locks for adapter temperature forwarding.

Stage 4 (the LLM injection classifier) must run deterministically. That requires
two things to hold:

  1. Adapters must actually forward their configured ``temperature`` to the
     underlying SDK call. ``AnthropicAdapter`` historically dropped it (defaulting
     the Anthropic API to ~1.0); this file is the regression lock that it no longer
     does.
  2. ``temperature=0`` set at construction must reach the wire call.

These tests are import-light on purpose: ``aegis_memory.extractors`` imports only
stdlib at module top, so we import the adapter classes directly and mock the
``_client`` / ``_async_client`` on the instance. No real SDK is ever constructed
and no network call is made.
"""

import asyncio
from unittest.mock import MagicMock

from aegis_memory.extractors import AnthropicAdapter, OpenAIAdapter


def _anthropic_response(text: str = "{}"):
    """Shape a mock Anthropic response: ``response.content[0].text``."""
    block = MagicMock()
    block.text = text
    resp = MagicMock()
    resp.content = [block]
    return resp


def _openai_response(content: str = "{}"):
    """Shape a mock OpenAI response: ``response.choices[0].message.content``."""
    choice = MagicMock()
    choice.message.content = content
    resp = MagicMock()
    resp.choices = [choice]
    return resp


def test_anthropic_complete_sync_forwards_temperature_zero():
    """Regression lock (Part 1): the sync path forwards temperature == 0."""
    adapter = AnthropicAdapter(api_key="unused", temperature=0)

    client = MagicMock()
    client.messages.create.return_value = _anthropic_response("{}")
    adapter._client = client  # bypass lazy SDK construction

    adapter.complete_sync("hello", system="sys")

    client.messages.create.assert_called_once()
    kwargs = client.messages.create.call_args.kwargs
    assert kwargs["temperature"] == 0


def test_anthropic_complete_async_forwards_temperature_zero():
    """The async path forwards temperature == 0 too."""
    adapter = AnthropicAdapter(api_key="unused", temperature=0)

    async_client = MagicMock()

    async def _create(**kwargs):
        _create.kwargs = kwargs
        return _anthropic_response("{}")

    async_client.messages.create = _create
    adapter._async_client = async_client

    asyncio.run(adapter.complete("hello", system="sys"))

    assert _create.kwargs["temperature"] == 0


def test_openai_complete_sync_forwards_temperature_zero():
    """Sanity: lock the already-correct OpenAI sync behavior."""
    adapter = OpenAIAdapter(api_key="unused", temperature=0)

    client = MagicMock()
    client.chat.completions.create.return_value = _openai_response("{}")
    adapter._client = client

    adapter.complete_sync("hello", system="sys")

    client.chat.completions.create.assert_called_once()
    kwargs = client.chat.completions.create.call_args.kwargs
    assert kwargs["temperature"] == 0
