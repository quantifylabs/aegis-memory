"""
Aegis ACE Features Demo

This example demonstrates how to use ACE (Agentic Context Engineering)
patterns with Aegis Memory to build self-improving agents.

Based on insights from:
1. ACE Paper (Stanford/SambaNova) - Agentic Context Engineering
2. Anthropic's Long-Running Agent Harnesses

Key Patterns Demonstrated:
1. Memory Voting - Track which memories helped/harmed tasks
2. Playbook Queries - Consult accumulated strategies before tasks
3. Reflections - Extract insights from failures
4. Delta Updates - Incremental context modification
5. Session Progress - Track work across context windows
6. Feature Tracking - Prevent premature victory
"""

from aegis_memory import AegisClient


def main():
    # Initialize client
    client = AegisClient(
        api_key="your-api-key",
        base_url="http://localhost:8000"
    )
    
    # =========================================================================
    # PATTERN 1: Session Progress Tracking
    # (Anthropic's claude-progress.txt pattern)
    # =========================================================================
    print("=" * 60)
    print("PATTERN 1: Session Progress Tracking")
    print("=" * 60)
    
    # Create a session for a coding task
    session = client.create_session(
        session_id="build-chatbot-v1",
        agent_id="coding-agent",
        namespace="project-alpha"
    )
    print(f"Created session: {session.session_id}")
    
    # Define features to track (prevents premature victory)
    features = [
        ("auth-login", "User can login with email/password", "auth", 
         ["Navigate to login", "Enter credentials", "Click login", "Verify redirect"]),
        ("auth-logout", "User can logout", "auth",
         ["Click logout button", "Verify session cleared", "Verify redirect to login"]),
        ("chat-send", "User can send a message", "chat",
         ["Type message", "Click send", "Verify message appears"]),
        ("chat-receive", "User receives AI response", "chat",
         ["Send message", "Wait for response", "Verify response appears"]),
    ]
    
    for fid, desc, cat, steps in features:
        client.create_feature(
            feature_id=fid,
            description=desc,
            session_id=session.session_id,
            namespace="project-alpha",
            category=cat,
            test_steps=steps,
        )
    print(f"Created {len(features)} features to track")
    
    # Update session with total items
    session = client.update_session(
        session.session_id,
        total_items=len(features),
        summary="Building chatbot with auth and chat features",
        next_items=["auth-login", "auth-logout", "chat-send", "chat-receive"],
    )
    
    # =========================================================================
    # PATTERN 2: Consulting the Playbook Before Starting
    # (ACE Pattern: Query strategies/reflections before task)
    # =========================================================================
    print("\n" + "=" * 60)
    print("PATTERN 2: Consulting the Playbook")
    print("=" * 60)
    
    # First, let's add some strategies to the playbook
    strategies = [
        "When implementing authentication, always hash passwords with bcrypt, never store plaintext.",
        "For real-time chat, use WebSocket connections. HTTP polling is inefficient.",
        "Always implement rate limiting on login endpoints to prevent brute force attacks.",
        "Store session tokens in HttpOnly cookies, not localStorage, to prevent XSS.",
    ]
    
    for strategy in strategies:
        client.apply_delta([{
            "type": "add",
            "content": strategy,
            "memory_type": "strategy",
            "agent_id": "coding-agent",
            "namespace": "project-alpha",
            "scope": "global",  # Share with all agents
        }])
    print(f"Added {len(strategies)} strategies to playbook")
    
    # Query playbook before starting auth implementation
    playbook = client.query_playbook(
        query="implementing user authentication login",
        agent_id="coding-agent",
        namespace="project-alpha",
        top_k=10,
        min_effectiveness=0.0,
    )
    
    print(f"\nPlaybook entries for auth task ({len(playbook.entries)} found):")
    for entry in playbook.entries:
        score_indicator = "✓" if entry.effectiveness_score >= 0 else "⚠"
        print(f"  [{score_indicator} {entry.effectiveness_score:+.2f}] {entry.content[:60]}...")
    
    # =========================================================================
    # PATTERN 3: Simulating Work & Updating Progress
    # =========================================================================
    print("\n" + "=" * 60)
    print("PATTERN 3: Working on Features")
    print("=" * 60)
    
    # Start working on auth-login
    session = client.set_in_progress(session.session_id, "auth-login")
    print(f"Started: {session.in_progress_item}")
    
    # Simulate implementation...
    # In real scenario, agent would generate code here
    
    # Mark as complete after testing
    feature = client.mark_feature_complete(
        "auth-login",
        verified_by="coding-agent",
        namespace="project-alpha",
        notes="Implemented with bcrypt password hashing"
    )
    print(f"Completed: {feature.feature_id} (passes={feature.passes})")
    
    # Update session
    session = client.update_session(
        session.session_id,
        completed_items=["auth-login"],
        last_action="Implemented login with bcrypt hashing",
    )
    print(f"Progress: {session.completed_count}/{session.total_items} ({session.progress_percent}%)")
    
    # =========================================================================
    # PATTERN 4: Recording a Failure & Creating Reflection
    # (ACE Pattern: Reflector extracts insights from failures)
    # =========================================================================
    print("\n" + "=" * 60)
    print("PATTERN 4: Handling Failure & Creating Reflection")
    print("=" * 60)
    
    # Simulate a failed feature
    session = client.set_in_progress(session.session_id, "chat-receive")
    print(f"Started: {session.in_progress_item}")
    
    # Oops, agent made a mistake - used HTTP polling instead of WebSocket
    feature = client.mark_feature_failed(
        "chat-receive",
        reason="HTTP polling causing 2-second delays, need WebSocket",
        namespace="project-alpha",
    )
    print(f"Failed: {feature.feature_id} - {feature.failure_reason}")
    
    # Create reflection from the failure
    reflection_id = client.add_reflection(
        content="HTTP polling for real-time chat causes unacceptable latency. "
                "Always use WebSocket for bi-directional real-time communication.",
        agent_id="coding-agent",
        namespace="project-alpha",
        source_trajectory_id="build-chatbot-v1",
        error_pattern="wrong_communication_protocol",
        correct_approach="Use WebSocket (ws://) for real-time features instead of HTTP polling",
        applicable_contexts=["chat", "notifications", "live_updates", "real_time"],
    )
    print(f"Created reflection: {reflection_id}")
    
    # =========================================================================
    # PATTERN 5: Voting on Memory Usefulness
    # (ACE Pattern: Self-improvement through feedback)
    # =========================================================================
    print("\n" + "=" * 60)
    print("PATTERN 5: Voting on Memories")
    print("=" * 60)
    
    # The playbook entry about WebSocket was helpful!
    # Find it and vote
    playbook = client.query_playbook(
        query="WebSocket real-time chat",
        agent_id="coding-agent",
        namespace="project-alpha",
        top_k=1,
    )
    
    if playbook.entries:
        entry = playbook.entries[0]
        vote_result = client.vote(
            entry.id,
            vote="helpful",
            voter_agent_id="coding-agent",
            context="This strategy correctly warned about HTTP polling",
            task_id="build-chatbot-v1",
        )
        print(f"Voted 'helpful' on memory {entry.id[:8]}...")
        print(f"  New effectiveness: {vote_result.effectiveness_score:+.2f}")
        print(f"  Helpful: {vote_result.bullet_helpful}, Harmful: {vote_result.bullet_harmful}")
    
    # =========================================================================
    # PATTERN 6: Delta Updates (Incremental Context)
    # (ACE Pattern: Never rewrite entire context)
    # =========================================================================
    print("\n" + "=" * 60)
    print("PATTERN 6: Delta Updates")
    print("=" * 60)
    
    # Add multiple items in a single delta batch
    result = client.apply_delta([
        # Add new strategy learned from this session
        {
            "type": "add",
            "content": "For chat applications, implement typing indicators using WebSocket 'typing' events",
            "memory_type": "strategy",
            "agent_id": "coding-agent",
            "namespace": "project-alpha",
            "scope": "global",
        },
        # Add project-specific memory
        {
            "type": "add", 
            "content": "Project Alpha uses JWT tokens with 24-hour expiration for auth",
            "memory_type": "standard",
            "agent_id": "coding-agent",
            "namespace": "project-alpha",
            "scope": "agent-shared",
            "metadata": {"project": "alpha", "component": "auth"},
        },
    ])
    
    print(f"Applied {len(result.results)} delta operations in {result.total_time_ms:.1f}ms")
    for r in result.results:
        status = "✓" if r.success else "✗"
        print(f"  [{status}] {r.operation}: {r.memory_id or r.error}")
    
    # =========================================================================
    # PATTERN 7: Session Handoff Summary
    # (Anthropic Pattern: Clean state for next session)
    # =========================================================================
    print("\n" + "=" * 60)
    print("PATTERN 7: Session Summary (for next context window)")
    print("=" * 60)
    
    # Update session with final summary
    session = client.update_session(
        session.session_id,
        summary="Auth login complete. Chat receive failed due to HTTP polling, "
                "needs WebSocket implementation. Created reflection for future reference.",
        last_action="Created reflection about WebSocket requirement",
        status="paused",  # Ready for next session to continue
    )
    
    # Show feature status
    features = client.list_features(
        namespace="project-alpha",
        session_id=session.session_id,
    )
    
    print(f"\nFeature Status Summary:")
    print(f"  Total: {features.total}")
    print(f"  Passing: {features.passing}")
    print(f"  Failing: {features.failing}")
    print(f"  In Progress: {features.in_progress}")
    
    print(f"\nSession State:")
    print(f"  Progress: {session.progress_percent}%")
    print(f"  Summary: {session.summary}")
    print(f"  Next items: {session.next_items}")
    
    # =========================================================================
    # PATTERN 8: ACE Run Tracking (v1.9.1)
    # (Full Generation -> Reflection -> Curation loop)
    # =========================================================================
    print("\n" + "=" * 60)
    print("PATTERN 8: ACE Run Tracking")
    print("=" * 60)

    # Query agent-specific playbook
    agent_playbook = client.get_playbook_for_agent(
        "coding-agent",
        query="implementing WebSocket chat",
        task_type="chat",
        namespace="project-alpha",
    )
    memory_ids = [e.id for e in agent_playbook.entries]
    print(f"Agent playbook: {len(agent_playbook.entries)} entries for chat task")

    # Start tracking a run
    run = client.start_run(
        run_id="fix-chat-ws",
        agent_id="coding-agent",
        task_type="chat",
        namespace="project-alpha",
        memory_ids_used=memory_ids,
    )
    print(f"Started run: {run.run_id} (status={run.status})")

    # ... agent does its work (fixing chat with WebSocket) ...

    # Complete the run with success
    completed = client.complete_run(
        "fix-chat-ws",
        success=True,
        evaluation={"score": 0.95, "latency_ms": 50},
        logs={"steps": ["replaced HTTP polling", "added WebSocket handler"]},
    )
    print(f"Completed run: {completed.run_id} (success={completed.success})")
    print(f"  Auto-voted 'helpful' on {len(completed.memory_ids_used)} memories")

    # =========================================================================
    # PATTERN 9: Curation Cycle (v1.9.1)
    # (Promote effective, flag ineffective, suggest consolidations)
    # =========================================================================
    print("\n" + "=" * 60)
    print("PATTERN 9: Curation Cycle")
    print("=" * 60)

    curation = client.curate(
        namespace="project-alpha",
        agent_id="coding-agent",
        top_k=5,
    )
    print(f"Curation results:")
    print(f"  Promoted: {len(curation.promoted)} high-effectiveness entries")
    print(f"  Flagged: {len(curation.flagged)} low-effectiveness entries")
    print(f"  Consolidation candidates: {len(curation.consolidation_candidates)}")

    for entry in curation.promoted[:3]:
        print(f"  [+{entry.effectiveness_score:.2f}] {entry.content[:60]}...")

    # =========================================================================
    # What the NEXT session would do:
    # =========================================================================
    print("\n" + "=" * 60)
    print("NEXT SESSION WOULD:")
    print("=" * 60)
    print("""
    1. Load session progress: client.get_session("build-chatbot-v1")
    2. Check features: client.list_features(session_id="build-chatbot-v1")
    3. Query agent playbook: client.get_playbook_for_agent("coding-agent", ...)
    4. See reflection about WebSocket (now highest ranked!)
    5. Start run: client.start_run("next-task", ...)
    6. Complete run: client.complete_run("next-task", success=True)
    7. Curate: client.curate() to clean up the playbook
    """)

    client.close()
    print("\nDemo complete!")


if __name__ == "__main__":
    main()
