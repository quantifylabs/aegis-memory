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
aegis inspect .                          # writes aegis-out/ (report, findings, map, policy)
python build_memory_map.py               # renders agent_memory_map.html from TWO real runs
```

`aegis inspect .` finds **all five** untrusted writes via the **general** sink catalog (it keys
off sink *shapes*, never this demo's filenames or strings):

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

`build_memory_map.py` renders the visual from **two real inspect runs** — the unscreened
`agent/` package vs. the screened `agent_screened/` package — so the header shows a real
governance transition, **100 → 2 / 100** (heuristic; not the benchmark). Both numbers are the
real `compute_score()` output; the "after" stays non-zero because residual risk is more
credible than a green 0. Open `agent_memory_map.html` — it's a self-contained, mobile-friendly
single file.

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
