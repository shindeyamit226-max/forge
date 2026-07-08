# 🔨 Forge — The Agentic Coding Tool That Actually Works

<p align="center">
  <img src="https://img.shields.io/badge/version-0.1.0-blue" alt="version">
  <img src="https://img.shields.io/badge/python-3.10+-green" alt="python">
  <img src="https://img.shields.io/badge/license-MIT-brightgreen" alt="license">
  <img src="https://img.shields.io/badge/⭐_Star-Forge-orange?style=for-the-badge&logo=github" alt="stars">
</p>

<p align="center">
  <b>100% local. Zero cloud. Your code never leaves your machine.</b><br>
  <i>Talk to your codebase like a senior engineer is sitting next to you.</i>
</p>

---

## 🤔 Why Another Coding Tool?

| Feature | Claude Code | Cursor | Copilot | **Forge** |
|---------|------------|--------|---------|-----------|
| Runs 100% local | ❌ | ❌ | ❌ | ✅ |
| Privacy-first | ❌ | ❌ | ❌ | ✅ |
| Multi-file agentic edits | ✅ | ✅ | ❌ | ✅ |
| Self-correcting loops | ❌ | ❌ | ❌ | ✅ |
| Bring your own LLM | ❌ | ❌ | ❌ | ✅ |
| Free & Open Source | ❌ | ❌ | ❌ | ✅ |
| Works offline | ❌ | ❌ | ❌ | ✅ |
| TUI with rich output | ❌ | ❌ | ❌ | ✅ |

**Forge** is an open-source, fully local agentic coding assistant. It uses LLMs (local via Ollama, or any OpenAI-compatible API) to understand your codebase, plan multi-step tasks, write code, run it, debug it, and iterate until it works — all without sending a single byte to the cloud.

## ⚡ Quick Start

### Prerequisites

- Python 3.10+
- [Ollama](https://ollama.com) (for local LLMs) — or any OpenAI-compatible API

### Install

```bash
# Clone
git clone https://github.com/your-username/forge.git
cd forge

# Install
pip install -e .

# Pull a local model
ollama pull codellama:13b
# or for best results:
ollama pull deepseek-coder:33b

# Run
forge
```

That's it. No accounts. No API keys. No cloud. It just works.

## 🎯 Features

### 🧠 Intelligent Agent Loop
Forge doesn't just generate code — it **thinks, plans, executes, and iterates**:
1. **Understand** — Analyzes your request and codebase context
2. **Plan** — Breaks complex tasks into ordered steps
3. **Execute** — Runs each step, using the right tool for the job
4. **Verify** — Tests results, catches errors
5. **Self-Correct** — If something fails, it analyzes the error and retries with a fix

### 🔧 Built-in Tools
- **read/write/edit** — File operations with surgical precision
- **shell** — Execute commands with intelligent error recovery
- **search** — Ripgrep-powered codebase search
- **git** — Full git integration (status, diff, commit, branch)
- **analyze** — Deep project structure analysis
- **test** — Auto-detect and run tests

### 🎨 Beautiful TUI
- Rich terminal UI with syntax highlighting
- Real-time tool execution visualization
- Streaming responses
- Split-pane code preview

### 🔌 Plugin System
```python
# Create custom tools in seconds
from forge.tools import tool

@tool(description="Deploy to production")
def deploy(service: str, environment: str = "staging"):
    # Your deployment logic
    return f"Deployed {service} to {environment}"
```

## 💡 Usage

### Interactive Mode
```bash
forge                    # Start interactive session
forge --model llama3     # Use specific model
forge --provider openai  # Use OpenAI API
```

### One-Shot Commands
```bash
forge run "add authentication with JWT to the API"
forge run "fix the failing tests in src/auth/"
forge run "refactor the database layer to use async"
forge run "write unit tests for the UserService class"
```

### Piped Input
```bash
cat error.log | forge run "analyze this error and suggest a fix"
git diff | forge run "review these changes"
```

### Examples

```bash
# Build a feature
forge run "create a REST API for user management with CRUD operations"

# Debug
forge run "the login endpoint returns 500, find and fix the bug"

# Refactor
forge run "convert all callbacks to async/await in src/services/"

# Test
forge run "write comprehensive tests for the payment module"

# Explain
forge run "explain how the authentication middleware works"
```

## ⚙️ Configuration

Forge works out of the box, but you can customize everything:

```bash
# ~/.forge/config.yaml
provider: ollama          # ollama | openai | anthropic | custom
model: codellama:13b      # Default model
temperature: 0.1          # Lower = more deterministic
max_iterations: 25        # Max agent loop iterations
auto_approve: false       # Ask before destructive ops
theme: dark               # TUI theme

# Custom API endpoint (for OpenAI-compatible APIs)
api_base: http://localhost:11434/v1  # Ollama default

# Safety
confirm_destructive: true # Confirm before rm, drop, etc.
sandbox_shell: true       # Restrict shell commands
```

### Environment Variables
```bash
export FORGE_PROVIDER=ollama
export FORGE_MODEL=codellama:13b
export FORGE_API_BASE=http://localhost:11434/v1
export FORGE_API_KEY=sk-...  # Only for cloud providers
```

## 🏗️ Architecture

```
┌─────────────────────────────────────────┐
│              forge CLI / TUI             │
├─────────────────────────────────────────┤
│            Agent Engine (core)           │
│  ┌─────────┐ ┌──────────┐ ┌──────────┐ │
│  │ Planner │ │ Executor │ │ Verifier │ │
│  └─────────┘ └──────────┘ └──────────┘ │
├─────────────────────────────────────────┤
│              Tool System                 │
│  ┌──────┐ ┌──────┐ ┌───────┐ ┌──────┐ │
│  │ read │ │ write│ │ shell │ │ git  │  │
│  └──────┘ └──────┘ └───────┘ └──────┘ │
├─────────────────────────────────────────┤
│           LLM Abstraction               │
│  ┌────────┐ ┌────────┐ ┌─────────────┐ │
│  │ Ollama │ │ OpenAI │ │ Anthropic   │ │
│  └────────┘ └────────┘ └─────────────┘ │
└─────────────────────────────────────────┘
```

## 🤝 Contributing

Forge is built to be extended. PRs welcome!

1. Fork the repo
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a PR

## 📜 License

MIT — do whatever you want with it.

---

<p align="center">
  <b>⭐ Star Forge if you believe coding tools should respect your privacy!</b><br>
  <sub>Built with ❤️ by developers, for developers.</sub>
</p>
