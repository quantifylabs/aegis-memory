# Aegis Memory Firewall — multi-source poisoning demo

Production agents don't read memory from one place. They absorb untrusted data from **five
realistic channels** — a user/support ticket, a retrieved document, a tool/API result, a web
fetch, and an inbound email — and write it all into **shared memory** that a later, privileged
step reads and acts on. Any one of those writes can plant a fake "policy" that steers a
business decision. This demo shows that attack end to end, and shows `aegis inspect` acting as
the **write-path firewall** that catches it — backed by the **real** `ContentSecurityScanner`
and the **real** computed risk score, never hardcoded.

Everything here is **offline and deterministic** — no API keys, no network, identical output
every run.

## Why prompt-time guardrails miss this

The malicious instruction **never comes from the user**. In `run_without_aegis.py` the agent
ingests an untrusted **web page** whose text carries a buried instruction-override asserting a
fake auto-approval policy. It lands in shared memory with no provenance. Later, a perfectly
benign user request — *"process this $8,000 refund"* — reads that poisoned memory and is wrongly
**APPROVED**. A guardrail that inspects the *user's prompt* sees nothing wrong, because the
poison arrived through a **memory write**. That write is the one place Aegis screens.

## Run it

```powershell
pip install -r requirements.txt          # langgraph + aegis-memory (demo-local deps)

python run_without_aegis.py              # staged web poison lands -> $8,000 refund APPROVED (fraud)
python run_with_aegis.py                 # real scan() REJECTS the write -> refund correctly DENIED
```

`run_with_aegis.py` prints the scanner's live verdict:

```
[AEGIS] write to 'latest_note' REJECTED by ContentSecurityScanner (action=reject, detected=['injection_override'])
```

That `reject` is a real `scan()` call on the benchmark-validated pipeline — no hardcoded verdict.
The benign seeds in `inputs/benign/` carry no injection and are correctly left alone (no false
positive — precision-first).

## Inspect it the way a stranger would

```powershell
aegis inspect agent                            # the THREAT view  -> agent/aegis-out/ (5 exposed writes, score 100)
aegis inspect agent_screened --baseline agent  # the BEFORE->AFTER -> agent_screened/aegis-out/ (5 blocked, 100 -> 2)
```

Each run writes a single canonical `aegis-out/` **inside the inspected path** — no second copy
floating at the example root. `aegis inspect agent` shows the threat (five untrusted writes
reaching memory, score 100). `aegis inspect agent_screened --baseline agent` inspects the
screened package (every write blocked at a guard, score 2) and uses the unscreened `agent/`
score as the "before", so the map header shows the real `100 → 2 / 100` governance transition —
both numbers are the real `compute_score()` output, never hardcoded. (A plain run also shows a
before→after on its own whenever a project mixes screened and unscreened writes: the "before" is
the same heuristic with screening discounts ignored.)

`aegis inspect agent` finds **all five** untrusted writes via the **general** sink catalog (it
keys off sink *shapes*, never this demo's filenames or strings):

```
AEG-001 [critical/EXTRACTED] Untrusted input written to memory via vectorstore.add_documents
  agent/ingest_document.py · sink vectorstore.add_documents (vectordb) · source untrusted_input
AEG-002 [critical/INFERRED]  Untrusted input written to memory via checkpointer.put
  agent/ingest_email.py · sink checkpointer.put (langgraph) · source untrusted_input
AEG-003 [critical/EXTRACTED] Tool output written to memory via memory.save
  agent/ingest_tool.py · sink memory.save (custom) · source tool_output
AEG-004 [critical/INFERRED]  Untrusted input written to memory via store.put
  agent/ingest_user.py · sink store.put (langgraph) · source untrusted_input
AEG-005 [critical/EXTRACTED] Untrusted input written to memory via store.put
  agent/ingest_web.py · sink store.put (langgraph) · source untrusted_input

  Fix (paste this):
    from aegis_memory import guard
    guard.write(content, trust_level='untrusted', require_classifier=True)
```

`aegis-out/agent_memory_map.html` is a **proof-first memory-trace report**, not a poster. It
leads with a **faithful trace**: one lane per untrusted source→memory write, each lane anchored
to a real `file:line` and sink call, with the edge styled by the *one* provable distinction —
**exposed** (no guard in scope, the write reaches memory) vs **screened** (a guard wraps the
write, so it's blocked at the gate). Below it, a **live scan replay** panel shows the real
`ContentSecurityScanner.scan()` verdict on a memory-poisoning payload (`action: reject`, the
`injection_override` detector that fired, and the literal text it matched) — a real `scan()`
call, never a hardcoded string. The full findings table (same data as `findings.json`) sits
below. The header shows the real risk transition **100 → 2 / 100** (heuristic, lower is safer;
not the benchmark), and the "after" stays non-zero because residual risk is more credible than a
green 0. Open `aegis-out/agent_memory_map.html` — it's a self-contained, mobile-friendly single
file (the trace lanes stack vertically on a phone).

## How it maps to the code

| Channel | File | Sink idiom | Framework |
|---|---|---|---|
| user / ticket | `agent/ingest_user.py` | `store.put(ns, key, value)` | LangGraph store |
| retrieved document | `agent/ingest_document.py` | `vectorstore.add_documents([...])` | vector DB |
| tool / API result | `agent/ingest_tool.py` | `memory.save(tool_result)` | custom memory |
| web fetch | `agent/ingest_web.py` | `store.put(...)` of `requests.get(url).text` | LangGraph store |
| email body | `agent/ingest_email.py` | `checkpointer.put(cfg, key, value)` | LangGraph checkpointer |

- `agent/decide.py` — the privileged step that reads shared memory and makes the refund call.
  It cannot tell a vetted internal policy from a poisoned web note — which is why the *write* is
  where the firewall belongs.
- `agent_screened/ingest_screened.py` — the same five writes, each with a real `scan()` gate in
  scope (the copy-pasteable fix the findings point at). `aegis inspect` marks these **screened**
  and downgrades them, which is the "after" score the map renders.
- `run_without_aegis.py` / `run_with_aegis.py` — the staged attack at runtime; the "with" script
  wraps the store in `AegisGuardedStore`, which screens every write through the real scanner.
- `inputs/poisoned/` and `inputs/benign/` — the web/email payloads (poisoned carries the
  instruction-override; benign does not).

The findings are the defensible object a security reviewer reads; the score is labeled UX sugar
built *from* the findings. See `../ROADMAP.md` for the next tiers (RAG/document poisoning and
multi-agent shared-memory cross-contamination).
