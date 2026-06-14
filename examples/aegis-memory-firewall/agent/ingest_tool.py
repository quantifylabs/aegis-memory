"""Channel 3 — tool / API result → custom memory (sink: ``memory.save``).

A CRM tool's output is untrusted data crossing a trust boundary. It is written into a
custom memory object via ``memory.save(...)`` — the general "custom memory-ish sink" shape.
"""

from __future__ import annotations

from typing import Any


def ingest_tool_result(memory: Any, crm_tool: Any, account_id: str) -> None:
    # Tool egress → memory (one hop through ``tool_result``: INFERRED, tool_output).
    tool_result = crm_tool.invoke({"account": account_id})
    memory.save(tool_result)
