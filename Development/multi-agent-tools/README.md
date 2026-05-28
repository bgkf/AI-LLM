 # multi-agent-tools

A pair of CLI tools built on a multi-agent architecture. Each tool fans out to
specialist AI agents running concurrently, collects their structured outputs, and
presents a unified result. Both support Anthropic's API and any OpenAI-compatible
local LLM (llama.cpp, Ollama, LM Studio).

---

## Tools

### `review-pr` — Multi-agent PR reviewer

Points five specialist agents at your staged changes or a diff. Each agent runs
concurrently on each changed file, produces structured findings, and the results are
aggregated into a single formatted review.

A deliberation pass runs after the specialist agents complete. It groups findings
by location, detects when multiple agents flag the same line, and enriches each
finding with a confidence score and corroboration or conflict metadata before rendering.

**Agents:**

| Agent | Model | Looks for |
|---|---|---|
| 🧠 `logic` | Sonnet (smart) | Off-by-one errors, null dereferences, resource leaks, async bugs, swallowed exceptions |
| 🔒 `security` | Sonnet (smart) | Hardcoded secrets, injection risks, unsafe `eval`/`exec`, insecure deserialization |
| ✏️ `style` | Haiku (fast) | Naming conventions, dead code, magic numbers, inconsistent formatting |
| 🧪 `tests` | Haiku (fast) | Untested public APIs, missing edge cases, branches with no coverage |
| 📝 `docs` | Haiku (fast) | Missing docstrings, stale parameter docs, undocumented public functions |

The `security` agent runs a fast regex prescan for secrets before making any LLM
call — obvious leaks are caught even if the API is unreachable.

Output is colour-coded by severity (`error` / `warning` / `info`), grouped by file,
and exits with code `1` if any blocking errors are found (useful in CI).

### `ask-codebase` — Codebase Q&A *(coming in v0.2)*

Index a repository once, then ask questions in plain language from the terminal.
A router agent classifies the intent of each question and dispatches to the right
retrieval strategy — semantic search for "what does X do", AST-based lookup for
"where is X called", dependency tracing for "what imports Y".

---

## Requirements

- **Python 3.9+**
- **[uv](https://github.com/astral-sh/uv)** — recommended for venv and dependency management
- One of:
  - An **Anthropic API key** (for cloud inference — default)
  - A running **OpenAI-compatible local server** (llama.cpp, Ollama, LM Studio — for local inference)
- **git** — for `--staged` and `--commit` modes

---

## Setup & Install

### 1. Clone and create a virtual environment

```bash
git clone https://github.com/your-username/multi-agent-tools.git
cd multi-agent-tools

uv venv
source .venv/bin/activate      # on Windows: .venv\Scripts\activate
```

### 2. Install dependencies

```bash
# Anthropic provider (default)
uv add anthropic

# OpenAI-compatible provider (for local LLMs)
uv add openai

# Both (recommended — lets you switch per-run)
uv add anthropic openai

# Dev tools
uv add --dev pytest ruff mypy
```

### 3. Configure environment

```bash
cp .env.example .env
```

Edit `.env`:

```bash
# Required for Anthropic provider
ANTHROPIC_API_KEY=your-key-here

# Required for local LLM provider
LOCAL_LLM_BASE_URL=http://localhost:8080/v1   # llama.cpp default
LOCAL_LLM_MODEL=local                          # ignored by llama.cpp; use model name for Ollama

# Set the default provider so you don't need --provider on every run
# Options: anthropic | local
DEFAULT_PROVIDER=anthropic
```

To use a local LLM by default (e.g. llama.cpp with Qwen):

```bash
DEFAULT_PROVIDER=local
LOCAL_LLM_BASE_URL=http://localhost:8080/v1
LOCAL_LLM_MODEL=local
```

For Ollama:

```bash
DEFAULT_PROVIDER=local
LOCAL_LLM_BASE_URL=http://localhost:11434/v1
LOCAL_LLM_MODEL=qwen2.5   # or whichever model you have loaded
```

### 4. Symlink into your PATH

```bash
chmod +x scripts/review-pr
ln -sf "$(pwd)/scripts/review-pr" /usr/local/bin/review-pr
```

`review-pr` will now work from any directory without activating the venv manually.
The script resolves the symlink back to the project and uses the project's own
`.venv/bin/python` directly.

---

## Usage

### Reference

```
usage: review-pr [-h] [--staged | --commit SHA | --diff FILE] [--agents LIST]
                 [--provider {anthropic,local}] [--format {full,compact}]
                 [--workers WORKERS] [--verbose]

Multi-agent PR review tool

options:
  -h, --help            show this help message and exit
  --staged              Review staged git changes (default)
  --commit SHA          Review a specific commit
  --diff FILE           Review a diff file (use - for stdin)
  --agents LIST         Comma-separated list of agents to run: logic,security,style,tests,docs
  --provider {anthropic,local}
                        LLM provider (default: value of DEFAULT_PROVIDER in .env)
  --format {full,compact}
                        Output format (default: full)
  --workers WORKERS     Max concurrent agent threads (default: 10)
  --verbose, -v         Enable debug logging
```

### Common invocations

```bash
# Review staged changes (most common)
git add myfile.py
review-pr

# Review the last commit
review-pr --commit HEAD

# Review a specific commit
review-pr --commit abc1234

# Review a saved diff file
review-pr --diff changes.diff

# Pipe a diff directly
git diff main...feature-branch | review-pr --diff -

# Run only specific agents
review-pr --agents logic,security

# Use a local LLM for this run (overrides DEFAULT_PROVIDER)
review-pr --provider local

# Use Anthropic for this run (overrides DEFAULT_PROVIDER)
review-pr --provider anthropic

# Compact one-line output — good for CI scripts
review-pr --format compact

# Debug logging — shows which agents ran, token counts, timing
review-pr --verbose
```

### Exit codes

| Code | Meaning |
|------|---------|
| `0` | No errors (may have warnings) |
| `1` | One or more `error`-severity findings — use in CI to block merges |
| `2` | Configuration error (missing API key, no staged changes, etc.) |

### Example output

```
PR Review
  reviewed 2 file(s) · 10 agent runs · 4,821 tokens · 3.2s
  deliberation: 2 corroborated · 1 conflicted

auth/token.py  1 error(s), 2 warning(s)
────────────────────────────────────────────────────────────
  ✗ ERROR  auth/token.py:14  [🔒 security]  [2 agents agree]
  Possible hardcoded secret detected in added code
  → Move secrets to environment variables or a secrets manager
    +API_KEY = "sk-abc***"

  ⚠ WARNING  auth/token.py:22  [🧠 logic]
  Token expiry check uses local time but JWT validates UTC
  → Use datetime.utcnow() or datetime.now(timezone.utc)
  ⚡ conflicts with style (they rated this lower severity)

────────────────────────────────────────────────────────────
✗ REVIEW REQUIRED  1 error(s) · 2 warning(s) · 1 info
```

The `[2 agents agree]` badge appears when multiple agents independently flag the
same line at the same severity — a stronger signal than a single-agent finding.
The `⚡ conflicts with` marker means agents disagree on severity; both positions
are shown so the reviewer can weigh them.

### Switching providers

`DEFAULT_PROVIDER` in `.env` sets the default for every run. The `--provider`
flag overrides it per-run. To change which model a specific agent uses, edit
`shared/llm.py` — the `model_for_role()` function maps agent names to models
and `complete()` accepts a `model=` override per call.

---

## Architecture

### How it works

```
git diff / diff file
       │
       ▼
  parse_diff()         splits into per-file diffs, skips binary/generated files
       │
       ▼
  supervisor — Phase 1: concurrent specialist analysis
  ┌────┴────────────────────────────────────────┐
  │  ThreadPoolExecutor — one thread per pair   │
  │                                             │
  │  logic    security    style    tests    docs│
  │  logic    security    style    tests    docs│  ← one row per file
  └────┬────────────────────────────────────────┘
       │  findings written to SharedFindingStore as agents complete
       ▼
  supervisor — Phase 2: deliberation
  ┌────┴────────────────────────────────────────┐
  │  group findings by (file, line)             │
  │  corroboration: same line, same severity    │  → confidence rises
  │  conflict:      same line, diff severity    │  → both positions flagged
  │  enrich each finding with confidence score  │
  └────┬────────────────────────────────────────┘
       │  enriched findings sorted by severity then corroboration
       ▼
  renderer             CLI (colour terminal) or GitHub PR comment (stub)
```

### Phase 1 — Concurrent specialist analysis

Each `(file × agent)` pair is an independent unit of work submitted to a
`ThreadPoolExecutor`. Agents run concurrently and write findings to a
`SharedFindingStore` as they complete. A failure in one agent does not affect
the others — it produces an empty result and is logged.

### Phase 2 — Deliberation

After all agents finish, the supervisor runs a deliberation pass over the
`SharedFindingStore`. For every `(file, line)` flagged by more than one agent:

- **Corroboration** — agents agree on severity → confidence rises, badge shown
- **Conflict** — agents disagree on severity → both findings flagged with `⚡`

Each finding is enriched with three fields before rendering:

| Field | Meaning |
|---|---|
| `confidence` | `0.5` (one agent) → `0.75` (two agree) → `0.95` (three or more) |
| `corroborated_by` | Names of other agents that flagged the same line at the same severity |
| `conflicts_with` | Names of agents that flagged the same line at a different severity |

The deliberation function has a fixed signature designed as an extraction point.
When a dedicated consensus service is needed, the supervisor passes the same
arguments through a request/response transport instead of a direct call —
nothing else changes.

### Data contract between agents

Every specialist agent returns `list[Finding]`. Never raises. The `Finding`
dataclass enforces invariants at construction time:

```python
@dataclass
class Finding:
    message:    str          # non-empty
    file:       str          # non-empty
    severity:   str          # one of: "error" | "warning" | "info"
    line:       int | None   # >= 1 if set
    suggestion: str | None   # concrete fix, not just a complaint
    agent:      str          # set by supervisor after agent returns
    context:    str | None   # the relevant code snippet
```

The supervisor stamps `agent` onto each finding — agents don't need to know
their own name. The renderer never calls into an agent. Analysis, coordination,
and presentation stay completely separated.

### SharedFindingStore

The `SharedFindingStore` in `shared/finding_store.py` is the shared state layer
between Phase 1 and Phase 2. It is an append-only, thread-safe log:

```python
store = SharedFindingStore()
store.append(finding)              # called by supervisor as each agent completes
store.hot_lines()                  # [(file, line, count)] sorted by agent count desc
store.by_line("auth.py", 14)      # all agents that flagged line 14
store.by_agent("security")        # all findings from the security agent
```

Findings are immutable once appended. The deliberation phase reads the log and
derives enriched state from it — the same append-only pattern used in event
sourcing systems.

### File tree

```
multi-agent-tools/
│
├── shared/                         # shared across both tools
│   ├── llm.py                      # multi-provider LLM wrapper (Anthropic + OpenAI-compat)
│   ├── findings.py                 # Finding + AgentResult dataclasses — agent output contract
│   └── finding_store.py            # SharedFindingStore + EnrichedFinding — Phase 2 shared state
│
├── pr_review/                      # PR review tool
│   ├── __main__.py                 # CLI entry point (argparse, .env loading)
│   ├── supervisor.py               # diff parser, two-phase orchestrator, aggregator
│   ├── deliberation.py             # Phase 2: corroboration + conflict detection
│   ├── agents/
│   │   ├── logic.py                # logic & correctness (uses Sonnet)
│   │   ├── security.py             # secrets + vulnerability scan (uses Sonnet)
│   │   ├── style.py                # style & formatting (uses Haiku)
│   │   ├── tests.py                # test coverage gaps (uses Haiku)
│   │   └── docs.py                 # documentation gaps (uses Haiku)
│   └── renderers/
│       ├── cli.py                  # colour terminal output
│       └── github.py               # GitHub PR comment (stub — v0.3)
│
├── codeqa/                         # codebase Q&A tool (v0.2)
│   └── __init__.py
│
├── scripts/
│   └── review-pr                   # bash entry point — symlink this into PATH
│
├── pyproject.toml                  # dependencies, entry points
├── .env.example                    # environment variable template
└── .gitignore
```

### LLM provider abstraction

`shared/llm.py` is the only file that touches the Anthropic or OpenAI SDK.
Every agent calls `complete()` — never a client directly. Adding a new provider
is a single addition to `llm.py` with no changes to any agent.

```python
# Anthropic (default)
resp = complete("Review this diff...", system="...", provider=Provider.ANTHROPIC)

# Local llama.cpp / Ollama / LM Studio
resp = complete("Review this diff...", provider=Provider.LOCAL)

# Override model per call
resp = complete("...", model="claude-sonnet-4-6", provider=Provider.ANTHROPIC)
```

Retries with exponential backoff (2s → 4s → 8s) are handled in `llm.py` so
agents never need to think about transient failures.

---

## Design decisions

**Why concurrent fan-out?** Each `(file × agent)` pair is independent. Running
them sequentially on a 10-file PR with 5 agents would be 50 sequential LLM calls.
Concurrently it's bounded by the slowest single call. On a typical PR the
wall-clock time is 3–8 seconds regardless of file count.

**Why per-file diffs, not whole-diff?** Whole-diff exceeds the context window on
any real PR. Per-file keeps each agent call focused and well within limits. The
agent sees enough context (the full file diff plus the file name for language
detection) without being overwhelmed.

**Why `error`-severity findings block merge but `warning` doesn't?** Mirrors how
real code review works. A hardcoded secret or null dereference must be fixed.
A missing docstring or style violation is worth noting but shouldn't block a
time-sensitive fix. The exit code contract (`1` on errors, `0` on warnings-only)
lets you enforce this in CI without configuration.

**Why does `security.py` prescan with regex before calling the LLM?** Speed and
reliability. A `sk-...` pattern in a diff is unambiguously a secret — no reasoning
required. The prescan catches it in microseconds and the finding is already in hand
even if the LLM call fails, times out, or hits a rate limit.

**Why is deliberation in the supervisor, not a separate agent?** Clean interface
now, easy extraction later. The `deliberate()` function signature is fixed:
`(store, config, agent_runners) -> list[EnrichedFinding]`. When a dedicated
consensus service is needed, the body is replaced with a request/response call
and nothing else changes — not the supervisor, not the agents, not the renderer.

**Why does corroboration raise confidence rather than deduplicate?** Two agents
independently flagging the same line is stronger evidence than one agent flagging
it. Deduplication would throw that signal away. The confidence score lets the
renderer weight corroborated findings differently and lets downstream automation
threshold on confidence rather than severity alone.

---

## Roadmap

- **v0.2** — `ask-codebase`: index a repo, ask questions in plain language from
  the terminal. Semantic search + AST-based lookup + dependency tracing.
- **v0.3** — GitHub renderer: post findings as inline PR review comments via the
  GitHub API, with a summary comment on the PR itself.
- **v0.3** — Deliberation Phase 2b: ask conflicting agents to reconsider before
  the final report is generated, using the request/response pattern.
- **v0.4** — SQLite backend for `ask-codebase`: replace the file-based index with
  `sqlite-vec` for vector search. Same interface, persistent and queryable.
- **v0.5** — Incremental indexing: only re-embed files that changed since the last
  index run, tracked by content hash.

---

## Contributing

The agent contract is strict: every agent must return `list[Finding]` and must
never raise. Adding a new specialist agent means:

1. Create `pr_review/agents/your_agent.py` with a `run(filename, diff, provider) -> AgentResult` function
2. Register it in `pr_review/supervisor.py` in the `AGENTS` list
3. Add an icon for it in `pr_review/renderers/cli.py` in `AGENT_ICON`

No other files need to change. The deliberation phase picks up findings from any
registered agent automatically — there is nothing to configure in `deliberation.py`.

