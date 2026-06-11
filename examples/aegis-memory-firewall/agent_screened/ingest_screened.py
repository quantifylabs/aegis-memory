"""The five channels of ``agent/`` — but every write is screened first.

This is the copy-pasteable fix the inspector points at (SSOT §4.3 runtime bridge): the same
untrusted source, the same sink, with a real ``scan()`` gate in between — in the *same scope*
as the write, which is what lets ``aegis inspect`` see the screening and downgrade each flow
from critical to screened/low.
"""

from __future__ import annotations

from typing import Any

from aegis_memory.inspect._scanner_bridge import ContentAction, get_scanner

SHARED_NS = ("shared", "knowledge")
SUMMARY_KEY = "latest_note"


def ingest_ticket(store: Any, ticket: dict) -> None:
    summary = f"Ticket from {ticket.get('customer', 'unknown')}: {ticket['body']}"
    verdict = get_scanner().scan(summary)
    if verdict.allowed and verdict.action != ContentAction.REJECT:
        store.put(SHARED_NS, SUMMARY_KEY, {"text": summary})


def ingest_document(vectorstore: Any, Document: Any, doc: Any) -> None:
    body = doc.text
    verdict = get_scanner().scan(body)
    if verdict.allowed and verdict.action != ContentAction.REJECT:
        vectorstore.add_documents([Document(page_content=body, metadata={"src": "kb"})])


def ingest_tool_result(memory: Any, crm_tool: Any, account_id: str) -> None:
    tool_result = crm_tool.invoke({"account": account_id})
    verdict = get_scanner().scan(str(tool_result))
    if verdict.allowed and verdict.action != ContentAction.REJECT:
        memory.save(tool_result)


def ingest_web_page(store: Any, requests: Any, url: str) -> None:
    fetched = requests.get(url).text
    verdict = get_scanner().scan(fetched)
    if verdict.allowed and verdict.action != ContentAction.REJECT:
        store.put(SHARED_NS, SUMMARY_KEY, {"text": fetched})


def ingest_email(checkpointer: Any, cfg: dict, email: Any) -> None:
    body = email.body
    verdict = get_scanner().scan(body)
    if verdict.allowed and verdict.action != ContentAction.REJECT:
        checkpointer.put(cfg, "email_note", {"note": body})
