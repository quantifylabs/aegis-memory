## Aegis adaptive paraphrase probe — summary

Date: 2026-06-28T09:04:44.143113+00:00  |  Seeds: 15  |  Paraphrases: 45  |  Intent-preserved: 39  |  Excluded: 6

_Directional probe, not a benchmark. The publishable artifact is the full Phase 2 harness (TASK_adaptive_harness.md)._

### Per-system evasion (over intent-preserved paraphrases)

| System                       | Evasion rate (1-recall)  | 95% bootstrap CI       |
|------------------------------|--------------------------|------------------------|
| aegis_stages_1_3             | 35.9%                    | [20.5%, 51.3%]         |
| aegis_stages_1_4_openai      | 2.6%                     | [0.0%, 7.7%]           |
| aegis_stages_1_4_anthropic   | 0.0%                     | [0.0%, 0.0%]           |
| llm_guard                    | 28.2%                    | [15.3%, 43.6%]         |

### The hand-off (decision headline)

Of 14 candidates that evaded Stage 3:
  - aegis_stages_1_4_openai caught: 92.9% of them (13/14)
  - aegis_stages_1_4_anthropic caught: 100.0% of them (14/14)

### Decision thresholds (suggested reading)
- Stage 4 catches >80% of Stage-3 evaders -> defense-in-depth holds; apply with confidence.
- Stage 4 catches 50-80% -> publishable but discuss; apply with the hand-off framed honestly.
- Stage 4 catches <50% -> recalibrate narrative before applying; possibly reframe as testbed-fund.

