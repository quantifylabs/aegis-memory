"""
Dashboard Router - re-exports existing routes_dashboard router.

The dashboard routes remain in routes_dashboard.py for now;
this module provides the new import path.
"""
from routes_dashboard import router

__all__ = ["router"]
