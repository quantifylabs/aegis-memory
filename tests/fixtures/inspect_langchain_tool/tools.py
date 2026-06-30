"""LangChain/LangGraph tool functions whose model-supplied args reach memory.

A tool is called by the model with arguments it generates from the conversation — those args are
untrusted. The framework-injected params (``InjectedToolArg``/``InjectedStore``) are NOT model-
supplied and must not be treated as the untrusted leaf. Mirrors the real ``memory-agent`` shape.
"""

import uuid
from typing import Annotated

from langchain_core.tools import InjectedToolArg, tool
from langgraph.store.base import BaseStore


@tool
def remember(fact: str, store: Annotated[BaseStore, InjectedToolArg]) -> str:
    """Persist a fact to long-term memory (model supplies ``fact``)."""
    store.put(("memories",), key=str(uuid.uuid4()), value={"content": fact})
    return "ok"


async def upsert_memory(
    content: str,
    context: str,
    *,
    user_id: Annotated[str, InjectedToolArg],
    store: Annotated[BaseStore, InjectedToolArg],
):
    """Upsert a memory — InjectedToolArg signature, no @tool decorator (the memory-agent shape)."""
    await store.aput(
        ("memories", user_id),
        key=str(uuid.uuid4()),
        value={"content": content, "context": context},
    )
    return "stored"
