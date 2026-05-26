"""
pr_review/agents/logic.py
==========================
Specialist agent: logic and correctness review.

Looks for:
  - Off-by-one errors and boundary condition bugs
  - Null / None dereference risks
  - Incorrect conditionals or inverted logic
  - Resource leaks (files, connections, locks not closed)
  - Async/concurrency issues (race conditions, missing awaits)
  - Error handling gaps (bare except, swallowed exceptions)
  - Unreachable code or dead branches
  - Type mismatches that type checkers might miss at runtime

Uses the smarter model (sonnet) — logic review benefits most from
deeper reasoning. This is the agent most likely to catch real bugs.

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

SYSTEM_PROMPT = """You are an expert code reviewer specialising in logic correctness and runtime bugs.

Your job is to find real bugs — not style issues, not security issues, not test coverage gaps.
Focus on problems that would cause incorrect behaviour at runtime.

You review unified diffs. Lines starting with + are additions. Lines starting with - are removals.
Only comment on added lines (starting with +) unless a removal creates a new bug by itself.

Return ONLY a JSON array of findings. No prose, no markdown, no explanation outside the JSON.
If there are no issues, return an empty array: []

Each finding must have this exact shape:
{
  "severity": "error" | "warning" | "info",
  "line": <line number in the diff, integer or null>,
  "message": "<what is wrong, one clear sentence>",
  "suggestion": "<concrete fix, one clear sentence>",
  "context": "<the specific line(s) of code this refers to>"
}

Severity guide:
  error   — will cause a crash, data corruption, or incorrect output at runtime
  warning — likely to cause problems in edge cases or under load
  info    — worth knowing, but not urgent"""


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
    start = time.time()

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
            model       = model_for_role(ROLE),
            max_tokens  = 2048,
            temperature = 0.1,    # very low — we want consistent analysis
        )

        findings = parse_findings_from_json(resp.content, filename)

        # Stamp agent name onto every finding
        for f in findings:
            f.agent = ROLE

        duration = time.time() - start
        log.debug(
            "[logic] %s — %d finding(s) in %.1fs (%d tokens)",
            filename, len(findings), duration, resp.total_tokens
        )

        return AgentResult(
            agent    = ROLE,
            ok       = True,
            findings = findings,
            duration = duration,
            tokens   = resp.total_tokens,
        )

    except Exception as exc:
        duration = time.time() - start
        log.error("[logic] failed on %s: %s", filename, exc)
        return AgentResult(
            agent    = ROLE,
            ok       = False,
            findings = [],
            error    = str(exc),
            duration = duration,
        )
