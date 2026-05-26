"""
shared/findings.py
==================
The data contract between every specialist agent and the aggregator.

Every agent returns list[Finding]. Nothing else.

Design rules:
  - Agents never raise exceptions — failures become Finding(severity="error")
  - Every Finding must have a message (what) and file (where)
  - suggestion is strongly encouraged — a finding without a fix is just a complaint
  - line is optional; agents should include it when they can determine it
  - agent field is set by the supervisor, not the agent itself
    (agents don't need to know their own name)

Severity levels:
  "error"   — must fix before merge (secrets, logic bugs, broken tests)
  "warning" — should fix (style violations, missing docs, untested paths)
  "info"    — worth knowing (observations, suggestions, non-blocking notes)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
import json


@dataclass
class Finding:
    """
    A single observation from a specialist agent.

    Invariants:
      - message is non-empty
      - file is non-empty
      - severity is one of: "error", "warning", "info"
      - line >= 1 if set
      - agent is set by the supervisor after the agent returns
    """
    message:    str
    file:       str
    severity:   str                  = "warning"
    line:       Optional[int]        = None
    suggestion: Optional[str]        = None
    agent:      str                  = ""        # filled by supervisor
    context:    Optional[str]        = None      # relevant code snippet

    VALID_SEVERITIES = {"error", "warning", "info"}

    def __post_init__(self):
        assert self.message.strip(),                          \
            "Finding.message must not be empty"
        assert self.file.strip(),                             \
            "Finding.file must not be empty"
        assert self.severity in self.VALID_SEVERITIES,       \
            f"Finding.severity must be one of {self.VALID_SEVERITIES}, got {self.severity!r}"
        if self.line is not None:
            assert self.line >= 1,                            \
                f"Finding.line must be >= 1, got {self.line}"

    def to_dict(self) -> dict:
        return {
            "agent":      self.agent,
            "severity":   self.severity,
            "file":       self.file,
            "line":       self.line,
            "message":    self.message,
            "suggestion": self.suggestion,
            "context":    self.context,
        }

    @classmethod
    def from_dict(cls, d: dict) -> Finding:
        return cls(
            message    = d["message"],
            file       = d["file"],
            severity   = d.get("severity",   "warning"),
            line       = d.get("line"),
            suggestion = d.get("suggestion"),
            agent      = d.get("agent",      ""),
            context    = d.get("context"),
        )

    def __str__(self) -> str:
        loc = f"{self.file}"
        if self.line:
            loc += f":{self.line}"
        icon = {"error": "✗", "warning": "⚠", "info": "ℹ"}.get(self.severity, "?")
        parts = [f"{icon} [{self.severity.upper()}] {loc}", f"  {self.message}"]
        if self.suggestion:
            parts.append(f"  → {self.suggestion}")
        return "\n".join(parts)


@dataclass
class AgentResult:
    """
    What a specialist agent returns to the supervisor.
    Always returned even on failure — failures become an empty findings
    list with ok=False and error set.
    """
    agent:    str
    ok:       bool
    findings: list[Finding]          = field(default_factory=list)
    error:    Optional[str]          = None
    duration: float                  = 0.0      # seconds
    tokens:   int                    = 0        # total tokens used

    @property
    def error_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "warning")


def parse_findings_from_json(raw: str, file: str) -> list[Finding]:
    """
    Parse LLM output that should be a JSON array of finding objects.
    Handles common LLM formatting issues (markdown fences, trailing commas).
    Returns an empty list if parsing fails — never raises.
    """
    import re

    # Strip markdown code fences if present
    cleaned = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("```").strip()

    # Find the first [ ... ] block
    match = re.search(r"\[.*\]", cleaned, re.DOTALL)
    if not match:
        return []

    try:
        items = json.loads(match.group())
    except json.JSONDecodeError:
        return []

    findings = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if not item.get("message"):
            continue
        try:
            findings.append(Finding(
                message    = item["message"],
                file       = item.get("file", file),
                severity   = item.get("severity", "warning"),
                line       = item.get("line"),
                suggestion = item.get("suggestion"),
                context    = item.get("context"),
            ))
        except AssertionError:
            continue   # skip malformed findings silently

    return findings
