#!/bin/sh
# Aegis write-path guard (v0.1) — PostToolUse hook for Edit/Write/MultiEdit.
#
# Reads the hook payload (JSON on stdin), finds the edited file, and runs the local,
# keyless Aegis analyzer over it to spot unsafe agent-memory write sinks / untrusted-
# content storage (OWASP ASI06). It only *warns* to stderr — it never blocks an edit
# and always exits 0. If Python or the aegis-memory package isn't importable, it is a
# silent no-op so it can never disrupt a session.

# Resolve a Python interpreter; no-op if none is available.
PY="$(command -v python3 || command -v python || true)"
[ -z "$PY" ] && exit 0

# Capture the payload to a temp file. We can't read it from Python's stdin because the
# heredoc below occupies stdin; instead we pass the temp path as an argument.
TMP="$(mktemp 2>/dev/null || echo "${TMPDIR:-/tmp}/aegis_hook_$$.json")"
cat > "$TMP" 2>/dev/null || { rm -f "$TMP"; exit 0; }

# Scan the edited file and print a concise one-line warning to stderr. The Python is
# fully defensive: any failure leaves no output and exits 0.
"$PY" - "$TMP" <<'PY'
import json
import os
import sys
import warnings

warnings.filterwarnings("ignore")


def main() -> None:
    try:
        with open(sys.argv[1], encoding="utf-8") as fh:
            payload = json.load(fh)
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

    risky = [
        f
        for f in findings
        if os.path.basename(getattr(f.sink, "file", "")) == target
        and f.severity in ("critical", "high")
    ]
    if not risky:
        return

    top = risky[0]
    sys.stderr.write(
        f"[Aegis] {len(risky)} unsafe memory-write finding(s) in {target} "
        f"(e.g. [{top.severity}] {top.title}). "
        f"Run /aegis:inspect for the full memory map + risk score.\n"
    )


try:
    main()
except Exception:
    pass
PY

rm -f "$TMP" 2>/dev/null
exit 0
