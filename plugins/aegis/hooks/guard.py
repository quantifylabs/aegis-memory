"""Aegis write-path guard (v0.1) — PostToolUse hook for Edit/Write/MultiEdit.

Reads the hook payload (JSON on stdin), finds the edited file, and runs the local,
keyless Aegis analyzer over it to spot unsafe agent-memory write sinks / untrusted-
content storage (OWASP ASI06). On a risky write it emits a non-blocking warning as
documented PostToolUse hook JSON on *stdout* (hookSpecificOutput.additionalContext,
which Claude Code only parses on exit 0) — it never blocks an edit and always exits 0.
If Python or the aegis-memory package isn't importable, it is a silent no-op so it can
never disrupt a session.

This is the cross-platform replacement for the older guard.sh: it depends only on a
Python interpreter (already the hard requirement for the analyzer), not on a POSIX
shell, so it runs identically on Windows, macOS and Linux.
"""

from __future__ import annotations

import json
import os
import sys
import warnings

warnings.filterwarnings("ignore")


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return

    tool_input = payload.get("tool_input") or {}
    path = tool_input.get("file_path") or tool_input.get("path") or ""
    if not path or not path.endswith(".py") or not os.path.isfile(path):
        return

    try:
        from aegis_memory.inspect.analyzer import analyze_project
    except Exception:
        return  # aegis-memory not importable in this env -> no-op

    target = os.path.basename(path)
    parent = os.path.dirname(os.path.abspath(path)) or "."
    try:
        findings = analyze_project(parent)
    except Exception:
        return

    # Match on the full path of the edited file, not just its basename: analyze_project
    # scans `parent` recursively and reports findings by path relative to that root, so a
    # same-named file in a subdir (e.g. sub/memory.py) must not be attributed to the edited
    # memory.py. Resolve each finding's path against `parent` and compare to the edited file.
    edited = os.path.normcase(os.path.realpath(path))
    risky = []
    for f in findings:
        if f.severity not in ("critical", "high"):
            continue
        sink_file = getattr(f.sink, "file", "")
        if not sink_file:
            continue
        finding_path = os.path.normcase(os.path.realpath(os.path.join(parent, str(sink_file))))
        if finding_path == edited:
            risky.append(f)
    if not risky:
        return

    top = risky[0]
    message = (
        f"[Aegis] {len(risky)} unsafe memory-write finding(s) in {target} "
        f"(e.g. [{top.severity}] {top.title}). "
        f"Run /aegis:inspect for the full memory map + risk score."
    )
    # Emit documented non-blocking PostToolUse hook output on stdout. Claude Code only
    # parses stdout JSON on exit 0 (stderr is surfaced to Claude only on exit 2), so this
    # is the supported "warn, don't block" path. additionalContext -> Claude; the optional
    # systemMessage surfaces the same warning to the user.
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PostToolUse",
                    "additionalContext": message,
                },
                "systemMessage": message,
            }
        )
    )


try:
    main()
except Exception:
    pass

sys.exit(0)
