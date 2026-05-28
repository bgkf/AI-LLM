"""
pr_review/renderers/cli.py
===========================
Colour terminal renderer for PR review results.

Supports both plain Finding objects (v1 API) and EnrichedFinding objects
(v2 API with deliberation metadata). When EnrichedFindings are present on
the ReviewResult, the richer display path is used automatically.

EnrichedFinding extras rendered:
  - Corroboration badges:  [2 agents agree], [confirmed by security]
  - Conflict markers:      ⚡ conflicts with style
  - Confidence dimming:    low-confidence findings rendered in grey

ANSI colour codes are disabled automatically when stdout is not a TTY
(piped output, CI logs), when NO_COLOR env var is set, or TERM=dumb.

Output modes
────────────
  print_full(result)      — all findings grouped by file, full annotation
  print_compact(result)   — one line per finding (CI-friendly)
  render_full(result)     — same as print_full but returns a string
  render_compact(result)  — same as print_compact but returns a string
  render_summary(result)  — one line per finding, sorted by severity (string)
"""

from __future__ import annotations

import io
import os
import sys
from contextlib import redirect_stdout
from typing import Union

from pr_review.supervisor import ReviewResult
from shared.findings import Finding

# EnrichedFinding is optional — import gracefully so the module works even
# when the deliberation layer hasn't been wired in yet.
try:
    from shared.finding_store import EnrichedFinding
    _HAS_ENRICHED = True
except ImportError:
    EnrichedFinding = None  # type: ignore[assignment,misc]
    _HAS_ENRICHED = False

AnyFinding = Union["Finding", "EnrichedFinding"]


# ── ANSI colour helpers ────────────────────────────────────────────────────────

_USE_COLOR = (
    hasattr(sys.stdout, "isatty")
    and sys.stdout.isatty()
    and os.getenv("NO_COLOR") is None
    and os.getenv("TERM") != "dumb"
)


def _c(code: str, text: str) -> str:
    if not _USE_COLOR:
        return text
    return f"\033[{code}m{text}\033[0m"


def red(t: str)     -> str: return _c("31", t)
def yellow(t: str)  -> str: return _c("33", t)
def cyan(t: str)    -> str: return _c("36", t)
def grey(t: str)    -> str: return _c("90", t)
def bold(t: str)    -> str: return _c("1",  t)
def green(t: str)   -> str: return _c("32", t)
def magenta(t: str) -> str: return _c("35", t)
def dim(t: str)     -> str: return _c("2",  t)


# ── Lookup tables ─────────────────────────────────────────────────────────────

AGENT_ICON = {
    "logic":    "🧠",
    "security": "🔒",
    "style":    "✏️",
    "tests":    "🧪",
    "docs":     "📝",
}

SEVERITY_ICON = {
    "error":   "✗",
    "warning": "⚠",
    "info":    "ℹ",
}

SEVERITY_COLOR = {
    "error":   red,
    "warning": yellow,
    "info":    cyan,
}


def _fmt_severity(severity: str, text: str) -> str:
    fn = SEVERITY_COLOR.get(severity, lambda x: x)
    return fn(text)


# ── Single-finding formatters ─────────────────────────────────────────────────

def _fmt_plain_finding(f: Finding, indent: str = "  ") -> list[str]:
    """Format a plain Finding (v1) into display lines."""
    lines: list[str] = []

    icon    = SEVERITY_ICON.get(f.severity, "?")
    sev_str = _fmt_severity(f.severity, f"{icon} {f.severity.upper()}")
    loc     = f"{f.file}:{f.line}" if f.line else f.file
    agent_icon = AGENT_ICON.get(f.agent, "·")

    lines.append(
        f"{indent}{sev_str}  {bold(loc)}  [{agent_icon} {f.agent}]"
    )
    lines.append(f"{indent}  {f.message}")

    if f.context:
        for ctx_line in f.context.strip().splitlines():
            lines.append(f"{indent}  {dim(ctx_line)}")

    if f.suggestion:
        lines.append(f"{indent}  {green('→')} {f.suggestion}")

    return lines


def _fmt_enriched_finding(ef: "EnrichedFinding", indent: str = "  ") -> list[str]:
    """
    Format an EnrichedFinding (v2) into display lines.

    Layout:
      ✗ ERROR  auth/token.py:14  [🔒 security]  [2 agents agree]
      Possible hardcoded secret detected in added code
      → Move secrets to environment variables
      ⚡ conflicts with style (they rated this lower severity)
      +API_KEY = "sk-***"
    """
    lines: list[str] = []

    icon       = SEVERITY_ICON.get(ef.severity, "?")
    sev_str    = _fmt_severity(ef.severity, f"{icon} {ef.severity.upper()}")
    loc        = f"{ef.file}:{ef.line}" if ef.line else ef.file
    agent_icon = AGENT_ICON.get(ef.agent, "·")

    # Corroboration badge
    badge = ""
    if ef.corroborated_by:
        n = len(ef.corroborated_by) + 1
        badge = (
            green(f" [{n} agents agree]")
            if n >= 3
            else green(f" [confirmed by {ef.corroborated_by[0]}]")
        )

    # Dim low-confidence location strings
    loc_str = grey(loc) if ef.confidence < 0.6 else bold(loc)

    lines.append(f"{indent}{sev_str}  {loc_str}  [{agent_icon} {ef.agent}]{badge}")

    msg_color = grey if ef.confidence < 0.6 else (lambda x: x)
    lines.append(f"{indent}  {msg_color(ef.message)}")

    if ef.suggestion:
        lines.append(f"{indent}  {cyan('→')} {ef.suggestion}")

    if ef.has_conflict:
        hint = _opposite_severity(ef.severity)
        conflict_str = magenta(
            f"  ⚡ conflicts with {', '.join(ef.conflicts_with)} "
            f"(they rated this {hint})"
        )
        lines.append(f"{indent}  {conflict_str}")

    if ef.context:
        lines.append(f"{indent}  {grey(ef.context.strip())}")

    return lines


def _opposite_severity(s: str) -> str:
    return {
        "error":   "lower severity",
        "warning": "higher or lower severity",
        "info":    "higher severity",
    }.get(s, "different severity")


def _fmt_finding(f: AnyFinding, indent: str = "  ") -> list[str]:
    """Dispatch to the right formatter based on finding type."""
    if _HAS_ENRICHED and isinstance(f, EnrichedFinding):
        return _fmt_enriched_finding(f, indent)
    return _fmt_plain_finding(f, indent)  # type: ignore[arg-type]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _all_findings(result: ReviewResult) -> list[AnyFinding]:
    """Return enriched findings if available, else plain findings."""
    if _HAS_ENRICHED and result.enriched_findings:
        return result.enriched_findings  # type: ignore[return-value]
    return result.findings


def _print_footer(result: ReviewResult) -> None:
    """Print the final verdict line and any agent failures."""
    print("  " + "─" * 60)

    if result.failed_agents:
        print()
        print(yellow("  ⚠ Some agents failed:"))
        for fa in result.failed_agents:
            print(grey(f"    {fa}"))

    print()
    if result.has_blockers:
        verdict = red("✗ REVIEW REQUIRED")
        counts: list[str] = []
        if result.error_count:   counts.append(red(f"{result.error_count} error(s)"))
        if result.warning_count: counts.append(yellow(f"{result.warning_count} warning(s)"))
        if result.info_count:    counts.append(cyan(f"{result.info_count} info"))
        print(f"  {verdict}  {' · '.join(counts)}")
    else:
        verdict = green("✓ APPROVED")
        if result.warning_count or result.info_count:
            counts = []
            if result.warning_count: counts.append(yellow(f"{result.warning_count} warning(s)"))
            if result.info_count:    counts.append(cyan(f"{result.info_count} info"))
            print(f"  {verdict}  {' · '.join(counts)} (no blocking errors)")
        else:
            print(f"  {verdict}")

    print()


# ── Full renderer ─────────────────────────────────────────────────────────────

def print_full(result: ReviewResult) -> None:
    """
    Full colour-coded output grouped by file.
    Uses EnrichedFinding display (corroboration badges, conflict markers)
    when available, otherwise falls back to plain Finding display.
    """
    print()
    print(bold("PR Review"))

    # Metadata summary line
    agent_runs   = len(result.agent_results)
    duration_str = f"{result.duration:.1f}s"
    tokens_str   = f"{result.total_tokens:,} tokens"

    summary_parts = [
        f"reviewed {bold(str(result.files_reviewed))} file(s)",
        f"{bold(str(agent_runs))} agent runs",
        tokens_str,
        duration_str,
    ]
    if result.files_skipped:
        summary_parts.append(f"{result.files_skipped} skipped")
    print(grey("  " + " · ".join(summary_parts)))

    # Deliberation summary line (only when enriched data is present)
    if (
        _HAS_ENRICHED
        and getattr(result, "deliberation", False)
        and (getattr(result, "corroborated_count", 0) or getattr(result, "conflict_count", 0))
    ):
        delib_parts: list[str] = []
        if result.corroborated_count:
            delib_parts.append(green(f"{result.corroborated_count} corroborated"))
        if result.conflict_count:
            delib_parts.append(magenta(f"{result.conflict_count} conflicted"))
        print(grey("  deliberation: ") + " · ".join(delib_parts))

    findings = _all_findings(result)

    if not findings:
        print()
        print(green("  ✓ No issues found"))
        _print_footer(result)
        return

    # Group by file
    by_file: dict[str, list[AnyFinding]] = {}
    for f in findings:
        by_file.setdefault(f.file, []).append(f)

    for filename, file_findings in sorted(by_file.items()):
        errors   = sum(1 for f in file_findings if f.severity == "error")
        warnings = sum(1 for f in file_findings if f.severity == "warning")
        infos    = sum(1 for f in file_findings if f.severity == "info")

        count_parts: list[str] = []
        if errors:   count_parts.append(red(f"{errors} error(s)"))
        if warnings: count_parts.append(yellow(f"{warnings} warning(s)"))
        if infos:    count_parts.append(cyan(f"{infos} info"))

        print()
        print(f"  {bold(filename)}  {', '.join(count_parts)}")
        print("  " + "─" * 60)

        for f in file_findings:
            for line in _fmt_finding(f):
                print(line)
            print()

    _print_footer(result)


# ── Compact renderer ──────────────────────────────────────────────────────────

def print_compact(result: ReviewResult) -> None:
    """
    One line per finding — designed for CI log output.
    Includes corroboration and conflict markers as text suffixes when
    EnrichedFindings are present. No colour codes when piped.
    """
    findings = _all_findings(result)

    if not findings:
        print(f"✓ LGTM — {result.files_reviewed} file(s) reviewed, no issues")
        return

    for f in findings:
        loc  = f"{f.file}:{f.line}" if f.line else f.file
        icon = SEVERITY_ICON.get(f.severity, "?")

        # Enriched extras
        badge    = ""
        conflict = ""
        if _HAS_ENRICHED and isinstance(f, EnrichedFinding):
            if f.corroborated_by:
                badge = f" [{len(f.corroborated_by) + 1} agree]"
            if f.has_conflict:
                conflict = f" [!conflicts with {','.join(f.conflicts_with)}]"

        print(
            f"{icon} {f.severity.upper():7s} {loc:40s} "
            f"[{f.agent}]{badge}{conflict}  {f.message}"
        )

    # Summary footer
    print()
    status = "FAIL" if result.has_blockers else "PASS"
    print(
        f"{status}  "
        f"{result.error_count}E {result.warning_count}W {result.info_count}I  "
        f"{result.files_reviewed} file(s)  "
        f"{result.total_tokens:,} tokens  "
        f"{result.duration:.1f}s"
    )


# ── Summary renderer (one line per finding, sorted by severity) ───────────────

_SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}


def render_summary(result: ReviewResult) -> str:
    """
    One line per finding sorted by severity (errors first).
    Returns a string. Useful for compact human-readable summaries.
    """
    findings = sorted(
        _all_findings(result),
        key=lambda f: (_SEVERITY_ORDER.get(f.severity, 9), f.file, f.line or 0),
    )
    lines: list[str] = []
    for f in findings:
        loc  = f"{f.file}:{f.line}" if f.line else f.file
        icon = SEVERITY_ICON.get(f.severity, "?")
        lines.append(f"{icon} {f.severity.upper():7s}  {loc:40s}  [{f.agent}]  {f.message}")

    if not lines:
        lines.append(f"✓ No issues — {result.files_reviewed} file(s) reviewed")

    return "\n".join(lines)


# ── String-returning wrappers (v1 API compatibility) ──────────────────────────

def render_full(result: ReviewResult) -> str:
    """Return the full output as a string (same as print_full but captured)."""
    buf = io.StringIO()
    with redirect_stdout(buf):
        print_full(result)
    return buf.getvalue()


def render_compact(result: ReviewResult) -> str:
    """Return the compact output as a string (same as print_compact but captured)."""
    buf = io.StringIO()
    with redirect_stdout(buf):
        print_compact(result)
    return buf.getvalue()
