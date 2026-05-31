"""Research-grade prompt-injection detection benchmark for Aegis Memory.

Evaluates the Aegis four-stage content-security pipeline
(``server/content_security.py``) as a prompt-injection / memory-poisoning
detector, against established baselines, with full confusion-matrix metrics
and a per-stage ablation.

See ``README.md`` for how to reproduce.
"""
