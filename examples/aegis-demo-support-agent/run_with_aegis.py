"""WITH Aegis: the guard blocks the poison, so the refund is correctly DENIED.

Run:  python run_with_aegis.py

Same graph, same malicious ticket — but the shared store is wrapped by ``AegisGuardedStore``,
which screens every write through the real ``ContentSecurityScanner``. The poisoned summary
is REJECTED at write time, so the later $5,000 refund request reads clean memory and is
correctly DENIED. Deterministic and offline.
"""

from __future__ import annotations

import argparse

from _demo_common import AegisGuardedStore, load_ticket, new_store, print_decision
from support_agent_graph import build_support_graph

FRAUD_AMOUNT = 5000.0


def main(use_llm: bool = False) -> str:
    if use_llm:
        print("[notice] --llm requested; no node-level model needed for this deterministic demo.")

    print("=" * 68)
    print("WITH AEGIS — the write gate screens memory before it persists")
    print("=" * 68)

    store = AegisGuardedStore(new_store())
    graph = build_support_graph(store)

    # Step 1: the malicious ticket is summarized, but the write is screened.
    malicious = load_ticket("malicious_ticket.json")
    print(f"\n[1] Summarizing ticket {malicious['id']} (write is screened by Aegis)...")
    graph.invoke({"ticket": malicious})
    item = store.get(("shared", "refund_policy"), "latest_summary")
    if item is None:
        print("    shared memory is clean: the poisoned summary never persisted.")

    # Step 2: the later refund request now reads clean memory.
    print(f"\n[2] New refund request for ${FRAUD_AMOUNT:,.2f} (separate operation)...")
    result = graph.invoke({"refund_amount": FRAUD_AMOUNT})
    print_decision("with-aegis", result, FRAUD_AMOUNT)

    blocked = len(store.blocked)
    print(f"\n>>> OUTCOME: the fraudulent refund was correctly DENIED. {blocked} poisoned write(s) blocked.")
    print("    The injection scanner stopped the poison from ever reaching memory.\n")
    return result["decision"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--llm", action="store_true", help="Use a real model for node logic if a key is set")
    args = parser.parse_args()
    decision = main(use_llm=args.llm)
    assert decision == "DENIED", "demo invariant: with Aegis the fraud is denied"
