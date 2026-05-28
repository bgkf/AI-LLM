"""
pr_review/agents/security.py
=============================
Specialist agent: security vulnerabilities and secrets scanning.

Two-stage analysis:
  Stage 1: Fast regex prescan for hardcoded secrets (runs even if LLM fails)
  Stage 2: LLM analysis for deeper vulnerability patterns

Stage 1 catches obvious secrets in milliseconds without an LLM call.
The finding is guaranteed even if the API is unreachable or rate-limited.

Looks for:
  Stage 1 (regex):
    - API keys and tokens (sk-, pk-, ghp_, ghs_, AKIA*, etc.)
    - Private key PEM blocks
    - Hardcoded passwords in assignments and connection strings
    - Generic high-entropy secret tokens in assignments

  Stage 2 (LLM):
    - SQL / command / path injection risks
    - Unsafe eval() / exec() / subprocess with shell=True
    - Insecure deserialization (pickle.loads on untrusted data)
    - SSRF vulnerabilities (user-controlled URLs in requests)
    - Weak cryptography (MD5, SHA1 for passwords, random for tokens)
    - Missing authentication / authorisation checks on new endpoints
    - Sensitive data in logs or error messages
    - Unsafe file permissions or temp file usage
    - Unvalidated user input passed to dangerous functions
    - Hardcoded credentials missed by regex

Uses the smarter model — security findings have high cost of false negatives.
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

# ── Stage 1: regex prescan ────────────────────────────────────────────────────

SECRET_PATTERNS = [
    # Anthropic / OpenAI / generic sk- and pk- keys
    (re.compile(r'\bsk-[A-Za-z0-9_\-]{20,}'),  "Possible API secret key"),
    (re.compile(r'\bpk-[A-Za-z0-9_\-]{20,}'),  "Possible API public key with secret"),
    # GitHub tokens
    (re.compile(r'\bghp_[A-Za-z0-9]{36}\b'),    "Possible GitHub personal access token"),
    (re.compile(r'\bghs_[A-Za-z0-9]{36}\b'),    "Possible GitHub Actions token"),
    # AWS
    (re.compile(r'\bAKIA[0-9A-Z]{16}\b'),        "Possible AWS access key ID"),
    (re.compile(r'(?i)aws[_-]?secret[_-]?access[_-]?key\s*=\s*["\'][^"\']+["\']'),
     "AWS secret access key"),
    # Private keys
    (re.compile(r'-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----'),
     "PEM private key block"),
    # Passwords in assignments and connection strings
    (re.compile(r'(?:password|passwd|pwd)\s*=\s*["\'][^"\']{4,}["\']', re.I),
     "Possible hardcoded password"),
    # Generic high-entropy tokens in assignments
    (re.compile(r'(?:token|secret|api[_-]?key|apikey)\s*=\s*["\'][A-Za-z0-9+/=_\-]{16,}["\']', re.I),
     "Possible hardcoded secret token"),
]


def prescan(diff: str, filename: str) -> list[Finding]:
    """
    Fast regex scan of added lines (lines starting with '+').
    Skips the '+++ b/filename' diff header line.
    Returns findings without an LLM call — always runs, even if LLM fails.
    """
    findings = []
    for i, line in enumerate(diff.splitlines(), start=1):
        if not line.startswith("+") or line.startswith("+++"):
            continue
        code = line[1:]   # strip the leading '+' before pattern matching
        for pattern, label in SECRET_PATTERNS:
            if pattern.search(code):
                # Redact matched value, keeping first 6 chars for identification
                redacted = pattern.sub(
                    lambda m: m.group()[:6] + "***", code
                )
                findings.append(Finding(
                    message    = f"Possible {label} detected in added code",
                    file       = filename,
                    severity   = "error",
                    line       = i,
                    suggestion = (
                        "Move secrets to environment variables or a secrets manager "
                        "(e.g. HashiCorp Vault, AWS Secrets Manager). Never commit credentials."
                    ),
                    context    = f"+{redacted.strip()}",
                    agent      = ROLE,
                ))
                break   # one finding per line max from prescan
    return findings


# ── Stage 2: LLM analysis ─────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a security engineer reviewing a git diff for vulnerabilities.

You review unified diffs. Lines starting with + are additions (what to review).
Lines starting with - are removals (context only — don't flag these).

Focus on:
- SQL / command / path injection risks
- Unsafe eval() / exec() / subprocess with shell=True
- Insecure deserialization (pickle.loads on untrusted data)
- SSRF vulnerabilities (user-controlled URLs passed to requests)
- Weak cryptography (MD5/SHA1 for passwords, random for security tokens)
- Missing authentication / authorisation checks on new endpoints
- Sensitive data in logs or error messages
- Unsafe file permissions or temp file usage
- Unvalidated user input passed to dangerous functions
- Hardcoded credentials not caught by pattern matching

Do NOT report: style issues, missing tests, documentation gaps.
Do NOT repeat findings that obviously match /sk-[A-Za-z0-9]{20,}/ or similar
token patterns — those are caught by a prescan and will be deduplicated.

Return ONLY a JSON array. Each element:
  "message":    string — specific vulnerability description (reference the code)
  "file":       string — filename
  "severity":   "error" | "warning" | "info"
  "line":       integer | null
  "suggestion": string — concrete remediation step
  "context":    string | null — relevant code snippet (redact actual secret values with ***)

Severity guide:
  error   — exposed secret, direct injection risk, auth bypass
  warning — potential vulnerability depending on context, weak crypto
  info    — security smell worth investigating, defense-in-depth suggestion

If no security issues found, return [].
Do not include markdown fences. Return raw JSON only."""


USER_PROMPT_TEMPLATE = """Scan this diff for security vulnerabilities.
File: {filename}

Pre-scan flags (automatic pattern matches already found on added lines):
{prescan_summary}

```diff
{diff}
```

Return a JSON array. Redact any actual secret values in the context field."""


def run(
    filename: str,
    diff:     str,
    provider: Provider = Provider.ANTHROPIC,
) -> AgentResult:
    """
    Analyse one file's diff for security issues and secrets.

    Stage 1 (prescan) always runs and its findings are always returned,
    even if Stage 2 (LLM) fails. LLM failure is treated as degraded, not
    fatal — ok=True is returned so the supervisor doesn't suppress results.
    """
    start = time.monotonic()

    if not diff.strip():
        return AgentResult(agent=ROLE, ok=True, findings=[],
                           duration=0.0, tokens=0)

    # Stage 1: always run, no LLM needed
    prescan_findings = prescan(diff, filename)
    if prescan_findings:
        log.debug(
            "[security prescan] %s — %d secret(s)",
            filename, len(prescan_findings),
        )

    prescan_summary = "\n".join(
        f"  - Line {f.line}: {f.message}" for f in prescan_findings
    ) or "  none"

    # Stage 2: LLM analysis
    llm_findings: list[Finding] = []
    tokens = 0
    try:
        prompt = USER_PROMPT_TEMPLATE.format(
            filename        = filename,
            prescan_summary = prescan_summary,
            diff            = diff,
        )
        resp = complete(
            prompt,
            system      = SYSTEM_PROMPT,
            provider    = provider,
            model       = model_for_role(ROLE) if provider == Provider.ANTHROPIC else None,
            max_tokens  = 2048,
            temperature = 0.1,
        )
        llm_findings = parse_findings_from_json(resp.content, filename)
        for f in llm_findings:
            f.agent = ROLE
        tokens = resp.total_tokens
        log.debug("[security llm] %s — %d finding(s)", filename, len(llm_findings))

    except Exception as exc:
        log.error("[security] LLM stage failed on %s: %s", filename, exc)
        # prescan findings are still returned below

    # Deduplicate: if prescan already caught something on the same line,
    # keep the prescan version (it has a redacted context) and drop the LLM duplicate
    prescan_lines = {f.line for f in prescan_findings if f.line}
    deduped_llm   = [f for f in llm_findings if f.line not in prescan_lines]

    all_findings = prescan_findings + deduped_llm
    duration     = time.monotonic() - start

    log.debug(
        "[security] %s — %d finding(s) total (%d prescan, %d llm) in %.1fs",
        filename, len(all_findings), len(prescan_findings), len(deduped_llm), duration,
    )

    return AgentResult(
        agent    = ROLE,
        ok       = True,   # prescan always works; LLM failure is degraded not fatal
        findings = all_findings,
        duration = duration,
        tokens   = tokens,
    )
