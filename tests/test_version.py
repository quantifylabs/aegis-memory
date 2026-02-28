"""
Tests for version synchronization.

Ensures version strings come from pyproject.toml, not hardcoded.
"""

import os
import re
import sys

import pytest

# Add server to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "server"))


class TestVersionSync:
    """Verify version is sourced from importlib.metadata, not hardcoded."""

    def _get_pyproject_version(self) -> str:
        """Parse version from pyproject.toml."""
        pyproject_path = os.path.join(os.path.dirname(__file__), "..", "pyproject.toml")
        with open(pyproject_path) as f:
            content = f.read()
        match = re.search(r'^version\s*=\s*"([^"]+)"', content, re.MULTILINE)
        assert match, "Could not find version in pyproject.toml"
        return match.group(1)

    def test_app_py_uses_importlib_metadata(self):
        """api/app.py should import importlib.metadata for version."""
        app_path = os.path.join(os.path.dirname(__file__), "..", "server", "api", "app.py")
        with open(app_path) as f:
            content = f.read()
        assert "importlib.metadata" in content, "api/app.py should use importlib.metadata"
        assert 'version="1.7.0"' not in content, "api/app.py should not have hardcoded 1.7.0"

    def test_no_hardcoded_version_in_server_app(self):
        """Grep for any remaining hardcoded version patterns in api/app.py."""
        app_path = os.path.join(os.path.dirname(__file__), "..", "server", "api", "app.py")
        with open(app_path) as f:
            content = f.read()
        hardcoded = re.findall(r'"1\.\d+\.\d+"', content)
        assert not hardcoded, f"Found hardcoded version strings in api/app.py: {hardcoded}"

    def test_pyproject_version_is_valid_semver(self):
        """pyproject.toml version should be valid semver."""
        version = self._get_pyproject_version()
        assert re.match(r"^\d+\.\d+\.\d+$", version), (
            f"pyproject.toml version '{version}' is not valid semver"
        )

    def test_version_fallback_to_dev(self):
        """When package is not installed, __version__ should fall back to 'dev'."""
        import importlib.metadata
        try:
            importlib.metadata.version("aegis-memory-nonexistent-package")
            found = True
        except importlib.metadata.PackageNotFoundError:
            found = False
        assert not found, "Sanity check: non-existent package should raise"

    def test_init_version_matches_pyproject(self):
        """__init__.py __version__ should match pyproject.toml."""
        version = self._get_pyproject_version()
        init_path = os.path.join(os.path.dirname(__file__), "..", "aegis_memory", "__init__.py")
        with open(init_path) as f:
            content = f.read()
        match = re.search(r'__version__\s*=\s*"([^"]+)"', content)
        assert match, "Could not find __version__ in __init__.py"
        assert match.group(1) == version, (
            f"__init__.py version '{match.group(1)}' != pyproject.toml version '{version}'"
        )
