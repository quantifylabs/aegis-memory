# Aegis CLI Reference

Complete reference for the Aegis Memory command-line interface.

## Installation

```bash
pip install aegis-memory
```

## Configuration

### `aegis config init`

Interactive first-run setup.

```bash
aegis config init          # Interactive
aegis config init -y       # Use defaults (non-interactive)
```

### `aegis config show`

Display current configuration.

```bash
aegis config show
```

### `aegis config set`

Set a configuration value.

```bash
aegis config set output.format json
aegis config set profiles.local.api_url http://localhost:8000
```

### `aegis config use`

Switch active profile.

```bash
aegis config use production
```

### `aegis config profiles`

List all configured profiles.

```bash
aegis config profiles
```

---

## Server Status

### `aegis status`

Check server health and connection.

```bash
aegis status           # Pretty output
aegis status -j        # JSON output
aegis status -q        # Quiet (exit code only)
```

**Exit codes:**
- `0` - Server healthy
- `1` - Server unhealthy
- `2` - Connection failed

### `aegis stats`

Show namespace statistics.

```bash
aegis stats                    # Default namespace
aegis stats -n production      # Specific namespace
aegis stats -a executor        # Filter by agent
aegis stats -j                 # JSON output
```

---

## Memory Operations

### `aegis add`

Add a memory.

```bash
aegis add "Memory content"                    # Basic
aegis add "Strategy" -t strategy -s global    # Strategy with global scope
aegis add -f ./insight.txt -t reflection      # From file
echo "Piped" | aegis add                      # From stdin
```

**Options:**
| Flag | Short | Description |
|------|-------|-------------|
| `--agent` | `-a` | Agent ID |
| `--user` | `-u` | User ID |
| `--namespace` | `-n` | Namespace |
| `--scope` | `-s` | Scope: `agent-private`, `agent-shared`, `global` |
| `--type` | `-t` | Type: `standard`, `strategy`, `reflection` |
| `--share-with` | | Agent IDs to share with |
| `--metadata` | `-m` | JSON metadata |
| `--ttl` | | TTL in seconds |
| `--file` | `-f` | Read content from file |
| `--json` | `-j` | JSON output |

### `aegis query`

Semantic search for memories.

```bash
aegis query "search text"                     # Basic search
aegis query "patterns" -t strategy -k 5       # Filter by type
aegis query "task" -x planner,coordinator     # Cross-agent query
aegis query "test" --ids-only                 # IDs only for scripting
```

**Options:**
| Flag | Short | Description |
|------|-------|-------------|
| `--agent` | `-a` | Requesting agent ID |
| `--namespace` | `-n` | Namespace |
| `--top-k` | `-k` | Number of results (default: 10) |
| `--min-score` | | Minimum similarity score |
| `--type` | `-t` | Filter by memory type |
| `--cross-agent` | `-x` | Query across these agents |
| `--json` | `-j` | JSON output |
| `--full` | | Show full content |
| `--ids-only` | | Print only memory IDs |

### `aegis get`

Get a single memory by ID.

```bash
aegis get 7f3a8b2c1d4e                        # Pretty output
aegis get 7f3a8b2c1d4e -j                     # JSON output
aegis get 7f3a8b2c1d4e --content-only         # Content only (for piping)
```

### `aegis delete`

Delete a memory.

```bash
aegis delete 7f3a8b2c1d4e                     # With confirmation
aegis delete 7f3a8b2c1d4e -f                  # Force (no confirmation)
```

---

## Voting

### `aegis vote`

Vote on memory usefulness.

```bash
aegis vote <id> helpful                       # Vote helpful
aegis vote <id> harmful -c "Caused bug"       # Vote harmful with context
aegis vote <id> helpful -t feature-auth       # Link to task
```

**Options:**
| Flag | Short | Description |
|------|-------|-------------|
| `--voter` | `-v` | Voting agent ID |
| `--context` | `-c` | Why this vote |
| `--task` | `-t` | Related task/feature ID |
| `--json` | `-j` | JSON output |

---

## Playbook

### `aegis playbook`

Query proven strategies and reflections.

```bash
aegis playbook "error handling"               # Search playbook
aegis playbook "API" -t strategy -e 0.5       # Only high-rated strategies
aegis playbook "patterns" -k 10 --json        # JSON output
```

**Options:**
| Flag | Short | Description |
|------|-------|-------------|
| `--agent` | `-a` | Agent ID |
| `--namespace` | `-n` | Namespace |
| `--top-k` | `-k` | Number of results (default: 20) |
| `--min-effectiveness` | `-e` | Minimum effectiveness score |
| `--type` | `-t` | `strategy`, `reflection`, or both |
| `--json` | `-j` | JSON output |

---

## Session Progress

### `aegis progress list`

List all sessions.

```bash
aegis progress list                           # All sessions
aegis progress list -s active                 # Filter by status
```

### `aegis progress show`

Show session details.

```bash
aegis progress show build-dashboard
```

### `aegis progress create`

Create a new session.

```bash
aegis progress create build-api -a executor
aegis progress create feature-x -s "Building feature X" -t 5
```

**Options:**
| Flag | Short | Description |
|------|-------|-------------|
| `--agent` | `-a` | Agent ID |
| `--namespace` | `-n` | Namespace |
| `--total` | `-t` | Total items count |
| `--summary` | `-s` | Initial summary |

### `aegis progress update`

Update session progress.

```bash
aegis progress update build-api -c auth -c routing
aegis progress update build-api -i api-client
aegis progress update build-api -b "payments:Waiting for API keys"
aegis progress update build-api --status completed
```

**Options:**
| Flag | Short | Description |
|------|-------|-------------|
| `--completed` | `-c` | Mark item complete (repeatable) |
| `--in-progress` | `-i` | Set current item |
| `--next` | | Next items (comma-separated) |
| `--blocked` | `-b` | Blocked item (`item:reason`) |
| `--summary` | `-s` | Update summary |
| `--status` | | Set status |

---

## Feature Tracking

### `aegis features list`

List all features.

```bash
aegis features list                           # All features
aegis features list -s in_progress            # Filter by status
aegis features list -c auth                   # Filter by category
```

### `aegis features show`

Show feature details.

```bash
aegis features show user-auth
```

### `aegis features create`

Create a feature.

```bash
aegis features create user-auth \
    -d "User authentication with JWT" \
    -c auth \
    -t "Can login" \
    -t "Can logout"
```

**Options:**
| Flag | Short | Description |
|------|-------|-------------|
| `--description` | `-d` | Feature description (required) |
| `--category` | `-c` | Category |
| `--session` | | Link to session |
| `--namespace` | `-n` | Namespace |
| `--test-step` | `-t` | Test step (repeatable) |

### `aegis features update`

Update feature status.

```bash
aegis features update user-auth -s in_progress --implemented-by executor
```

### `aegis features verify`

Mark feature as passing.

```bash
aegis features verify user-auth --by qa-agent
```

### `aegis features fail`

Mark feature as failed.

```bash
aegis features fail 2fa-totp -r "TOTP validation fails on time skew"
```

---

## Data Management

### `aegis export`

Export memories to file.

```bash
aegis export > backup.jsonl                   # To stdout
aegis export -o backup.jsonl                  # To file
aegis export -n prod -f json -o prod.json     # JSON format
aegis export --include-embeddings             # Include vectors
```

**Options:**
| Flag | Short | Description |
|------|-------|-------------|
| `--namespace` | `-n` | Filter namespace |
| `--agent` | `-a` | Filter agent |
| `--format` | `-f` | `jsonl` or `json` |
| `--include-embeddings` | | Include embedding vectors |
| `--output` | `-o` | Output file |
| `--limit` | | Max memories |

### `aegis import`

Import memories from file.

```bash
aegis import backup.jsonl                     # Import from file
aegis import backup.jsonl -n staging          # Override namespace
aegis import backup.jsonl --dry-run           # Validate only
```

**Options:**
| Flag | Short | Description |
|------|-------|-------------|
| `--namespace` | `-n` | Override namespace |
| `--agent` | `-a` | Override agent |
| `--skip-duplicates` | | Skip duplicates (default: true) |
| `--dry-run` | | Validate without importing |

---

## Other

### `aegis version`

Show version information.

```bash
aegis version
```

---

## Environment Variables

| Variable | Description |
|----------|-------------|
| `AEGIS_API_KEY` | API key (highest priority) |
| `AEGIS_API_URL` | Server URL |
| `AEGIS_PROFILE` | Active profile |
| `AEGIS_NAMESPACE` | Default namespace |
| `AEGIS_AGENT_ID` | Default agent ID |

---

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | General error |
| 2 | Connection error |
| 3 | Authentication error |
| 4 | Not found |
| 5 | Validation error |
