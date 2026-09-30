# 🌐 `mcp-mesh`

> **The Dynamic Model Context Protocol Gateway & Lazy Tool Router**  
> Aggregate 50+ upstream MCP servers, eliminate tool schema context bloat, and slash Turn-0 token consumption by 85–95% with zero external dependencies.

[![Official Portal](https://img.shields.io/badge/Website-existentialcloud.ccwu.cc-8A2BE2?style=flat-square)](https://existentialcloud.ccwu.cc)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Architecture: Zero Dependencies](https://img.shields.io/badge/dependencies-zero-brightgreen.svg)](#architecture)
[![Protocol: MCP](https://img.shields.io/badge/protocol-MCP%202024--11--05-orange.svg)](https://modelcontextprotocol.io/)


---

## 💡 Why `mcp-mesh`?

The **Model Context Protocol (MCP)** is revolutionizing how LLMs interface with databases, code repositories, and external APIs. However, as developers connect agents to multiple MCP servers (GitHub, Postgres, Slack, Memory, Filesystem, AWS), a severe bottleneck emerges:

1. **Turn-0 Token Bloat**: Connecting to 10 MCP servers injects **50 to 100+ full JSON schemas** into the system prompt before the user types a single word. This burns **15,000 to 40,000 tokens** per request.
2. **Context Window Degradation ("Lost in the Middle")**: Flooding the prompt with hundreds of parameter definitions degrades LLM attention, causing tool hallucinations, invalid parameter formatting, and dropped instructions.
3. **Subprocess Hell**: Managing dozens of discrete child processes across Cursor, Claude Desktop, and terminal agents leads to resource leaks and configuration fragility.

`mcp-mesh` solves this by acting as a **single, transparent MCP gateway**. Instead of exposing all 100 downstream schemas statically, it indexes your tools and exposes **lightweight meta-tools** (`mesh_search_tools`, `mesh_describe_tool`, `mesh_invoke_tool`).

Schemas are loaded lazily on demand. The result? **Turn-0 context overhead drops from 25,000+ tokens to ~380 tokens—an immediate ~90% cost and latency reduction.**

---

## ✨ Features

* 🚀 **Zero External Dependencies**: Engineered purely with Python 3.10+ standard library (`json`, `subprocess`, `argparse`, `sys`, `dataclasses`). Runs instantly anywhere without `pip install` friction.
* 🔍 **Semantic Keyword Tool Indexer**: Sub-millisecond inverted index with BM25-style keyword and parameter matching across all aggregated upstream servers.
* ⚡ **Lazy Schema Loading**: Exposes ultra-compact tool signatures (15–30 tokens) during discovery, loading full JSON schemas only when explicitly inspected or invoked.
* 🔄 **Transparent Stdio Multiplexing**: Connects to your MCP client (Claude Desktop, Cursor, Antigravity, Cline) as a single standard stdio server while supervising downstream child processes.
* 🛡️ **Direct Invocation Fallback**: Automatically resolves direct tool invocations (e.g. `query_readonly` or `postgres::query_readonly`) even if the agent bypasses the meta-tool wrapper.
* 📊 **Built-in Token Economy Meter**: CLI diagnostic tools to inspect aggregated servers, measure Turn-0 token footprints, and verify net token savings.

---

## 🏛️ Architecture

```text
 ┌────────────────────────────────────────────────────────┐
 │                    AI Client / IDE                     │
 │          (Claude Desktop, Cursor, Antigravity)         │
 └───────────────────────────┬────────────────────────────┘
                             │ stdio (JSON-RPC 2.0)
                             │ Only 3-4 Meta-Tools Exposed (~380 tokens)
                             ▼
 ┌────────────────────────────────────────────────────────┐
 │                   mcp-mesh Gateway                     │
 │  ┌──────────────────────────────────────────────────┐  │
 │  │      JSON-RPC 2.0 Parser & Stdio Transport       │  │
 │  └────────────────────────┬─────────────────────────┘  │
 │                           ▼                            │
 │  ┌──────────────────────────────────────────────────┐  │
 │  │        Tool Indexer & Token Economy Meter        │  │
 │  │      (BM25 Scoring, Signatures, Token Stats)     │  │
 │  └────────────────────────┬─────────────────────────┘  │
 │                           ▼                            │
 │  ┌──────────────────────────────────────────────────┐  │
 │  │    Process Multiplexer & Upstream Stdio Router   │  │
 │  └────────────────────────┬─────────────────────────┘  │
 └───────────────────────────┼────────────────────────────┘
                             │
         ┌───────────────────┼───────────────────┐
         ▼ stdio             ▼ stdio             ▼ stdio
 ┌───────────────┐   ┌───────────────┐   ┌───────────────┐
 │ GitHub MCP    │   │ Postgres MCP  │   │ Filesystem    │
 │ (35+ tools)   │   │ (15+ tools)   │   │ (12+ tools)   │
 └───────────────┘   └───────────────┘   └───────────────┘
```

---

## ⚡ Quick Start (5 Minutes)

### 1. Clone & Run Built-in Benchmark Demo
No dependencies or package installations are required. Clone and execute the demo immediately:

```bash
git clone https://github.com/VanSchulist/mcp-mesh.git
cd mcp-mesh

# Run the interactive demo and token savings meter
python main.py demo
```

You will see the live economy report:
```text
=================================================================
  mcp-mesh: Dynamic MCP Gateway & Lazy Tool Router (v1.0.0)
  Engineered by Van Schulist (@VanSchulist / Existential Cloud)
=================================================================

[+] AGGREGATION & TOKEN ECONOMY REPORT:
  Connected Servers  : 5
  Server IDs         : aws, filesystem, github, postgres, slack
  Total Tools        : 12
-----------------------------------------------------------------
  Raw Schema Tokens  : 2317 tokens (Turn-0 baseline)
  mcp-mesh Overhead  : 380 tokens (Meta-tool signatures)
  Net Tokens Saved   : 1937 tokens
  Efficiency Gain    : 83.6% token reduction!
=================================================================
```

---

## 🛠️ Configuration & Client Setup

### Claude Desktop / Cursor / Antigravity Integration
Configure `mcp-mesh` as your single master MCP server in your `claude_desktop_config.json` or Cursor MCP settings:

```json
{
  "mcpServers": {
    "mcp-mesh": {
      "command": "python",
      "args": ["/path/to/mcp-mesh/main.py", "run", "--config", "/path/to/mcp_mesh_config.json"]
    }
  }
}
```

### Gateway Configuration (`mcp_mesh_config.json`)
List all your downstream MCP servers in standard JSON format:

```json
{
  "mcpServers": {
    "github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {
        "GITHUB_PERSONAL_ACCESS_TOKEN": "ghp_xxxxxxxxxxxx"
      }
    },
    "postgres": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-postgres", "postgresql://localhost/mydb"]
    },
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/Users/dev/workspace"]
    }
  }
}
```

---

## 💻 CLI Commands

`mcp-mesh` includes an ergonomic CLI for diagnostics and discovery:

```bash
# 1. Start gateway in MCP stdio mode
python main.py run --config mcp_mesh_config.json

# 2. View token savings and server aggregation stats
python main.py stats

# 3. Test natural language tool search from terminal
python main.py search "commit code and create pull request"

# 4. Inspect full JSON schema for an indexed tool
python main.py inspect github::create_pull_request

# 5. Run zero-config demonstration suite
python main.py demo
```

---

## 🧪 Testing

The repository maintains a comprehensive automated test suite testing the JSON-RPC engine, keyword indexer, process supervisor, and gateway protocol:

```bash
# Run all unit tests
python -m unittest discover -s tests -v
```

All tests execute synchronously using standard library `unittest` with zero setup.

---

## 🗺️ Roadmap & Ecosystem

`mcp-mesh` serves as the **Flagship Project** of the [Existential Cloud AI Studio](https://github.com/VanSchulist/github-ai-studio).

* [x] **Phase 1: Core Engine (v1.0.0)** - Zero-dependency stdio proxy, token indexer, CLI suite. *(Current)*
* [ ] **Phase 2: `mcp-mesh-eval` (Satellite 1)** - Benchmark harness evaluating tool-calling accuracy vs token reduction across Claude 3.7, Gemini 2.0, and GPT-4o.
* [ ] **Phase 3: `mcp-mesh-ui` (Satellite 2)** - Terminal ANSI dashboard and web visualization charting live tool invocations and latency.
* [ ] **Phase 4: `mcp-registry-cli` (Satellite 3)** - Community package manager to install curated MCP servers in one command.

---

## 🤝 Contributing

Contributions, feedback, and issue reports are warmly welcomed:

1. Fork the repository.
2. Create your feature branch (`git checkout -b feature/dynamic-lru-cache`).
3. Commit your changes with semantic commit messages (`git commit -m 'feat: add LRU cache for active schemas'`).
4. Ensure all tests pass (`python -m unittest discover -s tests`).
5. Open a Pull Request.

---

## 📄 License

Distributed under the **MIT License**. See [`LICENSE`](LICENSE) for complete details.

---

**Crafted with 🖤 by [Van Schulist](https://github.com/VanSchulist) | [Existential Cloud](https://github.com/VanSchulist/github-ai-studio)**
