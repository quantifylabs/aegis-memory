"""The (unscreened) agent: five untrusted channels writing into shared memory.

Each ``ingest_*`` module writes one realistic input channel into the agent's memory with a
*different* framework idiom, so ``aegis inspect`` proves it generalizes across sink shapes
rather than pattern-matching one form. None of these screen the value before the write —
that is the vulnerability the firewall demo is about.
"""
