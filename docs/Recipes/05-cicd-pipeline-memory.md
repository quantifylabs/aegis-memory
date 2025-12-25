# Recipe 5: CI/CD Pipeline Memory

**Learn from build failures. Prevent regressions. Never see the same CI error twice.**

| Metric | Value |
|--------|-------|
| Complexity | Intermediate |
| Time to Build | 1-2 hours |
| Key Patterns | Reflections, Global scope, Error pattern taxonomy |

---

## The Problem

Your CI pipeline fails:

```
❌ Build #4521 failed
   
   test_user_authentication FAILED
   > assert response.status_code == 200
   E assert 401 == 200
```

Developer fixes it. Next week, different developer, same error:

```
❌ Build #4589 failed
   
   test_user_authentication FAILED  
   > assert response.status_code == 200
   E assert 401 == 200
```

**The pipeline learned nothing.** No one told it "this happens when you forget to set AUTH_TOKEN in test fixtures."

Meanwhile:
- 1 in 10 builds fail from flaky tests
- AI-generated tests break unpredictably
- Context pollution cascades across workflows
- Developers waste hours on errors that have known fixes

---

## Current Solutions (And Why They Fail)

### Build Logs
- **Approach**: Store all logs, grep when problems recur
- **Fails because**: No semantic understanding. Can't match "connection timeout" to "server was restarting."

### Flaky Test Detection
- **Approach**: Track test pass/fail rates, quarantine flaky tests
- **Fails because**: Treats symptoms, not causes. Doesn't explain *why* or *how to fix*.

### Documentation/Wiki
- **Approach**: Document known issues in wiki
- **Fails because**: No one reads it. Not surfaced at point of failure.

### Slack/Teams Channels
- **Approach**: Post failures to channel, hope someone remembers
- **Fails because**: Knowledge in chat is ephemeral. New team members don't have history.

**The core issue**: CI systems are stateless. Every build starts fresh with no memory of past failures and fixes.

---

## The Aegis Approach

Aegis creates a **learning pipeline** that:

1. **Captures failure context** - Error, stack trace, recent changes
2. **Matches to known patterns** - "This looks like the AUTH_TOKEN issue"
3. **Suggests fixes** - From past successful resolutions
4. **Learns from resolutions** - When you fix it, the pattern gets stronger

```
┌─────────────────────────────────────────────────────────────────┐
│                     BUILD FAILS                                  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                  FAILURE ANALYZER AGENT                          │
│                                                                  │
│  1. Extract error pattern                                        │
│  2. Query Aegis: "Have we seen this before?"                     │
│  3. If yes → Suggest known fix                                   │
│  4. If no → Create new reflection                                │
└─────────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
┌─────────────────────────┐     ┌─────────────────────────┐
│     KNOWN PATTERN       │     │     NEW PATTERN         │
│                         │     │                         │
│  "AUTH_TOKEN missing"   │     │  Store as reflection    │
│  Fix: Add to fixtures   │     │  Wait for resolution    │
│  Confidence: 0.85       │     │  Learn from fix         │
└─────────────────────────┘     └─────────────────────────┘
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    CI/CD PIPELINE                                │
│                                                                  │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐  │
│  │  Build   │───►│   Test   │───►│  Deploy  │───►│  Verify  │  │
│  └──────────┘    └──────────┘    └──────────┘    └──────────┘  │
│       │               │               │               │         │
│       ▼               ▼               ▼               ▼         │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                 AEGIS MEMORY LAYER                       │   │
│  │                                                          │   │
│  │  ┌────────────────┐  ┌────────────────┐                 │   │
│  │  │   FAILURES     │  │   PATTERNS     │                 │   │
│  │  │  - Error logs  │  │  - Known fixes │                 │   │
│  │  │  - Stack trace │  │  - Root causes │                 │   │
│  │  │  - Context     │  │  - Prevention  │                 │   │
│  │  └────────────────┘  └────────────────┘                 │   │
│  │                                                          │   │
│  │  ┌────────────────┐  ┌────────────────┐                 │   │
│  │  │  RESOLUTIONS   │  │   LEARNINGS    │                 │   │
│  │  │  - What fixed  │  │  - Reflections │                 │   │
│  │  │  - Who fixed   │  │  - Playbooks   │                 │   │
│  │  │  - When        │  │  - Voting      │                 │   │
│  │  └────────────────┘  └────────────────┘                 │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

## Implementation

### Step 1: Failure Pattern Taxonomy

```python
from aegis_memory import AegisClient
from openai import OpenAI
from dataclasses import dataclass
from typing import List, Dict, Optional
from enum import Enum
import json
import re

aegis = AegisClient(api_key="your-key", base_url="http://localhost:8000")
llm = OpenAI()

class FailureCategory(Enum):
    TEST_FLAKY = "test_flaky"
    TEST_ASSERTION = "test_assertion"
    BUILD_DEPENDENCY = "build_dependency"
    BUILD_COMPILATION = "build_compilation"
    ENVIRONMENT_CONFIG = "environment_config"
    ENVIRONMENT_RESOURCE = "environment_resource"
    INTEGRATION_TIMEOUT = "integration_timeout"
    INTEGRATION_AUTH = "integration_auth"
    DEPLOYMENT_RESOURCE = "deployment_resource"
    DEPLOYMENT_CONFIG = "deployment_config"
    UNKNOWN = "unknown"

@dataclass
class BuildFailure:
    build_id: str
    stage: str  # build, test, deploy, verify
    error_message: str
    stack_trace: Optional[str]
    exit_code: int
    changed_files: List[str]
    environment: str  # dev, staging, prod
    branch: str
    commit_sha: str
    timestamp: str
```

### Step 2: Failure Analyzer Agent

```python
class FailureAnalyzer:
    """Analyzes build failures and matches to known patterns."""
    
    def __init__(self, project_id: str):
        self.project_id = project_id
        self.agent_id = "ci-analyzer"
    
    def analyze(self, failure: BuildFailure) -> Dict:
        """Analyze a build failure."""
        
        # Step 1: Categorize the failure
        category = self._categorize(failure)
        
        # Step 2: Search for known patterns
        matches = self._find_matches(failure, category)
        
        # Step 3: Generate analysis
        if matches:
            return self._generate_known_fix(failure, matches)
        else:
            return self._create_new_pattern(failure, category)
    
    def _categorize(self, failure: BuildFailure) -> FailureCategory:
        """Categorize failure type."""
        
        error_lower = failure.error_message.lower()
        
        # Test failures
        if failure.stage == "test":
            if any(word in error_lower for word in ["flaky", "timeout", "intermittent"]):
                return FailureCategory.TEST_FLAKY
            if any(word in error_lower for word in ["assert", "expect", "should"]):
                return FailureCategory.TEST_ASSERTION
        
        # Build failures
        if failure.stage == "build":
            if any(word in error_lower for word in ["dependency", "package", "module not found"]):
                return FailureCategory.BUILD_DEPENDENCY
            if any(word in error_lower for word in ["syntax", "compile", "type"]):
                return FailureCategory.BUILD_COMPILATION
        
        # Environment failures
        if any(word in error_lower for word in ["env", "config", "variable", "secret"]):
            return FailureCategory.ENVIRONMENT_CONFIG
        if any(word in error_lower for word in ["memory", "disk", "cpu", "quota"]):
            return FailureCategory.ENVIRONMENT_RESOURCE
        
        # Integration failures
        if any(word in error_lower for word in ["timeout", "connection"]):
            return FailureCategory.INTEGRATION_TIMEOUT
        if any(word in error_lower for word in ["401", "403", "auth", "token"]):
            return FailureCategory.INTEGRATION_AUTH
        
        return FailureCategory.UNKNOWN
    
    def _find_matches(self, failure: BuildFailure, category: FailureCategory) -> List:
        """Find matching known patterns."""
        
        # Build search query from failure context
        search_query = f"{category.value} {failure.error_message[:200]} {failure.stage}"
        
        # Query reflections (learnings from past failures)
        matches = aegis.playbook(
            query=search_query,
            agent_id=self.agent_id,
            include_types=["reflection", "strategy"],
            min_effectiveness=0.2,
            top_k=5
        )
        
        # Filter for high-confidence matches
        return [m for m in matches if m.effectiveness_score > 0.3 or 
                self._is_exact_match(failure, m)]
    
    def _is_exact_match(self, failure: BuildFailure, pattern) -> bool:
        """Check if pattern is an exact match for this failure."""
        
        pattern_metadata = pattern.metadata or {}
        
        # Check for exact error signature match
        if pattern_metadata.get("error_signature"):
            failure_sig = self._compute_signature(failure)
            if pattern_metadata["error_signature"] == failure_sig:
                return True
        
        return False
    
    def _compute_signature(self, failure: BuildFailure) -> str:
        """Compute unique signature for failure."""
        
        # Normalize error message (remove line numbers, timestamps, etc.)
        normalized = re.sub(r'\d+', 'N', failure.error_message)
        normalized = re.sub(r'0x[0-9a-f]+', 'ADDR', normalized.lower())
        
        return f"{failure.stage}:{normalized[:100]}"
    
    def _generate_known_fix(self, failure: BuildFailure, matches: List) -> Dict:
        """Generate fix suggestion from known patterns."""
        
        best_match = matches[0]
        
        # Vote that we're using this pattern
        aegis.vote(
            memory_id=best_match.id,
            vote="helpful",
            voter_agent_id=self.agent_id,
            context=f"Matched build {failure.build_id}"
        )
        
        return {
            "status": "known_pattern",
            "pattern_id": best_match.id,
            "category": best_match.metadata.get("error_pattern"),
            "confidence": best_match.effectiveness_score,
            "suggested_fix": best_match.metadata.get("correct_approach", best_match.content),
            "similar_failures": best_match.metadata.get("occurrence_count", 1),
            "last_seen": best_match.metadata.get("last_seen"),
            "message": f"🔍 This looks like a known issue: {best_match.content[:200]}"
        }
    
    def _create_new_pattern(self, failure: BuildFailure, category: FailureCategory) -> Dict:
        """Create new pattern for unknown failure."""
        
        # Use LLM to analyze the failure
        analysis = self._llm_analyze(failure)
        
        # Store as reflection (pending resolution)
        memory = aegis.reflection(
            content=f"Build failure: {failure.error_message[:500]}",
            agent_id=self.agent_id,
            error_pattern=category.value,
            scope="global",
            metadata={
                "error_signature": self._compute_signature(failure),
                "stage": failure.stage,
                "environment": failure.environment,
                "analysis": analysis,
                "status": "unresolved",
                "first_seen": failure.timestamp,
                "occurrence_count": 1
            }
        )
        
        return {
            "status": "new_pattern",
            "pattern_id": memory.id,
            "category": category.value,
            "confidence": 0.0,
            "analysis": analysis,
            "message": f"🆕 New failure pattern detected. Analysis: {analysis['summary']}"
        }
    
    def _llm_analyze(self, failure: BuildFailure) -> Dict:
        """Use LLM to analyze unknown failure."""
        
        response = llm.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": """You are a CI/CD failure analyst.
Analyze the build failure and provide:
1. summary: One-line description of the issue
2. likely_cause: What probably caused this
3. suggested_fix: How to fix it
4. prevention: How to prevent in future
Output JSON."""},
                {"role": "user", "content": f"""
Build ID: {failure.build_id}
Stage: {failure.stage}
Error: {failure.error_message}
Stack trace: {failure.stack_trace or 'N/A'}
Changed files: {json.dumps(failure.changed_files)}
Branch: {failure.branch}
"""}
            ]
        )
        
        return json.loads(response.choices[0].message.content)
```

### Step 3: Resolution Tracker

```python
class ResolutionTracker:
    """Track how failures are resolved and learn from fixes."""
    
    def __init__(self, project_id: str):
        self.project_id = project_id
        self.agent_id = "ci-resolver"
    
    def record_resolution(self, failure_pattern_id: str, resolution: Dict):
        """Record how a failure was resolved."""
        
        # resolution = {
        #     "fixed_by": "developer@company.com",
        #     "fix_commit": "abc123",
        #     "fix_description": "Added AUTH_TOKEN to test fixtures",
        #     "fix_type": "code_change" | "config_change" | "environment_fix" | "rerun"
        # }
        
        # Get the original pattern
        pattern = aegis.get(failure_pattern_id)
        
        if resolution["fix_type"] == "rerun":
            # Flaky test - vote harmful (pattern wasn't a real issue)
            aegis.vote(
                memory_id=failure_pattern_id,
                vote="harmful",
                voter_agent_id=self.agent_id,
                context=f"Resolved by rerun - likely flaky"
            )
            
            # Update metadata
            aegis.delta([{
                "type": "update",
                "memory_id": failure_pattern_id,
                "metadata_patch": {
                    "flaky_count": (pattern.metadata.get("flaky_count", 0) + 1),
                    "status": "flaky"
                }
            }])
        else:
            # Real fix - update pattern with resolution
            aegis.delta([{
                "type": "update",
                "memory_id": failure_pattern_id,
                "metadata_patch": {
                    "status": "resolved",
                    "correct_approach": resolution["fix_description"],
                    "fix_commit": resolution["fix_commit"],
                    "fixed_by": resolution["fixed_by"],
                    "resolved_at": datetime.now().isoformat()
                }
            }])
            
            # Vote helpful (pattern correctly identified real issue)
            aegis.vote(
                memory_id=failure_pattern_id,
                vote="helpful",
                voter_agent_id=self.agent_id,
                context=f"Fixed by {resolution['fixed_by']}: {resolution['fix_description'][:100]}"
            )
            
            # Create a strategy for future prevention
            self._create_prevention_strategy(pattern, resolution)
    
    def _create_prevention_strategy(self, pattern, resolution: Dict):
        """Create strategy to prevent this failure in future."""
        
        aegis.add(
            content=f"When you see '{pattern.content[:100]}...', "
                   f"fix by: {resolution['fix_description']}",
            agent_id=self.agent_id,
            scope="global",
            memory_type="strategy",
            metadata={
                "type": "ci_fix_strategy",
                "error_pattern": pattern.metadata.get("error_pattern"),
                "stage": pattern.metadata.get("stage"),
                "fix_type": resolution["fix_type"]
            }
        )
    
    def track_recurrence(self, failure: BuildFailure, pattern_id: str):
        """Track when a failure recurs."""
        
        pattern = aegis.get(pattern_id)
        count = pattern.metadata.get("occurrence_count", 1) + 1
        
        aegis.delta([{
            "type": "update",
            "memory_id": pattern_id,
            "metadata_patch": {
                "occurrence_count": count,
                "last_seen": failure.timestamp
            }
        }])
        
        # If recurring after fix, might need better solution
        if pattern.metadata.get("status") == "resolved" and count > 3:
            aegis.vote(
                memory_id=pattern_id,
                vote="harmful",
                voter_agent_id=self.agent_id,
                context=f"Fix didn't stick - recurred {count} times"
            )
```

### Step 4: GitHub Actions Integration

```yaml
# .github/workflows/ci-with-memory.yml
name: CI with Memory

on: [push, pull_request]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Run tests
        id: tests
        continue-on-error: true
        run: |
          pytest tests/ --tb=short 2>&1 | tee test_output.txt
          echo "exit_code=$?" >> $GITHUB_OUTPUT
      
      - name: Analyze failure
        if: steps.tests.outputs.exit_code != '0'
        env:
          AEGIS_API_KEY: ${{ secrets.AEGIS_API_KEY }}
        run: |
          python scripts/analyze_failure.py \
            --build-id "${{ github.run_id }}" \
            --stage "test" \
            --error-file "test_output.txt" \
            --branch "${{ github.ref_name }}" \
            --commit "${{ github.sha }}"
      
      - name: Post fix suggestion
        if: steps.tests.outputs.exit_code != '0'
        uses: actions/github-script@v7
        with:
          script: |
            const analysis = require('./failure_analysis.json');
            
            let body = `## 🔴 Build Failed\n\n`;
            
            if (analysis.status === 'known_pattern') {
              body += `### Known Issue (${(analysis.confidence * 100).toFixed(0)}% confidence)\n`;
              body += `${analysis.message}\n\n`;
              body += `**Suggested Fix:**\n${analysis.suggested_fix}\n\n`;
              body += `_This issue has occurred ${analysis.similar_failures} times before._`;
            } else {
              body += `### New Issue\n`;
              body += `${analysis.analysis.summary}\n\n`;
              body += `**Likely Cause:** ${analysis.analysis.likely_cause}\n\n`;
              body += `**Suggested Fix:** ${analysis.analysis.suggested_fix}`;
            }
            
            github.rest.issues.createComment({
              issue_number: context.issue.number,
              owner: context.repo.owner,
              repo: context.repo.repo,
              body: body
            });
```

```python
# scripts/analyze_failure.py
import argparse
import json
from aegis_memory import AegisClient
from ci_memory import FailureAnalyzer, BuildFailure

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--build-id", required=True)
    parser.add_argument("--stage", required=True)
    parser.add_argument("--error-file", required=True)
    parser.add_argument("--branch", required=True)
    parser.add_argument("--commit", required=True)
    args = parser.parse_args()
    
    # Read error output
    with open(args.error_file) as f:
        error_output = f.read()
    
    # Create failure object
    failure = BuildFailure(
        build_id=args.build_id,
        stage=args.stage,
        error_message=error_output[:2000],
        stack_trace=extract_stack_trace(error_output),
        exit_code=1,
        changed_files=get_changed_files(),
        environment="ci",
        branch=args.branch,
        commit_sha=args.commit,
        timestamp=datetime.now().isoformat()
    )
    
    # Analyze
    analyzer = FailureAnalyzer(project_id="my-project")
    analysis = analyzer.analyze(failure)
    
    # Write result
    with open("failure_analysis.json", "w") as f:
        json.dump(analysis, f)

if __name__ == "__main__":
    main()
```

---

## Production Tips

### 1. Signature Normalization
```python
# Remove noise from error messages for better matching
def normalize_error(error: str) -> str:
    # Remove timestamps
    error = re.sub(r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}', 'TIMESTAMP', error)
    # Remove line numbers
    error = re.sub(r'line \d+', 'line N', error)
    # Remove file paths (keep filename)
    error = re.sub(r'/[^\s]+/([^/\s]+)', r'\1', error)
    return error
```

### 2. Flaky Test Quarantine
```python
def should_quarantine(pattern_id: str) -> bool:
    pattern = aegis.get(pattern_id)
    flaky_count = pattern.metadata.get("flaky_count", 0)
    occurrence_count = pattern.metadata.get("occurrence_count", 1)
    
    # Quarantine if >50% of occurrences resolve by rerun
    return flaky_count / occurrence_count > 0.5
```

### 3. Pattern Aging
```python
# Reduce confidence of old patterns that haven't recurred
def age_patterns():
    patterns = aegis.query(
        query="*",
        agent_id="ci-analyzer",
        include_types=["reflection"],
        top_k=1000
    )
    
    for pattern in patterns:
        last_seen = pattern.metadata.get("last_seen")
        if last_seen and days_since(last_seen) > 90:
            aegis.delta([{
                "type": "deprecate",
                "memory_id": pattern.id,
                "deprecation_reason": "Not seen in 90 days"
            }])
```

---

## Expected Outcomes

| Metric | Without Aegis | With Aegis |
|--------|---------------|------------|
| Time to diagnose | 15-60 min | <1 min |
| Repeat failures | Common | Rare (known fixes) |
| Flaky test detection | Manual | Automatic |
| Knowledge transfer | Tribal | Systematic |
| Fix effectiveness | Unknown | Measured |

---

## Next Steps

- [Recipe 4: Code Review Swarm](./04-code-review-swarm.md) - Catch issues before CI
- [Recipe 6: Debugging Agent](./06-debugging-agent-reflection.md) - Deep failure analysis
