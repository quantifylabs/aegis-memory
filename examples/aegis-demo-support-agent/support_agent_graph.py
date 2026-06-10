"""A real LangGraph support agent with a poisonable shared memory.

Two nodes behave like two agents that share one memory store:

* ``support_summarizer`` reads an incoming ticket and writes a summary into the **shared
  store** via ``store.put(...)``. This is the **write sink** and the tainted path — the
  ticket text is untrusted and flows straight into stored memory.
* ``refund_decider`` later loads memory via ``store.get(...)`` and applies a refund rule.
  It is steerable by stored content — which is exactly what lets the poison bite.

Node logic is deterministic Python by default (no LLM). The store is accessed through a
closure so the demo can swap a *guarded* store in ``run_with_aegis.py`` without touching
this graph. Routing is conditional so a ticket and a later refund request are two separate
operations over the same persistent store.
"""

from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

# The shared memory namespace both "agents" read and write.
REFUND_POLICY_NS = ("shared", "refund_policy")
SUMMARY_KEY = "latest_summary"

# Refunds at or below this need no review; above it requires manual review by default.
REVIEW_THRESHOLD = 500.0


class SupportState(TypedDict, total=False):
    ticket: dict[str, Any]
    refund_amount: float
    summary: str
    decision: str
    reason: str


def build_support_graph(store: Any):
    """Compile a real StateGraph whose nodes share ``store`` via closure."""

    def support_summarizer(state: SupportState) -> SupportState:
        ticket = state["ticket"]
        # Untrusted customer text flows directly into a shared-memory summary.
        summary = f"Ticket from {ticket.get('customer', 'unknown')}: {ticket['body']}"
        store.put(REFUND_POLICY_NS, SUMMARY_KEY, {"text": summary})
        return {"summary": summary}

    def refund_decider(state: SupportState) -> SupportState:
        amount = float(state.get("refund_amount", 0.0))
        item = store.get(REFUND_POLICY_NS, SUMMARY_KEY)
        memory_text = (item.value or {}).get("text", "") if item else ""

        # Business rule: high-value refunds are DENIED unless memory says auto-approve.
        memo = memory_text.lower()
        auto_approve = "approved automatically" in memo or "auto-approve" in memo
        if amount > REVIEW_THRESHOLD and auto_approve:
            return {
                "decision": "APPROVED",
                "reason": "stored refund policy says high-value refunds are auto-approved",
            }
        if amount > REVIEW_THRESHOLD:
            return {
                "decision": "DENIED",
                "reason": "high-value refund requires manual review",
            }
        return {"decision": "APPROVED", "reason": "low-value refund within policy"}

    def route(state: SupportState) -> str:
        return "support_summarizer" if state.get("ticket") else "refund_decider"

    graph = StateGraph(SupportState)
    graph.add_node("support_summarizer", support_summarizer)
    graph.add_node("refund_decider", refund_decider)
    graph.add_conditional_edges(
        START,
        route,
        {"support_summarizer": "support_summarizer", "refund_decider": "refund_decider"},
    )
    graph.add_edge("support_summarizer", END)
    graph.add_edge("refund_decider", END)
    return graph.compile()
