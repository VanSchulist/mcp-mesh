# Community Outreach & Distribution Kit: `mcp-mesh`

This document contains ready-to-use submission materials, pull request specifications, and technical distribution posts for the `mcp-mesh` ecosystem.

---

## 1. Upstream Pull Request: `punkpeye/awesome-mcp-servers`

### 1.1 Scope Evaluation
- **Target Category**: `### 🔗 <a name="aggregators"></a>Aggregators`
- **Inclusion Assessment for `mcp-registry-cli`**:
  - `awesome-mcp-servers` strictly indexes *MCP Server implementations* (servers offering MCP endpoints/tools to models).
  - `mcp-registry-cli` is a developer package manager CLI for installing servers into local config files, not an MCP server itself.
  - Submitting non-server CLI tools to `awesome-mcp-servers` risks PR rejection.
  - **Decision**: Keep this PR strictly focused on `mcp-mesh`, which is a 100% compliant MCP Aggregator / Gateway server.

### 1.2 Git & Branch Status
- **Fork Remote**: `VanSchulist/awesome-mcp-servers` (synced with upstream `main`)
- **Branch**: `feat/add-mcp-mesh`
- **Commit**: `fcc5afc` (`Add VanSchulist/mcp-mesh to Aggregators`)
- **Diff Preview**:
  ```diff
  --- a/README.md
  +++ b/README.md
  @@ -259,2 +259,3 @@ Servers for accessing many apps and tools through a single MCP server.
   - [toadlyBroodle/satring](https://github.com/toadlyBroodle/satring/tree/main/mcp) [![toadlyBroodle/satring MCP server](https://glama.ai/mcp/servers/toadlyBroodle/satring/badges/score.svg)](https://glama.ai/mcp/servers/toadlyBroodle/satring) 🐍 ☁️ 🍎 🪟 🐧 - Discover and compare L402 and x402 paid API services from satring.com, a curated Lightning and USDC API directory.
  +- [VanSchulist/mcp-mesh](https://github.com/VanSchulist/mcp-mesh) 🐍 🏠 ☁️ 🍎 🪟 🐧 - Zero-dependency MCP reverse proxy and lazy tool router in pure Python stdlib that cuts Turn-0 tool schema tokens by 85–95%.
   - [VeriTeknik/pluggedin-mcp-proxy](https://github.com/VeriTeknik/pluggedin-mcp-proxy) 📇 🏠 - Proxy combining multiple MCP servers into one interface, with discovery and management of tools, prompts, resources and templates plus a debugging playground.
  ```

### 1.3 PR Metadata
- **PR Title**: `Add VanSchulist/mcp-mesh to Aggregators 🤖🤖🤖`
  *(Note: Appended `🤖🤖🤖` as instructed by `CONTRIBUTING.md` to trigger the upstream fast-track agent merge flow)*
- **Target Repo**: `punkpeye/awesome-mcp-servers`
- **Target Branch**: `main`
- **Head Branch**: `VanSchulist:feat/add-mcp-mesh`

### 1.4 PR Body Markdown
```markdown
### What does this PR do?
Adds [`VanSchulist/mcp-mesh`](https://github.com/VanSchulist/mcp-mesh) to the **Aggregators** section.

### Server Details
- **Repository**: https://github.com/VanSchulist/mcp-mesh
- **Category**: Aggregators
- **Badges**: `🐍` (Python stdlib), `🏠` (Local), `☁️` (Cloud/Self-hosted), `🍎` (macOS), `🪟` (Windows), `🐧` (Linux)
- **Description**: Zero-dependency MCP reverse proxy and lazy tool router in pure Python stdlib that cuts Turn-0 tool schema tokens by 85–95%.

### Quality & Compliance Checklist
- [x] Follows existing format and badge conventions.
- [x] Placed strictly in alphabetical order (`VanSchulist` after `toadlyBroodle` and before `VeriTeknik`).
- [x] Exactly one single-line entry.
- [x] Factual, concise description without marketing buzzwords.
- [x] Verified repository is public, open-source (MIT), has active CI, and runs on pure Python standard library.
```

### 1.5 Ready-to-Run GitHub CLI Submission Command
```bash
gh pr create \
  --repo punkpeye/awesome-mcp-servers \
  --head VanSchulist:feat/add-mcp-mesh \
  --base main \
  --title "Add VanSchulist/mcp-mesh to Aggregators 🤖🤖🤖" \
  --body "### What does this PR do?
Adds [VanSchulist/mcp-mesh](https://github.com/VanSchulist/mcp-mesh) to the **Aggregators** section.

### Server Details
- **Repository**: https://github.com/VanSchulist/mcp-mesh
- **Category**: Aggregators
- **Badges**: 🐍 🏠 ☁️ 🍎 🪟 🐧
- **Description**: Zero-dependency MCP reverse proxy and lazy tool router in pure Python stdlib that cuts Turn-0 tool schema tokens by 85–95%.

### Quality & Compliance Checklist
- [x] Follows existing format and badge conventions.
- [x] Placed strictly in alphabetical order (between toadlyBroodle and VeriTeknik).
- [x] Exactly one single-line entry.
- [x] Factual, concise description without marketing buzzwords.
- [x] Verified repository is public, open-source (MIT), and has clean CI."
```

---

## 2. Hacker News Show HN Submission

### 2.1 Post Title
```text
Show HN: mcp-mesh – Pure stdlib MCP gateway that cuts prompt tool bloat by 90%
```

### 2.2 Post Body (~250 words)
```text
Hey HN,

When you hook an AI coding agent or LLM up to multiple Model Context Protocol (MCP) servers (GitHub, Postgres, Slack, Docker, AWS), a frustrating scaling cliff hits: before the user types their first prompt, 50+ tool JSON schemas get dumped into the context window.

In our benchmarks across 60 real MCP tools, static injection consumed ~9,790 tokens on Turn 0. On models with smaller context or high per-token pricing, this burns budget, adds ~600ms of pre-fill latency, and degrades tool selection accuracy ("lost in the middle").

To solve this, I built mcp-mesh (https://github.com/VanSchulist/mcp-mesh). Instead of pulling in heavy asynchronous frameworks or third-party dependencies, it is written entirely in Python standard library (http.server, sqlite3, concurrent.futures, json).

How it works:
1. It runs locally as a single MCP reverse proxy exposing just 4 meta-tools: `mesh_search_tools`, `mesh_describe_tool`, `mesh_invoke_tool`, and `mesh_status`.
2. Backends are indexed into an in-memory SQLite table.
3. The LLM performs a 2-stage lazy lookup: it searches for tools by natural intent, inspects only the selected schema, and invokes it through the proxy.
4. Each upstream server gets a three-state circuit breaker (Closed/Open/Half-Open) that isolates crashes after 5 failures.

Results: Turn-0 tokens drop from 9,790 to 527 (-94.6%). Memory footprint is ~18MB RSS, with 1.4ms P50 internal proxy overhead.

Trade-off: If you only use ≤3 tools, don't use this—the extra retrieval round trip outweighs the token savings.

Online simulator: http://www.existentialcloud.ccwu.cc
Benchmark suite: https://github.com/VanSchulist/mcp-mesh-eval

Code is MIT. Please roast my architecture or tell me what I got wrong.
```

### 2.3 First Comment (Technical Architecture Follow-Up)
```text
A few implementation details for anyone interested in the stdlib design choices:

- Why pure Python stdlib? We wanted zero supply-chain risk and instant execution via `uvx` or `pipx` with zero wheel compilation. `http.server` combined with `ThreadPoolExecutor` easily handles 50 concurrent SSE/HTTP calls at ~1.4ms P50 latency.
- State storage: SQLite in `:memory:` (or local file fallback) provides indexed BM25-style token tokenization with zero external search daemon.
- Circuit breaker: Uses atomic counters with a 30s exponential backoff probe window. When an upstream server throws 5 consecutive HTTP 5xx or connection resets, it flips to Open, preventing agent hang.
- Reproducibility: You can run the live 50-tool cluster demo locally without setup via:
  `uvx --from git+https://github.com/VanSchulist/mcp-mesh mcp-mesh --demo`

Looking forward to your critiques, especially around HTTP/2 multiplexing vs. stdlib constraints.
```

---

## 3. Reddit Post (`r/LocalLLaMA` / `r/ArtificialIntelligence`)

### 3.1 Post Title
```text
I got tired of 50 MCP tools eating 10k tokens on every turn, so I built a zero-dep proxy in pure Python stdlib (95% context reduction)
```

### 3.2 Post Content
```text
If you run local models with Ollama, vLLM, or llama.cpp (e.g. Llama-3.3-70B, Qwen-2.5-Coder-32B, or 8B variants), you know that context window is precious. Even with 32k or 128k windows, KV cache memory footprint explodes and needle-in-a-haystack recall drops when you dump massive system prompts.

The problem with Model Context Protocol (MCP) right now is that the default behavior is static: if you connect 6 MCP servers with 10 tools each, your agent receives 60 full JSON schemas (~9,800 tokens) right at Turn 0 before you even say "hello".

I built **mcp-mesh** to fix this:
https://github.com/VanSchulist/mcp-mesh

### How it works:
- It aggregates all your upstream MCP servers behind a single local endpoint.
- It compresses your prompt down to 4 lightweight meta-tools (`mesh_search_tools`, `mesh_describe_tool`, `mesh_invoke_tool`, `mesh_status`).
- When your query needs a tool, the agent runs a quick search against the local catalog, retrieves the schema on demand, and invokes it.
- Turn-0 token footprint drops from **9,790 tokens to 527 tokens (94.6% reduction)**.

### Architecture choices:
- **Pure Python standard library (zero pip dependencies)**: Uses `http.server`, `sqlite3`, `concurrent.futures`. No FastAPI, no Pydantic, no heavy node packages.
- **Resource usage**: ~18MB RAM idle, 1.4ms P50 proxy overhead.
- **Failure isolation**: Built-in circuit breakers prevent a broken MCP server from hanging your local inference session.

### When NOT to use it:
If your workflow only uses 2 or 3 static tools, the extra two-stage tool discovery turn adds an unnecessary LLM inference step. The break-even point is around 8-10 tools or 4,000 schema tokens.

You can run the interactive 50-tool mock demo locally with:
```bash
uvx --from git+https://github.com/VanSchulist/mcp-mesh mcp-mesh --demo
```

Benchmark harness & numbers: https://github.com/VanSchulist/mcp-mesh-eval
Interactive token simulator: http://www.existentialcloud.ccwu.cc

Code is MIT. Would love to hear feedback from folks running heavy local agent tool chains!
```
