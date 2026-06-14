# Aegis demo series — roadmap

The `aegis inspect` demos exercise detection the engine already has across progressively
higher-LTV memory-poisoning surfaces. **Tier 1 ships now**; Tiers 2–3 are captured here so the
series intent is recorded without scope-creeping the current PR. They are separate future PRs.

## Tier 1 — multi-source memory firewall ✅ (shipped)

`examples/aegis-memory-firewall/` — untrusted data from five channels (user/ticket, retrieved
document, tool output, web fetch, email) flows into shared memory; a staged web/email poisoning
attack that prompt-time guardrails miss; `aegis inspect .` flags all five write sinks and the
real `ContentSecurityScanner` rejects the poisoned write. Exercises `user_input_to_memory`,
`tool_output_to_memory`, and `missing_injection_screening` across the LangGraph / vector-DB /
custom sink families.

## Tier 2 — RAG / document poisoning (future PR)

A retrieval pipeline where a poisoned **document** enters a vector store via `add_documents` and
resurfaces in a later prompt with no provenance. Exercises `vector_db_write` + `missing_provenance`.
Mirrors the document/RAG-poisoning class in arXiv:2512.16962. Implement as
`examples/aegis-rag-poisoning/` with a benign-vs-poisoned corpus and a retrieve→prompt step that
shows the unprovenanced reuse. Do not build yet.

## Tier 3 — multi-agent shared-memory cross-contamination (future PR)

Agent A (untrusted input) writes to **shared/global** memory; Agent B (privileged) reads and
acts. Exercises `overbroad_shared_access`. Highest enterprise-LTV story (the "we let agents
remember things — how do we control what becomes persistent context?" buyer pain). Implement as
`examples/aegis-multi-agent/`. Roadmap note only for now.
