# Contributing to `mcp-mesh`

Thank you for your interest in contributing to **`mcp-mesh`**! As the flagship platform anchor for the **Existential Cloud** studio, we maintain disciplined engineering rigor.

---

## 🏛️ Guiding Engineering Principles

1. **Zero External Dependencies (ADR-002)**:
   * The core gateway, indexer, and CLI must remain 100% executable using Python 3.10+ standard library.
   * Do not add dependencies to `dependencies = []` in `pyproject.toml` unless discussed and approved via an Architecture Decision Record (ADR).
2. **Deterministic Verification**:
   * Every PR must include automated unit tests under `tests/`.
   * Test execution must pass 100% across Linux, macOS, and Windows.
3. **Specification-First**:
   * Substantial architectural additions should be preceded by an issue discussion outlining problem scope and tradeoffs.

---

## 🛠️ Local Development Setup

Clone the repository and run the test suite:

```bash
git clone https://github.com/VanSchulist/mcp-mesh.git
cd mcp-mesh

# Run full test suite with standard library
python -m unittest discover -s tests -v

# Run interactive demonstration
python main.py demo
```

---

## 🌿 Branching Policy & Git Workflow

We follow standard branch naming:
* `feature/<short-name>`: New capabilities or optimizations.
* `fix/<short-name>`: Bug fixes and edge-case mitigations.
* `docs/<short-name>`: Documentation, guides, and comments.
* `test/<short-name>`: Test harness additions or benchmarks.

### Commit Messages
We follow the **Conventional Commits** specification:
```text
feat: add dynamic LRU cache for active tool schemas
fix: handle process termination on unexpected client disconnect
docs: update Claude Desktop configuration guide
test: add test coverage for invalid JSON-RPC batches
```

---

## 🚀 Submitting a Pull Request

1. Fork the repository on GitHub.
2. Create your topic branch: `git checkout -b feature/my-enhancement`.
3. Commit your changes with meaningful messages.
4. Run all unit tests: `python -m unittest discover -s tests -v`.
5. Push to your fork: `git push origin feature/my-enhancement`.
6. Open a Pull Request against `VanSchulist/mcp-mesh:main`.
