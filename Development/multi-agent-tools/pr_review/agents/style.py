"""
pr_review/agents/style.py
==========================
Specialist agent: style and formatting review.

Looks for:
  - Naming convention violations (snake_case/camelCase per language)
  - Line length violations
  - Inconsistent indentation
  - Unused imports or variables in added code
  - Magic numbers without named constants
  - Overly complex expressions that should be broken up
  - Missing or malformed docstrings / comments
  - Dead code in additions (commented-out code, print debug statements)
  - Inconsistent string quoting within the same file

Uses haiku — style is pattern-matching, not deep reasoning.
Fast and cheap is the right tradeoff here.
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

ROLE = "style"

SYSTEM_PROMPT = """You are a code style reviewer. You check that new code follows
the conventions of its language and the surrounding codebase.

Review unified diffs. Only comment on added lines (starting with +).
Be concise. Do not flag things that are stylistic preferences without a clear
community standard — only flag genuine violations.

Return ONLY a JSON array of findings. If no style issues, return: []

Each finding:
{
  "severity": "warning" | "info",
  "line": <integer or null>,
  "message": "<what style rule is violated>",
  "suggestion": "<the corrected version or what to change>",
  "context": "<the specific line(s)>"
}

Never use "error" severity — style issues are never blockers by themselves.
Limit yourself to the 5 most important findings. Quality over quantity."""


USER_PROMPT_TEMPLATE = """Review the style of this diff.
File: {filename}
Language: {language}

```diff
{diff}
```

Return at most 5 findings as a JSON array. Prioritise real violations over preferences."""


def detect_language(filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return {
        "py": "Python", "swift": "Swift", "js": "JavaScript",
        "ts": "TypeScript", "sh": "Shell", "zsh": "Zsh",
        "rb": "Ruby", "go": "Go", "rs": "Rust",
    }.get(ext, "unknown")


def run(
    filename: str,
    diff:     str,
    provider: Provider = Provider.ANTHROPIC,
) -> AgentResult:
    """Analyse one file's diff for style violations."""
    start = time.time()

    if not diff.strip():
        return AgentResult(agent=ROLE, ok=True, findings=[], duration=0.0, tokens=0)

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
            max_tokens  = 1024,
            temperature = 0.1,
        )

        findings = parse_findings_from_json(resp.content, filename)
        for f in findings:
            f.agent = ROLE

        duration = time.time() - start
        log.debug("[style] %s — %d finding(s) in %.1fs", filename, len(findings), duration)

        return AgentResult(agent=ROLE, ok=True, findings=findings,
                           duration=duration, tokens=resp.total_tokens)

    except Exception as exc:
        duration = time.time() - start
        log.error("[style] failed on %s: %s", filename, exc)
        return AgentResult(agent=ROLE, ok=False, findings=[], error=str(exc), duration=duration)
