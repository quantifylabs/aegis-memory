"""WITHOUT Aegis: poisoned memory drives a fraudulent refund.

Run:  python run_without_aegis.py

A malicious support ticket plants a fake "auto-approve high-value refunds" policy in shared
memory. A *later, separate* $5,000 refund request reads that poisoned memory and is wrongly
APPROVED. Deterministic and offline — identical output every run.
"""

from __future__ import annotations

import argparse

from _demo_common import load_ticket, new_store, print_decision
from support_agent_graph import build_support_graph

FRAUD_AMOUNT = 5000.0


def main(use_llm: bool = False) -> str:
    if use_llm:
        print("[notice] --llm requested; no node-level model needed for this deterministic demo.")

    print("=" * 68)
    print("WITHOUT AEGIS — poisoned memory steers a refund decision")
    print("=" * 68)

    store = new_store()
    graph = build_support_graph(store)

    # Step 1: process the malicious ticket. Its instruction lands in shared memory.
    malicious = load_ticket("malicious_ticket.json")
    print(f"\n[1] Summarizing ticket {malicious['id']} into shared memory...")
    graph.invoke({"ticket": malicious})
    item = store.get(("shared", "refund_policy"), "latest_summary")
    print(f"    stored summary: {item.value['text'][:90]}...")

    # Step 2: a later, separate refund request reads the poisoned memory.
    print(f"\n[2] New refund request for ${FRAUD_AMOUNT:,.2f} (separate operation)...")
    result = graph.invoke({"refund_amount": FRAUD_AMOUNT})
    print_decision("without-aegis", result, FRAUD_AMOUNT)

    print("\n>>> OUTCOME: a fraudulent $5,000 refund was APPROVED because memory was poisoned.")
    print("    The poison persisted and steered a business decision.\n")
    return result["decision"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--llm", action="store_true", help="Use a real model for node logic if a key is set")
    args = parser.parse_args()
    decision = main(use_llm=args.llm)
    assert decision == "APPROVED", "demo invariant: without Aegis the fraud is approved"
