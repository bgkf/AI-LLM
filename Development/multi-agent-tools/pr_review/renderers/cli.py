"""
pr_review/renderers/cli.py
===========================
Renders a ReviewResult to terminal output.

Design: the renderer knows nothing about agents or findings logic.
It receives a ReviewResult and produces formatted output.
Swapping to the GitHub renderer later is a one-line change in __main__.py.

Output modes:
  full      — all findings, grouped by file, with context and suggestions
  summary   — one line per finding, sorted by severity
  compact   — just the counts and a pass/fail signal (good for CI)
"""

from __future__ import annotations
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from pr_review.supervisor import ReviewResult
from shared.findings import Finding

# ANSI colours — disabled automatically when stdout is not a tty
def _supports_colour() -> bool:
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()

RESET  = "\033[0m"  if _supports_colour() else ""
BOLD   = "\033[1m"  if _supports_colour() else ""
RED    = "\033[91m" if _supports_colour() else ""
YELLOW = "\033[93m" if _supports_colour() else ""
CYAN   = "\033[96m" if _supports_colour() else ""
GREEN  = "\033[92m" if _supports_colour() else ""
DIM    = "\033[2m"  if _supports_colour() else ""

SEVERITY_COLOUR = {
    "error":   RED,
    "warning": YELLOW,
    "info":    CYAN,
}

SEVERITY_ICON = {
    "error":   "✗",
    "warning": "⚠",
    "info":    "ℹ",
}

AGENT_ICON = {
    "logic":    "🧠",
    "security": "🔒",
    "style":    "✏️ ",
    "tests":    "🧪",
    "docs":     "📝",
}


def _severity_label(severity: str) -> str:
    colour = SEVERITY_COLOUR.get(severity, "")
    icon   = SEVERITY_ICON.get(severity, "?")
    return f"{colour}{icon} {severity.upper()}{RESET}"


def _finding_block(f: Finding) -> str:
    """Format a single finding as a multi-line block."""
    lines = []

    # Header: severity + file + line
    loc = f.file
    if f.line:
        loc += f":{f.line}"
    agent_icon = AGENT_ICON.get(f.agent, "·")
    lines.append(
        f"  {_severity_label(f.severity)}  {BOLD}{loc}{RESET}  "
        f"{DIM}[{agent_icon} {f.agent}]{RESET}"
    )

    # Message
    lines.append(f"  {f.message}")

    # Context (the actual code)
    if f.context:
        for ctx_line in f.context.strip().splitlines():
            lines.append(f"  {DIM}  {ctx_line}{RESET}")

    # Suggestion
    if f.suggestion:
        lines.append(f"  {GREEN}→ {f.suggestion}{RESET}")

    return "\n".join(lines)


def render_full(result: ReviewResult) -> str:
    """Full output: findings grouped by file."""
    out = []

    # Header
    out.append(f"\n{BOLD}PR Review{RESET}")
    out.append(
        f"{DIM}reviewed {result.files_reviewed} file(s) · "
        f"{len(result.agent_results)} agent runs · "
        f"{result.total_tokens:,} tokens · "
        f"{result.duration:.1f}s{RESET}"
    )

    if result.files_skipped:
        out.append(f"{DIM}skipped {result.files_skipped} file(s) (binary/generated){RESET}")

    # Failed agents warning
    if result.failed_agents:
        out.append(f"\n{YELLOW}⚠ Some agents failed:{RESET}")
        for fa in result.failed_agents:
            out.append(f"  {DIM}{fa}{RESET}")

    # No findings
    if not result.findings:
        out.append(f"\n{GREEN}✓ No issues found{RESET}")
        return "\n".join(out)

    # Findings grouped by file
    by_file: dict[str, list[Finding]] = {}
    for f in result.findings:
        by_file.setdefault(f.file, []).append(f)

    out.append("")
    for filename, findings in sorted(by_file.items()):
        errors   = sum(1 for f in findings if f.severity == "error")
        warnings = sum(1 for f in findings if f.severity == "warning")
        infos    = sum(1 for f in findings if f.severity == "info")

        counts = []
        if errors:   counts.append(f"{RED}{errors} error(s){RESET}")
        if warnings: counts.append(f"{YELLOW}{warnings} warning(s){RESET}")
        if infos:    counts.append(f"{CYAN}{infos} info{RESET}")

        out.append(f"{BOLD}{filename}{RESET}  {', '.join(counts)}")
        out.append("─" * 60)
        for f in findings:
            out.append(_finding_block(f))
            out.append("")

    # Summary line
    out.append("─" * 60)
    summary_parts = []
    if result.error_count:
        summary_parts.append(f"{RED}{result.error_count} error(s){RESET}")
    if result.warning_count:
        summary_parts.append(f"{YELLOW}{result.warning_count} warning(s){RESET}")
    if result.info_count:
        summary_parts.append(f"{CYAN}{result.info_count} info{RESET}")

    verdict = (
        f"{RED}✗ REVIEW REQUIRED{RESET}" if result.has_blockers
        else f"{GREEN}✓ APPROVED (warnings only){RESET}" if result.warning_count
        else f"{GREEN}✓ LGTM{RESET}"
    )
    out.append(f"{verdict}  {' · '.join(summary_parts)}")

    return "\n".join(out)


def render_compact(result: ReviewResult) -> str:
    """One-line output — useful for CI scripts checking exit code."""
    if not result.findings:
        return f"✓ LGTM — {result.files_reviewed} file(s) reviewed, no issues"

    parts = []
    if result.error_count:   parts.append(f"{result.error_count} error(s)")
    if result.warning_count: parts.append(f"{result.warning_count} warning(s)")
    if result.info_count:    parts.append(f"{result.info_count} info")

    status = "✗ BLOCKED" if result.has_blockers else "⚠ WARNINGS"
    return f"{status} — {', '.join(parts)} across {result.files_reviewed} file(s)"


def print_full(result: ReviewResult):
    print(render_full(result))


def print_compact(result: ReviewResult):
    print(render_compact(result))
