"""
pr_review/agents/logic.py
==========================
Specialist agent: logic and correctness review.

Looks for:
  - Off-by-one errors and boundary condition bugs
  - Null / None dereference risks on unguarded paths
  - Resource leaks (files, connections, sockets not closed in all paths)
  - Async/concurrency issues (missing await, unawaited coroutines, blocking
    calls in async context)
  - Error handling gaps (bare except, swallowed exceptions, silent continues)
  - Incorrect boolean logic (De Morgan errors, always-true/false conditions)
  - Mutating a collection while iterating over it
  - Unreachable code or dead branches
  - Type mismatches that type checkers might miss at runtime

Uses the smarter model (Sonnet) — logic errors are expensive to miss and
benefit most from deeper reasoning.

Does NOT look for:
  - Style issues (that's style.py)
  - Security vulnerabilities (that's security.py)
  - Test coverage (that's tests.py)
"""

from __future__ import annotations
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import time
import logging
from shared.llm import complete, Provider, model_for_role
from shared.findings import Finding, AgentResult, parse_findings_from_json

log = logging.getLogger(__name__)

ROLE = "logic"

SYSTEM_PROMPT = """You are a senior software engineer specialising in logic and correctness review.
You are reviewing a git diff. Your job is to find real bugs — not style issues, not missing
docs, not test gaps. Only flag things that could cause incorrect behaviour at runtime.

You review unified diffs. Lines starting with + are additions. Lines starting with - are removals.
Only comment on added lines (starting with +) unless a removal creates a new bug by itself.

Focus on:
- Off-by-one errors and boundary conditions
- Null / None dereferences on unguarded paths
- Resource leaks (files, connections, sockets not closed in all paths)
- Async/await misuse (missing await, unawaited coroutines, blocking calls in async context)
- Swallowed exceptions (bare except, except: pass, logging error then continuing silently)
- Incorrect boolean logic (De Morgan errors, always-true/false conditions)
- Mutating a collection while iterating over it
- Unreachable code or dead branches
- Type mismatches that type checkers might miss at runtime

Do NOT report: style issues, missing docstrings, test coverage, formatting.

Return ONLY a JSON array. Each element must have:
  "message":    string — what the bug is (be specific, reference the code)
  "file":       string — filename
  "severity":   "error" | "warning" | "info"
  "line":       integer | null — line number in the diff (+ lines)
  "suggestion": string — concrete fix (not just "fix this")
  "context":    string | null — the relevant code snippet

Severity guide:
  error   — will cause a crash, data corruption, or incorrect output at runtime
  warning — likely to cause problems in edge cases or under load
  info    — worth knowing, but not urgent

If no logic issues found, return [].
Do not include markdown fences. Return raw JSON only."""


USER_PROMPT_TEMPLATE = """Review this diff for logic and correctness issues.
File: {filename}
Language detected: {language}

```diff
{diff}
```

Return a JSON array of findings. Empty array if no issues."""


def detect_language(filename: str) -> str:
    """Crude but fast language detection from file extension."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return {
        "py":    "Python",
        "swift": "Swift",
        "js":    "JavaScript",
        "ts":    "TypeScript",
        "sh":    "Bash/Shell",
        "zsh":   "Zsh",
        "bash":  "Bash",
        "rb":    "Ruby",
        "go":    "Go",
        "rs":    "Rust",
    }.get(ext, "unknown")


def run(
    filename: str,
    diff:     str,
    provider: Provider = Provider.ANTHROPIC,
) -> AgentResult:
    """
    Analyse one file's diff for logic bugs.

    Parameters
    ----------
    filename : the file path from the diff header
    diff     : the unified diff text for this file
    provider : which LLM backend to use

    Returns
    -------
    AgentResult — always returned, never raises
    """
    start = time.monotonic()

    if not diff.strip():
        return AgentResult(agent=ROLE, ok=True, findings=[],
                           duration=0.0, tokens=0)

    prompt = USER_PROMPT_TEMPLATE.format(
        filename = filename,
        language = detect_language(filename),
        diff     = diff,
    )

    try:
        resp = complete(
            prompt,
            system      = SYSTEM_PROMPT,
            provider    = provider,
            model       = model_for_role(ROLE) if provider == Provider.ANTHROPIC else None,
            max_tokens  = 2048,
            temperature = 0.1,    # very low — we want consistent analysis
        )

        findings = parse_findings_from_json(resp.content, filename)

        # Stamp agent name onto every finding
        for f in findings:
            f.agent = ROLE

        duration = time.monotonic() - start
        log.debug(
            "[logic] %s — %d finding(s) in %.1fs (%d tokens)",
            filename, len(findings), duration, resp.total_tokens,
        )

        return AgentResult(
            agent    = ROLE,
            ok       = True,
            findings = findings,
            duration = duration,
            tokens   = resp.total_tokens,
        )

    except Exception as exc:
        duration = time.monotonic() - start
        log.error("[logic] failed on %s: %s", filename, exc)
        return AgentResult(
            agent    = ROLE,
            ok       = False,
            findings = [],
            error    = str(exc),
            duration = duration,
        )
