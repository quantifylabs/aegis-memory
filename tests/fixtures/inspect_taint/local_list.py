"""True-negative fixture: a plain local ``list.append`` must NOT be flagged as a memory sink.

The variable is deliberately named ``stored`` — the exact shape that the old name-substring matcher
false-positived on. ``list.append`` is not a durable memory write, so the analyzer must produce no
finding anchored to this line.
"""

from __future__ import annotations


def collect_papers(papers: list) -> list:
    stored = []
    for paper in papers:
        stored.append(paper)  # local list accumulation — NOT a memory write
    return stored
