"""Comprehensive tests for all Forge core systems."""

import asyncio
import json
import os
import tempfile
from pathlib import Path

import pytest

from forge.config import Config
from forge.tools.registry import ToolRegistry, Tool, ToolResult
from forge.core.context import ProjectContext
from forge.core.ast_editor import PythonASTParser, JavaScriptASTParser, parse_file, find_symbol_in_project
from forge.core.indexer import CodeIndexer, tokenize
from forge.core.error_recovery import ErrorRecoveryEngine, PythonErrorParser, JavaScriptErrorParser
from forge.core.git_workflow import GitWorkflow
from forge.core.context_window import ContextWindowManager, ConversationContext
from forge.core.memory import SessionMemory
from forge.core.planner import Planner, Plan, PlanStep, StepStatus


# ============================================================
# AST Editor Tests
# ============================================================

class TestPythonASTParser:
    def setup_method(self):
        self.parser = PythonASTParser()

    def test_parse_functions(self):
        source = '''
def hello():
    print("hello")

def add(a: int, b: int) -> int:
    return a + b

async def fetch(url: str):
    pass
'''
        symbols = self.parser.parse(source)
        names = [s.name for s in symbols]
        assert "hello" in names
        assert "add" in names
        assert "fetch" in names

    def test_parse_classes(self):
        source = '''
class UserService:
    def __init__(self, db):
        self.db = db

    def get_user(self, user_id: int):
        return self.db.find(user_id)

class AdminService(UserService):
    pass
'''
        symbols = self.parser.parse(source)
        classes = [s for s in symbols if s.kind == "class"]
        methods = [s for s in symbols if s.kind == "method"]

        assert len(classes) == 2
        assert len(methods) == 2
        assert any(s.name == "UserService" for s in classes)
        assert any(s.name == "get_user" and s.parent == "UserService" for s in methods)

    def test_find_symbol(self):
        source = '''
def process_data(data: list) -> dict:
    """Process input data."""
    return {"result": data}
'''
        sym = self.parser.find_symbol(source, "process_data")
        assert sym is not None
        assert sym.name == "process_data"
        assert sym.kind == "function"
        assert "data" in sym.params
        assert sym.return_type == "dict"
        assert sym.docstring == "Process input data."

    def test_get_function_body(self):
        source = '''def greet(name: str) -> str:
    message = f"Hello, {name}!"
    print(message)
    return message

def other():
    pass
'''
        body = self.parser.get_function_body(source, "greet")
        assert body is not None
        assert "message = f\"Hello, {name}!\"" in body
        assert "return message" in body

    def test_replace_function_body(self):
        source = '''def greet(name: str) -> str:
    return f"Hello, {name}!"

def other():
    pass
'''
        new_body = '    msg = f"Hi, {name}!"\n    return msg'
        result = self.parser.replace_function_body(source, "greet", "msg = f\"Hi, {name}!\"\nreturn msg")
        assert result is not None
        assert "Hi, {name}!" in result
        assert "def other():" in result

    def test_add_import(self):
        source = '''import os
import sys

def main():
    pass
'''
        result = self.parser.add_import(source, "import json")
        assert "import json" in result
        lines = result.splitlines()
        # Should be after sys
        json_idx = next(i for i, l in enumerate(lines) if "import json" in l)
        sys_idx = next(i for i, l in enumerate(lines) if "import sys" in l)
        assert json_idx > sys_idx

    def test_extract_function(self):
        source = '''def process():
    x = 1
    y = 2
    z = x + y
    print(z)
'''
        modified, new_func = self.parser.extract_function(source, 2, 4, "calculate")
        assert "calculate()" in modified
        assert "def calculate():" in new_func


class TestJavaScriptASTParser:
    def test_parse_functions(self):
        parser = JavaScriptASTParser()
        source = '''
function hello() {
    console.log("hello");
}

const add = (a, b) => a + b;

async function fetchData(url) {
    return await fetch(url);
}
'''
        symbols = parser.parse(source)
        names = [s.name for s in symbols]
        assert "hello" in names
        assert "add" in names
        assert "fetchData" in names

    def test_parse_class_methods(self):
        parser = JavaScriptASTParser()
        source = '''
class UserService {
    constructor(db) {
        this.db = db;
    }

    async getUser(id) {
        return this.db.find(id);
    }
}
'''
        symbols = parser.parse(source)
        classes = [s for s in symbols if s.kind == "class"]
        methods = [s for s in symbols if s.kind == "method"]
        assert len(classes) == 1
        assert len(methods) >= 1


# ============================================================
# Indexer Tests
# ============================================================

class TestCodeIndexer:
    def test_tokenize(self):
        tokens = tokenize("helloWorld my_function camelCase")
        assert "hello" in tokens
        assert "world" in tokens
        assert "my" in tokens
        assert "function" in tokens
        assert "camel" in tokens
        assert "case" in tokens

    def test_index_and_search(self):
        indexer = CodeIndexer()

        # Create a temp project
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create some files
            (Path(tmpdir) / "auth.py").write_text('''
def login(username: str, password: str) -> bool:
    """Authenticate user with credentials."""
    return verify_password(username, password)

def logout(session_id: str):
    """End user session."""
    clear_session(session_id)
''')

            (Path(tmpdir) / "database.py").write_text('''
def connect(connection_string: str):
    """Connect to the database."""
    return create_connection(connection_string)

def query(sql: str) -> list:
    """Execute a SQL query."""
    return execute(sql)
''')

            # Index
            files = indexer.index_directory(tmpdir)
            assert files > 0
            assert len(indexer.chunks) > 0

            # Search for authentication
            results = indexer.search("user login authentication")
            assert len(results) > 0
            # Should find auth.py results
            auth_results = [r for r in results if "auth" in r.chunk.file]
            assert len(auth_results) > 0

            # Search for database
            results = indexer.search("database connection SQL")
            assert len(results) > 0
            db_results = [r for r in results if "database" in r.chunk.file]
            assert len(db_results) > 0

    def test_search_by_symbol(self):
        indexer = CodeIndexer()
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "main.py").write_text('''
def process_payment(amount: float, currency: str):
    pass

class PaymentService:
    def charge(self, card, amount):
        pass
''')
            indexer.index_directory(tmpdir)

            results = indexer.search_by_symbol("process_payment")
            assert len(results) > 0
            assert results[0].chunk.symbols[0] == "process_payment"

    def test_stats(self):
        indexer = CodeIndexer()
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "test.py").write_text("def hello(): pass\n")
            indexer.index_directory(tmpdir)
            stats = indexer.stats
            assert stats["total_chunks"] > 0
            assert stats["total_files"] > 0


# ============================================================
# Error Recovery Tests
# ============================================================

class TestErrorRecovery:
    def test_parse_python_traceback(self):
        engine = ErrorRecoveryEngine()
        output = '''
Traceback (most recent call last):
  File "app.py", line 10, in main
    result = process(data)
  File "app.py", line 25, in process
    return data["key"]
KeyError: 'key'
'''
        errors = engine.parse_errors(output, "python")
        # Should find the KeyError
        assert any("KeyError" in e.message or "key" in e.message.lower() for e in errors)

    def test_parse_mypy_errors(self):
        engine = ErrorRecoveryEngine()
        output = '''
src/auth.py:15:4: error: Incompatible return value type (got "str", expected "bool")  [return-value]
src/auth.py:23:1: error: Missing return statement  [return]
'''
        errors = engine.parse_errors(output, "python")
        assert len(errors) >= 2
        assert errors[0].file == "src/auth.py"
        assert errors[0].line == 15
        assert errors[0].source == "mypy"

    def test_parse_typescript_errors(self):
        engine = ErrorRecoveryEngine()
        output = '''
src/app.ts(10,5): error TS2322: Type 'string' is not assignable to type 'number'.
src/app.ts(15,10): error TS2339: Property 'name' does not exist on type 'User'.
'''
        errors = engine.parse_errors(output, "typescript")
        assert len(errors) >= 2
        assert errors[0].code == "TS2322"

    def test_analyze_and_suggest(self):
        engine = ErrorRecoveryEngine()
        output = '''
src/auth.py:15:4: error: Incompatible return value type  [return-value]
src/auth.py:23:1: error: Missing return statement  [return]
'''
        analysis = engine.analyze(output, "python")
        assert analysis.error_count >= 2
        assert len(analysis.affected_files) > 0
        assert analysis.fix_strategy  # Should have a fix strategy

    def test_generate_fix_prompt(self):
        engine = ErrorRecoveryEngine()
        analysis = engine.analyze("KeyError: 'user_id'\n", "python")
        prompt = engine.generate_fix_prompt(analysis)
        assert "error" in prompt.lower() or "Error" in prompt


# ============================================================
# Context Window Tests
# ============================================================

class TestContextWindow:
    def test_token_estimation(self):
        cwm = ContextWindowManager(max_tokens=1000)
        tokens = cwm.estimate_tokens("hello world this is a test")
        assert tokens > 0
        assert tokens < 100

    def test_add_and_trim(self):
        cwm = ContextWindowManager(max_tokens=100, reserve_tokens=20)

        # Add items that exceed the limit (must set can_drop=True for trimming)
        for i in range(20):
            cwm.add(f"item_{i}", f"This is test content number {i} with some extra text.", priority=0.5, can_drop=True)

        # Should have trimmed
        assert cwm.token_count <= cwm.available_tokens + 100  # Allow some slack

    def test_priority_ordering(self):
        cwm = ContextWindowManager(max_tokens=100, reserve_tokens=20)

        # Add high and low priority items
        cwm.add("high", "Important system prompt", priority=1.0, kind="system")
        cwm.add("low", "Low priority content " * 50, priority=0.1, can_drop=True)

        # High priority should survive
        assert any(i.id == "high" for i in cwm.items)

    def test_conversation_context(self):
        cc = ConversationContext(max_tokens=5000)
        cc.set_system("You are a helpful assistant.")
        cc.add_user_message("Hello")
        cc.add_assistant_message("Hi there!")
        cc.add_tool_result("read", "file content here")

        messages = cc.to_messages()
        assert len(messages) >= 3

    def test_utilization(self):
        cc = ConversationContext(max_tokens=10000)
        cc.set_system("You are a helpful assistant with a long system prompt " * 10)
        cc.add_user_message("Hello world this is a test message")
        stats = cc.stats
        assert "total_tokens" in stats
        assert stats["total_tokens"] > 0


# ============================================================
# Memory Tests
# ============================================================

class TestMemory:
    def test_remember_and_recall(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            memory = SessionMemory(Path(tmpdir))

            memory.remember("pref:indent", "4 spaces", kind="preference")
            result = memory.recall("pref:indent")
            assert result == "4 spaces"

    def test_search(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            memory = SessionMemory(Path(tmpdir))

            memory.remember("auth_pattern", "Use JWT tokens for authentication", kind="pattern")
            memory.remember("db_pattern", "Use SQLAlchemy for database", kind="pattern")

            results = memory.search("authentication")
            assert len(results) > 0
            assert any("JWT" in r.content for r in results)

    def test_persistence(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            memory1 = SessionMemory(Path(tmpdir))
            memory1.remember("test_key", "test_value")

            # Create new instance — should load from disk
            memory2 = SessionMemory(Path(tmpdir))
            result = memory2.recall("test_key")
            assert result == "test_value"

    def test_preferences(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            memory = SessionMemory(Path(tmpdir))
            memory.learn_preference("tabs", "4 spaces")
            memory.learn_preference("quotes", "double")

            prefs = memory.get_preferences()
            assert prefs["tabs"] == "4 spaces"
            assert prefs["quotes"] == "double"

    def test_forget(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            memory = SessionMemory(Path(tmpdir))
            memory.remember("key", "value")
            assert memory.forget("key") is True
            assert memory.recall("key") is None


# ============================================================
# Planner Tests
# ============================================================

class TestPlanner:
    def test_plan_step_status(self):
        step = PlanStep(id=1, description="Test step")
        assert step.status == StepStatus.PENDING
        assert not step.is_done
        assert not step.is_failed

    def test_plan_progress(self):
        plan = Plan(
            goal="Test",
            steps=[
                PlanStep(id=1, description="Step 1", status=StepStatus.COMPLETED),
                PlanStep(id=2, description="Step 2", status=StepStatus.IN_PROGRESS),
                PlanStep(id=3, description="Step 3", status=StepStatus.PENDING),
            ]
        )
        assert plan.progress == pytest.approx(1/3, abs=0.01)
        assert not plan.is_complete

    def test_plan_advance(self):
        plan = Plan(
            goal="Test",
            steps=[
                PlanStep(id=1, description="Step 1"),
                PlanStep(id=2, description="Step 2"),
            ]
        )
        step = plan.advance()
        assert step is not None
        assert step.id == 1
        assert step.status == StepStatus.IN_PROGRESS

    def test_plan_complete(self):
        plan = Plan(
            goal="Test",
            steps=[
                PlanStep(id=1, description="Step 1", status=StepStatus.COMPLETED),
                PlanStep(id=2, description="Step 2", status=StepStatus.COMPLETED),
            ]
        )
        assert plan.is_complete

    def test_plan_format(self):
        plan = Plan(
            goal="Build API",
            steps=[
                PlanStep(id=1, description="Create routes", status=StepStatus.COMPLETED),
                PlanStep(id=2, description="Add tests", status=StepStatus.PENDING),
            ]
        )
        formatted = plan.format()
        assert "Build API" in formatted
        assert "Create routes" in formatted


# ============================================================
# Integration Tests
# ============================================================

class TestToolExecution:
    @pytest.mark.asyncio
    async def test_read_file(self):
        from forge.tools.builtin import read_file

        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("def hello():\n    print('hello')\n")
            f.flush()

            result = await read_file(f.name)
            assert result.success
            assert "def hello()" in result.output
            os.unlink(f.name)

    @pytest.mark.asyncio
    async def test_write_and_read(self):
        from forge.tools.builtin import write_file, read_file

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.py")

            # Write
            result = await write_file(path, "x = 42\n")
            assert result.success

            # Read
            result = await read_file(path)
            assert result.success
            assert "x = 42" in result.output

    @pytest.mark.asyncio
    async def test_edit_file(self):
        from forge.tools.builtin import write_file, edit_file

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.py")
            await write_file(path, "old_code = True\n")

            result = await edit_file(path, "old_code = True", "new_code = True")
            assert result.success

            from forge.tools.builtin import read_file
            content = await read_file(path)
            assert "new_code = True" in content.output

    @pytest.mark.asyncio
    async def test_shell_command(self):
        from forge.tools.builtin import shell_exec

        result = await shell_exec("echo hello")
        assert result.success
        assert "hello" in result.output

    @pytest.mark.asyncio
    async def test_shell_dangerous_blocked(self):
        from forge.tools.builtin import shell_exec

        result = await shell_exec("rm -rf /")
        assert not result.success
        assert "dangerous" in result.error.lower() or "blocked" in result.error.lower()

    @pytest.mark.asyncio
    async def test_search(self):
        from forge.tools.builtin import search_code

        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "test.py").write_text("def hello_world():\n    pass\n")

            result = await search_code("hello_world", path=tmpdir)
            assert result.success
            assert "hello_world" in result.output


class TestConfig:
    def test_defaults(self):
        config = Config()
        assert config.provider == "ollama"
        assert config.model == "codellama:13b"
        assert config.temperature == 0.1

    def test_override(self):
        config = Config()
        config.override("model", "llama3")
        assert config.get("model") == "llama3"

    def test_parse_bool(self):
        assert Config._parse_bool("true") is True
        assert Config._parse_bool("false") is False
        assert Config._parse_bool("yes") is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
