# Community Playbooks

Share your agent's best strategies with the Aegis community!

## 🏆 Featured Contributors

*Your name could be here! Submit a PR with quality strategies.*

## 📜 Contribution Guidelines

### What Makes a Good Playbook Entry?

#### ✅ Good Strategies

```json
{
  "content": "When implementing retry logic, use exponential backoff with jitter. Start with a base delay of 100ms, double it on each retry, and add random jitter (±25%) to prevent thundering herd. Cap at 30 seconds max delay. This pattern works for: API calls, database connections, distributed locks.",
  "memory_type": "strategy",
  "namespace": "aegis/resilience/retry",
  "metadata": {
    "category": "resilience",
    "tags": ["retry", "exponential-backoff", "jitter"],
    "applicable_contexts": ["api-clients", "distributed-systems", "microservices"]
  }
}
```

**Why it's good:**
- Specific numbers (100ms, 25%, 30s)
- Explains the why (thundering herd)
- Lists applicable contexts
- Properly namespaced

#### ✅ Good Reflections

```json
{
  "content": "REFLECTION: Used a simple counter-based retry that hammered a failing service, causing cascading failures. All clients retried simultaneously after each failure. Exponential backoff with jitter spread the retries over time, allowing the service to recover.",
  "memory_type": "reflection",
  "namespace": "aegis/resilience/retry",
  "error_pattern": "thundering-herd",
  "metadata": {
    "category": "resilience",
    "tags": ["retry", "cascading-failure", "recovery"],
    "correct_approach": "Implement exponential backoff with jitter"
  }
}
```

**Why it's good:**
- Describes the mistake clearly
- Explains the consequence
- Provides the correction
- Uses error_pattern for categorization

#### ❌ Bad Entries

```json
{
  "content": "Use retry logic",
  "memory_type": "strategy"
}
```

**Why it's bad:**
- Too vague
- No actionable details
- No namespace
- No context

### Submission Process

1. **Fork** the repository
2. **Create** your playbook file: `playbooks/community/[topic].json`
3. **Follow** the schema (see below)
4. **Test** your entries load correctly
5. **Submit** a Pull Request

### File Naming Convention

```
community/
├── kubernetes.json         # K8s strategies
├── aws-lambda.json        # AWS Lambda patterns
├── graphql.json           # GraphQL best practices
├── rust.json              # Rust-specific strategies
├── llm-prompting.json     # LLM/AI strategies
└── your-topic.json        # Your contribution!
```

### Schema Reference

```json
{
  "metadata": {
    "version": "1.0.0",
    "name": "Your Playbook Name",
    "description": "What this playbook covers",
    "author": "Your Name/GitHub",
    "created_at": "YYYY-MM-DD"
  },
  "entries": [
    {
      "content": "Required: The strategy or reflection text",
      "memory_type": "strategy|reflection",
      "namespace": "aegis/category/subcategory",
      "metadata": {
        "category": "category-name",
        "tags": ["tag1", "tag2"],
        "applicable_contexts": ["context1", "context2"]
      },
      "error_pattern": "for-reflections-only"
    }
  ]
}
```

### Quality Checklist

Before submitting, verify each entry:

- [ ] Content is specific and actionable
- [ ] Content explains *why*, not just *what*
- [ ] Namespace follows `aegis/category/subcategory` pattern
- [ ] Tags are relevant and help discoverability
- [ ] Reflections include `error_pattern`
- [ ] No duplicate content from genesis.json
- [ ] Tested locally (entries load without errors)

### Testing Your Playbook

```python
import json

# Validate JSON
with open('playbooks/community/your-topic.json') as f:
    data = json.load(f)
    
# Check required fields
for entry in data['entries']:
    assert 'content' in entry
    assert 'memory_type' in entry
    assert entry['memory_type'] in ['strategy', 'reflection']
    assert 'namespace' in entry
    print(f"✓ {entry['namespace']}: {entry['content'][:50]}...")
```

### Namespace Guidelines

```
aegis/
├── python/           # Python-specific
│   ├── async/       # Async patterns
│   ├── api/         # API development
│   └── testing/     # Python testing
├── javascript/       # JS/Node.js
│   ├── react/       # React patterns
│   └── node/        # Node.js specific
├── infrastructure/   # DevOps/Infra
│   ├── kubernetes/  # K8s patterns
│   ├── docker/      # Docker patterns
│   └── terraform/   # IaC patterns
├── database/         # Database patterns
│   ├── postgresql/  # PostgreSQL specific
│   └── mongodb/     # MongoDB specific
├── ai/               # AI/ML patterns
│   ├── prompting/   # LLM prompting
│   └── agents/      # Agent patterns
└── architecture/     # System design
    ├── microservices/
    └── resilience/
```

### Review Process

1. **Automated checks**: JSON validity, schema compliance
2. **Human review**: Quality, accuracy, no duplicates
3. **Community feedback**: 2 approvals needed for merge
4. **Integration**: Merged entries added to community bundle

### Recognition

Contributors with merged PRs get:
- Name in CONTRIBUTORS.md
- "Community Contributor" badge (coming soon)
- Shoutout in release notes

## 🚀 Ideas for Contributions

Looking for inspiration? Here are topics we'd love to see:

- [ ] Kubernetes deployment patterns
- [ ] AWS service integration strategies
- [ ] GraphQL schema design
- [ ] Rust error handling patterns
- [ ] LLM prompt engineering strategies
- [ ] Security hardening patterns
- [ ] Performance optimization strategies
- [ ] Monitoring and observability patterns

## ❓ Questions?

Open an issue with the `playbook-contribution` label or reach out on Discord.
