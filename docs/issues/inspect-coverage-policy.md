# `aegis inspect` — coverage policy & the corpus gate

> **Why this file exists.** Testing a static analyzer by cloning repos one at a time is an *unbounded*
> loop: every new repo can surface one more idiosyncrasy, so "no gaps on any repo" never terminates.
> This document replaces that stop rule with a **bounded** one: a fixed taxonomy of what we claim to
> detect, a fixed corpus that measures it, and a written rule for when a newly-found gap triggers a fix
> versus a deferral. Publish on the corpus bar — not on the last repo you cloned.

## The stop rule (when `inspect` is "done enough")

Ship when **both** hold:

1. **Every supported taxonomy cell has a green fixture/test** (the table below), and
2. **The acceptance corpus passes the stated bar** — currently *no critical false positives* and
   100% precision on flow-level (critical/high) findings.

New internet repos are **spot-checks**, not the gate. When a spot-check reveals something:

- **In-taxonomy defect** (a shape we claim to support, mis-scored) → **fix now** + regression test.
- **Out-of-taxonomy** (a shape we explicitly don't support) → it's a **documented scope boundary**
  ([#76](https://github.com/quantifylabs/aegis-memory/issues/76) /
  [#77](https://github.com/quantifylabs/aegis-memory/issues/77)), not an automatic fix.
- **Genuinely new + prevalent shape** → **promote it into the corpus deliberately** and re-baseline.
  This is a controlled expansion of the acceptance set, not an open-ended chase.

This is how "fix everything found" stays finite: the universe of things to fix is the corpus, which is
closed. A repo outside it can *propose* an addition, but it doesn't silently move the bar.

## The detection taxonomy (source × sink)

A finding is an **untrusted source** reaching a **durable memory-write sink** with no screening between.
Both axes are finite and enumerated here; each supported cell has a fixture + test.

### Untrusted sources (what we claim to detect)

| Source shape | How it's detected | Test/fixture |
| --- | --- | --- |
| Direct untrusted I/O (request/web/file/tool/`input()`) | name/attr hints + call egress (`taint.py` `_UNTRUSTED_*`) | `inspect`, `inspect_taint`, `inspect_streamlit` |
| Network/IO/LLM call egress (`httpx.get().text`, `.invoke()`, `.read_text()`) | strong verbs fire anywhere; weak verbs (`get`/`read`/`run`) only on a known network receiver | `inspect_taint`, `test_network_get_is_still_an_untrusted_source` |
| LangGraph node `state` param | import-gated `state` shape (`_untrusted_params`) | `test_langgraph_state_*` |
| CrewAI tool `_run`/`_arun` args | `*Tool` subclass method shape | `test_crewai_*` |
| **LangChain/LangGraph tool args** (`@tool` / `Injected*`) | `_is_langchain_tool` — non-injected params untrusted | `inspect_langchain_tool` |
| LLM egress (assistant message `.content`/`.text` → memory) | attribute hints + bounded interproc | corpus `mem0_patterns`, `self_reflection_memory` |
| Bounded cross-function (param ascent / return descent) | `interproc.py` (`MAX_HOPS`/`MAX_FUNCS`) | `inspect_taint` cross-file |

### Memory-write sinks (what counts as durable memory)

LangGraph store/checkpointer (`put`/`aput`/`put_writes`) · vector DB (`add`/`upsert`/`add_texts`/async
variants on a vector receiver) · mem0/embedchain (constructor-bound) · aegis distinctive methods ·
custom memory-ish receivers. (`sinks.py`, three precision tiers + constructor binding.)

### Explicitly out of scope (documented boundaries, not bugs)

- **JS/TS** — the analyzer walks Python `.py` + `.ipynb` only.
- **`append`/buffer** writes to ephemeral local containers ([#77](https://github.com/quantifylabs/aegis-memory/issues/77)).
- **Async vector** `aadd_texts`/`aadd_documents` and other niche `a*` sinks ([#76](https://github.com/quantifylabs/aegis-memory/issues/76)).
- **Letta/Zep/Graphiti/AutoGen/LlamaIndex** first-class shapes — generic/name-hint coverage only ([#76](https://github.com/quantifylabs/aegis-memory/issues/76)).
- **Framework-managed / declarative memory** — e.g. CrewAI `Crew(memory=True)`, or a LangChain
  `ConversationBufferMemory` auto-wired into a chain. The durable writes happen *inside the library*,
  so there is **no explicit memory-write sink in the user's source** for a static analyzer to anchor
  to. `inspect` correctly reports nothing — but **absence of findings here is not a safety proof**: the
  poisoning surface still exists inside the framework. Flagging it would require modeling each
  framework's internal memory wiring (a much larger, lower-precision effort) and is deliberately not
  attempted.

## Acceptance corpus

**`NirDiamant/Agent_Memory_Techniques`** — 30 runnable `.ipynb` across short-term/long-term/cognitive
memory, vector stores, and the mem0/Letta/Zep frameworks. Chosen because it is a diverse, framework-spanning,
*fixed* set (also the FP-validation corpus named in `docs/issues/buffer-memory-mode.md`).

### Baseline — 2026-06-30 (run with the LangChain-tool shape + `get()` precision fix)

`python -m aegis_memory.cli inspect <corpus>` over all 30 notebooks:

| | Count |
| --- | --- |
| Findings total | 52 |
| Critical | 2 |
| High | 0 |
| Medium | 2 |
| Low | 48 (46 structural `memory_write`, 2 `missing_provenance`) |

- **Both criticals are true positives**, verified against the source:
  - `mem0_patterns.ipynb` — `self.memory.add([... assistant_message ...])` where
    `assistant_message = response.choices[0].message.content` (LLM output → mem0, unscreened).
  - `self_reflection_memory.ipynb` — `self.store.add({... outcome ...})` where `outcome` traces to
    `response.content[0].text` (LLM/agent output → reflection memory, unscreened).
- **Precision on flow findings: 2/2 = 100%. No critical false positives.**
- The 48 lows are honest structural sinks (source unresolved within the bounded search) — labeled
  "not detected at this site," never a claim the value is safe. They are not counted as false positives.

### Defects this corpus run found and fixed (in-taxonomy)

- **Bare `.get()` treated as network egress.** `reflection.get("insight")` / `config.get(...)` /
  `dict.get(...)` were read as untrusted I/O purely on the verb. Split the call-egress hints into
  **strong** verbs (fire anywhere) and **weak** verbs (fire only on a known network/IO/tool receiver),
  matched across the full receiver token set so `self.client.get(...)` still qualifies. Regression:
  `test_plain_dict_get_is_not_an_untrusted_source`, `test_network_get_is_still_an_untrusted_source`.
- (Same round) **LangChain tool args** not treated as untrusted — added the `_is_langchain_tool`
  source shape; `langchain-ai/memory-agent`'s `store.aput` flow now escalates to critical.

### Spot-checks — 2026-06-30 (the loop, demonstrated)

Per the stop rule, these are validation runs, not gate-movers. Result: **neither triggered a code
change** — one confirmed the bar against a pre-registered ground truth, the other revealed a documented
boundary. That is the loop terminating by design.

| Repo | Result | Verdict |
| --- | --- | --- |
| `langchain-ai/memory-agent` | `tools.py:34 store.aput` → **critical** (LangChain tool arg) | In-taxonomy; drove the tool-arg shape, now a fixture. |
| `FareedKhan-dev/langgraph-long-memory` | `code.ipynb:231 store.put` → **critical** via LLM-egress `invoke()`; `:24`/`:193` stay low | **Exactly matches** the pre-registered expectation in `second-wave.md`. No action. |
| `botextractai/ai-crewai-deep-research` | **0 findings** (memory is `Crew(memory=True)`; scrape `_run` returns, never writes; local `set.add` ignored) | Correct — framework-managed memory is an out-of-scope boundary (now documented). No action. |

## Re-baselining procedure

1. `git clone --depth 1 https://github.com/NirDiamant/Agent_Memory_Techniques` (sibling of the repo).
2. `python -m aegis_memory.cli inspect <corpus>`; read `aegis-out/findings.json`.
3. Triage every critical/high for TP/FP; spot-check notebooks with known untrusted→memory writes for FN.
4. Fix in-taxonomy defects (+ regression test); record out-of-taxonomy items against #76/#77.
5. Update the dated baseline table above. Ship when the stop rule holds.
