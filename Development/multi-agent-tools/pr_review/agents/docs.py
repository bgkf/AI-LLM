"""
pr_review/agents/docs.py
=========================
Specialist agent: documentation gaps review.

Looks for:
  - Public functions / methods / classes with no docstring
  - Docstrings that don't match the current signature (stale docs)
  - Missing parameter or return type documentation
  - Parameter types or return types missing from existing docstrings
    when new parameters were added
  - Complex logic with no inline explanation
  - README or changelog sections that reference removed functionality
    or should be updated for changed behaviour
  - Public APIs that changed their behaviour without updating their docs
  - Exported symbols with no usage example

Only flags documentation gaps for code ADDED in this diff.
Does not flag pre-existing undocumented code unless the diff touched it.
Does not flag private functions (starting with _) or test functions.

Uses haiku — documentation review is pattern recognition,
not deep reasoning. Fast is the right tradeoff here.
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

ROLE = "docs"

SYSTEM_PROMPT = """You are a documentation reviewer. You check that new and changed
code is adequately documented for the next developer who reads it.

Review unified diffs. Focus on added lines (starting with +).

Flag:
  - Public APIs (functions, classes, methods) with no docstring
  - Docstrings that clearly don't match the current code or are stale
  - Non-obvious logic with no explanation
  - Parameters or return values that aren't documented
  - README sections that reference removed functionality
  - Public APIs that changed their behaviour without updating their docs

Only flag documentation gaps for code ADDED in this diff.
Do not flag pre-existing undocumented code unless the diff touched it.

Do NOT flag:
  - Private helpers (leading underscore) unless they're complex
  - One-liners that are self-explanatory
  - Test functions (they document themselves by name)

Return ONLY a JSON array. If documentation looks adequate, return: []

Each finding:
{
  "severity": "warning" | "info",
  "line": <integer or null>,
  "message": "<what documentation is missing or wrong>",
  "suggestion": "<what should be documented and how — one-sentence example is ideal>",
  "context": "<the undocumented code or function/class signature>"
}

Limit to 5 findings maximum. Prioritise public APIs over internals.
Docs issues are never "error" severity."""


USER_PROMPT_TEMPLATE = """Review documentation in this diff.
File: {filename}
Language: {language}

```diff
{diff}
```

Return a JSON array of documentation findings."""


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
    """Analyse one file's diff for documentation gaps."""
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
            # Docs agent can only emit warning/info — downgrade any errors
            if f.severity == "error":
                f.severity = "warning"

        duration = time.time() - start
        log.debug("[docs] %s — %d finding(s) in %.1fs", filename, len(findings), duration)

        return AgentResult(agent=ROLE, ok=True, findings=findings,
                           duration=duration, tokens=resp.total_tokens)

    except Exception as exc:
        duration = time.time() - start
        log.error("[docs] failed on %s: %s", filename, exc)
        return AgentResult(agent=ROLE, ok=False, findings=[], error=str(exc), duration=duration)
