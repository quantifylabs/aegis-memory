"""Phase 1.5 adaptive paraphrase probe.

A small, cheap directional check (NOT a benchmark) of whether Stage 4 catches
what Stage 3 misses under paraphrase. Reuses the static benchmark machinery
(``Dataset``, ``System``, ``run_system_on_dataset``, ``ResponseCache``,
``metrics.*``) so it also smoke-validates the Phase 2 harness contracts.

The publishable artifact remains the full Phase 2 harness
(``TASK_adaptive_harness.md``); this only de-risks the spend on it.
"""
