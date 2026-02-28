<p align="center">
  <img src=".github/banner.svg" alt="Aegis Memory" width="400"/>
</p>

<p align="center">
  <strong>Your memory layer is your attack surface. Act accordingly.</strong>
</p>

<p align="center">
  Open-source memory engine for multi-agent AI.<br/>
  Content security. Memory integrity. Trust hierarchy. Self-improving agents.
</p>

<p align="center">
  <a href="https://opensource.org/licenses/Apache-2.0"><img src="https://img.shields.io/badge/License-Apache_2.0-blue.svg" alt="License"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.10+-blue.svg" alt="Python 3.10+"></a>
  <a href="https://docs.aegismemory.com"><img src="https://img.shields.io/badge/docs-aegismemory.com-6366F1" alt="Docs"></a>
</p>

<p align="center">
  <a href="https://www.aegismemory.com/">Website</a> •
  <a href="https://docs.aegismemory.com/introduction/overview">Docs</a> •
  <a href="https://www.aegismemory.com/blog/">Blog</a> •
  <a href="https://docs.aegismemory.com/quickstart/installation">Quickstart</a> •
  <a href="https://docs.aegismemory.com/guides/security">Security Guide</a>
</p>

---

## The Problem Nobody Else Is Solving

Agents are getting compromised. Not theoretically — right now.

- [**EchoLeak**](https://arxiv.org/html/2509.10540v1) (CVE-2025-32711, CVSS 9.3) — a single email triggered zero-click data exfiltration from Microsoft 365 Copilot[^echoleak]
- [**CrewAI + GPT-4o**](https://openreview.net/pdf?id=DAozI4etUp) — researchers achieved 65% exfiltration success rate against multi-agent systems (COLM 2025)[^crewai]
- [**Drift chatbot cascade**](https://socprime.com/blog/cve-2025-32711-zero-click-ai-vulnerability/) — one compromised chatbot integration cascaded into 700+ organizations via Salesforce, Google Workspace, Slack, S3, and Azure[^drift]
- [**OWASP Top 10 for Agentic Applications**](https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/) published December 2025 — memory and context manipulation is a top risk category[^owasp-top10]

**Agent A's output is Agent B's instruction. Memory is the vector.**

Every other memory layer trusts content by default. That is the vulnerability.

## What Your Memory Layer Is Missing

We checked the docs, repos, and changelogs of every major competitor.[^comparison] These protections do not exist anywhere else:

| Security Feature | mem0 | Zep | Letta | Aegis |
|---|---|---|---|---|
| Content injection detection | — | — | — | 4-stage pipeline |
| Memory integrity | — | — | — | HMAC-SHA256 |
| Agent identity binding | — | — | — | Cryptographic API key |
| Trust hierarchy | — | — | — | 4-tier OWASP model |
| Per-agent rate limiting | — | — | — | Sliding window |
| Security audit trail | — | — | — | Immutable event log |
| Sensitive data protection | — | — | — | Auto-detect + reject/redact/flag |

## Built for a World Where Agents Get Compromised

Aegis implements [OWASP AI Agent Security](https://cheatsheetseries.owasp.org/cheatsheets/AI_Agent_Security_Cheat_Sheet.html) recommendations natively. Six capabilities, none optional:

1. **[4-stage content security pipeline](https://docs.aegismemory.com/guides/security)** — input validation, sensitive data scanning, prompt injection detection, optional LLM-based injection classification. Every memory write. Not optional.
2. **[HMAC-SHA256 integrity signing](https://docs.aegismemory.com/guides/security)** — tamper detection on store, verification on demand. You know if a memory was modified.
3. **[OWASP 4-tier trust hierarchy](https://docs.aegismemory.com/guides/security)** — untrusted, internal, privileged, system. Agents get compromised. Aegis limits the blast radius.
4. **[Cryptographic agent binding](https://docs.aegismemory.com/guides/security)** — API keys bound to agent identity. No more trusting a request body that says "I'm the admin agent."
5. **[ACE loop](https://docs.aegismemory.com/guides/ace-patterns)** — generation, reflection, curation. Agents that learn from their own mistakes and promote what works.
6. **[Multi-agent coordination](https://docs.aegismemory.com/quickstart/installation)** — scoped access control, cross-agent query, structured handoffs. Memory sharing with boundaries.

## Get Running in 2 Minutes

### Start the server

```bash
git clone https://github.com/quantifylabs/aegis-memory.git
cd aegis-memory

export OPENAI_API_KEY=sk-...
docker compose up -d

curl http://localhost:8000/health
# {"status": "healthy"}
```

### Install the SDK

```bash
pip install aegis-memory
```

### Multi-agent memory in 10 lines

```python
from aegis_memory import AegisClient

client = AegisClient(api_key="dev-key", base_url="http://localhost:8000")

# Planner agent stores task breakdown
client.add(
    content="Task: Build login. Steps: 1) Form, 2) Validation, 3) API",
    agent_id="planner",
    scope="agent-shared",
    shared_with_agents=["executor"]
)

# Executor queries planner's memories
memories = client.query_cross_agent(
    query="current task",
    requesting_agent_id="executor",
    target_agent_ids=["planner"]
)
print(memories[0].content)
```

**[Full Quickstart Guide](https://docs.aegismemory.com/quickstart/installation)**

## Agents That Learn From Their Own Mistakes

Aegis is the first memory engine with a complete ACE loop — the Generation → Reflection → Curation cycle from Stanford/SambaNova's research, engineered for production.

Your agent made the same mistake 5 times? ACE loop remembers the fix forever. Stale memories polluting retrieval? Curation auto-cleans your playbook.

```
Generation          Execution          Reflection          Curation
    |                   |                   |                  |
 Query playbook  ->  Run task with   ->  Auto-vote on    ->  Promote effective
 for strategies      tracked memories    used memories       Flag ineffective
                                         Auto-reflect        Consolidate duplicates
                                         on failures
```

### Full ACE Loop in Code

```python
from aegis_memory import AegisClient

client = AegisClient(api_key="your-key")

# 1. GENERATION: Query agent-specific playbook
playbook = client.get_playbook_for_agent(
    "executor",
    query="API pagination task",
    task_type="api-integration",
)
memory_ids = [e.id for e in playbook.entries]

# 2. EXECUTION: Track which memories the agent uses
run = client.start_run(
    "task-42", "executor",
    task_type="api-integration",
    memory_ids_used=memory_ids,
)

# ... agent does its work ...

# 3. REFLECTION: Complete with outcome (auto-feedback!)
client.complete_run("task-42", success=True, evaluation={"score": 0.95})
# -> Auto-votes 'helpful' on every memory used
# -> On failure: auto-votes 'harmful' AND creates a reflection memory

# 4. CURATION: Periodically clean up
curation = client.curate(namespace="production")
# -> Promotes high-effectiveness entries
# -> Flags low-effectiveness for deprecation
# -> Identifies duplicate entries to consolidate
```

### What "Engineered" Means vs "Inspired"

| Feature | ACE-Inspired | Aegis ACE-Engineered |
|---------|-------------|---------------------|
| Voting | Manual vote endpoints | Auto-voting tied to run outcomes |
| Reflection | Manual reflection creation | Auto-reflection on failure with error context |
| Curation | Not implemented | Full curation cycle with promote/flag/consolidate |
| Run tracking | Not tracked | First-class `ace_runs` table linking memories to outcomes |
| Agent-specific playbook | Generic query | Filtered by agent_id + task_type |

**[ACE Patterns Guide](https://docs.aegismemory.com/guides/ace-patterns)**

## Choosing the Right Memory Solution

Different tools solve different problems. This comparison stays focused on capabilities clearly documented in public repos and docs.[^comparison]

| If you need... | Usually pick | Reason |
|---|---|---|
| Personalized assistant memory (user/profile facts) | **mem0** | Designed around persistent user/agent memory for assistants |
| Personal/team "second brain" with ingestion | **Supermemory** | Knowledge-base style memory with connectors |
| Graph-native episodic memory over agent events | **Graphiti / Zep** | Focused on temporal + knowledge graph memory models |
| Stateful agent runtime + built-in memory blocks | **Letta** | Agent framework centered on durable state |
| Security-first multi-agent memory | **Aegis Memory** | Only memory layer with content security, integrity, and trust hierarchy |
| Multi-agent coordination with access boundaries | **Aegis Memory** | Scope-aware ACLs + cross-agent query APIs |
| Self-improving memory loops (what worked / failed) | **Aegis Memory** | ACE patterns: vote, reflection, playbook |

### Quick Feature Comparison

| Capability | mem0 | Graphiti / Zep | Letta | Aegis Memory |
|---|---|---|---|---|
| **Primary focus** | Assistant personalization | Graph-based episodic memory | Stateful agents | Secure multi-agent coordination |
| **Open source** | Yes | Yes | Yes | Yes |
| **Self-host posture** | Available | Available | Available | Self-host-first |
| **Content security pipeline** | — | — | — | 4-stage (validation, PII, injection, LLM) |
| **Memory integrity** | — | — | — | HMAC-SHA256 |
| **Trust hierarchy** | — | — | — | 4-tier OWASP model |
| **Multi-agent ACL/scopes** | — | — | — | Yes |
| **Cross-agent query** | — | — | — | Yes |
| **Handoff baton** | — | — | — | Yes |
| **ACE loop** | — | — | — | Yes |
| **Typed memory model** | — | — | — | Yes |
| **Temporal decay** | — | Partial | — | Yes |

### When to Pick Aegis

Pick **Aegis Memory** when most of these are true:

- You need **content security** — injection detection, integrity verification, sensitive data protection.
- You need **multiple agents** to share memory safely with explicit ACL/scopes.
- You need **handoffs** where one agent passes a reliable state bundle to another.
- You want **ACE patterns** (vote/reflection/playbook) to continuously improve memory quality.
- You prefer a **self-host posture** with operational control over storage and deployment.
- You need **temporal decay** so stale memories don't pollute retrieval over time.

## Performance

Benchmarked on 8 vCPU / 7.6 GB RAM (Intel 13th Gen), 1000 memories, Docker Compose (PostgreSQL 16 + pgvector), concurrency=10. Queries include OpenAI embedding latency. Reproduce with `cd benchmarks && bash run_benchmark.sh`.

| Operation | p50 | p95 | p99 | Throughput |
|-----------|-----|-----|-----|------------|
| Sequential add | 72ms | 89ms | 97ms | 14.1 ops/s |
| Batch add (5x20) | 216ms | 292ms | 292ms | 4.6 ops/s |
| Concurrent add (c=10) | 100ms | 193ms | 511ms | 85.1 ops/s |
| Sequential query | 282ms | 411ms | 1502ms | 3.8 ops/s |
| Concurrent query (c=10) | 413ms | 1832ms | 1897ms | 18.6 ops/s |
| Cross-agent query | 304ms | 380ms | 380ms | 3.3 ops/s |
| Vote | 64ms | 176ms | 176ms | 14.1 ops/s |
| Deduplication | 75ms | 112ms | 112ms | 13.6 ops/s |

> Query tail latency (p95/p99) is dominated by the external OpenAI embedding call, not Aegis or PostgreSQL. Write and vote operations that skip embedding are consistently under 100ms at p50.

## Deployment

### Docker Compose

```bash
docker compose up -d
```

### Kubernetes

```bash
kubectl apply -f k8s/
```

### Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql+asyncpg://...` | PostgreSQL connection |
| `OPENAI_API_KEY` | — | For embeddings |
| `AEGIS_API_KEY` | `dev-key` | API authentication |
| `CONTENT_POLICY_INJECTION` | `flag` | `reject` / `redact` / `flag` / `allow` |
| `CONTENT_POLICY_SECRETS` | `reject` | `reject` / `redact` / `flag` / `allow` |
| `ENABLE_LLM_INJECTION_CLASSIFIER` | `false` | Enable Stage 4 LLM classifier |
| `INJECTION_CLASSIFIER_MODEL` | `gpt-4o-mini` | Model for injection classification |

**[Full Configuration](https://docs.aegismemory.com/guides/production-deployment)**

## Documentation

**[docs.aegismemory.com](https://docs.aegismemory.com)** — Full documentation

- **[Quickstart](https://docs.aegismemory.com/quickstart/installation)** — Get running in 5 minutes
- **[Security Guide](https://docs.aegismemory.com/guides/security)** — Content security, integrity, trust hierarchy
- **[ACE Patterns](https://docs.aegismemory.com/guides/ace-patterns)** — Self-improving agent patterns
- **[Smart Memory](https://docs.aegismemory.com/guides/smart-memory)** — Zero-config memory extraction
- **[Integrations](https://docs.aegismemory.com/integrations/crewai)** — CrewAI, LangChain guides
- **[CLI Reference](https://docs.aegismemory.com/api-reference/cli)** — Command-line tools

## Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

```bash
# Run tests
pytest tests/ -v

# Run linting
ruff check server/
```

## License

Apache 2.0 — Use it however you want. See [LICENSE](LICENSE).

## Links

- [Documentation](https://docs.aegismemory.com)
- [GitHub Discussions](https://github.com/quantifylabs/aegis-memory/discussions)
- [Issue Tracker](https://github.com/quantifylabs/aegis-memory/issues)
- [Changelog](CHANGELOG.md)

---

Built by engineers who read the [OWASP reports](https://cheatsheetseries.owasp.org/cheatsheets/AI_Agent_Security_Cheat_Sheet.html) and acted on them.

[^echoleak]: EchoLeak: Zero-click exfiltration from M365 Copilot. [arxiv.org/html/2509.10540v1](https://arxiv.org/html/2509.10540v1)
[^crewai]: Multi-agent exfiltration study (COLM 2025). [openreview.net/pdf?id=DAozI4etUp](https://openreview.net/pdf?id=DAozI4etUp)
[^drift]: CVE-2025-32711 zero-click AI vulnerability analysis. [socprime.com/blog/cve-2025-32711-zero-click-ai-vulnerability/](https://socprime.com/blog/cve-2025-32711-zero-click-ai-vulnerability/)
[^owasp-top10]: OWASP Top 10 for Agentic Applications (2026). [genai.owasp.org](https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/)
[^comparison]: Security comparison based on public documentation and open-source repositories as of February 2026. Sources: [mem0 docs](https://docs.mem0.ai/) | [Zep docs](https://help.getzep.com/) | [Letta repo](https://github.com/letta-ai/letta) | [Aegis docs](https://docs.aegismemory.com/)
