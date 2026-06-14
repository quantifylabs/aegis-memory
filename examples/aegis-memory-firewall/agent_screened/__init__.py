"""The screened ("after") agent: the same five channels, now firewalled.

Each write first passes its value through the real ``ContentSecurityScanner.scan(...)`` and
only persists when the verdict allows it. ``aegis inspect`` marks these sinks *screened*, so
their findings are downgraded and the heuristic score drops — the before→after that
``aegis inspect agent_screened --baseline agent`` renders from two real runs.
"""
