"""
Cross-platform benchmark runner for Aegis Memory.

Usage:
    python run_benchmark.py
    python run_benchmark.py --count 500 --concurrency 10
"""

import argparse
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent


def run(cmd: list[str], label: str):
    print(f"\n{'=' * 50}")
    print(f"  {label}")
    print(f"{'=' * 50}")
    result = subprocess.run(cmd, cwd=str(SCRIPT_DIR))
    if result.returncode != 0:
        print(f"  FAILED (exit code {result.returncode})")
        sys.exit(result.returncode)


def main():
    parser = argparse.ArgumentParser(description="Aegis Memory Benchmark Runner")
    parser.add_argument("--count", type=int, default=200, help="Number of memories to generate")
    parser.add_argument("--queries", type=int, default=50, help="Number of queries")
    parser.add_argument("--cross-queries", type=int, default=20, help="Number of cross-agent queries")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--base-url", type=str, default="http://localhost:8000", help="Server URL")
    parser.add_argument("--api-key", type=str, default="dev-secret-key", help="API key")
    parser.add_argument("--concurrency", type=int, default=5, help="Max concurrent requests")
    args = parser.parse_args()

    py = sys.executable

    # Step 1: Machine profile
    run([py, "machine_profile.py"], "Machine Profile")

    # Step 2: Generate dataset
    run([
        py, "generate_dataset.py",
        "--count", str(args.count),
        "--queries", str(args.queries),
        "--cross-queries", str(args.cross_queries),
        "--seed", str(args.seed),
        "--output", "dataset.jsonl",
    ], "Generate Dataset")

    # Step 3: Run workload
    run([
        py, "query_workload.py",
        "--dataset", "dataset.jsonl",
        "--base-url", args.base_url,
        "--api-key", args.api_key,
        "--concurrency", str(args.concurrency),
        "--output", "results.json",
    ], "Run Workload")

    print(f"\n{'=' * 50}")
    print("  Benchmark Complete")
    print(f"  Results: {SCRIPT_DIR / 'results.json'}")
    print(f"{'=' * 50}")


if __name__ == "__main__":
    main()
