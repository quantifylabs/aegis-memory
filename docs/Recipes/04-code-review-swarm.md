# Recipe 4: Code Review Agent Swarm

**Coordinated security, performance, and style reviews that don't duplicate work.**

| Metric | Value |
|--------|-------|
| Complexity | Advanced |
| Time to Build | 2-3 hours |
| Agents | 4 (Security, Performance, Style, Coordinator) |
| Key Patterns | Scope isolation, Cross-agent queries, Delta updates |

---

## The Problem

You set up multiple AI code reviewers—one for security, one for performance, one for style. They all review the same PR:

```
Security Bot: "This SQL query might be vulnerable to injection"
Performance Bot: "This SQL query might be slow on large tables"  
Style Bot: "This SQL query doesn't follow our naming conventions"

Developer: "Great, 3 bots found the same line. None of them saw the 
           actual auth bypass on line 47."
```

**Problems:**
1. **Duplicate findings** - Multiple agents flag the same obvious issues
2. **Missing coverage** - While all focus on one area, others are ignored
3. **No coordination** - Agent 2 doesn't know what Agent 1 already found
4. **No learning** - False positives repeat forever

---

## Current Solutions (And Why They Fail)

### Sequential Review
- **Approach**: Run reviewers one after another, pass findings along
- **Fails because**: Later reviewers don't understand earlier context. No real coordination.

### Single Mega-Reviewer
- **Approach**: One agent does everything
- **Fails because**: Context window overflow on large PRs. Jack of all trades, master of none.

### GitHub Actions Parallel
- **Approach**: Run all checks in parallel, aggregate results
- **Fails because**: No communication during review. Can't say "Security already flagged this, I'll look elsewhere."

### Rule-Based Dedup
- **Approach**: Post-process to remove duplicate findings
- **Fails because**: Semantic duplicates slip through. "SQL injection risk" ≠ "Unsanitized input" but same issue.

**The core issue**: Reviewers need real-time coordination—knowing what others found, what areas are covered, and what to prioritize.

---

## The Aegis Approach

Aegis enables **coordinated review swarms**:

```
┌─────────────────────────────────────────────────────────────────┐
│                    COORDINATOR AGENT                             │
│  Assigns focus areas, prevents overlap, aggregates findings      │
├─────────────────────────────────────────────────────────────────┤
│                    SHARED MEMORY SCOPE                           │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │
│  │  Security   │  │ Performance │  │    Style    │              │
│  │   Agent     │  │    Agent    │  │    Agent    │              │
│  │             │  │             │  │             │              │
│  │ Writes:     │  │ Writes:     │  │ Writes:     │              │
│  │ -Findings   │  │ -Findings   │  │ -Findings   │              │
│  │ -Covered    │  │ -Covered    │  │ -Covered    │              │
│  │  areas      │  │  areas      │  │  areas      │              │
│  │             │  │             │  │             │              │
│  │ Reads:      │  │ Reads:      │  │ Reads:      │              │
│  │ -Others'    │  │ -Others'    │  │ -Others'    │              │
│  │  findings   │  │  findings   │  │  findings   │              │
│  └─────────────┘  └─────────────┘  └─────────────┘              │
└─────────────────────────────────────────────────────────────────┘
```

Each agent:
1. **Checks shared memory** before reviewing a file
2. **Claims areas** they're reviewing (prevents overlap)
3. **Reads others' findings** to avoid duplicates
4. **Votes on past patterns** that proved useful/useless

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         PR SUBMITTED                             │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      COORDINATOR AGENT                           │
│                                                                  │
│  1. Parse PR diff                                                │
│  2. Identify file types and risk areas                           │
│  3. Query global playbook for review priorities                  │
│  4. Assign files to specialist reviewers                         │
│  5. Store assignments in SHARED memory                           │
└─────────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
        ┌──────────┐   ┌──────────┐   ┌──────────┐
        │ SECURITY │   │   PERF   │   │  STYLE   │
        │  AGENT   │   │  AGENT   │   │  AGENT   │
        └──────────┘   └──────────┘   └──────────┘
              │               │               │
              │   ┌───────────┴───────────┐   │
              │   │    SHARED MEMORY      │   │
              └──►│  - Claimed files      │◄──┘
                  │  - Findings           │
                  │  - Coverage map       │
                  └───────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      COORDINATOR AGENT                           │
│                                                                  │
│  1. Aggregate all findings                                       │
│  2. Deduplicate semantic overlaps                                │
│  3. Prioritize by severity                                       │
│  4. Generate unified review                                      │
│  5. Store successful patterns for future                         │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                       PR COMMENT                                 │
│  ## Code Review Summary                                          │
│  🔴 Critical: 2 | 🟡 Warning: 5 | 🔵 Info: 3                     │
│                                                                  │
│  ### Security (reviewed by @security-bot)                        │
│  - [CRITICAL] SQL injection risk in user_query.py:45             │
│                                                                  │
│  ### Performance (reviewed by @perf-bot)                         │
│  - [WARNING] N+1 query pattern in orders.py:23                   │
└─────────────────────────────────────────────────────────────────┘
```

---

## Implementation

### Step 1: Review Coordinator

```python
from aegis_memory import AegisClient
from openai import OpenAI
from dataclasses import dataclass
from typing import List, Dict, Optional
import json
import asyncio

aegis = AegisClient(api_key="your-key", base_url="http://localhost:8000")
llm = OpenAI()

@dataclass
class ReviewAssignment:
    agent_id: str
    files: List[str]
    focus_areas: List[str]
    priority: str

@dataclass 
class Finding:
    agent_id: str
    file: str
    line: int
    severity: str  # critical, warning, info
    category: str
    message: str
    suggestion: Optional[str] = None

class ReviewCoordinator:
    """Coordinates multiple review agents."""
    
    def __init__(self, pr_id: str):
        self.pr_id = pr_id
        self.session_id = f"review-{pr_id}"
        self.agents = ["security", "performance", "style"]
    
    async def coordinate_review(self, diff: str, files: List[str]) -> Dict:
        """Orchestrate the full review process."""
        
        # Phase 1: Analyze and assign
        assignments = await self._create_assignments(diff, files)
        
        # Store assignments in shared memory
        for assignment in assignments:
            aegis.add(
                content=json.dumps({
                    "type": "assignment",
                    "agent": assignment.agent_id,
                    "files": assignment.files,
                    "focus": assignment.focus_areas
                }),
                agent_id="coordinator",
                scope="agent-shared",
                shared_with_agents=self.agents,
                metadata={"session_id": self.session_id, "type": "assignment"}
            )
        
        # Phase 2: Parallel review
        review_tasks = [
            self._run_agent_review(assignment)
            for assignment in assignments
        ]
        await asyncio.gather(*review_tasks)
        
        # Phase 3: Aggregate and deduplicate
        findings = await self._aggregate_findings()
        
        # Phase 4: Generate report
        report = self._generate_report(findings)
        
        # Phase 5: Learn from this review
        self._store_learnings(findings)
        
        return report
    
    async def _create_assignments(self, diff: str, files: List[str]) -> List[ReviewAssignment]:
        """Intelligently assign files to specialist agents."""
        
        # Get past review patterns
        patterns = aegis.playbook(
            query="code review file assignment",
            agent_id="coordinator",
            min_effectiveness=0.3,
            top_k=5
        )
        patterns_context = "\n".join([p.content for p in patterns]) if patterns else ""
        
        response = llm.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": f"""You are a code review coordinator.

Past successful assignment patterns:
{patterns_context}

Assign files to specialist reviewers:
- security: Auth, input validation, SQL, API keys, encryption
- performance: DB queries, loops, memory, caching, algorithms
- style: Naming, formatting, documentation, patterns

Consider file types, risk areas, and optimal coverage.
Output JSON array of assignments."""},
                {"role": "user", "content": f"Files: {json.dumps(files)}\n\nDiff preview:\n{diff[:3000]}"}
            ]
        )
        
        assignments_data = json.loads(response.choices[0].message.content)
        
        return [
            ReviewAssignment(
                agent_id=a["agent"],
                files=a["files"],
                focus_areas=a["focus"],
                priority=a.get("priority", "normal")
            )
            for a in assignments_data
        ]
    
    async def _run_agent_review(self, assignment: ReviewAssignment):
        """Run a single agent's review."""
        agent = ReviewAgent(assignment.agent_id, self.session_id)
        await agent.review(assignment.files, assignment.focus_areas)
    
    async def _aggregate_findings(self) -> List[Finding]:
        """Collect and deduplicate all findings."""
        
        # Query all findings from shared memory
        raw_findings = aegis.query_cross_agent(
            query="finding",
            requesting_agent_id="coordinator",
            target_agent_ids=self.agents,
            filter_metadata={"session_id": self.session_id, "type": "finding"},
            top_k=100
        )
        
        findings = []
        seen_locations = set()
        
        for memory in raw_findings:
            data = json.loads(memory.content)
            location_key = f"{data['file']}:{data['line']}"
            
            # Deduplicate by location
            if location_key not in seen_locations:
                seen_locations.add(location_key)
                findings.append(Finding(
                    agent_id=memory.agent_id,
                    file=data["file"],
                    line=data["line"],
                    severity=data["severity"],
                    category=data["category"],
                    message=data["message"],
                    suggestion=data.get("suggestion")
                ))
            else:
                # Log that we prevented a duplicate
                aegis.add(
                    content=f"Duplicate finding prevented: {data['message'][:100]}",
                    agent_id="coordinator",
                    scope="agent-private",
                    metadata={"type": "dedup_log"}
                )
        
        # Sort by severity
        severity_order = {"critical": 0, "warning": 1, "info": 2}
        findings.sort(key=lambda f: severity_order.get(f.severity, 3))
        
        return findings
    
    def _generate_report(self, findings: List[Finding]) -> Dict:
        """Generate the final review report."""
        
        by_severity = {"critical": [], "warning": [], "info": []}
        by_agent = {agent: [] for agent in self.agents}
        
        for finding in findings:
            by_severity[finding.severity].append(finding)
            by_agent[finding.agent_id].append(finding)
        
        return {
            "summary": {
                "critical": len(by_severity["critical"]),
                "warning": len(by_severity["warning"]),
                "info": len(by_severity["info"])
            },
            "by_agent": {
                agent: [
                    {
                        "file": f.file,
                        "line": f.line,
                        "severity": f.severity,
                        "message": f.message,
                        "suggestion": f.suggestion
                    }
                    for f in agent_findings
                ]
                for agent, agent_findings in by_agent.items()
            },
            "requires_changes": len(by_severity["critical"]) > 0
        }
    
    def _store_learnings(self, findings: List[Finding]):
        """Store patterns for future reviews."""
        
        # If we found critical issues, store what to look for
        critical_findings = [f for f in findings if f.severity == "critical"]
        
        for finding in critical_findings:
            aegis.add(
                content=f"Critical finding pattern: {finding.category} - {finding.message}",
                agent_id="coordinator",
                scope="global",
                memory_type="strategy",
                metadata={
                    "type": "review_pattern",
                    "category": finding.category,
                    "original_agent": finding.agent_id
                }
            )
```

### Step 2: Specialist Review Agents

```python
class ReviewAgent:
    """Specialist code review agent."""
    
    SPECIALIZATIONS = {
        "security": {
            "focus": ["SQL injection", "XSS", "auth bypass", "secrets exposure", 
                     "input validation", "CSRF", "path traversal"],
            "file_priority": [".py", ".js", ".ts", ".sql", ".env"]
        },
        "performance": {
            "focus": ["N+1 queries", "unbounded loops", "memory leaks",
                     "missing indexes", "blocking I/O", "cache misses"],
            "file_priority": [".py", ".js", ".sql", ".go"]
        },
        "style": {
            "focus": ["naming conventions", "documentation", "code organization",
                     "DRY violations", "magic numbers", "error handling"],
            "file_priority": ["*"]
        }
    }
    
    def __init__(self, agent_id: str, session_id: str):
        self.agent_id = agent_id
        self.session_id = session_id
        self.spec = self.SPECIALIZATIONS.get(agent_id, {})
    
    async def review(self, files: List[str], focus_areas: List[str]):
        """Review assigned files."""
        
        # Check what others have already found
        existing_findings = self._get_existing_findings()
        
        # Get relevant patterns from global playbook
        patterns = aegis.playbook(
            query=f"{self.agent_id} code review patterns",
            agent_id=self.agent_id,
            min_effectiveness=0.3,
            top_k=10
        )
        
        for file in files:
            # Claim the file
            self._claim_file(file)
            
            # Review with context
            findings = await self._review_file(file, focus_areas, patterns, existing_findings)
            
            # Store findings
            for finding in findings:
                self._store_finding(finding)
    
    def _get_existing_findings(self) -> List[Dict]:
        """Get findings from other agents to avoid duplicates."""
        
        memories = aegis.query_cross_agent(
            query="finding",
            requesting_agent_id=self.agent_id,
            target_agent_ids=[a for a in ["security", "performance", "style"] if a != self.agent_id],
            filter_metadata={"session_id": self.session_id, "type": "finding"},
            top_k=50
        )
        
        return [json.loads(m.content) for m in memories]
    
    def _claim_file(self, file: str):
        """Claim a file to prevent overlap."""
        
        aegis.add(
            content=json.dumps({
                "type": "claim",
                "file": file,
                "agent": self.agent_id,
                "status": "reviewing"
            }),
            agent_id=self.agent_id,
            scope="agent-shared",
            shared_with_agents=["security", "performance", "style", "coordinator"],
            metadata={"session_id": self.session_id, "type": "claim"}
        )
    
    async def _review_file(self, file: str, focus_areas: List[str], 
                           patterns: List, existing_findings: List[Dict]) -> List[Finding]:
        """Review a single file."""
        
        # Build context from patterns and existing findings
        patterns_context = "\n".join([
            f"- {p.content}" for p in patterns
        ]) if patterns else "No prior patterns."
        
        existing_context = "\n".join([
            f"- {f['file']}:{f['line']} - {f['message'][:50]}"
            for f in existing_findings
            if f['file'] == file
        ]) if existing_findings else "No existing findings for this file."
        
        # Read file content (simplified - in practice, fetch from git)
        file_content = self._get_file_content(file)
        
        response = llm.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": f"""You are a {self.agent_id} code reviewer.

Your specialization: {json.dumps(self.spec['focus'])}

Proven patterns to look for:
{patterns_context}

Already found by other reviewers (DON'T DUPLICATE):
{existing_context}

Focus on: {json.dumps(focus_areas)}

For each issue found, output JSON:
{{
    "findings": [
        {{
            "line": <line_number>,
            "severity": "critical|warning|info",
            "category": "<category>",
            "message": "<description>",
            "suggestion": "<how to fix>"
        }}
    ]
}}

Only report issues in your specialization. Skip issues others already found."""},
                {"role": "user", "content": f"File: {file}\n\n{file_content}"}
            ]
        )
        
        result = json.loads(response.choices[0].message.content)
        
        return [
            Finding(
                agent_id=self.agent_id,
                file=file,
                line=f["line"],
                severity=f["severity"],
                category=f["category"],
                message=f["message"],
                suggestion=f.get("suggestion")
            )
            for f in result.get("findings", [])
        ]
    
    def _store_finding(self, finding: Finding):
        """Store a finding in shared memory."""
        
        aegis.add(
            content=json.dumps({
                "type": "finding",
                "file": finding.file,
                "line": finding.line,
                "severity": finding.severity,
                "category": finding.category,
                "message": finding.message,
                "suggestion": finding.suggestion
            }),
            agent_id=self.agent_id,
            scope="agent-shared",
            shared_with_agents=["security", "performance", "style", "coordinator"],
            metadata={
                "session_id": self.session_id,
                "type": "finding",
                "severity": finding.severity
            }
        )
    
    def _get_file_content(self, file: str) -> str:
        """Get file content (simplified)."""
        # In practice: fetch from git/GitHub API
        return f"# Content of {file}\n# ... file contents ..."
```

### Step 3: Voting on Review Patterns

```python
class ReviewPatternVoter:
    """Track which review patterns are effective."""
    
    def __init__(self, pr_id: str):
        self.pr_id = pr_id
    
    def process_feedback(self, feedback: Dict):
        """Process developer feedback on review findings."""
        
        # feedback = {
        #     "finding_id": "...",
        #     "action": "fixed" | "ignored" | "disputed",
        #     "comment": "..."
        # }
        
        # Get the original finding
        finding_memory = aegis.get(feedback["finding_id"])
        
        if feedback["action"] == "fixed":
            # Developer fixed the issue - pattern was helpful
            self._vote_helpful(finding_memory)
            
        elif feedback["action"] == "disputed":
            # Developer disagreed - might be false positive
            self._vote_harmful(finding_memory, feedback.get("comment", ""))
            
        # "ignored" is neutral - don't vote
    
    def _vote_helpful(self, finding_memory):
        """Pattern led to a fix - helpful."""
        
        # Find the pattern that led to this finding
        finding_data = json.loads(finding_memory.content)
        
        patterns = aegis.playbook(
            query=f"{finding_data['category']} {finding_memory.agent_id}",
            agent_id=finding_memory.agent_id,
            top_k=3
        )
        
        for pattern in patterns:
            aegis.vote(
                memory_id=pattern.id,
                vote="helpful",
                voter_agent_id="feedback-processor",
                context=f"Led to fix in PR {self.pr_id}: {finding_data['message'][:100]}"
            )
    
    def _vote_harmful(self, finding_memory, dispute_reason: str):
        """Pattern led to false positive - harmful."""
        
        finding_data = json.loads(finding_memory.content)
        
        patterns = aegis.playbook(
            query=f"{finding_data['category']} {finding_memory.agent_id}",
            agent_id=finding_memory.agent_id,
            top_k=3
        )
        
        for pattern in patterns:
            aegis.vote(
                memory_id=pattern.id,
                vote="harmful",
                voter_agent_id="feedback-processor",
                context=f"False positive in PR {self.pr_id}: {dispute_reason}"
            )
        
        # Create reflection about false positive
        aegis.reflection(
            content=f"False positive: {finding_data['category']} - {finding_data['message']}. "
                   f"Developer feedback: {dispute_reason}",
            agent_id=finding_memory.agent_id,
            error_pattern="false_positive"
        )
```

### Step 4: Usage

```python
async def review_pull_request(pr_id: str, diff: str, files: List[str]):
    """Main entry point for PR review."""
    
    coordinator = ReviewCoordinator(pr_id)
    report = await coordinator.coordinate_review(diff, files)
    
    # Format as GitHub comment
    comment = format_github_comment(report)
    
    # Post to PR (simplified)
    post_pr_comment(pr_id, comment)
    
    return report

def format_github_comment(report: Dict) -> str:
    """Format report as GitHub markdown."""
    
    lines = [
        "## 🤖 AI Code Review",
        "",
        f"| 🔴 Critical | 🟡 Warning | 🔵 Info |",
        f"|-------------|------------|---------|",
        f"| {report['summary']['critical']} | {report['summary']['warning']} | {report['summary']['info']} |",
        ""
    ]
    
    for agent, findings in report["by_agent"].items():
        if findings:
            lines.append(f"### {agent.title()} Review")
            for f in findings:
                emoji = {"critical": "🔴", "warning": "🟡", "info": "🔵"}[f["severity"]]
                lines.append(f"- {emoji} **{f['file']}:{f['line']}** - {f['message']}")
                if f.get("suggestion"):
                    lines.append(f"  - 💡 {f['suggestion']}")
            lines.append("")
    
    if report["requires_changes"]:
        lines.append("---")
        lines.append("⛔ **Changes requested** - Please address critical issues before merging.")
    
    return "\n".join(lines)

# Run review
if __name__ == "__main__":
    asyncio.run(review_pull_request(
        pr_id="123",
        diff="...",
        files=["src/auth.py", "src/api/users.py", "src/db/queries.py"]
    ))
```

---

## Production Tips

### 1. Timeout Handling
```python
async def review_with_timeout(agent, files, timeout=60):
    try:
        return await asyncio.wait_for(
            agent.review(files),
            timeout=timeout
        )
    except asyncio.TimeoutError:
        # Store partial results
        aegis.add(
            content=f"Review timed out for {agent.agent_id}",
            agent_id="coordinator",
            metadata={"type": "timeout"}
        )
        return []
```

### 2. Large PR Handling
```python
def chunk_large_pr(files: List[str], max_per_batch: int = 10):
    """Split large PRs into reviewable chunks."""
    for i in range(0, len(files), max_per_batch):
        yield files[i:i + max_per_batch]
```

### 3. Priority Override
```python
# High-risk files always get security review
HIGH_RISK_PATTERNS = [
    r"auth", r"login", r"password", r"secret",
    r"payment", r"billing", r"admin"
]

def enforce_security_review(files: List[str]) -> List[str]:
    """Ensure high-risk files get security review."""
    return [f for f in files if any(re.search(p, f, re.I) for p in HIGH_RISK_PATTERNS)]
```

---

## Expected Outcomes

| Metric | Without Aegis | With Aegis |
|--------|---------------|------------|
| Duplicate findings | 30-40% | <5% |
| Review coverage | Overlapping | Coordinated |
| False positive rate | Static | Decreasing (voting) |
| Review time | Serial | Parallel |
| Cross-review learning | None | Automatic |

---

## Next Steps

- [Recipe 5: CI/CD Pipeline Memory](./05-cicd-pipeline-memory.md) - Integrate reviews with builds
- [Recipe 6: Debugging Agent](./06-debugging-agent-reflection.md) - Self-improving issue detection
