"""
Capture machine profile for benchmark reproducibility.

Usage:
    python machine_profile.py
"""

import os
import platform
import sys


def get_profile() -> dict:
    profile = {
        "python_version": sys.version,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "cpu_count": os.cpu_count(),
    }

    try:
        import psutil
        mem = psutil.virtual_memory()
        profile["memory_total_gb"] = round(mem.total / (1024 ** 3), 1)
        profile["memory_available_gb"] = round(mem.available / (1024 ** 3), 1)
    except ImportError:
        profile["memory_total_gb"] = "psutil not installed"

    try:
        import importlib.metadata
        profile["aegis_version"] = importlib.metadata.version("aegis-memory")
    except Exception:
        profile["aegis_version"] = "unknown"

    return profile


def main():
    profile = get_profile()
    max_key_len = max(len(k) for k in profile)
    print("=== Machine Profile ===")
    for key, value in profile.items():
        print(f"  {key:<{max_key_len + 2}} {value}")


if __name__ == "__main__":
    main()
