"""
pr_review/agents/security.py
=============================
Specialist agent: security vulnerabilities and secrets scanning.

Looks for:
  - Hardcoded secrets, API keys, tokens, passwords, private keys
  - SQL injection, command injection, path traversal risks
  - Insecure deserialization
  - Unsafe use of eval(), exec(), subprocess with shell=True
  - Missing authentication / authorisation checks
  - Sensitive data in logs or error messages
  - Insecure random number generation for security purposes
  - Unsafe file permissions or temp file usage
  - Unvalidated user input passed to dangerous functions

Uses the smarter model — security review needs careful reasoning
and broad knowledge of attack patterns.
"""

from __future__ import annotations
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import re
import time
import logging
from shared.llm import complete, Provider, model_for_role
from shared.findings import Finding, AgentResult, parse_findings_from_json

log = logging.getLogger(__name__)

ROLE = "security"

# Fast pre-scan patterns — catch obvious secrets before hitting the LLM
# If any match, we still send to LLM but flag the pre-scan hit immediately
SECRET_PATTERNS = [
    (re.compile(r'(?i)(api[_-]?key|secret|password|passwd|token|private[_-]?key)\s*=\s*["\'][^"\']{8,}["\']'), "hardcoded secret"),
    (re.compile(r'(?i)aws[_-]?(access[_-]?key[_-]?id|secret[_-]?access[_-]?key)\s*=\s*["\'][^"\']+["\']'), "AWS credential"),
    (re.compile(r'sk-[a-zA-Z0-9]{20,}'), "OpenAI API key pattern"),
    (re.compile(r'ghp_[a-zA-Z0-9]{36}'), "GitHub personal access token"),
    (re.compile(r'(?i)BEGIN (RSA |EC |DSA |OPENSSH )?PRIVATE KEY'), "private key"),
]

SYSTEM_PROMPT = """You are a security-focused code reviewer and secrets scanner.

Your job is to find security vulnerabilities and hardcoded secrets in code changes.
Be thorough but avoid false positives — only flag real risks.

You review unified diffs. Lines starting with + are additions (what to review).
Lines starting with - are removals (context only — don't flag these).

Return ONLY a JSON array of findings. No prose, no markdown, no preamble.
If there are no issues, return: []

Each finding:
{
  "severity": "error" | "warning" | "info",
  "line": <integer line number or null>,
  "message": "<what the vulnerability or secret is>",
  "suggestion": "<how to fix it>",
  "context": "<the problematic code — redact actual secret values with ***>"
}

Severity guide:
  error   — exposed secret, direct injection risk, auth bypass
  warning — potential vulnerability depending on context, weak crypto
  info    — security smell worth investigating, defense-in-depth suggestion"""


USER_PROMPT_TEMPLATE = """Scan this diff for security issues and hardcoded secrets.
File: {filename}

Pre-scan flags (automatic pattern matches on added lines):
{prescan_flags}

```diff
{diff}
```

Return a JSON array. Redact any actual secret values in the context field."""


def prescan(diff: str, filename: str) -> list[Finding]:
    """
    Fast regex-based pre-scan for obvious secrets.
    Runs before the LLM call — catches things that don't need reasoning.
    """
    findings = []
    for i, line in enumerate(diff.splitlines(), 1):
        if not line.startswith("+"):
            continue
        for pattern, label in SECRET_PATTERNS:
            if pattern.search(line):
                # Redact the matched value before storing
                redacted = re.sub(r'(["\'])[^"\']{4}[^"\']*(["\'])', r'\1***\2', line)
                findings.append(Finding(
                    message    = f"Possible {label} detected in added code",
                    file       = filename,
                    severity   = "error",
                    line       = i,
                    suggestion = "Move secrets to environment variables or a secrets manager. Never commit credentials.",
                    context    = redacted.strip(),
                    agent      = ROLE,
                ))
                break   # one finding per line max from pre-scan
    return findings


def run(
    filename: str,
    diff:     str,
    provider: Provider = Provider.ANTHROPIC,
) -> AgentResult:
    """Analyse one file's diff for security issues and secrets."""
    start = time.time()

    if not diff.strip():
        return AgentResult(agent=ROLE, ok=True, findings=[],
                           duration=0.0, tokens=0)

    # Pre-scan first — fast, no LLM needed
    prescan_findings = prescan(diff, filename)
    prescan_summary  = "\n".join(
        f"  - Line {f.line}: {f.message}" for f in prescan_findings
    ) or "  none"

    prompt = USER_PROMPT_TEMPLATE.format(
        filename       = filename,
        prescan_flags  = prescan_summary,
        diff           = diff,
    )

    try:
        resp = complete(
            prompt,
            system      = SYSTEM_PROMPT,
            provider    = provider,
            model       = model_for_role(ROLE),
            max_tokens  = 2048,
            temperature = 0.1,
        )

        llm_findings = parse_findings_from_json(resp.content, filename)
        for f in llm_findings:
            f.agent = ROLE

        # Deduplicate: if prescan already caught something on the same line,
        # keep prescan version (it has a redacted context) and skip LLM duplicate
        prescan_lines = {f.line for f in prescan_findings if f.line}
        deduped = [f for f in llm_findings if f.line not in prescan_lines]

        all_findings = prescan_findings + deduped
        duration     = time.time() - start

        log.debug(
            "[security] %s — %d finding(s) (%d prescan, %d llm) in %.1fs",
            filename, len(all_findings), len(prescan_findings), len(deduped), duration
        )

        return AgentResult(
            agent    = ROLE,
            ok       = True,
            findings = all_findings,
            duration = duration,
            tokens   = resp.total_tokens,
        )

    except Exception as exc:
        duration = time.time() - start
        log.error("[security] failed on %s: %s", filename, exc)
        # Still return prescan findings even if LLM fails
        return AgentResult(
            agent    = ROLE,
            ok       = False,
            findings = prescan_findings,
            error    = str(exc),
            duration = duration,
        )
