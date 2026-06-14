"""WITHOUT Aegis: a poisoned *web page* steers a fraudulent refund.

Run:  python run_without_aegis.py

The poison never comes from the user. The agent ingests an untrusted web page (a mirrored
"knowledge base" page) whose text carries a buried instruction-override that asserts a fake
auto-approval policy. It lands in shared memory with no provenance. Later, a perfectly benign
user request — "process this $8,000 refund" — reads that poisoned memory and is wrongly
APPROVED. Deterministic and offline.
"""

from __future__ import annotations

import argparse

from _demo_common import SHARED_NS, SUMMARY_KEY, load_text, new_store, plant_via_channel, print_decision

from agent.decide import decide_refund

TRIGGER_AMOUNT = 8000.0


def main(use_llm: bool = False) -> str:
    if use_llm:
        print("[notice] --llm requested; no node-level model needed for this deterministic demo.")

    print("=" * 70)
    print("WITHOUT AEGIS — a poisoned web page steers a refund decision")
    print("=" * 70)

    store = new_store()

    # Plant: untrusted WEB content is ingested into shared memory (not a user prompt).
    web = load_text("inputs/poisoned/web_page.txt")
    plant_via_channel(store, "web-page", web)
    note = store.get(SHARED_NS, SUMMARY_KEY)
    print(f"    shared memory now holds: {note.value['text'][:80].strip()}...")

    # Trigger: a benign-looking user request, later and separate.
    print(f"\n[trigger] benign user request: process a ${TRIGGER_AMOUNT:,.0f} refund")
    result = decide_refund(store, TRIGGER_AMOUNT)
    print_decision(result, TRIGGER_AMOUNT)

    print(f"\n>>> OUTCOME: a fraudulent ${TRIGGER_AMOUNT:,.0f} refund was APPROVED.")
    print("    A prompt-time guardrail saw nothing wrong with the user's request — the")
    print("    malicious instruction arrived through a memory write, not the prompt.\n")
    return result["decision"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--llm", action="store_true", help="Use a real model for node logic if a key is set")
    args = parser.parse_args()
    decision = main(use_llm=args.llm)
    assert decision == "APPROVED", "demo invariant: without Aegis the staged poison approves the fraud"
