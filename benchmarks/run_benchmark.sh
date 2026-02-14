#!/usr/bin/env bash
set -euo pipefail

# Aegis Memory Benchmark Runner
# Usage: cd benchmarks && bash run_benchmark.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

SEED="${SEED:-42}"
COUNT="${COUNT:-1000}"
QUERIES="${QUERIES:-100}"
BASE_URL="${BASE_URL:-http://localhost:8000}"
API_KEY="${API_KEY:-dev-secret-key}"
CONCURRENCY="${CONCURRENCY:-10}"

echo "=== Aegis Memory Benchmark ==="
echo ""

# Step 1: Machine profile
echo "--- Machine Profile ---"
python machine_profile.py
echo ""

# Step 2: Generate dataset
echo "--- Generating Dataset ---"
python generate_dataset.py \
    --count "$COUNT" \
    --queries "$QUERIES" \
    --seed "$SEED" \
    --output dataset.jsonl
echo ""

# Step 3: Run workload
echo "--- Running Workload ---"
python query_workload.py \
    --dataset dataset.jsonl \
    --base-url "$BASE_URL" \
    --api-key "$API_KEY" \
    --concurrency "$CONCURRENCY"
echo ""

echo "=== Benchmark Complete ==="
