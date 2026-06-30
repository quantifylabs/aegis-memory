# `aegis inspect` — analyzer second wave (deferred, not forgotten)

> **Tracked in [#76](https://github.com/quantifylabs/aegis-memory/issues/76)** (async writes + AutoGen/LlamaIndex/Letta/Zep + TS/JS); `append`/buffer is [#77](https://github.com/quantifylabs/aegis-memory/issues/77). This file is the detailed spec; follow the issues for status.

The closing analyzer item (`fix/inspect-langgraph-state-source`, "Fix 1") completed the
LangGraph node-`state` / field source resolution. With it merged, the analyzer is
*done enough* for launch. The items below are **explicitly deferred** — tracked here so
they aren't silently dropped. Do not start them as part of the closing fix.

> **Coverage policy:** the supported source×sink taxonomy, the acceptance corpus, and the
> fix-vs-defer stop rule now live in `docs/issues/inspect-coverage-policy.md`. Use that as the gate;
> this list is the deferred-detail spec.

## Landed since
- **LangChain/LangGraph tool-arg source shape** — a tool function's model-supplied args are now
  untrusted-by-default (`taint.py` `_is_langchain_tool`); injected runtime params are excluded.
- **`.get()`/weak-verb egress precision** — bare `dict.get()`/`config.get()` no longer read as network
  input (strong vs. weak call-verb split). See the coverage policy's baseline notes.

## Deferred sink / source detection
- **`append` / buffer-mode writes** — punted by decision (list/deque buffer poisoning).
  See also `docs/issues/buffer-memory-mode.md`.
- **Async writes** — `aadd_texts` and other `a*` vector-store coroutine variants (note: LangGraph
  `aput` *is* covered on the sink side).
- **More frameworks as first-class** — AutoGen, LlamaIndex, Letta, Zep (currently only
  generic/name-hint coverage, not tailored shapes).
- **TS / JS** — the analyzer walks Python (`.py` + notebook code cells) only.

See also `docs/issues/inspect-followups.md` for UX / scoring / distribution follow-ups
and the bounded-taint engine upgrade candidates (import-alias resolution, receiver type
binding, container element tracking).

## Honest non-escalations (precision-first, by design)
Recorded so a future reader doesn't mistake these for analyzer gaps. In
`langgraph-long-memory` (`code.ipynb`) only the genuinely untrusted write was escalated:

- **`code.ipynb:24`** `in_memory_store.put(..., memory)` — `memory` is a hardcoded
  literal dict (`{"food_preference": "I like pizza"}`). Trusted; stays `low`.
- **`code.ipynb:193`** `store.put(ns, "user_preferences", default_content)` —
  `default_content` traces to imported default-prompt constants (`default_*` from
  `email_assistant.prompts`). Trusted defaults; stays `low`.
- **`code.ipynb:231`** `store.put(ns, "user_preferences", result.user_preferences)` —
  the **escalated** flow. `result = memory_updater_llm.invoke([...] + messages)` over
  node-supplied `state['messages'] + [...]`. Resolves `untrusted` at the **LLM-egress
  boundary** (the existing `.invoke()` source hint), not the upstream
  `state['messages']`: the LLM transform is a real trust boundary, and threading through
  it (list-comprehension + binop dataflow) is intentionally out of scope for the bounded
  resolver.

Forcing 24/193 to escalate would be over-marking and would contradict the analyzer's
precision-first contract — so it is deliberately not done.
