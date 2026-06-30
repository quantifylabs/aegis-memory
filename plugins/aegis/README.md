# Aegis — Claude Code plugin

**Secure your agent's memory.** Aegis detects **OWASP ASI06 — Memory & Context
Poisoning** in your agent code. It runs **locally, with no API key — your code
never leaves your machine.**

## Why

Agents read untrusted content (user messages, tool output, web pages, email,
documents) and write it into long-term memory. If that path isn't screened, an
attacker can *poison* the memory so future decisions are silently steered. Aegis
finds those unsafe write paths and gives you an always-on guard against them.

## What you get

The plugin ships three components, all keyless and local by default:

1. **`/aegis:inspect`** — a slash command that runs `aegis inspect .` and
   summarizes the **memory map**, a **risk score (0–100)**, and **findings**
   mapped to OWASP ASI06. Writes an interactive `agent_memory_map.html`, an
   `INSPECTION_REPORT.md`, and a **`findings.sarif`** (for GitHub code scanning /
   CI annotations) to `aegis-out/`. Silence an accepted sink with an inline
   `# aegis: ignore` comment; gate CI with `aegis inspect . --ci --max-risk N`.
2. **Write-path guard hook** — a `PostToolUse` hook on `Edit`/`Write`/`MultiEdit`
   that warns (never blocks, in v0.1) when an edit touches an unsafe memory-write
   sink, and suggests `/aegis:inspect`.
3. **Local MCP server** — exposes model-callable `inspect_project` and
   `replay_attack` tools that run fully keyless (no network, no backend). Set
   `AEGIS_API_KEY` to additionally enable the hosted memory-runtime tools
   (`add_memory`, `query_memory`, cross-agent, voting, sessions, …); without a
   key those degrade with a clear message instead of failing.

## Install

```bash
# Add the marketplace, then install the plugin:
/plugin marketplace add quantifylabs/aegis-memory
/plugin install aegis@aegis-marketplace
```

> **Requirement:** the MCP server runs `python -m aegis_memory.mcp_server`, so the
> `aegis-memory` package must be importable in the environment Claude Code
> launches (`pip install aegis-memory`). The `/aegis:inspect` command likewise uses
> the `aegis` CLI from that install — and falls back to `python -m aegis_memory.cli`
> if the script isn't on `PATH`.
>
> Installing into a **virtualenv** (and launching Claude Code from it) is the most
> reliable setup: a venv always provides a `python` executable, which is what the
> bundled `.mcp.json` invokes. On a system where only `python3` exists (some bare
> Linux/macOS installs), either use a venv or edit the MCP `command` in
> `.mcp.json` from `python` to `python3`. The write-path guard hook needs no such
> change — it already tries `python` then `python3`.

## Modes

| | Local (no key) | Hosted (`AEGIS_API_KEY` set) |
| :-- | :-- | :-- |
| `inspect_project`, `replay_attack`, `/aegis:inspect`, guard hook | ✅ | ✅ |
| memory-runtime tools (add/query/vote/sessions/…) | degrade with a message | ✅ |

## Links

- Repository: https://github.com/quantifylabs/aegis-memory
- OWASP Agentic Security Initiative — ASI06: Memory & Context Poisoning
