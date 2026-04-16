# code-review-mcp-server

A Claude Code sub-agent that performs automated code review using Claude as the review engine.

## What it does

Exposes two MCP tools to Claude Code:

| Tool | Description |
|------|-------------|
| `review_file` | Reviews a complete source file |
| `review_diff` | Reviews staged/unstaged git changes or a diff against a base ref |

Every review covers:
- 🔴 **Security vulnerabilities** — injections, hardcoded secrets, auth flaws
- 🐛 **Logic bugs** — edge cases, null dereferences, race conditions
- 🎨 **Code style** — naming, DRY, complexity, readability
- ⚡ **Performance** — N+1 queries, unnecessary allocations, blocking ops
- 🧪 **Test coverage gaps** — missing happy path, edge case, and error tests
- 💬 **Comments & docs** — missing docstrings, misleading or outdated comments

Output is delivered in two places simultaneously:
1. **Inline summary** printed in Claude Code with verdict + top issues
2. **Full `review.md`** written to disk with every issue, severity, and suggested fix

## Prerequisites

- Node.js 18+
- An Anthropic API key (get one at [console.anthropic.com](https://console.anthropic.com))

## Installation

```bash
cd code-review-mcp-server
npm install
npm run build
```

## Register with Claude Code

Use the Claude Code CLI to register the server. Because Claude Code launches with a minimal PATH, you need to use the **absolute path to node** rather than just `node`.

Find your node path:
```bash
which node
```

Then register the server (replace paths accordingly):
```bash
claude mcp add code-review --env ANTHROPIC_API_KEY=your-key-here -- /opt/homebrew/bin/node /absolute/path/to/code-review-mcp-server/dist/index.js
```

Verify it registered:
```bash
claude mcp list
```

> **Note:** Using `/opt/homebrew/bin/node` is correct for Homebrew-installed Node on Apple Silicon. If your `which node` returned a different path (e.g. `~/.nvm/versions/node/.../bin/node`), use that instead.

## Verify the connection

Inside a Claude Code session, run:
```
/mcp
```

You should see `code-review` listed with `review_file` and `review_diff` as available tools.

## Usage in Claude Code

Once registered, you can invoke the tools naturally:

```
Review src/auth.ts
```
```
Review my staged changes
```
```
Review changes vs main branch
```
```
Check this file for security issues: utils/db.ts
```

## Tool Reference

### `review_file`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `file_path` | string | required | Path to the source file to review |
| `output_path` | string | `review.md` | Where to write the full report |

### `review_diff`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `diff` | string | auto-captured | Raw git diff text (optional) |
| `base_ref` | string | — | Git ref to diff against, e.g. `main` |
| `output_path` | string | `review.md` | Where to write the full report |
| `working_dir` | string | `cwd` | Directory for git commands |

## Verdict levels

| Verdict | Meaning |
|---------|---------|
| ✅ `APPROVE` | No significant issues found |
| ❌ `REQUEST_CHANGES` | Critical or high-severity issues must be fixed |
| 💬 `NEEDS_DISCUSSION` | Issues that require a judgment call or design discussion |

## Severity levels

| Severity | Meaning |
|----------|---------|
| 🔴 CRITICAL | Must fix — security hole, crash, or data loss risk |
| 🟠 HIGH | Should fix before merge |
| 🟡 MEDIUM | Should address soon |
| 🔵 LOW | Nice to have |
| ⚪ INFO | Informational, no action required |
