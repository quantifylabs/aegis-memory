"""WITH Aegis: the write gate rejects the poison, so the refund is correctly DENIED.

Run:  python run_with_aegis.py

Same staged attack — the agent ingests the same untrusted web page. But the shared store is
wrapped by ``AegisGuardedStore``, which screens every write through the real
``ContentSecurityScanner``. The instruction-override is detected and the write is REJECTED, so
memory stays clean and the later $8,000 refund is correctly DENIED. Deterministic and offline.
"""

from __future__ import annotations

import argparse

from _demo_common import (
    SHARED_NS,
    SUMMARY_KEY,
    AegisGuardedStore,
    load_text,
    new_store,
    plant_via_channel,
    print_decision,
)

from agent.decide import decide_refund

TRIGGER_AMOUNT = 8000.0


def main(use_llm: bool = False) -> str:
    if use_llm:
        print("[notice] --llm requested; no node-level model needed for this deterministic demo.")

    print("=" * 70)
    print("WITH AEGIS — the write gate screens memory before it persists")
    print("=" * 70)

    store = AegisGuardedStore(new_store())

    # Plant: the same untrusted web page — but the write is screened by the real scanner.
    web = load_text("inputs/poisoned/web_page.txt")
    plant_via_channel(store, "web-page", web)
    note = store.get(SHARED_NS, SUMMARY_KEY)
    if note is None:
        print("    shared memory is clean: the poisoned write never persisted.")

    # Trigger: the same benign user request now reads clean memory.
    print(f"\n[trigger] benign user request: process a ${TRIGGER_AMOUNT:,.0f} refund")
    result = decide_refund(store, TRIGGER_AMOUNT)
    print_decision(result, TRIGGER_AMOUNT)

    blocked = len(store.blocked)
    print(f"\n>>> OUTCOME: the fraudulent refund was correctly DENIED. {blocked} poisoned write(s) blocked.")
    print("    The injection scanner stopped the poison from ever reaching memory.\n")
    return result["decision"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--llm", action="store_true", help="Use a real model for node logic if a key is set")
    args = parser.parse_args()
    decision = main(use_llm=args.llm)
    assert decision == "DENIED", "demo invariant: with Aegis the poisoned write is rejected and the fraud denied"
