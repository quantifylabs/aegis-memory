---
description: Scan this project for unsafe agent-memory flows (OWASP ASI06) — memory map, risk score, and findings. Local & keyless.
---

Run a local, keyless Aegis inspection of the current project and report the results.

1. Run the inspector from the project root:

   ```bash
   aegis inspect .
   ```

   This needs **no API key and no server** — it analyzes the code statically and
   writes artifacts to `aegis-out/` (including `agent_memory_map.html` and
   `INSPECTION_REPORT.md`).

2. Summarize for the user:
   - The **Memory Risk Score** (0–100) and what it means.
   - The **memory map**: which untrusted sources (user input, tool output, web,
     email, documents) flow into memory write sinks, and where (`file:line`).
   - The **findings**, grouped by severity, each mapped to **OWASP ASI06
     (Memory & Context Poisoning)**. For every finding, state the source → sink
     flow and the suggested fix (e.g. screen the write with `aegis.guard.write`).

3. Call out the highest-severity unscreened flows first and recommend concrete
   next steps. Point the user to `aegis-out/agent_memory_map.html` for the full
   interactive map.

Keep the summary tight and actionable.
