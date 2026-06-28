"""Phase 2 adaptive attack harness for the Aegis injection benchmark.

Three adaptive attacks that actively try to *evade* the content-security
pipeline (rather than measuring detection on a fixed corpus):

  - Attack 1 (``attack_rule_evasion``): rule-evasion against the deterministic
    Stage 3 (free oracle); headline = the Stage-3 -> Stage-4 hand-off.
  - Attack 2 (``attack_oracle``): classifier-oracle evasion against the Stage-4
    LLM classifier; records queries-to-evade + an evasion-vs-budget curve.
  - Attack 3 (``attack_composition``): payload-splitting / composition
    (illustrative, smaller-by-design).

The harness REUSES the static benchmark machinery (``Dataset``, ``System``,
``ResponseCache``, ``metrics``, ``run_system_on_dataset``) and the proven
``probe`` primitives (cached cheap-model paraphrase + intent judge, the
error-aware ``evasion = 1 - recall`` evaluation, and the hand-off arithmetic)
rather than forking them. It writes a SEPARATE ``adaptive_results.json`` and
never touches the static ``results/results.json``.
"""
