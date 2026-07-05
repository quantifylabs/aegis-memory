"""
Aegis Memory — LangGraph Basic Example

Shows the two things a stateful graph needs from long-term memory:
  1. retrieve relevant memory into state *before* a node reasons, and
  2. persist what the node produced *after* it runs.

The AegisLangGraphMemory adapter is framework-agnostic — LangGraph state is just a
dict — so this example runs with a plain function pipeline and needs no `langgraph`
install, no server and no API key (it uses local mode).

NOTE: this adapter is a retrieve/persist helper, not a LangGraph checkpointer. It does
not save/restore graph execution state; use LangGraph's own checkpointer for that.

Install:
    pip install aegis-memory numpy
    # For offline embeddings (no OpenAI key needed):
    pip install aegis-memory[local]
    # To run inside a real LangGraph graph as well:
    pip install aegis-memory[langgraph]

Usage:
    python examples/langgraph_basic.py
"""

from aegis_memory import local_client
from aegis_memory.integrations.langgraph import AegisLangGraphMemory


def main():
    # In-process SQLite + numpy backend — no server needed.
    client = local_client(db_path="demo_langgraph.db")
    memory = AegisLangGraphMemory(client=client, namespace="support-graph")

    AGENT = "assistant"

    # ── Seed some prior knowledge (as if from earlier runs) ──────────────
    print("Seeding prior memory...")
    memory.remember("The customer's account tier is Enterprise.", agent_id=AGENT)
    memory.remember("The customer prefers email over phone support.", agent_id=AGENT)
    memory.remember("Refunds above $500 require manager approval.", agent_id=AGENT)

    # ── A node: retrieve-before, persist-after ───────────────────────────
    def agent_node(state: dict) -> dict:
        # 1. Pull relevant memory into state before reasoning.
        state = memory.load_into_state(state, state["question"], agent_id=AGENT)
        context = state["aegis_memories"]

        print(f"\nRetrieved {len(context)} memories for: {state['question']!r}")
        for mem in context:
            print(f"  [{mem['score']:.2f}] {mem['content']}")

        # 2. "Reason" using the retrieved context (stubbed here).
        answer = (
            f"Handled '{state['question']}' using {len(context)} prior facts."
        )
        state["answer"] = answer

        # 3. Persist what this node produced back into memory.
        state["answer_meta"] = {"question": state["question"]}
        mem_id = memory.persist_from_state(
            state, "answer", agent_id=AGENT, metadata_key="answer_meta"
        )
        print(f"Persisted answer as memory {mem_id}")
        return state

    # ── Drive the "graph" ────────────────────────────────────────────────
    result = agent_node({"question": "How does this customer like to be contacted?"})
    print(f"\nFinal answer: {result['answer']}")

    # The persisted answer is now retrievable on the next run.
    print("\nNext run sees the new memory:")
    for mem in memory.retrieve("what did we tell the customer?", agent_id=AGENT, top_k=3):
        print(f"  [{mem['score']:.2f}] {mem['content']}")

    client.close()
    print("\nDone! Database saved to demo_langgraph.db")


if __name__ == "__main__":
    main()
