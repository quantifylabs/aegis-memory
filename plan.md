
Priority 5: Security Hardening — The Secure Memory Layer for Multi-Agent AI
                                                                                                             
 Context

 The 2025 AI agent security landscape revealed critical vulnerabilities in multi-agent systems:
 - EchoLeak (CVE-2025-32711, CVSS 9.3): single email triggers automatic data exfiltration from Microsoft 365 
  Copilot
 - CrewAI + GPT-4o: exfiltrated private data in 65% of tested scenarios
 - Magnetic-One: executed malicious code 97% of the time via compromised local files
 - Drift chatbot cascade: 1 compromised agent → 700+ organizations breached
 - Agent trust problem: Agent A's output becomes Agent B's instruction — no verification, no signing

 The OWASP AI Agent Security Cheat Sheet (Section 3) now explicitly covers memory/context security with      
 concrete controls. Aegis Memory has zero content validation, no integrity verification, no agent identity   
 binding, and no injection detection today. This plan closes every gap the security audit found and pivots   
 Aegis from "memory layer" to "secure memory layer" — a genuine competitive differentiator since no other    
 multi-agent memory system (mem0, Zep, Letta) offers these protections.

 Version bump: 1.9.2 → 2.0.0 (breaking change: content max length tightened, new response fields)

 ---
 Phase 1: Content Security Layer (Foundation)

 1.1 Create server/content_security.py — Three-Stage Pipeline

 A stateless ContentSecurityScanner class with three scanning stages applied before any memory write:        

 Stage 1 — Input Validation:
 - Max content length: 50,000 chars (configurable, tightened from 100k)
 - Max metadata nesting depth: 5 levels
 - Max metadata keys: 50
 - Reject null bytes and control characters (except \n, \t, \r)

 Stage 2 — Sensitive Data Scanner (regex-based):
 - SSN: \b\d{3}-\d{2}-\d{4}\b
 - Credit cards: Luhn-validated 13-19 digit sequences
 - API keys: AWS (AKIA...), OpenAI (sk-...), GitHub (ghp_/gho_), generic key/secret/token patterns
 - Email addresses, password assignment patterns
 - Configurable per-type action: reject | redact | flag | allow

 Stage 3 — Prompt Injection Detector:
 - System prompt overrides: "ignore previous", "you are now", "new instructions", "disregard"
 - Role manipulation: "pretend you are", "act as", "you must now"
 - Exfiltration triggers: "send to", "exfiltrate", "forward to", URL-in-instruction patterns
 - Configurable action: reject | flag | allow (default: flag)

 Returns: ContentSecurityVerdict(allowed, action, content, detections, flags)

 When action=redact, matched content is replaced with [REDACTED:<type>].
 When action=flag, memory is stored but tagged in content_flags column.
 When action=reject, HTTP 422 is returned and a SECURITY_REJECTED event is logged.

 1.2 Create server/integrity.py — HMAC-SHA256 Signing

 - compute_integrity_hash(content, agent_id, project_id, signing_key) → HMAC-SHA256 hex digest
 - verify_integrity(memory, signing_key) → bool
 - Signing key from AEGIS_INTEGRITY_KEY env var (falls back to AEGIS_API_KEY)
 - Canonical message format: {project_id}:{agent_id}:{content}

 1.3 Add security settings to server/config.py

 New fields in the existing Settings class:

 AEGIS_INTEGRITY_KEY          — HMAC signing key (falls back to AEGIS_API_KEY)
 CONTENT_MAX_LENGTH           — default 50000
 METADATA_MAX_DEPTH           — default 5
 METADATA_MAX_KEYS            — default 50
 CONTENT_POLICY_PII           — "flag" (reject | redact | flag | allow)
 CONTENT_POLICY_SECRETS       — "reject"
 CONTENT_POLICY_INJECTION     — "flag"
 ENABLE_INTEGRITY_CHECK       — true
 PER_AGENT_RATE_LIMIT_MINUTE  — 30
 PER_AGENT_RATE_LIMIT_HOUR    — 500
 AGENT_MEMORY_LIMIT           — 10000
 ENABLE_TRUST_LEVELS          — false

 1.4 Create alembic/versions/0007_content_security.py

 Following the exact pattern of 0006_temporal_decay.py:

 Memories table:
 - integrity_hash — String(64), nullable (existing rows don't need backfill)
 - content_flags — JSON, server_default='[]' (zero-downtime)
 - trust_level — String(16), server_default='internal'

 Api_keys table:
 - trust_level — String(16), server_default='internal'
 - bound_agent_id — String(64), nullable

 Index: GIN index on (project_id, content_flags) for admin queries on flagged memories

 1.5 Update server/models.py

 - Add TrustLevel enum: UNTRUSTED, INTERNAL, PRIVILEGED, SYSTEM
 - Add 5 new MemoryEventType entries: SECURITY_FLAGGED, SECURITY_REJECTED, AUTH_FAILED, DELETED,
 INTEGRITY_FAILED
 - Add 3 columns to Memory class: integrity_hash, content_flags, trust_level
 - Add 2 columns to ApiKey class: trust_level, bound_agent_id

 1.6 Integrate into memory write paths

 server/api/routers/memories.py — In add_memory() and add_memory_batch():
 1. Run ContentSecurityScanner.scan() on content + metadata
 2. If rejected → emit SECURITY_REJECTED event → HTTP 422
 3. If flagged → store with content_flags populated
 4. If redacted → use redacted content for embedding and storage
 5. Compute integrity_hash and store on Memory object
 6. Pass content_flags and trust_level through to repository
 7. Update MemoryOut to include content_flags and trust_level fields
 8. Update _mem_to_out() helper

 server/api/routers/typed_memory.py — Same integration for all 4 typed memory creation endpoints

 server/memory_repository.py — Accept integrity_hash, content_flags, trust_level params in add() and
 add_batch(); add count_agent_memories() static method

 ---
 Phase 2: Agent Identity & Trust Hierarchy

 2.1 Create server/trust_levels.py — Trust Policy Engine

 TrustPolicy class with static methods:
 - can_write(trust_level, scope) — untrusted cannot write; internal can write private/shared only;
 privileged/system can write all
 - can_read_scope(trust_level, scope, is_owner) — untrusted reads global only; internal reads global + own;  
 privileged/system reads all
 - can_delete(trust_level, is_owner) — only owners or privileged+
 - can_admin(trust_level) — only privileged/system can access /security/* endpoints

 2.2 Extend server/auth.py — Agent Binding

 - TokenVerifier._verify_project_key() → return trust_level and bound_agent_id from ApiKey record
 - TokenVerifier._verify_legacy_key() → add deprecation warning log
 - Existing get_project_id() continues returning str for backward compat

 2.3 Update server/api/dependencies/auth.py — AuthContext

 - Add AuthContext dataclass: project_id, trust_level, bound_agent_id, auth_method, key_id
 - Add get_auth_context() dependency that returns full AuthContext
 - Existing check_rate_limit() continues to return str (project_id) — no breaking change
 - New security-aware routers can depend on get_auth_context directly

 2.4 Agent ID spoofing prevention

 In memories.py, typed_memory.py, interaction_events.py — when auth context has bound_agent_id set and       
 request body has a different agent_id, return HTTP 403. Opt-in: only enforced when API key has
 bound_agent_id configured.

 ---
 Phase 3: Per-Agent Rate Limiting & Memory Quotas

 3.1 Extend server/rate_limiter.py

 Add check_agent(project_id, agent_id) method to both RateLimiter and RedisRateLimiter:
 - Separate sliding windows keyed by {project_id}:{agent_id}
 - Uses PER_AGENT_RATE_LIMIT_MINUTE and PER_AGENT_RATE_LIMIT_HOUR from settings
 - Redis keys: ratelimit:agent:minute:{project_id}:{agent_id}

 3.2 Memory quota enforcement

 Add MemoryRepository.count_agent_memories() static method — counts non-deprecated memories per agent in a   
 project.

 In add_memory() router: before storage, check count against AGENT_MEMORY_LIMIT. Return HTTP 429 if exceeded 
  with message to deprecate old memories first.

 3.3 Integrate in server/api/dependencies/auth.py

 After project-level check(), call check_agent() when bound_agent_id is present.

 ---
 Phase 4: Audit Hardening & Security Admin Endpoints

 4.1 Extend server/event_repository.py

 Add log_security_event() convenience method wrapping create_event() with security-specific defaults.        

 4.2 Add audit events throughout codebase

 - server/api/routers/memories.py delete endpoint → emit DELETED event
 - Content security rejections → emit SECURITY_REJECTED (already in Phase 1)
 - Content security flags → emit SECURITY_FLAGGED
 - Agent binding violations → emit AUTH_FAILED
 - Integrity verification failures → emit INTEGRITY_FAILED

 4.3 Create server/api/routers/security.py — Admin Endpoints

 Following the exact pattern of decay.py (router, Pydantic models, auth dependency, repo calls):

 Endpoint: /security/audit
 Method: GET
 Purpose: Query security events with time/type/agent filters
 ────────────────────────────────────────
 Endpoint: /security/flagged
 Method: GET
 Purpose: List memories with non-empty content_flags, paginated
 ────────────────────────────────────────
 Endpoint: /security/verify/{memory_id}
 Method: POST
 Purpose: Recompute and verify HMAC integrity of a memory
 ────────────────────────────────────────
 Endpoint: /security/config
 Method: GET
 Purpose: Return current security settings (signing key redacted)
 ────────────────────────────────────────
 Endpoint: /security/scan
 Method: POST
 Purpose: Dry-run content scan without storing — for client pre-validation

 All endpoints require privileged or system trust level (via get_auth_context dependency).

 4.4 Register in server/api/app.py

 from api.routers import security
 app.include_router(security.router, prefix="/security", tags=["security"])

 ---
 Phase 5: SDK Client Updates

 5.1 Update aegis_memory/client.py

 New dataclasses: ContentScanResult, SecurityAuditEvent, IntegrityCheckResult

 New methods on both AegisClient and AsyncAegisClient:
 - scan_content(content, metadata) → ContentScanResult (calls POST /security/scan)
 - verify_integrity(memory_id) → IntegrityCheckResult (calls POST /security/verify/{id})
 - get_flagged_memories(namespace, limit) → list[Memory] (calls GET /security/flagged)
 - get_security_audit(event_type, start_time, end_time, limit) → list[SecurityAuditEvent]
 - get_security_config() → dict

 Update Memory dataclass: add content_flags: list[str], trust_level: str, integrity_valid: bool | None       

 Update _parse_memory_data() to extract new fields from response JSON.

 ---
 Phase 6: Documentation & Positioning Pivot

 6.1 README.md — Full Rewrite of Positioning

 - Tagline: "The Memory Layer for Multi-Agent Systems" → "The Secure Memory Layer for Multi-Agent AI"        
 - Add "Why Security?" section citing 2025 incidents (EchoLeak, CrewAI exfil, Drift cascade)
 - Add security comparison rows to feature table (injection protection, HMAC integrity, trust hierarchy,     
 agent binding)
 - Add "Threat Model" section covering the 3 attack classes prevented
 - Update "Why Aegis?" competitive table with security column
 - Highlight OWASP compliance in feature list

 6.2 ROADMAP.md — Add Priority 5

 Add completed Priority 5 section after Priority 4 with all checkboxes. Update thesis:

 "Aegis is the SOTA secure agent-native memory fabric [...]. In a world where one compromised agent can      
 cascade to 700+ organizations, memory security is not optional — it's the feature."

 6.3 Create docs/guides/security.mdx — Comprehensive Security Guide

 Sections: Why Memory Security Matters, Content Security Pipeline, Memory Integrity (HMAC), Agent Trust      
 Hierarchy, Per-Agent Rate Limiting, Security Configuration (env vars table), Security Audit Trail, SDK      
 Security Methods (code examples)

 6.4 Update existing docs

 - docs/introduction/overview.mdx — add security positioning paragraph
 - docs/introduction/why-aegis.mdx — add security to competitive positioning
 - docs/introduction/concepts.mdx — add Trust Level, Content Flags, Integrity concepts
 - docs/guides/production-deployment.mdx — security env vars, CORS production warning
 - docs/mint.json — add guides/security to navigation (after typed-memory, before interaction-events)        

 6.5 Update CHANGELOG.md

 Add [2.0.0] section at top with full release notes grouped into Added, Changed, Security subsections.       

 6.6 Update pyproject.toml

 - Version: "1.9.1" → "2.0.0"
 - Description: add "Secure" prefix
 - Add "security" to keywords

 6.7 Update .env.example

 Add all new security environment variables with comments.

 ---
 Files Inventory

 Create (7 files)

 File: server/content_security.py
 Purpose: Three-stage content validation pipeline
 ────────────────────────────────────────
 File: server/integrity.py
 Purpose: HMAC-SHA256 signing and verification
 ────────────────────────────────────────
 File: server/trust_levels.py
 Purpose: Agent trust hierarchy and policy engine
 ────────────────────────────────────────
 File: server/api/routers/security.py
 Purpose: Security admin endpoints (5 endpoints)
 ────────────────────────────────────────
 File: alembic/versions/0007_content_security.py
 Purpose: Migration: integrity_hash, content_flags, trust_level, bound_agent_id
 ────────────────────────────────────────
 File: tests/test_content_security.py
 Purpose: ~80 tests covering all security features
 ────────────────────────────────────────
 File: docs/guides/security.mdx
 Purpose: Comprehensive security guide

 Modify (20 files)

 File: server/models.py
 Changes: TrustLevel enum, 5 MemoryEventType entries, 3 Memory cols, 2 ApiKey cols
 ────────────────────────────────────────
 File: server/config.py
 Changes: ~12 security settings fields
 ────────────────────────────────────────
 File: server/memory_repository.py
 Changes: Accept security params in add/add_batch; add count_agent_memories()
 ────────────────────────────────────────
 File: server/auth.py
 Changes: Return trust_level + bound_agent_id; legacy deprecation warning
 ────────────────────────────────────────
 File: server/api/dependencies/auth.py
 Changes: AuthContext dataclass; get_auth_context dep; per-agent rate check
 ────────────────────────────────────────
 File: server/rate_limiter.py
 Changes: check_agent() method on both implementations
 ────────────────────────────────────────
 File: server/event_repository.py
 Changes: log_security_event() convenience method
 ────────────────────────────────────────
 File: server/api/app.py
 Changes: Import + mount security router
 ────────────────────────────────────────
 File: server/api/routers/memories.py
 Changes: Content scanning, integrity, agent binding, MemoryOut fields, delete audit
 ────────────────────────────────────────
 File: server/api/routers/typed_memory.py
 Changes: Content scanning integration on all 4 create endpoints
 ────────────────────────────────────────
 File: server/api/routers/interaction_events.py
 Changes: Agent binding check
 ────────────────────────────────────────
 File: aegis_memory/client.py
 Changes: 5 security methods (sync+async), Memory dataclass fields, parsing
 ────────────────────────────────────────
 File: README.md
 Changes: Security-first positioning, threat model, comparison table
 ────────────────────────────────────────
 File: ROADMAP.md
 Changes: Priority 5 section, updated thesis
 ────────────────────────────────────────
 File: CHANGELOG.md
 Changes: v2.0.0 release notes
 ────────────────────────────────────────
 File: pyproject.toml
 Changes: Version 2.0.0, description, keywords
 ────────────────────────────────────────
 File: .env.example
 Changes: Security environment variables
 ────────────────────────────────────────
 File: docs/introduction/overview.mdx
 Changes: Security paragraph
 ────────────────────────────────────────
 File: docs/introduction/why-aegis.mdx
 Changes: Security competitive positioning
 ────────────────────────────────────────
 File: docs/mint.json
 Changes: Navigation entry for security guide

 ---
 Backward Compatibility

 All changes are additive with safe defaults — zero breaking changes for existing clients:
 - Content scanning defaults to flag mode (not reject) — existing content stores normally, just gets flagged 
 - Trust levels default to internal — matches current implicit behavior
 - Per-agent rate limiting only activates when bound_agent_id is set on the API key
 - Integrity check is opt-in via ENABLE_INTEGRITY_CHECK (default: true for new, existing rows have NULL      
 integrity_hash which is fine)
 - New MemoryOut fields have defaults — clients ignoring extra fields are unaffected
 - Only tightening: content max_length 100k → 50k (configurable via CONTENT_MAX_LENGTH)

 ---
 Testing & Verification

 Test file: tests/test_content_security.py (~80 tests)

 - TestInputValidation — length limits, null bytes, metadata depth/keys
 - TestSensitiveDataScanner — SSN, credit card, API key, email, password; false positive resistance
 - TestPromptInjectionDetector — system override, role manipulation, exfiltration, encoding evasion
 - TestContentPolicy — reject/redact/flag/allow per detection type
 - TestIntegrityHash — HMAC computation, verification pass, tamper detection
 - TestTrustPolicy — 4 trust levels x read/write/delete/admin operations
 - TestAgentBinding — bound_agent_id enforcement, mismatch rejection, unbound passthrough
 - TestPerAgentRateLimiting — separate windows, project vs agent limits, isolation
 - TestMemoryQuota — enforcement, bypass for system trust, quota with deprecation
 - TestSecurityRouter — all 5 endpoints, trust level access control
 - TestAuditEvents — security events for rejections, flags, deletions, auth failures
 - TestMigration0007 — columns exist, defaults correct, index present

 Run commands

 pytest tests/test_content_security.py -v          # New security tests
 pytest tests/ -v                                    # Full regression suite
 alembic upgrade head && alembic downgrade -1 && alembic upgrade head  # Migration round-trip