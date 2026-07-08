"""
Refactoring Engine — safe, AST-aware code transformations.
Supports: rename, extract method, inline, move, change signature.
"""

from .engine import RefactorEngine, RefactorResult

__all__ = ["RefactorEngine", "RefactorResult"]
