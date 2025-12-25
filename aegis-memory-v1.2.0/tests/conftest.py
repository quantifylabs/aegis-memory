"""
Pytest configuration and fixtures for Aegis Memory tests.

This file:
1. Adds the server directory to Python path so imports work correctly
2. Provides shared fixtures for all tests
"""

import sys
from pathlib import Path

# Add server directory to Python path so 'from models import ...' works
server_dir = Path(__file__).parent.parent / "server"
sys.path.insert(0, str(server_dir))

# Re-export fixtures from the test file so they're available globally
# (pytest will automatically pick up fixtures from conftest.py)

