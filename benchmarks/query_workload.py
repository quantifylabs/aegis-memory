"""
Production benchmark workload for Aegis Memory.

Runs a multi-phase benchmark against a live server:
  Phase 0: Health check + warm-up (not measured)
  Phase 1: Sequential single-add latency
  Phase 2: Batch add latency (groups of 50)
  Phase 3: Concurrent add throughput
  Phase 4: Sequential query latency (warm DB)
  Phase 5: Concurrent query throughput
  Phase 6: Cross-agent query latency
  Phase 7: Vote latency
  Phase 8: Deduplication (re-insert existing content)

Usage:
    python query_workload.py --dataset dataset.jsonl --base-url http://localhost:8000
    python query_workload.py --dataset dataset.jsonl --output results.json
"""

import argparse
import asyncio
import json
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx


def percentile(data: list[float], p: float) -> float:
    """Calculate percentile from sorted data."""
    if not data:
        return 0.0
    s = sorted(data)
    idx = int(len(s) * p / 100)
    return s[min(idx, len(s) - 1)]


def summarize(latencies: list[float], wall_time: float) -> dict:
    """Compute latency summary stats."""
    if not latencies:
        return {"count": 0}
    return {
        "count": len(latencies),
        "p50_ms": round(statistics.median(latencies), 1),
        "p95_ms": round(percentile(latencies, 95), 1),
        "p99_ms": round(percentile(latencies, 99), 1),
        "mean_ms": round(statistics.mean(latencies), 1),
        "min_ms": round(min(latencies), 1),
        "max_ms": round(max(latencies), 1),
        "wall_time_s": round(wall_time, 2),
        "throughput_ops": round(len(latencies) / wall_time, 1) if wall_time > 0 else 0,
    }


def print_phase(name: str, stats: dict, errors: int = 0):
    """Pretty-print a phase result."""
    print(f"\n--- {name} ---")
    if stats["count"] == 0:
        print("  (no data)")
        return
    print(f"  Requests:   {stats['count']}")
    print(f"  p50:        {stats['p50_ms']:.1f} ms")
    print(f"  p95:        {stats['p95_ms']:.1f} ms")
    print(f"  p99:        {stats['p99_ms']:.1f} ms")
    print(f"  mean:       {stats['mean_ms']:.1f} ms")
    print(f"  min/max:    {stats['min_ms']:.1f} / {stats['max_ms']:.1f} ms")
    print(f"  throughput: {stats['throughput_ops']:.1f} ops/s")
    if errors > 0:
        print(f"  ERRORS:     {errors}")


async def run_workload(dataset_path: str, base_url: str, api_key: str, concurrency: int, output_path: str | None):
    """Run the full benchmark workload."""
    # Load dataset
    memories = []
    queries = []
    cross_queries = []

    with open(dataset_path) as f:
        for line in f:
            record = json.loads(line)
            rtype = record.get("type", "memory")
            if rtype == "query":
                queries.append(record)
            elif rtype == "cross_agent_query":
                cross_queries.append(record)
            else:
                memories.append(record)

    print(f"Dataset: {len(memories)} memories, {len(queries)} queries, {len(cross_queries)} cross-agent queries")

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    results = {"timestamp": datetime.now(timezone.utc).isoformat(), "base_url": base_url, "dataset": dataset_path}
    memory_ids = []  # Track inserted memory IDs for vote phase

    async with httpx.AsyncClient(base_url=base_url, headers=headers, timeout=60.0) as client:

        # ── Phase 0: Health check + warm-up ──
        print("\nPhase 0: Health check + warm-up")
        try:
            resp = await client.get("/health")
            health = resp.json()
            print(f"  Server: {health.get('status', 'unknown')} | version: {health.get('version', '?')}")
            results["server_version"] = health.get("version", "unknown")
        except Exception as e:
            print(f"  FATAL: Cannot reach server at {base_url}: {e}")
            sys.exit(1)

        # Warm-up: 5 inserts + 3 queries (not measured)
        print("  Warming up (5 adds + 3 queries)...")
        for mem in memories[:5]:
            try:
                resp = await client.post("/memories/add", json={
                    "content": mem["content"], "agent_id": mem["agent_id"],
                    "namespace": mem["namespace"], "scope": mem["scope"],
                    "memory_type": mem["memory_type"],
                    "shared_with_agents": mem.get("shared_with_agents", []),
                    "metadata": mem.get("metadata", {}),
                })
                if resp.status_code == 200:
                    body = resp.json()
                    if "id" in body:
                        memory_ids.append(body["id"])
            except Exception:
                pass
        for q in queries[:3]:
            try:
                await client.post("/memories/query", json={
                    "query": q["query_text"], "agent_id": q["agent_id"],
                    "namespace": q["namespace"], "top_k": q["top_k"],
                })
            except Exception:
                pass
        print("  Warm-up complete")

        # ── Phase 1: Sequential single-add latency ──
        phase1_latencies = []
        phase1_errors = 0
        seq_adds = memories[5:55]  # 50 sequential adds
        print(f"\nPhase 1: Sequential add ({len(seq_adds)} memories)...")
        t0 = time.perf_counter()
        for mem in seq_adds:
            start = time.perf_counter()
            try:
                resp = await client.post("/memories/add", json={
                    "content": mem["content"], "agent_id": mem["agent_id"],
                    "namespace": mem["namespace"], "scope": mem["scope"],
                    "memory_type": mem["memory_type"],
                    "shared_with_agents": mem.get("shared_with_agents", []),
                    "metadata": mem.get("metadata", {}),
                })
                elapsed = (time.perf_counter() - start) * 1000
                if resp.status_code == 200:
                    phase1_latencies.append(elapsed)
                    body = resp.json()
                    if "id" in body:
                        memory_ids.append(body["id"])
                else:
                    phase1_errors += 1
                    print(f"    ERR {resp.status_code}: {resp.text[:100]}")
            except Exception as e:
                phase1_errors += 1
                print(f"    ERR: {e}")
        phase1_wall = time.perf_counter() - t0
        results["phase1_sequential_add"] = summarize(phase1_latencies, phase1_wall)
        results["phase1_sequential_add"]["errors"] = phase1_errors
        print_phase("Phase 1: Sequential Add", results["phase1_sequential_add"], phase1_errors)

        # ── Phase 2: Batch add latency ──
        batch_size = 20
        batch_memories = memories[55:155]  # 100 memories in batches of 20
        num_batches = len(batch_memories) // batch_size
        phase2_latencies = []
        phase2_errors = 0
        print(f"\nPhase 2: Batch add ({num_batches} batches x {batch_size})...")
        t0 = time.perf_counter()
        for i in range(num_batches):
            batch = batch_memories[i * batch_size:(i + 1) * batch_size]
            payload = {
                "items": [{
                    "content": m["content"], "agent_id": m["agent_id"],
                    "namespace": m["namespace"], "scope": m["scope"],
                    "memory_type": m["memory_type"],
                    "shared_with_agents": m.get("shared_with_agents", []),
                    "metadata": m.get("metadata", {}),
                } for m in batch]
            }
            start = time.perf_counter()
            try:
                resp = await client.post("/memories/add_batch", json=payload)
                elapsed = (time.perf_counter() - start) * 1000
                if resp.status_code == 200:
                    phase2_latencies.append(elapsed)
                    body = resp.json()
                    for item in body.get("results", []):
                        if "id" in item:
                            memory_ids.append(item["id"])
                else:
                    phase2_errors += 1
                    print(f"    ERR {resp.status_code}: {resp.text[:100]}")
            except Exception as e:
                phase2_errors += 1
                print(f"    ERR: {e}")
        phase2_wall = time.perf_counter() - t0
        results["phase2_batch_add"] = summarize(phase2_latencies, phase2_wall)
        results["phase2_batch_add"]["errors"] = phase2_errors
        results["phase2_batch_add"]["batch_size"] = batch_size
        print_phase("Phase 2: Batch Add", results["phase2_batch_add"], phase2_errors)

        # ── Phase 3: Concurrent add throughput ──
        conc_adds = memories[155:]
        phase3_latencies = []
        phase3_errors = 0
        sem = asyncio.Semaphore(concurrency)

        async def concurrent_add(mem):
            nonlocal phase3_errors
            async with sem:
                start = time.perf_counter()
                try:
                    resp = await client.post("/memories/add", json={
                        "content": mem["content"], "agent_id": mem["agent_id"],
                        "namespace": mem["namespace"], "scope": mem["scope"],
                        "memory_type": mem["memory_type"],
                        "shared_with_agents": mem.get("shared_with_agents", []),
                        "metadata": mem.get("metadata", {}),
                    })
                    elapsed = (time.perf_counter() - start) * 1000
                    if resp.status_code == 200:
                        phase3_latencies.append(elapsed)
                        body = resp.json()
                        if "id" in body:
                            memory_ids.append(body["id"])
                    else:
                        phase3_errors += 1
                except Exception:
                    phase3_errors += 1

        print(f"\nPhase 3: Concurrent add ({len(conc_adds)} memories, concurrency={concurrency})...")
        t0 = time.perf_counter()
        await asyncio.gather(*[concurrent_add(m) for m in conc_adds])
        phase3_wall = time.perf_counter() - t0
        results["phase3_concurrent_add"] = summarize(phase3_latencies, phase3_wall)
        results["phase3_concurrent_add"]["errors"] = phase3_errors
        results["phase3_concurrent_add"]["concurrency"] = concurrency
        print_phase("Phase 3: Concurrent Add", results["phase3_concurrent_add"], phase3_errors)

        # ── Phase 4: Sequential query latency ──
        phase4_latencies = []
        phase4_errors = 0
        seq_queries = queries[:30]
        print(f"\nPhase 4: Sequential query ({len(seq_queries)} queries)...")
        t0 = time.perf_counter()
        for q in seq_queries:
            start = time.perf_counter()
            try:
                resp = await client.post("/memories/query", json={
                    "query": q["query_text"], "agent_id": q["agent_id"],
                    "namespace": q["namespace"], "top_k": q["top_k"],
                })
                elapsed = (time.perf_counter() - start) * 1000
                if resp.status_code == 200:
                    phase4_latencies.append(elapsed)
                else:
                    phase4_errors += 1
                    print(f"    ERR {resp.status_code}: {resp.text[:100]}")
            except Exception as e:
                phase4_errors += 1
                print(f"    ERR: {e}")
        phase4_wall = time.perf_counter() - t0
        results["phase4_sequential_query"] = summarize(phase4_latencies, phase4_wall)
        results["phase4_sequential_query"]["errors"] = phase4_errors
        print_phase("Phase 4: Sequential Query", results["phase4_sequential_query"], phase4_errors)

        # ── Phase 5: Concurrent query throughput ──
        conc_queries = queries[30:]
        phase5_latencies = []
        phase5_errors = 0

        async def concurrent_query(q):
            nonlocal phase5_errors
            async with sem:
                start = time.perf_counter()
                try:
                    resp = await client.post("/memories/query", json={
                        "query": q["query_text"], "agent_id": q["agent_id"],
                        "namespace": q["namespace"], "top_k": q["top_k"],
                    })
                    elapsed = (time.perf_counter() - start) * 1000
                    if resp.status_code == 200:
                        phase5_latencies.append(elapsed)
                    else:
                        phase5_errors += 1
                except Exception:
                    phase5_errors += 1

        print(f"\nPhase 5: Concurrent query ({len(conc_queries)} queries, concurrency={concurrency})...")
        t0 = time.perf_counter()
        await asyncio.gather(*[concurrent_query(q) for q in conc_queries])
        phase5_wall = time.perf_counter() - t0
        results["phase5_concurrent_query"] = summarize(phase5_latencies, phase5_wall)
        results["phase5_concurrent_query"]["errors"] = phase5_errors
        results["phase5_concurrent_query"]["concurrency"] = concurrency
        print_phase("Phase 5: Concurrent Query", results["phase5_concurrent_query"], phase5_errors)

        # ── Phase 6: Cross-agent query latency ──
        phase6_latencies = []
        phase6_errors = 0
        print(f"\nPhase 6: Cross-agent query ({len(cross_queries)} queries)...")
        t0 = time.perf_counter()
        for cq in cross_queries:
            start = time.perf_counter()
            try:
                resp = await client.post("/memories/query_cross_agent", json={
                    "query": cq["query_text"],
                    "requesting_agent_id": cq["requesting_agent_id"],
                    "target_agent_ids": cq["target_agent_ids"],
                    "namespace": cq["namespace"],
                    "top_k": cq["top_k"],
                })
                elapsed = (time.perf_counter() - start) * 1000
                if resp.status_code == 200:
                    phase6_latencies.append(elapsed)
                else:
                    phase6_errors += 1
                    print(f"    ERR {resp.status_code}: {resp.text[:100]}")
            except Exception as e:
                phase6_errors += 1
                print(f"    ERR: {e}")
        phase6_wall = time.perf_counter() - t0
        results["phase6_cross_agent_query"] = summarize(phase6_latencies, phase6_wall)
        results["phase6_cross_agent_query"]["errors"] = phase6_errors
        print_phase("Phase 6: Cross-Agent Query", results["phase6_cross_agent_query"], phase6_errors)

        # ── Phase 7: Vote latency ──
        vote_ids = memory_ids[:20] if len(memory_ids) >= 20 else memory_ids
        phase7_latencies = []
        phase7_errors = 0
        print(f"\nPhase 7: Vote ({len(vote_ids)} votes)...")
        t0 = time.perf_counter()
        for i, mid in enumerate(vote_ids):
            vote_type = "helpful" if i % 2 == 0 else "harmful"
            start = time.perf_counter()
            try:
                resp = await client.post(f"/memories/ace/vote/{mid}", json={
                    "vote": vote_type,
                    "voter_agent_id": "benchmark-agent",
                    "context": "benchmark test",
                })
                elapsed = (time.perf_counter() - start) * 1000
                if resp.status_code == 200:
                    phase7_latencies.append(elapsed)
                else:
                    phase7_errors += 1
                    print(f"    ERR {resp.status_code}: {resp.text[:100]}")
            except Exception as e:
                phase7_errors += 1
                print(f"    ERR: {e}")
        phase7_wall = time.perf_counter() - t0
        results["phase7_vote"] = summarize(phase7_latencies, phase7_wall)
        results["phase7_vote"]["errors"] = phase7_errors
        print_phase("Phase 7: Vote", results["phase7_vote"], phase7_errors)

        # ── Phase 8: Deduplication ──
        dedup_memories = memories[:20]
        phase8_latencies = []
        phase8_dedup_count = 0
        phase8_errors = 0
        print(f"\nPhase 8: Deduplication ({len(dedup_memories)} re-inserts)...")
        t0 = time.perf_counter()
        for mem in dedup_memories:
            start = time.perf_counter()
            try:
                resp = await client.post("/memories/add", json={
                    "content": mem["content"], "agent_id": mem["agent_id"],
                    "namespace": mem["namespace"], "scope": mem["scope"],
                    "memory_type": mem["memory_type"],
                    "shared_with_agents": mem.get("shared_with_agents", []),
                    "metadata": mem.get("metadata", {}),
                })
                elapsed = (time.perf_counter() - start) * 1000
                if resp.status_code == 200:
                    phase8_latencies.append(elapsed)
                    body = resp.json()
                    if body.get("deduplicated"):
                        phase8_dedup_count += 1
                else:
                    phase8_errors += 1
            except Exception as e:
                phase8_errors += 1
                print(f"    ERR: {e}")
        phase8_wall = time.perf_counter() - t0
        results["phase8_deduplication"] = summarize(phase8_latencies, phase8_wall)
        results["phase8_deduplication"]["errors"] = phase8_errors
        results["phase8_deduplication"]["dedup_detected"] = phase8_dedup_count
        print_phase("Phase 8: Deduplication", results["phase8_deduplication"], phase8_errors)
        if phase8_dedup_count > 0:
            print(f"  Dedup detected: {phase8_dedup_count}/{len(dedup_memories)}")

    # ── Summary ──
    total_ops = sum(
        results.get(k, {}).get("count", 0)
        for k in results if k.startswith("phase")
    )
    total_errors = sum(
        results.get(k, {}).get("errors", 0)
        for k in results if k.startswith("phase")
    )
    results["summary"] = {
        "total_operations": total_ops,
        "total_errors": total_errors,
        "error_rate_pct": round(total_errors / max(total_ops + total_errors, 1) * 100, 2),
    }

    print("\n" + "=" * 50)
    print("BENCHMARK SUMMARY")
    print("=" * 50)
    print(f"  Total operations: {total_ops}")
    print(f"  Total errors:     {total_errors}")
    print(f"  Error rate:       {results['summary']['error_rate_pct']}%")

    # Save JSON output
    if output_path:
        with open(output_path, "w") as f:
            json.dump(results, f, indent=2)
        print(f"\n  Results saved to: {output_path}")

    return results


def main():
    parser = argparse.ArgumentParser(description="Run Aegis Memory benchmark workload")
    parser.add_argument("--dataset", type=str, default="dataset.jsonl", help="JSONL dataset file")
    parser.add_argument("--base-url", type=str, default="http://localhost:8000", help="Server base URL")
    parser.add_argument("--api-key", type=str, default="dev-secret-key", help="API key")
    parser.add_argument("--concurrency", type=int, default=5, help="Max concurrent requests")
    parser.add_argument("--output", type=str, default="results.json", help="Output JSON results file")
    args = parser.parse_args()

    asyncio.run(run_workload(args.dataset, args.base_url, args.api_key, args.concurrency, args.output))


if __name__ == "__main__":
    main()
