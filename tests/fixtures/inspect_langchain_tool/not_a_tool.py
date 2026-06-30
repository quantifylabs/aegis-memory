"""True negative: a plain helper with the same param names as a tool, but NO tool signal — no
``@tool`` decorator and no ``Injected*`` param. Even though the module imports langchain, this must
NOT be treated as a model-facing tool, so its ``content`` param is not untrusted-by-default.
"""

from langchain_core.tools import tool  # noqa: F401  (imported, but this function is not decorated)
from langgraph.store.base import BaseStore


def persist(content: str, store: BaseStore) -> str:
    """An ordinary internal helper — ``content`` here is an internal value, not a model-supplied arg."""
    store.put(("memories",), key="k", value={"content": content})
    return "ok"
