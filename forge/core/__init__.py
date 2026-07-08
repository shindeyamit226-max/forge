"""Core agent engine — the brain of Forge."""

from .agent import Agent
from .context import ProjectContext
from .planner import Planner, Plan, PlanStep
from .ast_editor import CodeSymbol, PythonASTParser, parse_file, find_symbol_in_project
from .indexer import CodeIndexer, SearchResult
from .error_recovery import ErrorRecoveryEngine, ParsedError, ErrorAnalysis
from .git_workflow import GitWorkflow, GitStatus
from .context_window import ContextWindowManager, ConversationContext
from .memory import SessionMemory
from .watcher import FileWatcher

__all__ = [
    "Agent", "ProjectContext", "Planner", "Plan", "PlanStep",
    "CodeSymbol", "PythonASTParser", "parse_file", "find_symbol_in_project",
    "CodeIndexer", "SearchResult",
    "ErrorRecoveryEngine", "ParsedError", "ErrorAnalysis",
    "GitWorkflow", "GitStatus",
    "ContextWindowManager", "ConversationContext",
    "SessionMemory", "FileWatcher",
]
