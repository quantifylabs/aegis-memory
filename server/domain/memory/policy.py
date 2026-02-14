"""Memory access control policy.

Re-exports scope inference and access control logic.
"""
from scope_inference import ScopeInference
from auth import AuthPolicy

__all__ = ["ScopeInference", "AuthPolicy"]
