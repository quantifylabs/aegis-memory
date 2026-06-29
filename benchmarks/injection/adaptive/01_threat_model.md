# Aegis adaptive evaluation — Threat Model (Phase 1, the spine)

This document pre-registers the adaptive harness threat model used by
`benchmarks/injection/adaptive/`.

## Tier G — Grey-box (the deployed-realism tier)

The attacker knows the pipeline is a multi-stage validator with an LLM
classifier component and knows the general category of checks, but does not have
the exact Stage-3 rule list or threshold.

For Attack 1, Tier G is a single committed blind variant per seed: the attacker
may filter blind paraphrases for intent preservation, then commits to the first
intent-preserving variant, and Stage 3 is queried only afterward for measurement
rather than to select among variants.
