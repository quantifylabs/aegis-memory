# `aegis inspect` — opt-in buffer-memory mode (`--include-buffers`)

**Status:** proposed / not implemented. Tracked out of Batch B (constructor-binding receiver
resolution). **Default stays PUNT** — `append` and plain local containers are out of scope by design.

## Why this is deferred, not done
`inspect` deliberately scopes itself to writes to **persistent and shared** memory (the ASI06
poisoning surface). Ephemeral in-process buffers — `list.append`, a local `dict`, a `set` — are not a
durable cross-turn/cross-agent store, so flagging them on-by-default would mint exactly the
false-positive class (`results.append(x)` looking like a sink) that the catalog header warns about and
that nearly sank the tool once. Batch B's whole safety story is that **new detection ships only behind
a measured FP gate**; a blanket `append` rule cannot pass that gate.

## What the mode would do
An explicit `--include-buffers` flag (off by default) that flags a buffer write **only when both**
hold, never on the method name alone:

1. **Receiver is memory-ish** — the receiver resolves (via the Batch-B constructor binding in
   `aegis_memory/inspect/bindings.py`) to a memory handle, *or* its name matches an existing memory
   hint. A bare `results.append(...)` on an unbound local never qualifies.
2. **Value taints to an untrusted source** — the appended value resolves `untrusted` through the
   existing taint / interproc engine (`taint.py`, `interproc.py`). A constant or internal value is
   not flagged.

Findings would be emitted at a distinct low confidence (`AMBIGUOUS`) and clearly labeled
"buffer (opt-in)", separate from the durable-memory findings.

## Before it can ship
- Validate against the 30-technique corpus (`NirDiamant/Agent_Memory_Techniques`): measure the FP rate
  on innocent `append`/local-container sites. It ships on-by-default **only** if that rate is ~zero.
- Add owned TP/TN fixtures mirroring the Batch-B gate (`tests/fixtures/inspect_binding/`): an untrusted
  value appended to a *bound* buffer (TP) vs. `results.append(x)` / constant appends / unbound
  containers (TN, must stay clean).
- Decide the runtime-guard story: the runtime `WRITE_METHODS` contract already includes `append`/`set`
  (`sinks.py`), so the static side is the only gap.

## Related
- `docs/issues/inspect-followups.md` — other tracked `inspect` increments.
