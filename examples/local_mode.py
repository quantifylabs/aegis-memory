"""
Aegis Memory — Local Mode Example

Local mode runs entirely in-process with SQLite + numpy.
No server, no Docker, no PostgreSQL needed.

Install:
    pip install aegis-memory numpy
    # For offline embeddings (no OpenAI key needed):
    pip install aegis-memory[local]

Usage:
    python examples/local_mode.py
"""

from aegis_memory import AegisClient, local_client


def main():
    # ── Option 1: Convenience factory ────────────────────────────────────
    # Uses ~/.aegis/memory.db by default.
    # Embedding provider auto-detected:
    #   - sentence-transformers (if installed) → fully offline
    #   - OpenAI (if OPENAI_API_KEY is set) → API-based
    client = local_client(db_path="demo_memory.db")

    # ── Option 2: Explicit constructor ───────────────────────────────────
    # client = AegisClient(
    #     mode="local",
    #     db_path="demo_memory.db",
    #     openai_api_key="sk-...",         # or set OPENAI_API_KEY env var
    #     embedding_model="text-embedding-3-small",
    # )

    # ── Add memories ─────────────────────────────────────────────────────
    print("Adding memories...")
    client.add("User prefers dark mode", agent_id="ui-agent")
    client.add("User is a Python developer", agent_id="ui-agent")
    client.add("Project deadline is March 15", agent_id="pm-agent")
    client.add("Always run tests before deploying", agent_id="devops-agent")

    # ── Semantic query ───────────────────────────────────────────────────
    print("\nQuerying 'what theme does the user like?'...")
    results = client.query("what theme does the user like?", agent_id="ui-agent")
    for mem in results:
        print(f"  [{mem.score:.2f}] {mem.content}")

    # ── Cross-agent query ────────────────────────────────────────────────
    print("\nCross-agent query from pm-agent for 'developer preferences'...")
    cross = client.query_cross_agent(
        "developer preferences", requesting_agent_id="pm-agent"
    )
    for mem in cross:
        print(f"  [{mem.score:.2f}] {mem.content} (agent: {mem.agent_id})")

    # ── Batch add ────────────────────────────────────────────────────────
    print("\nBatch adding...")
    batch_results = client.add_batch([
        {"content": "Sprint velocity is 21 points", "agent_id": "pm-agent"},
        {"content": "User prefers VS Code", "agent_id": "ui-agent"},
    ])
    print(f"  Added {len(batch_results)} memories")

    # ── Vote on a memory (ACE pattern) ───────────────────────────────────
    first = results[0] if results else None
    if first:
        print(f"\nVoting 'helpful' on: {first.content}")
        vote = client.vote(first.id, vote="helpful", voter_agent_id="feedback-agent")
        print(f"  Effectiveness score: {vote.effectiveness_score:.2f}")

    # ── Session progress tracking ────────────────────────────────────────
    print("\nSession tracking...")
    session = client.create_session("onboarding-session", agent_id="ui-agent")
    print(f"  Created session: {session.session_id}")

    client.update_session("onboarding-session", completed_items=["welcome"])
    updated = client.update_session("onboarding-session", completed_items=["preferences"])
    print(f"  Completed items: {updated.completed_items}")

    # ── Feature tracking ─────────────────────────────────────────────────
    print("\nFeature tracking...")
    feat = client.create_feature("dark-mode", "Support dark mode in UI")
    print(f"  Created feature: {feat.feature_id}")

    client.update_feature("dark-mode", status="complete", passes=True, verified_by="qa-agent")
    print("  Marked as complete")

    # ── Handoff between agents ───────────────────────────────────────────
    print("\nAgent handoff (ui-agent → pm-agent)...")
    baton = client.handoff(
        "ui-agent", "pm-agent",
        task_context="user onboarding status",
    )
    print(f"  Baton: {len(baton.memory_ids)} memories transferred")
    print(f"  Key facts: {baton.key_facts}")

    # ── Export ────────────────────────────────────────────────────────────
    print("\nExporting all memories...")
    stats = client.export_json("demo_export.json")
    print(f"  Exported to demo_export.json")

    # ── Cleanup ──────────────────────────────────────────────────────────
    client.close()
    print("\nDone! Database saved to demo_memory.db")


if __name__ == "__main__":
    main()
