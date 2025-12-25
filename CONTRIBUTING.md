# Contributing to Aegis Memory

Thank you for your interest in contributing to Aegis Memory! This document provides guidelines and information for contributors.

## 🎯 Project Philosophy

Key principles we follow:

1. **Agent-native, multi-agent first** - Features should make multi-agent systems more reliable
2. **Context engineering > raw storage** - We're not just a vector store
3. **Monday-morning usable** - Prioritize DX and easy adoption
4. **Boring to run** - Production reliability over clever features
5. **Open and composable** - No walled garden

## 🚀 Quick Start for Contributors

### Setup Development Environment

```bash
# Clone the repo
git clone https://github.com/quantifylabs/aegis-memory.git
cd aegis-memory

# Create virtual environment
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows

# Install dev dependencies
pip install -e ".[dev]"

# Start local services
docker-compose up -d

# Run tests
pytest
```

### Code Style

We use [Ruff](https://github.com/astral-sh/ruff) for linting and formatting:

```bash
# Check code
ruff check .

# Format code
ruff format .

# Type checking
mypy aegis_memory
```

## 📝 How to Contribute

### Reporting Issues

- **Bug Reports**: Include steps to reproduce, expected behavior, and actual behavior
- **Feature Requests**: Explain the use case and why it benefits multi-agent systems
- **Questions**: Use GitHub Discussions instead of Issues

### Pull Requests

1. **Fork and branch**: Create a branch from `main` with a descriptive name
   - `feat/add-langgraph-integration`
   - `fix/query-timeout-handling`
   - `docs/improve-quickstart`

2. **Make changes**: Follow the code style and add tests

3. **Test locally**:
   ```bash
   pytest tests/
   ruff check .
   ```

4. **Write a good PR description**:
   - What does this change?
   - Why is it needed?
   - How was it tested?

5. **Link related issues**: Use "Fixes #123" or "Relates to #456"

### Commit Messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add LangGraph memory integration
fix: handle timeout in cross-agent query
docs: add quickstart guide for CrewAI
test: add tests for ACE voting endpoint
chore: update dependencies
```

## 🏗️ Architecture Overview

```
aegis-memory/
├── aegis_memory/           # Python SDK (pip installable)
│   ├── client.py           # Main client
│   └── integrations/       # Framework integrations
├── server/                 # FastAPI server
│   ├── models.py           # SQLAlchemy models
│   ├── routes.py           # API endpoints
│   ├── routes_ace.py       # ACE pattern endpoints
│   └── ...
├── examples/               # Usage examples
├── tests/                  # Test suite
└── docs/                   # Documentation
```

### Key Components

- **Memory Model**: Core data model with scopes, namespaces, ACE fields
- **Repositories**: Database operations (`memory_repository.py`, `ace_repository.py`)
- **Routes**: API endpoints (`routes.py` for core, `routes_ace.py` for ACE patterns)
- **SDK**: Python client for easy integration

## 🧪 Testing

### Running Tests

```bash
# All tests
pytest

# Specific test file
pytest tests/test_memory.py

# With coverage
pytest --cov=aegis_memory
```

### Writing Tests

- Use `pytest` and `pytest-asyncio`
- Test both success and error cases
- Mock external services (OpenAI, etc.)

```python
import pytest
from aegis_memory import AegisClient

@pytest.mark.asyncio
async def test_add_memory():
    client = AegisClient(api_key="test", base_url="http://localhost:8000")
    result = client.add("test content", agent_id="test-agent")
    assert "id" in result
```

## 📚 Documentation

### Updating Docs

- Keep README.md focused on quick start
- Detailed docs go in `docs/`
- Code examples should be runnable

### Adding Examples

Put examples in `examples/` with clear naming:

```
examples/
├── 01-quickstart/
├── 02-multi-agent-handoff/
├── 03-langchain-integration/
├── 04-crewai-integration/
└── 05-ace-patterns/
```

## 🔒 Security

- **Don't commit secrets** - Use environment variables
- **Report vulnerabilities** - Email security@quantifylabs.ai, not public issues
- **Review dependencies** - Be cautious with new dependencies

## 📋 Review Process

1. **Automated checks**: CI must pass (tests, linting)
2. **Code review**: At least one maintainer approval
3. **Documentation**: Update docs if behavior changes
4. **Changelog**: Add entry for user-facing changes

## 🎖️ Recognition

Contributors are recognized in:
- Release notes
- Project README (for significant contributions)

## ❓ Questions?

- **GitHub Discussions**: General questions
- **Email**: hello@quantifylabs.ai

---

Thank you for contributing to Aegis Memory! 🛡️
