"""TP: ``m = Memory()`` (mem0 import present) -> ``m.add`` is a mem0 sink via constructor binding,
even though the receiver ``m`` carries no name hint. Untrusted ``input()`` makes it a critical flow."""

from mem0 import Memory


def run():
    m = Memory()
    text = input("user> ")
    m.add(text)
