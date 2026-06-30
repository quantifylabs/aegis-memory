#!/usr/bin/env python3
"""Validate the Claude Code plugin + marketplace manifests before publish.

Catches the failure modes a marketplace user would hit on a fresh install: malformed JSON, a
marketplace entry pointing at a missing plugin dir, a plugin manifest missing required fields, or a
manifest referencing a file (icon, bundled hook/MCP config) that isn't actually there. Pure stdlib;
exits non-zero with a readable message on the first problem so it can gate CI.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
errors: list[str] = []


def _load_json(path: Path) -> dict | None:
    if not path.is_file():
        errors.append(f"missing file: {path.relative_to(REPO)}")
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        errors.append(f"invalid JSON in {path.relative_to(REPO)}: {e}")
        return None


def _require(cond: bool, msg: str) -> None:
    if not cond:
        errors.append(msg)


def main() -> int:
    market = _load_json(REPO / ".claude-plugin" / "marketplace.json")
    if market is not None:
        _require(bool(market.get("name")), "marketplace.json: missing 'name'")
        plugins = market.get("plugins") or []
        _require(isinstance(plugins, list) and bool(plugins), "marketplace.json: 'plugins' must be a non-empty list")
        for entry in plugins if isinstance(plugins, list) else []:
            name = entry.get("name", "<unnamed>")
            source = entry.get("source")
            _require(bool(source), f"marketplace plugin '{name}': missing 'source'")
            if source:
                plugin_dir = (REPO / source).resolve()
                _require(plugin_dir.is_dir(), f"marketplace plugin '{name}': source dir not found: {source}")
                _validate_plugin(plugin_dir, name)

    if errors:
        print("Plugin manifest validation FAILED:")
        for e in errors:
            print(f"  - {e}")
        return 1
    print("Plugin manifest validation passed.")
    return 0


def _validate_plugin(plugin_dir: Path, market_name: str) -> None:
    manifest = _load_json(plugin_dir / ".claude-plugin" / "plugin.json")
    if manifest is None:
        return
    for key in ("name", "version", "description"):
        _require(bool(manifest.get(key)), f"plugin '{market_name}': plugin.json missing '{key}'")
    _require(
        manifest.get("name") == market_name,
        f"plugin '{market_name}': plugin.json name '{manifest.get('name')}' != marketplace name",
    )
    # Referenced asset (icon) must exist.
    icon = manifest.get("icon")
    if icon:
        _require((plugin_dir / icon).is_file(), f"plugin '{market_name}': icon not found: {icon}")
    # Bundled MCP / hook configs, when present, must parse and reference real files.
    mcp = plugin_dir / ".mcp.json"
    if mcp.is_file():
        _load_json(mcp)
    hooks = plugin_dir / "hooks" / "hooks.json"
    if hooks.is_file():
        _load_json(hooks)


if __name__ == "__main__":
    sys.exit(main())
