"""
Generate synthetic benchmark dataset for Aegis Memory.

Produces JSONL files with reproducible memories, queries, and batch groups.
Usage:
    python generate_dataset.py --count 200 --seed 42 --output dataset.jsonl
"""

import argparse
import json
import random


CATEGORIES = ["preference", "fact", "reflection", "strategy", "procedure"]
NAMESPACES = ["default", "production", "staging"]
AGENTS = [f"agent-{i}" for i in range(1, 6)]
SCOPES = ["agent-private", "agent-shared", "global"]

CONTENT_TEMPLATES = [
    "User prefers {adj} {noun} for {context}",
    "The {noun} should be {adj} when handling {context}",
    "{context} requires {adj} {noun} configuration",
    "Always use {adj} {noun} during {context} operations",
    "Remember that {context} depends on {adj} {noun}",
    "Error pattern: {noun} fails when {context} is {adj}",
    "Strategy: apply {adj} {noun} before {context}",
    "Insight: {adj} {noun} improves {context} outcomes significantly",
]

ADJECTIVES = [
    "fast", "secure", "reliable", "minimal", "verbose", "async",
    "cached", "batched", "streaming", "compressed", "encrypted", "lazy",
]
NOUNS = [
    "responses", "queries", "embeddings", "connections", "tokens",
    "sessions", "handoffs", "reflections", "payloads", "exports",
]
CONTEXTS = [
    "production deployment", "user onboarding", "data migration",
    "error recovery", "peak traffic", "cold start", "batch processing",
    "real-time search", "model inference", "cache invalidation",
]


def generate_memory(idx: int, rng: random.Random) -> dict:
    template = rng.choice(CONTENT_TEMPLATES)
    content = template.format(
        adj=rng.choice(ADJECTIVES),
        noun=rng.choice(NOUNS),
        context=rng.choice(CONTEXTS),
    )
    agent_id = rng.choice(AGENTS)
    scope = rng.choice(SCOPES)
    shared_with = []
    if scope == "agent-shared":
        shared_with = rng.sample(
            [a for a in AGENTS if a != agent_id],
            k=rng.randint(1, 3),
        )

    return {
        "index": idx,
        "type": "memory",
        "content": content,
        "agent_id": agent_id,
        "namespace": rng.choice(NAMESPACES),
        "scope": scope,
        "memory_type": rng.choice(CATEGORIES),
        "shared_with_agents": shared_with,
        "metadata": {
            "category": rng.choice(CATEGORIES),
            "priority": rng.randint(1, 5),
        },
    }


def generate_query(idx: int, rng: random.Random) -> dict:
    return {
        "index": idx,
        "type": "query",
        "query_text": f"{rng.choice(ADJECTIVES)} {rng.choice(NOUNS)} for {rng.choice(CONTEXTS)}",
        "agent_id": rng.choice(AGENTS),
        "namespace": rng.choice(NAMESPACES),
        "top_k": rng.choice([5, 10, 20]),
    }


def generate_cross_agent_query(idx: int, rng: random.Random) -> dict:
    requesting = rng.choice(AGENTS)
    targets = rng.sample([a for a in AGENTS if a != requesting], k=rng.randint(1, 3))
    return {
        "index": idx,
        "type": "cross_agent_query",
        "query_text": f"{rng.choice(ADJECTIVES)} {rng.choice(NOUNS)} for {rng.choice(CONTEXTS)}",
        "requesting_agent_id": requesting,
        "target_agent_ids": targets,
        "namespace": rng.choice(NAMESPACES),
        "top_k": 10,
    }


def main():
    parser = argparse.ArgumentParser(description="Generate Aegis Memory benchmark dataset")
    parser.add_argument("--count", type=int, default=200, help="Number of memories to generate")
    parser.add_argument("--queries", type=int, default=50, help="Number of queries to generate")
    parser.add_argument("--cross-queries", type=int, default=20, help="Number of cross-agent queries")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility")
    parser.add_argument("--output", type=str, default="dataset.jsonl", help="Output JSONL file")
    args = parser.parse_args()

    rng = random.Random(args.seed)

    with open(args.output, "w") as f:
        for i in range(args.count):
            f.write(json.dumps(generate_memory(i, rng)) + "\n")
        for i in range(args.queries):
            f.write(json.dumps(generate_query(i, rng)) + "\n")
        for i in range(args.cross_queries):
            f.write(json.dumps(generate_cross_agent_query(i, rng)) + "\n")

    total = args.count + args.queries + args.cross_queries
    print(f"Generated {args.count} memories + {args.queries} queries + {args.cross_queries} cross-agent queries -> {args.output}")
    print(f"Total records: {total} | Seed: {args.seed}")


if __name__ == "__main__":
    main()
