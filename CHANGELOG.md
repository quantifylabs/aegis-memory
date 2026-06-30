# Changelog

All notable changes to Aegis Memory will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **`aegis inspect` — LangChain/LangGraph tool-arg source shape.** A tool function's model-supplied
  arguments (a `@tool`-decorated function, or one carrying an `Injected*` runtime param) are now
  treated as untrusted-by-default, mirroring the existing CrewAI `_run` / LangGraph `state` shapes
  (`taint.py` `_is_langchain_tool`). The framework-injected params (`InjectedToolArg`/`InjectedState`/
  `InjectedStore`/`ToolRuntime`/`RunnableConfig`) are excluded. This escalates the canonical
  `upsert_memory(content, …) → store.aput(...)` pattern (e.g. `langchain-ai/memory-agent`) to critical.
- **`aegis inspect` — coverage policy + acceptance corpus.** Added `docs/issues/inspect-coverage-policy.md`:
  a finite source×sink taxonomy, a fixed acceptance corpus (`NirDiamant/Agent_Memory_Techniques`, 30
  notebooks) with a dated, measured baseline (precision 2/2 on flow findings, no critical false
  positives), and a written stop rule so coverage work terminates instead of chasing every repo.
- **`aegis inspect` pre-publish hardening (Claude Code plugin).**
  - **SARIF output** — every run now writes `aegis-out/findings.sarif` (SARIF 2.1.0,
    `aegis_memory/inspect/sarif.py`) so findings drop into GitHub code scanning / CI annotations.
  - **Inline suppression** — an `# aegis: ignore` comment on (or directly above) a sink call drops
    its findings, matched on real comment tokens (never inside a string literal).
  - **Cross-platform guard hook** — the PostToolUse write-path guard is now a Python script
    (`plugins/aegis/hooks/guard.py`, replacing the POSIX-`sh` `guard.sh`), so it runs identically on
    Windows/macOS/Linux without a shell dependency.
  - **PATH-independent CLI** — added `python -m aegis_memory.cli` (`aegis_memory/cli/__main__.py`);
    `/aegis:inspect` falls back to it when the `aegis` console script isn't on `PATH`.
  - **Plugin/marketplace metadata + CI validation** — plugin `keywords`/`homepage`/`icon`, and a
    `scripts/validate_plugin_manifests.py` CI gate that catches malformed manifests / dangling paths
    before publish.

- **Adaptive attack harness for the injection benchmark** (`benchmarks/injection/adaptive/`). Three adaptive attacks that actively try to *evade* the content-security pipeline rather than scoring it on a fixed corpus: (1) **rule-evasion** — AutoDAN-style iterated paraphrase against the free, deterministic Stage 3, headlined by the **Stage-3 → Stage-4 hand-off** (of the Stage-3 evaders produced, what fraction Stage 4 still catches); (2) **classifier-oracle** — a DataSentinel-style detector-evasion loop against the Stage-4 LLM classifier that records *queries-to-evade* and an evasion-vs-budget curve, direct-searching the Aegis Stage-4 systems and *transferring* found samples to baselines; (3) **composition / payload-splitting** — an illustrative, smaller-by-design study of sub-threshold fragments whose assembled text carries intent. Reuses the existing `Dataset` / `System` / `ResponseCache` / `metrics` machinery and the `probe` primitives rather than forking them: **evasion = 1 − recall** comes from the same `bootstrap_cis` (n=1000, seed=42) as the static benchmark. A mandatory cheap-model **intent-preservation judge** (distinct from any Stage-4 classifier) excludes intent-lost candidates from the evasion numerator and reports them rather than silently dropping them. Results are written to a **separate** `adaptive/results/adaptive_results.json` with provenance-rich corpora; the static `results/results.json` is never touched. Network-free regression tests in `tests/test_injection_adaptive.py`. The harness is **smoke-validated end-to-end**; full pre-registered adaptive numbers (N=250/tier, budget=30) are pending a separate, approved billed sweep.

### Fixed

- **`aegis inspect` — bare `.get()`/`.run()` no longer read as network egress.** The call-egress source
  hints are split into *strong* verbs (`fetch`/`read_text`/`invoke`/`complete`/Streamlit widgets — fire
  on any receiver) and *weak* verbs (`get`/`post`/`read`/`load`/`run`/`call` — fire only on a known
  network/IO/tool receiver, matched across the full receiver token set). A plain `config.get(...)` /
  `reflection.get("insight")` / `dict.get(...)` is no longer mistaken for untrusted input. Surfaced by
  the acceptance-corpus run; regressions in `test_plain_dict_get_is_not_an_untrusted_source` and
  `test_network_get_is_still_an_untrusted_source`.
- **`aegis inspect` detection honesty.** Screening is now strictly **sink-tied**: a `scanner.scan(...)`
  of an *unrelated* value no longer marks every write in the function `screened` (the old blanket
  `has_sanitizer_call` scope flag, a false-"screened" — the worst error class for a memory scanner).
  Also tightened two substring heuristics: `_writes_shared_scope` keys off the scope/namespace
  argument (not any string literal, so `key="shared_calendar"` no longer mints an overbroad-shared
  finding), and the provenance read-path check matches identifier tokens instead of dumped AST text
  and now names the real store/framework instead of a hardcoded LangGraph `store.get`.

## [2.6.0] - 2026-06-25

### Added

- **`aegis inspect` — Claude Code plugin and keyless local MCP mode.** Ships the Aegis Claude Code plugin (commands, guard hook, bundled `.mcp.json`) and a local, keyless MCP server mode so `inspect` and the memory write-gate run without provisioning credentials (includes a FastMCP 1.26 compatibility fix).
- **Notebook ingestion + generalized source vocabulary.** `inspect` now ingests Jupyter notebooks (`.ipynb`) and recognizes a broader set of untrusted-input sources, with labeled findings.
- **Inline fix generation and verify-loop.** `inspect` can emit inline fixes for ASI06 flows and re-verify after applying them, with improved score direction and flow-path precision.

### Changed

- **More precise taint analysis.** Receiver+method sink detection, bounded cross-file taint propagation, and constructor-binding recovery for aliased-receiver sinks (FP-gated). Catches additional ASI06 flows while dropping known false positives (e.g. `list.append`).

## [2.5.3] - 2026-06-14

### Fixed

- `AnthropicAdapter` now forwards `temperature` to the Anthropic API in both `complete()` and `complete_sync()`. It was previously stored on the adapter but silently dropped from the `messages.create(...)` call, so the Anthropic path always ran at the API default (~1.0) regardless of the configured value.

### Changed

- Stage-4 injection classifier adapters are now pinned to `temperature=0` for deterministic screening across the server (`/memories/add`, `/security/scan`) and the injection benchmark. Combined with the `AnthropicAdapter` fix above, Stage 4 now runs deterministically.

## [2.5.2] - 2026-06-14

### Security

- Cleared all OpenSSF Scorecard / OSV-Scanner "Vulnerabilities" findings, which are evaluated against the lower bound of every `>=` pin across the repo's non-shipped dev/benchmark/demo manifests (the shipped library was already clean). Bumped `requests>=2.33.0` and `torch>=2.10.0` in `benchmarks/injection/requirements.txt` to clear fixable advisories, and added `osv-scanner.toml` ignore lists for the residual no-fix `torch`/`transformers` advisories and the demo-only `langgraph` advisory (`PYSEC-2026-83`). No shipped (`pip install aegis-memory`) dependency changed; verified `osv-scanner scan source -r .` reports 0 vulnerabilities repo-wide.

### Added

- Release signing: `.github/workflows/release.yml` builds the sdist + wheel on every `v*.*.*` tag, signs them keylessly with Sigstore, and publishes a GitHub Release with the artifacts and their `.sigstore.json` bundles attached — satisfying OpenSSF Scorecard's "Signed-Releases" check.

## [2.5.1] - 2026-06-14

### Changed

- `pyproject.toml`: aligned the wheel's dependency pins with the production server floors (`server/requirements.txt`). The `[server]` extra now carries `pydantic-settings>=2.14.1`, `opentelemetry-api>=1.42.1`, and `opentelemetry-sdk>=1.42.1` (previously only declared for the Docker image), so `pip install aegis-memory[server]` gets the same runtime deps the container does.

### Security

- Carried the OpenSSF Scorecard / OSV transitive security floors into the wheel so `pip install` enforces them too: `idna>=3.16` (via httpx) and `pygments>=2.20.0` (via rich) in core deps, `tqdm>=4.67.3` (via openai) in the `[server]` extra. Previously these floors existed only in `server/requirements.txt`, leaving SDK installs free to resolve known-vulnerable transitive versions.

## [2.5.0] - 2026-06-14

### Added

- **`aegis inspect`** — a static analysis engine that scans an agent project for unsafe memory-write flows (untrusted content reaching durable, agent-shared/global memory) and points each finding at the `guard` fix. Ships with `aegis replay` (replay a built-in memory-poisoning attack) and a generated before/after `agent_memory_map.html` convergence view. Includes a LangGraph memory-poisoning demo under `examples/`.
- **Skill packaging + MCP server** — `aegis install` / `aegis uninstall` package Aegis as a coding-assistant skill, and a new `aegis-mcp` entry point (`aegis_memory.mcp_server`) exposes Aegis over the Model Context Protocol. Adds `mcp>=1.6.0` to core dependencies.
- **`aegis_memory.guard`** — a first-class, framework-agnostic runtime memory **write-gate**, exported from `aegis_memory/__init__.py` (`from aegis_memory import guard`). This makes the remediation `aegis inspect` recommends *real*: previously the suggested fix `from aegis_memory import guard; guard.write(...)` referenced a `guard` that did not exist (an `ImportError` waiting to happen).
  - `guard.write(content, *, trust_level, scope, require_classifier=False, metadata=None, on_reject="raise") -> WriteVerdict` — screens one value and returns a `WriteVerdict` (`allowed`, `action`, possibly-redacted `content`, `detections`, `flags`, `reason`). Fail-closed by default (`on_reject="raise"` → `WriteBlocked`); `on_reject="return"` returns the verdict.
  - `guard.protect(store, *, value_key="text", trust_level, scope, on_reject="drop") -> GuardedStore` — wraps **any** store and screens every catalogued write idiom (`put`/`aput`/`add`/`upsert`/`add_texts`/`add_documents`/`save`/… across LangGraph, vector DBs, and custom stores), sync or async. Generalizes the demo's single-method `AegisGuardedStore`. Drops + records rejected writes on `.blocked` (or raises).
  - Adds **no detection logic of its own** — composes the one benchmark-validated `ContentSecurityScanner` (via `aegis_memory.inspect._scanner_bridge.get_scanner`, the same engine + reject-injection/secrets policy the server runs) with a small content-trust + scope policy.
- `tests/test_guard.py` — 12 offline tests covering injection/secrets reject, benign allow, the scope policy matrix, the `protect` wrapper across `put`/`add`/`save` (drop + raise modes), and that the exact inspect fix-string now imports and runs.

### Changed

- `aegis_memory/inspect/analyzer.py`: the recommended-fix string findings carry now references the real shipped API — both `guard.protect(store, scope='agent-shared')` (wrap the sink) and `guard.write(content, trust_level='untrusted', scope='agent-shared')` (screen one value).
- `aegis_memory/inspect/sinks.py`: extracted the per-framework write-method names into shared `WRITE_METHODS` / `KEYED_WRITE_METHODS` constants reused by `guard.protect`, so static detection and runtime enforcement key off the same idioms and never drift.
- `examples/aegis-memory-firewall/_demo_common.py`: `AegisGuardedStore` is now a thin shim over `guard.GuardedStore` (the shipped API) instead of bespoke example code; the demo invariants are unchanged (`run_with_aegis.py` → `DENIED`, `run_without_aegis.py` → `APPROVED`).
- `pyproject.toml` + `aegis_memory/__init__.py`: 2.4.0 → 2.5.0.
- README: surface `aegis inspect` + `aegis_memory.guard` in the hero block, and embed the multi-agent write-boundary diagram (`.github/mas_write_boundary_chokepoint.svg`) under "Guard every write (the firewall)".

### Fixed

- **`trust_level` resolved on the write path** — memory writes now resolve the real `trust_level` instead of a default, so content-trust policy is applied correctly at persistence time.
- **Production server image startup** — `server/content_security.py` is self-contained again (the four-stage pipeline lives in both `server/content_security.py` and the wheel's `aegis_memory/security/content_security.py`). The server image, built from `context: ./server`, no longer raises `ModuleNotFoundError: No module named 'aegis_memory'` at API startup. A new drift-guard test (`tests/test_content_security_no_drift.py`) keeps the two copies byte-identical.

### Security

- **Content trust ≠ agent trust.** `guard`'s `trust_level` labels the *content's provenance* (distinct from the server's `TrustPolicy`, which governs which *agent* may call the API). The gate always scans, blocks prompt-injection/secrets, flags PII, and additionally refuses to let `untrusted`/`unknown` content be written straight to `global` scope (every agent reads global; promotion there needs a privileged path). Screened-clean content is allowed into `agent-private` / `agent-shared` — screening *before* sharing is the point.
- Untrusted content reaching `agent-shared` / `global` is now blockable at the write boundary in **local / in-process** mode (previously enforcement existed only at the server HTTP boundary).

## [2.4.0] - 2026-05-16

### Added

- **Memory Depth** — three retrieval-and-lifecycle primitives that close the most-cited gaps vs mem0 / Zep / Letta. Each phase is independently shippable; this release lands all three together.
  - **Hybrid retrieval** (`POST /memories/hybrid_query`) — two-channel retrieval combining the existing pgvector HNSW cosine search with a new PostgreSQL `tsvector` + GIN sparse channel. Results fused with Reciprocal Rank Fusion (Cormack et al. 2009, k=60 default). Equal channel weighting by default; integer `dense_weight` / `sparse_weight` knobs available. Catches exact-token cases (entity names, error codes, file paths) that pure embedding similarity blurs.
  - **Memory graph + contradiction detection** — new `memory_edges` table with six typed edge types: `supersedes`, `contradicts`, `generalizes`, `elaborates`, `derives_from`, `entity_rel`. New `ContradictionDetector` (`server/contradiction_detector.py`) uses a two-stage strategy: cheap (cosine similarity ≥ 0.80 AND negation/opposition regex match) by default, with an optional `ContradictionLLM` adapter for stage-2 confirmation. Explicit resolution workflow with five states: `unresolved`, `kept_source`, `kept_target`, `both_valid`, `both_invalid`. New endpoints `POST /memories/contradictions/scan`, `GET /memories/contradictions/`, `GET /memories/contradictions/metrics` (the Simulation Reliability Index signal), `POST /memories/edges/`, `POST /memories/edges/{id}/resolve`, `GET /memories/edges/for-memory/{id}`.
  - **Semantic consolidation** (`POST /memories/ace/consolidate`) — replaces the legacy 50-character prefix-match heuristic. New `SemanticConsolidator` (`server/consolidation.py`) finds embedding-pair candidates above a `similarity_threshold` (default 0.92), then merges via heuristic (keep higher effectiveness score) or optional LLM adapter. Audit-preserving by design: losing memories are marked `is_deprecated=True` with `metadata.consolidated_into` pointing at the keeper, not deleted. Defaults to `dry_run=True` — caller explicitly opts into application.
- New ORM class: `MemoryEdge` in `server/models.py` with composite indexes (`ix_edges_source`, `ix_edges_target`, `ix_edges_type_resolution`, unique `ix_edges_pair_unique`)
- New module: `server/hybrid_retrieval.py` (`HybridRetriever`, `reciprocal_rank_fusion`)
- New module: `server/memory_graph.py` (`MemoryGraphRepository`, `EdgeType`, `EdgeResolution` enums)
- New module: `server/contradiction_detector.py` (`ContradictionDetector` with `ContradictionLLM` Protocol)
- New module: `server/consolidation.py` (`SemanticConsolidator` with `ConsolidationLLM` Protocol)
- New routers: `server/api/routers/memory_edges.py`, `server/api/routers/contradictions.py`
- Repository method: `MemoryRepository.hybrid_search` with ACL filtering that mirrors `semantic_search` behavior and optional decay rerank
- Generated column: `Memory.content_tsv` (`GENERATED ALWAYS AS to_tsvector('english', content) STORED`) with GIN index `ix_memories_content_tsv`; same on `interaction_events` with `ix_events_content_tsv`
- Alembic migration `0009_memory_depth` — tsvector columns + GIN indexes + `memory_edges` table
- 4 new `MemoryEventType` entries: `CONTRADICTION_DETECTED`, `EDGE_CREATED`, `EDGE_RESOLVED`, `MEMORIES_CONSOLIDATED` (all routed through `EventRepository.create_event` for audit logging)
- SDK methods on `AegisClient`: `hybrid_query`, `scan_contradictions`, `list_contradictions`, `contradiction_metrics`, `create_edge`, `resolve_edge`, `get_edges_for_memory`, `consolidate_memories`
- Integration tests in `tests/test_memory_depth.py` — 30 standalone unit checks (schema, RRF math, regex, cosine, router wiring, migration, SDK surface) plus 4 end-to-end tests (hybrid exact-token, contradiction scan, SRI metrics, consolidation dry-run)
- New test fixture `async_client` in `tests/conftest.py` — spins up the FastAPI app via `httpx.ASGITransport`, against a real PostgreSQL test database (`aegis_test`). Resets schema per session, truncates tables per test. Patches the engine to use `NullPool` (avoids cross-event-loop crashes under pytest-asyncio) and `embedding_service.get_embedding_service` to a deterministic fake (uses `sentence-transformers/all-MiniLM-L6-v2` if available, char-ngram hashing trick otherwise). Skips cleanly if Postgres isn't reachable.

### Changed

- `pyproject.toml`: 2.3.0 → 2.4.0
- `aegis_memory/__init__.py`: `__version__` 2.2.0 → 2.4.0
- README:
  - New "Memory Depth (v2.4.0)" section after the Context Hub block
  - "Quick Feature Comparison" table extended with three new rows (hybrid retrieval, contradiction detection, semantic consolidation) — and honest framing that mem0/Zep/Letta ship variants of these too; Aegis differs on audit-preservation, explicit resolution workflow, and OSS-first posture
  - "When to Pick Aegis" extended with three new bullets matching the new capabilities
  - New `[^memory-depth-sources]` footnote citing mem0/Zep/Letta primary sources used to write the comparison
- `server/api/app.py`: mounts 2 new routers under `/memories/edges` and `/memories/contradictions`
- `server/api/routers/ace_curation.py`: imports `HTTPException`, adds `ConsolidateRequest` model and `/consolidate` endpoint (the legacy 50-char prefix matcher in `ACERepository.curate` is left in place as a cheap read-only health report)
- `tests/test_ace_loop.py` + `tests/test_interaction_events.py`: updated stale `len(MemoryEventType) == 16` to 24 (16 baseline + 4 Context Hub + 4 Memory Depth) and stale `__version__ == "2.1.0"` to `"2.4.0"`. These assertions were already drifted before v2.4.0 — fixed during this release.

### Security

- All new edges and consolidation events flow through `EventRepository.create_event` for the immutable audit trail (`memory_events` table)
- Consolidation is audit-preserving: losing memories remain queryable with `is_deprecated=True` and `metadata.consolidated_into` — no destructive DELETE of facts in flight
- Contradiction resolution requires an explicit caller-supplied state (`kept_source`, `kept_target`, `both_valid`, `both_invalid`) — the system never silently invalidates conflicting memories
- `hybrid_search` enforces the same scope-aware access control as `semantic_search`: global-only when no `requesting_agent_id` is provided, otherwise full agent-private / agent-shared / global ACL filter (mirrors the `Memory.can_access` logic)

## [2.3.0] - 2026-05-15

### Added

- **Context Hub** — Aegis is now a full context hub, not just a memory layer. Three new artifact types plus a unifying load endpoint:
  - **Versioned Prompts** (`/prompts/*`) — multiple versions per name, exactly one active per `(project_id, namespace, name)`. Auto-extracts `{{variable}}` names. HMAC-signed, content-scanned, trust-gated.
  - **Skills** (`/skills/*`) — follows Anthropic's open Agent Skills spec. SKILL.md body + optional bundled files (scripts, references). Description is embedded for semantic activation matching (HNSW index). Default `trust_level=privileged` because skills can ship executable code.
  - **Subagents** (`/subagents/*`) — declarative delegation surface: name, description, model, allowed tools, allowed memory scopes, allowed skills, parent agent. Requires either inline `system_prompt` or `system_prompt_ref` to a versioned Prompt.
  - **`POST /context/load`** — the unifying call. Returns prompt + ranked memories + matched skills + available subagents in a single token-budgeted, integrity-verified bundle. Configurable budget split (defaults: 15% prompt / 55% memories / 25% skills / 5% subagents).
- New ORM classes: `Prompt`, `Skill`, `Subagent` in `server/models.py`
- New repositories: `PromptRepository`, `SkillRepository`, `SubagentRepository` (static async methods, repository pattern)
- New service: `ContextBundleService` in `server/context_bundle.py` — token-budgeted assembly across all four artifact types
- Alembic migration `0008_context_hub` — single transactional unit, includes HNSW index on skill description embeddings
- 4 new `MemoryEventType` entries: `PROMPT_CREATED`, `SKILL_CREATED`, `SUBAGENT_CREATED`, `CONTEXT_LOADED` (all written through `EventRepository.create_event` for audit logging)
- SDK methods on `AegisClient` and `AsyncAegisClient`: `create_prompt`, `get_prompt`, `list_prompt_versions`, `activate_prompt_version`, `create_skill`, `list_skills`, `get_skill`, `match_skills`, `create_subagent`, `list_subagents`, `load_context`
- Integration tests in `tests/test_context_hub.py` (prompt versioning, skill semantic match, subagent contract, full bundle assembly)

### Changed

- `pyproject.toml`: 2.2.0 → 2.3.0
- README: new "The Context Hub" section before the security comparison table
- `server/api/app.py`: mounts 4 new routers under `/prompts`, `/skills`, `/subagents`, `/context`

### Security

- All four artifact types pass through the existing 4-stage content security pipeline
- HMAC-SHA256 integrity hashes computed at create time, verified during `/context/load` assembly
- `Skill` defaults to `trust_level=privileged`; `Subagent` and `Prompt` default to `internal`
- Bundled skill files (`scripts/*`, `references/*`) are not run through the prompt-injection regex (false positives on legitimate code) — only the description + SKILL.md body are scanned

## [2.1.0] - 2026-03-01

### Added

- **LLM-Based Injection Classifier (Stage 4)** — optional async LLM classifier for prompt injection detection
  - `InjectionClassifier` class in `content_security.py` wrapping any `LLMAdapter` (OpenAI or Anthropic)
  - `scan_async()` method on `ContentSecurityScanner` — runs Stages 1-3, then conditionally triggers Stage 4
  - Trigger conditions: untrusted/unknown trust level, agent-shared/global scope, or regex-flagged content
  - Tiered escalation: confidence >= 0.8 → REJECT, threshold <= confidence < 0.8 → flag only
  - Graceful degradation: LLM errors fall back to regex-only verdict
  - 5 new config settings: `ENABLE_LLM_INJECTION_CLASSIFIER`, `INJECTION_CLASSIFIER_PROVIDER`, `INJECTION_CLASSIFIER_MODEL`, `INJECTION_CLASSIFIER_API_KEY`, `INJECTION_CLASSIFIER_CONFIDENCE_THRESHOLD`
  - `llm_classifier_enabled` field on `/security/config` response
  - `llm_checked` field on SDK `ContentScanResult`
  - Security scanning added to `/memories/add_batch` (was missing)
  - 9 new tests in `TestLLMInjectionClassifier`

### Changed

- `/memories/add` now uses `scan_async()` with trust/scope context
- `/security/scan` now uses `scan_async()` with `trust_level="system"`, `scope="global"`
- Content security pipeline docs updated from "three-stage" to "four-stage"

### Repositioned

- Aegis Memory is now positioned as **Secure Context Engineering for AI Agents**
- Memory remains a core capability; security, integrity, trust, and compliance lead the narrative
- Updated README, docs, pyproject.toml, and all public-facing copy
- GitHub description and topics updated for context engineering positioning

## [2.0.0] - 2026-02-25

### Added

- **Content Security Layer** — three-stage pipeline for all memory writes:
  - Input validation: content length (50k default), metadata depth (5), encoding checks
  - Sensitive data scanner: SSN, credit card, API key, email, password detection
  - Prompt injection detector: system override, role manipulation, exfiltration triggers
  - Configurable policy per detection: reject, redact, flag, or allow
- **Memory Integrity (HMAC-SHA256)** — tamper detection on store, verification on demand
  - `POST /security/verify/{memory_id}` endpoint
  - `integrity_hash` column on memories table
- **Agent Trust Hierarchy** — OWASP 4-tier model (untrusted/internal/privileged/system)
  - Trust-based operation restrictions (write scope, read scope, delete, admin)
  - Agent identity binding via API key `bound_agent_id`
- **Per-Agent Rate Limiting** — separate sliding window per `project_id:agent_id`
  - Configurable: `PER_AGENT_RATE_LIMIT_PER_MINUTE` (30), `PER_AGENT_RATE_LIMIT_PER_HOUR` (500)
- **Agent Memory Quota** — configurable max memories per agent (default: 10,000)
- **Security Admin Endpoints** under `/security/`:
  - `GET /audit` — security event audit trail
  - `GET /flagged` — memories with content security flags
  - `POST /verify/{memory_id}` — integrity verification
  - `GET /config` — current security settings
  - `POST /scan` — dry-run content scan
- **Audit Hardening** — events for auth failures, content rejections, deletions, integrity failures, agent binding violations
- **SDK methods**: `scan_content()`, `verify_integrity()`, `get_flagged_memories()`, `get_security_audit()`, `get_security_config()`
- **Alembic migration** `0007_content_security`
- **Test suite**: `tests/test_content_security.py` (~80 tests)
- **Docs**: `docs/guides/security.mdx`, updated concepts, positioning, deployment guide

### Changed

- Tagline: "The Memory Layer" -> "The Secure Memory Layer for Multi-Agent AI"
- `MemoryOut` response includes `content_flags` and `trust_level`
- `Memory` SDK dataclass includes `content_flags`, `trust_level`, `integrity_valid`
- Content max length tightened from 100,000 to 50,000 (configurable via `CONTENT_MAX_LENGTH`)
- Legacy single-key auth now logs deprecation warning
- Version bumped to 2.0.0

### Security

- Closes CRITICAL: Memory content security (zero validation -> 3-stage pipeline)
- Closes CRITICAL: Prompt injection vector (detection + flag/reject)
- Closes CRITICAL: Data integrity (HMAC signing + verification)
- Closes HIGH: Agent ID spoofing (API key binding)
- Closes HIGH: Authorization granularity (trust levels + per-operation checks)
- Closes MODERATE: Input validation (content security pipeline)
- Closes MODERATE: Rate limiting per-agent (separate sliding window)
- Closes MODERATE: Audit trail gaps (security events, deletion logs)
- Closes LOW: CORS documentation + production warning
- Closes LOW: Legacy auth deprecation notice

## [1.9.2] - 2026-02-22

### Added

- **Temporal Decay for Memory Relevance** — memories that aren't reused lose relevance over time (Priority 4)
  - `last_accessed_at` (nullable timestamptz) and `access_count` (integer, default 0) columns on `memories` table
  - Partial index `ix_memories_last_accessed` on `(project_id, last_accessed_at)` for efficient decay queries
  - `server/temporal_decay.py` — decay engine with configurable half-lives per memory type:
    - episodic: 7 days · progress/feature: 14 days · standard: 30 days · reflection: 60 days
    - strategy/semantic: 90 days · procedural/control: 180 days
  - Decay formula: `decay_factor = exp(-λ × age_days)` where `age_days` uses `last_accessed_at` falling back to `created_at`
  - `relevance_score` response field on `MemoryOut`/`TypedMemoryOut`: `effectiveness_score × decay_factor` (roadmap formula)
  - `apply_decay: bool = False` on `/memories/query`, `/memories/query_cross_agent`, `/memories/typed/query`
    — when `True`, re-ranks results by `semantic_score × decay_factor` before returning
  - Access tracking: every `/query` call bulk-updates `last_accessed_at` and increments `access_count` for returned memories
  - **2 new endpoints** under `/memories/decay/`:
    - `GET /config` — returns half-life table and formula description
    - `POST /archive` — soft-deprecates memories below a configurable relevance threshold (default 0.1), supports `dry_run`
  - **SDK**: `apply_decay=False` param on `query()` and `query_cross_agent()`
  - **Alembic migration** `0006_temporal_decay` (down_revision="0005")
  - **Test suite**: `tests/test_temporal_decay.py` (~35 tests across 8 classes)
  - **Docs**: `docs/guides/temporal-decay.mdx`

### Changed

- `MemoryOut` and `TypedMemoryOut` response models extended with `relevance_score: float | None`
- `MemoryQuery`, `CrossAgentQuery`, `TypedQuery` accept optional `apply_decay: bool = False`
- Version bumped to `1.9.2`

## [1.9.11] - 2026-02-21

### Added

- **Interaction Events** — lightweight multi-agent collaboration history (Priority 3)
  - `interaction_events` table with temporal + causal chain support
  - `POST /interaction-events/` — create event (201); optional `embed=True` for semantic search
  - `GET /interaction-events/session/{session_id}` — session timeline ordered ASC
  - `GET /interaction-events/agent/{agent_id}` — agent history ordered DESC
  - `POST /interaction-events/search` — embed query → cosine similarity search
  - `GET /interaction-events/{event_id}` — event + full causal chain (root → leaf)
  - Two composite B-tree indexes: `(project_id, session_id, timestamp)` and `(project_id, agent_id, timestamp)`
  - Partial index on `parent_event_id` for causal chain traversal
  - HNSW index on `embedding` for vector search (pgvector >= 0.5.0, skips NULLs automatically)
  - `INTERACTION_CREATED = "interaction_created"` added to `MemoryEventType` enum (now 11 members)
  - **SDK methods** (sync + async): `record_interaction()`, `get_session_interactions()`, `get_agent_interactions()`, `search_interactions()`, `get_interaction_chain()`
  - **Alembic migration** `0005_interaction_events` (down_revision="0004")
  - **Test suite**: `tests/test_interaction_events.py` (~400 lines, 10 test classes)
  - **Docs**: `docs/guides/interaction-events.mdx`

## [1.9.1] - 2026-02-20

### Added

- **Formalized ACE Loop** -- full Generation -> Reflection -> Curation cycle as native memory operations
  - `ace_runs` table for tracking agent execution runs with outcomes
  - `POST /ace/run` -- start tracking an agent run
  - `POST /ace/run/{run_id}/complete` -- complete run with auto-feedback:
    - Auto-votes memories used (helpful on success, harmful on failure)
    - Auto-creates reflection memories on failure
    - Links run results to playbook entries
  - `GET /ace/run/{run_id}` -- retrieve run details
  - `POST /ace/playbook/agent` -- agent-specific playbook retrieval with optional task_type filter
  - `POST /ace/curate` -- trigger curation cycle (identify effective, flag ineffective, suggest consolidations)
- **SDK methods**: `start_run()`, `complete_run()`, `get_run()`, `get_playbook_for_agent()`, `curate()`
- **Alembic migration** `0004_ace_runs`
- **Test suite**: `tests/test_ace_loop.py`

### Changed

- Version bumped to `1.9.1`

## [1.9.0] - 2026-02-14

### Added

- **Typed Memory API** — 4 cognitive memory types inspired by research SOTA systems (MIRIX, G-Memory, BMAM):
  - `episodic` — Time-ordered interaction traces linked to sessions
  - `semantic` — Facts, preferences, knowledge linked to entities
  - `procedural` — Workflows, strategies, reusable patterns
  - `control` — Meta-rules, error patterns, constraints
- **7 new API endpoints** under `/memories/typed/`:
  - `POST /memories/typed/episodic` — Store episodic memory
  - `POST /memories/typed/semantic` — Store semantic memory
  - `POST /memories/typed/procedural` — Store procedural memory
  - `POST /memories/typed/control` — Store control memory
  - `POST /memories/typed/query` — Type-filtered semantic search
  - `GET /memories/typed/episodic/session/{session_id}` — Session timeline
  - `GET /memories/typed/semantic/entity/{entity_id}` — Entity facts
- **3 new indexed columns** on Memory table: `session_id`, `entity_id`, `sequence_number`
- **2 partial indexes**: `ix_memories_session`, `ix_memories_entity`
- **Alembic migration** `0003_typed_memory` (upgrade + downgrade)
- **Repository methods**: `get_session_timeline()`, `get_entity_facts()`
- **Test suite**: `tests/test_typed_memory.py`

### Changed

- `MemoryOut` response model extended with `memory_type`, `session_id`, `entity_id`, `sequence_number` fields (both modular and legacy routes)
- `MemoryQuery` now accepts optional `memory_types` filter list
- `memory_type` column widened from `String(16)` to `String(32)` for extensibility
- Version bumped to `1.9.0`

## [1.8.0] - 2026-02-14

### Added

- **`RateLimiterProtocol`** (`runtime_checkable`) -- shared interface for all rate limiter implementations with `check()` and `get_remaining()` methods
- **`get_remaining()`** on `RedisRateLimiter` -- synchronous approximation + async-precise variant (`get_remaining_async()`)
- **`create_rate_limiter()` factory** -- auto-detects Redis from `REDIS_URL`, falls back to in-memory
- **`X-RateLimit-*` response headers** on every API response:
  - `X-RateLimit-Limit-Minute`, `X-RateLimit-Remaining-Minute`
  - `X-RateLimit-Limit-Hour`, `X-RateLimit-Remaining-Hour`
- **Reproducible benchmark harness** (`benchmarks/`):
  - `generate_dataset.py` -- seeded JSONL dataset generator
  - `query_workload.py` -- async workload runner with latency percentiles
  - `run_benchmark.sh` -- end-to-end benchmark script
  - `machine_profile.py` -- capture hardware profile for reproducibility
- Rate limiter test suite (`tests/test_rate_limiter_unified.py`) -- protocol conformance, factory, headers
- Version test suite (`tests/test_version.py`) -- checks no hardcoded version strings remain
- **Baseline benchmark results** (`benchmarks/results.json`) -- 1060 ops, 0% error rate on 8 vCPU / 7.6 GB RAM; concurrent writes at 85 ops/s (p50=100ms), concurrent queries at 18.6 ops/s (p50=413ms)
- README Performance section updated with actual benchmark data, replacing provisional numbers

### Changed

- **Version synchronized from `pyproject.toml`** via `importlib.metadata.version("aegis-memory")` with `"dev"` fallback
- Removed all hardcoded `"1.2.0"` version strings from `main.py` and `api/app.py`

## [1.7.0] - 2026-02-14

### Added

- **Modular application structure** -- decomposed into `api/`, `domain/`, `infra/` bounded contexts
  - `api/app.py` -- new modular FastAPI entry point via `create_app()`
  - `api/routers/` -- 9 focused routers (memories, handoffs, ace_votes, ace_delta, ace_reflections, ace_progress, ace_features, ace_eval, dashboard), each under 300 lines
  - `api/dependencies/` -- shared auth, rate_limit, and database dependencies
- **Domain layer** (`domain/`) with service, repository, and model modules for memory, ACE, events, and eval
- **Infrastructure layer** (`infra/`) with adapters for DB, embeddings, observability, auth, and config
- `KeyStore` class (`infra/auth/key_store.py`) for API key management

### Changed

- **Unified transaction boundaries** -- all `await db.commit()` calls removed from `ace_repository.py`; commit/rollback now handled exclusively by the `get_db()` FastAPI dependency
- Original `main.py`, `routes.py`, `routes_ace.py` retained as backward-compatible entry points
- `api/app.py` version bumped to `1.7.0`

## [1.6.0] - 2026-02-14

### Added

- **Normalized `memory_shared_agents` join table** for scalable ACL lookups
  - `MemorySharedAgent` ORM model with composite PK (`memory_id`, `shared_agent_id`)
  - Indexes: `ix_msa_memory_agent` (unique), `ix_msa_query` (project + namespace + agent)
  - Alembic migration `0002_memory_shared_agents`
- **Dual-write** on `add()` and `add_batch()` -- populates both JSON and join table
- **Backfill script** (`server/backfill_acl.py`) -- idempotent migration from JSON to join table
- ACL test suite (`tests/test_acl.py`) covering dual-write, join-based read, backfill, cascade

### Changed

- `semantic_search` ACL now uses indexed join-table subquery instead of JSONB `@>` containment
- `query_playbook` ACL switched from JSONB containment to join-table subquery
- `shared_with_agents` JSON column retained for backward compatibility but no longer read for ACL decisions

## [1.5.0] - 2026-02-14

### Added

- **Alembic as canonical schema source** -- deterministic schema lifecycle
  - `alembic.ini`, `alembic/env.py` with async migration support
  - Baseline migration `0001_baseline.py` capturing full v1.3.0+ schema
  - `script.py.mako` template for new migrations
- `Makefile` with `db-upgrade`, `db-downgrade`, `db-migrate`, `db-check` targets
- CI workflow `.github/workflows/migration-check.yml` for migration round-trip testing
- Migration test suite (`tests/test_migrations.py`)

### Changed

- `init_db()` is now environment-aware:
  - `AEGIS_ENV=development` (default): uses `create_all()` as before
  - `AEGIS_ENV=production`: verifies `alembic_version` table exists; fails fast if not
- `alembic>=1.13.0` added to `[server]` dependencies in `pyproject.toml`

### Removed

- `INIT_SQL` and `MIGRATION_SQL_V1_1` raw SQL constants from `models.py` (schema now managed by Alembic)

## [1.4.0] - 2026-02-14

### Added

- **Project-scoped API key authentication** behind `ENABLE_PROJECT_AUTH` feature flag
  - `Project` and `ApiKey` ORM models for multi-tenant isolation
  - `TokenVerifier` for bearer token validation (legacy + project key modes)
  - `AuthPolicy` with `can_write_memory()` and `can_query_memory()` checks
  - SHA-256 key hashing for secure storage
  - Key expiration and active/inactive status support
  - Audit logging for every authentication decision
- `ENABLE_PROJECT_AUTH` config flag (default: `false`) -- zero behavior change when off
- `AEGIS_ENV` config flag (`development` | `production`) for environment-aware behavior
- Migration `004_project_auth.sql` with `projects` and `api_keys` tables + default project seed
- Auth test suite (`tests/test_auth.py`) covering legacy fallback, project keys, policy, audit

### Changed

- `get_project_id` dependency extracted from `routes.py` into `server/auth.py`
- `routes.py` and `routes_ace.py` import auth from centralized module

### Added (Unreleased)

- CLI onboarding and productivity commands:
  - `aegis init` top-level setup wizard with lightweight framework detection (LangChain/CrewAI) and config bootstrap
  - `aegis new customer-support` starter template scaffold
  - `aegis explore` interactive memory browser for terminal workflows
- New observability guide with architecture and phased plan for memory analytics, Prometheus expansion, memory timeline events, effectiveness dashboards, and Langfuse/LangSmith exports (`docs/guides/observability.mdx`).

### Changed

- CLI command module wiring updated so top-level `init`, `new`, and `explore` commands load correctly.
- CLI error utilities now include `set_debug_mode()` used by the Typer entrypoint.
- CLI reference docs now document `aegis init`, `aegis new`, and `aegis explore`.
- README now highlights observability surfaces (metrics, evaluation, dashboard APIs) and links directly to the new observability guide.


## [1.3.0] - 2026-02-06

### Added

- **`aegis init` wizard** — Zero-config setup with framework auto-detection
  - Detects LangChain, CrewAI, or vanilla Python projects
  - Generates starter code and `.env` file
  - 4-step interactive wizard (or `--non-interactive` mode)

- **Memory Explorer CLI** — Interactive debugging with `aegis explore`
  - Full TUI with keyboard shortcuts (j/k/Enter/d/h/x for navigate/view/delete/vote)
  - Filter by namespace, agent, memory type
  - Search memories semantically
  - Fallback table view for simple terminals

- **Auto-instrumentation for LangChain and CrewAI**
  - Framework detection in `cli/utils/detection.py`
  - Scans pyproject.toml, requirements.txt, and Python imports

- **5 starter templates** via `aegis new <template>`
  - `customer-support` — Support agent with preferences and resolution tracking
  - `research-agent` — Research accumulator with findings and sources
  - `coding-assistant` — Code helper with playbook and reflections
  - `multi-agent-crew` — CrewAI-style multi-agent system with shared memory

- **Client `export_json()` method** — Export memories directly to a JSON file from the SDK
  - Supports namespace, agent_id, and limit filters
  - Optional embedding inclusion
  - Returns export stats (total exported, namespaces, agents)

- **Troubleshooting section in README** — Common issues and fixes

### Improved

- **Error messages now explain what went wrong AND how to fix it**
  - New `ConfigurationError` and `CommandNotFoundError` classes
  - `did_you_mean` suggestions via fuzzy matching
  - `related_docs` links to relevant documentation
  - `--debug` flag shows full stack traces

- **40% faster cold start time** — Optimized imports and lazy loading

- **Dependency versions bumped** to latest stable releases:
  - Core: httpx >=0.28.0, typer >=0.15.0, rich >=14.0.0, pyyaml >=6.0.2, textual >=0.50.0
  - Server: fastapi >=0.115.0, uvicorn >=0.34.0, sqlalchemy >=2.0.40, asyncpg >=0.30.0
  - Integrations: langchain >=0.3.0, crewai >=0.86.0

### Fixed

- **Critical SDK Fixes**
  - `smart.py`: Fixed `client.add(memory_type=...)` TypeError - `memory_type` now passed via metadata dict
  - `langchain.py`: Fixed `result["id"]` AttributeError - AddResult is a dataclass, use `result.id`
  - `crewai.py`: Fixed multiple issues with method names and result handling

- **Server Transaction & Data Integrity Fixes**
  - `embedding_service.py`: Added missing `await db.commit()` after cache insert
  - `ace_repository.py`: Fixed vote race condition with atomic SQL UPDATE
  - Fixed SQLAlchemy negation (`not_(col)` instead of `not col`)

- **CLI Fixes**
  - `memory.py`: `--type` option now properly stores `memory_type` in metadata
  - `export_import.py`: Fixed swapped agent/namespace labels in dry-run output

## [1.2.2] - 2025-12-28

### Added

- **Smart Memory** - Intelligent extraction layer that automatically decides what's worth remembering
  - `SmartMemory` class - Two-stage filter → LLM pipeline for automatic memory extraction
  - `SmartAgent` class - Full-auto agent with built-in memory (zero config)
  - Pre-built extraction profiles: conversational, task, coding, research, creative, support
  - Rule-based pre-filter saves ~70% of LLM extraction costs
  - Support for OpenAI and Anthropic as extraction LLMs

- **CLI with Interactive Demo**
  - `aegis demo` - 60-second narrative demo showing core value in 5 acts
  - `aegis demo --log` - Save demo output to `demo.log` for sharing
  - `aegis health` - Check server health
  - `aegis version` - Show version info

- **Enhanced Framework Integrations**
  - `AegisSmartMemory` for LangChain - Smart extraction built into the memory interface
  - Automatic noise filtering (greetings, confirmations filtered out)
  - Context retrieval with `get_context()` for prompt injection

- **New Extraction Components** (for customization)
  - `MessageFilter` - Fast rule-based pre-filtering
  - `MemoryExtractor` - LLM-based extraction with customizable prompts
  - `ExtractionPrompts` - Pre-built prompts for different use cases
  - `OpenAIAdapter`, `AnthropicAdapter`, `CustomLLMAdapter` - LLM adapters

- **Documentation**
  - [Smart Memory Guide](docs/SMART-MEMORY.md) - Comprehensive guide for smart extraction
  - Comparison table with mem0 and Supermemory (when to choose what)
  - Updated README with demo instructions

### Changed

- SDK version bumped to 1.2.2
- Added `click` as core dependency for CLI
- New optional dependencies: `smart` (OpenAI), `smart-anthropic` (Anthropic)

### Fixed

- Framework integrations now properly handle async context

## [1.1.0] - 2025-01-XX

### Added

- **ACE Patterns** - Agentic Context Engineering primitives
  - Memory voting (`/ace/vote/{id}`) - Track helpful/harmful feedback
  - Delta updates (`/ace/delta`) - Incremental context modification
  - Reflection memories (`/ace/reflection`) - Store insights from failures
  - Session progress (`/ace/session`) - Track work across context windows
  - Feature tracking (`/ace/feature`) - Prevent premature task completion
  - Playbook queries (`/ace/playbook`) - Query strategies by effectiveness

- **Framework Integrations**
  - LangChain memory and vector store adapters
  - LangGraph checkpointer and memory tools
  - CrewAI crew and agent memory

- **Observability**
  - Prometheus metrics endpoint (`/metrics`)
  - Structured JSON logging
  - Request tracing with correlation IDs

- **Data Export**
  - Export endpoint (`/memories/export`) for JSONL/JSON export
  - GDPR data portability support
  - No proprietary formats

- **Operations**
  - Backup/restore documentation
  - Kubernetes health probes
  - Migration guides

### Changed

- Improved OpenAPI documentation with examples
- Better error messages with structured responses
- Enhanced rate limiting with sliding window

### Fixed

- Connection pool exhaustion under high load
- Memory not appearing after add (index sync issue)

## [1.0.0] - 2024-XX-XX

### Added

- **Core Memory Operations**
  - Semantic search with pgvector HNSW index
  - Scope-aware access control (agent-private, agent-shared, global)
  - Multi-agent handoffs
  - Auto-deduplication via content hash

- **Production Features**
  - Async FastAPI with SQLAlchemy 2.0
  - Connection pooling with asyncpg
  - Embedding caching (in-memory + database)
  - Rate limiting per project
  - TTL support with pre-computed expiration

- **Performance**
  - O(log n) vector search vs O(n) in naive implementation
  - Batched embedding API calls
  - Composite indexes for common query patterns

### Performance Benchmarks

| Operation | v0 (naive) | v1.0 | Improvement |
|-----------|------------|------|-------------|
| Query 1M memories | 5-10s | 30-80ms | 100x |
| Batch insert (50) | 10s | 300ms | 30x |
| Deduplication | 200ms | 1ms | 200x |

## [0.1.0] - 2024-XX-XX

### Added

- Initial prototype
- Basic CRUD operations
- Simple vector similarity search

---

## Upgrade Notes

### 1.9.11 → 1.9.2

1. Run the Alembic migration:
   ```bash
   alembic upgrade 0006
   ```
   Adds `last_accessed_at` and `access_count` columns to the `memories` table. Zero downtime — both columns are nullable/default-zero.

2. No SDK changes required — `apply_decay` defaults to `False`, so existing query calls are unaffected.

3. To enable decay-aware ranking in queries:
   ```python
   memories = client.query("pagination strategies", agent_id="executor", apply_decay=True)
   ```

4. To archive stale memories below 10% relevance:
   ```bash
   curl -X POST /memories/decay/archive \
     -H "Authorization: Bearer $KEY" \
     -d '{"namespace": "default", "threshold": 0.1}'
   ```

### 1.2 → 1.3

1. Upgrade the SDK:
   ```bash
   pip install --upgrade aegis-memory
   ```

2. New `export_json()` method on `AegisClient`:
   ```python
   stats = client.export_json("backup.json", namespace="production")
   ```

3. Dependency minimums raised — if you pin exact versions, update to match:
   - httpx >=0.28.0, fastapi >=0.115.0, openai >=1.60.0, etc.
   - See pyproject.toml for full list

4. No database changes required

### 1.1 → 1.2

1. New CLI available after upgrade:
   ```bash
   pip install --upgrade aegis-memory
   aegis demo  # Try the interactive demo
   ```

2. Smart Memory (optional, requires OpenAI or Anthropic):
   ```bash
   pip install aegis-memory[smart]  # For OpenAI
   pip install aegis-memory[smart-anthropic]  # For Anthropic
   ```

3. No database changes required

4. Framework integrations enhanced with `AegisSmartMemory`:
   ```python
   # Before (stores everything)
   from aegis_memory.integrations.langchain import AegisMemory
   
   # After (smart extraction)
   from aegis_memory.integrations.langchain import AegisSmartMemory
   ```

### 1.0 → 1.1

1. Run database migrations:
   ```bash
   psql -f migrations/002_ace_tables.sql
   ```

2. New environment variables (optional):
   ```bash
   ENABLE_METRICS=true
   LOG_FORMAT=json
   ```

3. New dependencies:
   ```bash
   pip install prometheus-client
   ```

### 0.1 → 1.0

**Breaking changes:**
- Database schema redesign (full migration required)
- API endpoint paths changed (`/api/v1/` prefix removed)
- SDK client initialization changed

See [docs/DESIGN.md](docs/DESIGN.md) for migration guide.