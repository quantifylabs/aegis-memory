"""Framework detection helpers for CLI onboarding flows."""

from pathlib import Path

FRAMEWORK_MARKERS = {
    "langchain": ["langchain", "langgraph"],
    "crewai": ["crewai"],
}


def detect_framework(project_dir: Path | None = None) -> str | None:
    """Best-effort framework detection from project files."""
    root = project_dir or Path.cwd()

    files_to_scan = [
        "pyproject.toml",
        "requirements.txt",
        "requirements-dev.txt",
        "Pipfile",
    ]

    haystack = ""
    for rel in files_to_scan:
        path = root / rel
        if path.exists() and path.is_file():
            try:
                haystack += "\n" + path.read_text(encoding="utf-8", errors="ignore").lower()
            except Exception:
                continue

    if not haystack:
        return None

    for framework, markers in FRAMEWORK_MARKERS.items():
        if any(marker in haystack for marker in markers):
            return framework
    return None


def recommended_namespace(framework: str | None) -> str:
    if framework == "crewai":
        return "crewai"
    if framework == "langchain":
        return "langchain"
    return "default"
