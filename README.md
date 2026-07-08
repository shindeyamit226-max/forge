# 🔨 Forge — The Agentic Coding Tool That Actually Works

<p align="center">
  <img src="https://img.shields.io/badge/version-0.3.0-blue" alt="version">
  <img src="https://img.shields.io/badge/python-3.10+-green" alt="python">
  <img src="https://img.shields.io/badge/license-MIT-brightgreen" alt="license">
  <img src="https://img.shields.io/badge/⭐_Star-Forge-orange?style=for-the-badge&logo=github" alt="stars">
</p>

<p align="center">
  <b>100% local. Zero cloud. Your code never leaves your machine.</b><br>
  <i>14,000+ lines • 20 language parsers • 35 tools • Knowledge graph • Self-correcting agent</i>
</p>

---

## 🚀 Quick Start

### Prerequisites

- **Python 3.10+**
- **[Ollama](https://ollama.com)** (for local LLMs) — or any OpenAI-compatible API

### Install

```bash
# Clone
git clone https://github.com/shindeyamit226-max/forge.git
cd forge

# Install
pip install -e .

# Pull a local model (pick one)
ollama pull codellama:13b        # Good for code
ollama pull deepseek-coder:33b   # Better quality
ollama pull llama3:8b            # Good general

# Run Forge
forge
```

That's it. No accounts. No API keys. No cloud. It just works.

---

## 📖 Usage Guide

### Interactive Mode (Recommended)

```bash
forge
```

Starts an interactive session where you can:
- Type natural language tasks
- Forge plans, executes, and verifies automatically
- Use commands like `/help`, `/plan`, `/stats`, `/tools`

**Example session:**
```
You: Add rate limiting to all API endpoints
Forge: [analyzes codebase, creates plan, implements changes, runs tests]
You: The login endpoint is returning 500
Forge: [reads error, analyzes stack trace, finds bug, fixes it]
You: Write tests for the payment module
Forge: [reads payment code, generates comprehensive tests, runs them]
```

### One-Shot Commands

```bash
# Build a feature
forge run "create a REST API for user management with FastAPI"

# Fix a bug
forge run "the login endpoint returns 500, find and fix it"

# Refactor code
forge run "convert all callbacks to async/await in src/services/"

# Write tests
forge run "write unit tests for the UserService class"

# Code review
git diff | forge run "review these changes for issues"

# Explain code
forge run "explain how the authentication middleware works"

# Database migration
forge run "create a migration to add a 'role' column to users table"

# Docker setup
forge run "create a Dockerfile and docker-compose.yml for this project"
```

### Piped Input

```bash
# Analyze error logs
cat error.log | forge run "analyze these errors and suggest fixes"

# Review PR
git diff main..feature-branch | forge run "review this PR"

# Process data
cat data.csv | forge run "analyze this CSV and create visualizations"
```

---

## 🛠️ Commands

| Command | Description |
|---------|-------------|
| `/help` | Show all commands |
| `/tools` | List all 35 available tools |
| `/plan` | Show current execution plan |
| `/stats` | Show session statistics |
| `/project` | Show project analysis |
| `/memory` | Show learned memories |
| `/git` | Show git status |
| `/sessions` | List saved sessions |
| `/save [id]` | Save current session |
| `/model <name>` | Switch LLM model |
| `/clear` | Clear the screen |
| `/quit` | Exit Forge |

---

## 🔧 CLI Options

```bash
forge [OPTIONS] [COMMAND]

Options:
  -m, --model TEXT         LLM model to use
  -p, --provider TEXT      LLM provider (ollama, openai, anthropic, vllm, lmstudio, llamafile)
  --api-base TEXT          API base URL
  --api-key TEXT           API key (for cloud providers)
  -t, --temperature FLOAT  Temperature (0.0-1.0)
  --auto-approve           Auto-approve all tool calls
  --no-stream              Disable streaming
  -s, --session TEXT       Session ID to resume
  --config PATH            Config file path
  --version                Show version

Commands:
  run        Execute a one-shot task
  models     List available models
  status     Show configuration and provider status
  tools      List available tools
  sessions   List saved sessions
  resume     Resume a saved session
```

---

## ⚙️ Configuration

### Config File

Create `~/.forge/config.yaml`:

```yaml
# LLM Settings
provider: ollama
model: codellama:13b
temperature: 0.1
api_base: http://localhost:11434/v1

# Agent Behavior
max_iterations: 30
auto_approve: false

# Safety
confirm_destructive: true
sandbox_shell: false
```

### Environment Variables

```bash
export FORGE_PROVIDER=ollama
export FORGE_MODEL=codellama:13b
export FORGE_API_BASE=http://localhost:11434/v1
export FORGE_API_KEY=sk-***  # Only for cloud providers
```

### Use with Cloud Providers

**OpenAI:**
```bash
forge --provider openai --model gpt-4o --api-key sk-***
```

**Anthropic:**
```bash
forge --provider anthropic --model claude-sonnet-4-20250514 --api-key sk-ant-***
```

**LM Studio (local):**
```bash
forge --provider lmstudio --api-base http://localhost:1234/v1
```

---

## 🧠 What Makes Forge Different

### Knowledge Graph (Like Obsidian, But for Code)

Forge builds a **knowledge graph** of your entire codebase:
- **Who calls what** — trace call chains across files
- **Impact analysis** — know what breaks before you change it
- **Backlinks** — see all references to any symbol
- **Pattern detection** — find anti-patterns automatically

```
graph_impact("process_payment")
→ Risk Level: HIGH
→ Direct impacts: checkout(), refund(), subscription_renewal()
→ Tests to run: tests/test_payment.py
```

### 20 Language Parsers

Full AST parsing for: **Python, JavaScript, TypeScript, Go, Rust, Java, C, C++, Ruby, PHP, Swift, Kotlin, Scala, SQL, Shell, HTML, CSS, YAML, JSON, Markdown**

### Self-Correcting Agent

Forge doesn't just generate code — it:
1. **Plans** multi-step tasks
2. **Executes** with the right tools
3. **Verifies** by running tests
4. **Self-corrects** when things fail
5. **Learns** your preferences over time

### Security Scanner

Automatically detects: hardcoded secrets, SQL injection, XSS, weak crypto, insecure deserialization, path traversal, and more.

### Code Generators

Scaffold entire projects: FastAPI, Express, React, Vue, Docker, CI/CD pipelines, and more.

---

## 🏗️ Architecture

```
forge/
├── core/           # Agent engine, knowledge graph, planner, memory
├── parsers/        # 20 language parsers
├── tools/          # 35 built-in tools
├── generators/     # Code generators (projects, tests, Docker, CI)
├── security/       # Vulnerability scanner
├── refactor/       # Safe code transformations
├── plugins/        # Plugin system with hooks
├── llm/            # LLM provider abstraction
├── tui/            # Terminal UI
└── session.py      # Session persistence
```

---

## 🔌 Plugins

Drop a `.py` file in `~/.forge/plugins/`:

```python
# ~/.forge/plugins/my_tool.py
from forge.tools.registry import registry

@registry.register(
    name="deploy",
    description="Deploy to production",
    category="devops",
)
async def deploy(service: str, environment: str = "staging"):
    return f"Deployed {service} to {environment}"
```

Forge auto-loads it. Your tool is now available.

---

## 📊 Stats

| Metric | Value |
|--------|-------|
| Python files | 76 |
| Total lines | 14,156 |
| Tests | 54 (all passing) |
| Tools | 35 |
| Language parsers | 20 |
| Core systems | 12 |
| LLM providers | 6 |

---

## 🤝 Contributing

```bash
git clone https://github.com/shindeyamit226-max/forge.git
cd forge
pip install -e ".[dev]"
pytest tests/ -v
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

---

## 📜 License

MIT — do whatever you want with it.

---

<p align="center">
  <b>⭐ Star Forge if you believe coding tools should respect your privacy!</b><br>
  <sub>Built with ❤️ by developers, for developers.</sub>
</p>
