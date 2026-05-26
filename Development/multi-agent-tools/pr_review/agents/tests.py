"""
pr_review/agents/tests.py
==========================
Specialist agent: test coverage review.

Looks for:
  - New functions or methods with no corresponding test
  - New branches (if/else, try/except) not covered by tests
  - Changed behaviour in existing functions without updated tests
  - Tests that exist but don't assert anything meaningful
  - Missing edge case tests (empty input, None, boundary values)
  - Test files that don't follow the project's naming convention

This agent is aware that test files are often separate from
implementation files. It looks at the diff as a whole to reason
about whether tests were added alongside new behaviour.
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

ROLE = "tests"

SYSTEM_PROMPT = """You are a test coverage reviewer. Your job is to identify
new or changed code that lacks adequate test coverage.

You review unified diffs. Focus on:
1. New functions, methods, or classes with no test
2. New code paths (branches, error handling) not covered by tests
3. Changed behaviour that existing tests may no longer correctly verify

Be practical. Not everything needs a test. But public APIs,
business logic, and error handling paths almost always do.

Return ONLY a JSON array of findings. If coverage looks adequate, return: []

Each finding:
{
  "severity": "warning" | "info",
  "line": <integer or null>,
  "message": "<what is untested and why it matters>",
  "suggestion": "<what test cases should be added>",
  "context": "<the untested code>"
}"""


USER_PROMPT_TEMPLATE = """Review test coverage for this diff.
File: {filename}

Is this a test file itself? {is_test_file}

```diff
{diff}
```

Identify new code that lacks tests. Return a JSON array."""


def is_test_file(filename: str) -> bool:
    name = filename.lower()
    return any(x in name for x in ["test_", "_test.", "spec.", "_spec.", "/tests/", "/test/"])


def run(
    filename: str,
    diff:     str,
    provider: Provider = Provider.ANTHROPIC,
) -> AgentResult:
    """Analyse one file's diff for test coverage gaps."""
    start = time.time()

    if not diff.strip():
        return AgentResult(agent=ROLE, ok=True, findings=[], duration=0.0, tokens=0)

    prompt = USER_PROMPT_TEMPLATE.format(
        filename     = filename,
        is_test_file = "Yes — reviewing test quality" if is_test_file(filename) else "No — look for missing tests",
        diff         = diff,
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
        log.debug("[tests] %s — %d finding(s) in %.1fs", filename, len(findings), duration)

        return AgentResult(agent=ROLE, ok=True, findings=findings,
                           duration=duration, tokens=resp.total_tokens)

    except Exception as exc:
        duration = time.time() - start
        log.error("[tests] failed on %s: %s", filename, exc)
        return AgentResult(agent=ROLE, ok=False, findings=[], error=str(exc), duration=duration)
