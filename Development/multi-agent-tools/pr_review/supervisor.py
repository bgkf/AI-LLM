"""
pr_review/supervisor.py
========================
Supervisor for the PR review agent system.

Responsibilities:
  1. Parse the git diff into per-file chunks
  2. Fan out to all specialist agents concurrently (per file × per agent)
  3. Collect AgentResult objects and aggregate findings
  4. Pass aggregated findings to the selected renderer

Architecture: supervisor-worker with concurrent fan-out.
Each (file, agent) pair is an independent unit of work.
A failure in one does not affect the others.

Entry points:
  review_diff(diff_text)     — review a diff string directly
  review_staged()            — review `git diff --staged`
  review_pr(owner, repo, pr) — review a GitHub PR (requires GITHUB_TOKEN)
"""

from __future__ import annotations
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import re
import subprocess
import concurrent.futures
import logging
import time
from dataclasses import dataclass, field
from typing import Callable

from shared.llm import Provider
from shared.findings import Finding, AgentResult
from pr_review.agents import logic, security, style, tests, docs

log = logging.getLogger(__name__)


# ── File diff parsing ─────────────────────────────────────────────────────────

# Extensions to skip — binary files, generated files, lock files
SKIP_EXTENSIONS = {
    "png", "jpg", "jpeg", "gif", "svg", "ico", "pdf",
    "lock", "resolved",                        # package locks
    "pbxproj", "xcworkspacedata", "xcscheme",  # Xcode generated
    "min.js", "min.css",                       # minified
    "pyc", "pyo", "so", "dylib",               # compiled
}

SKIP_PATTERNS = [
    re.compile(r"package-lock\.json$"),
    re.compile(r"Podfile\.lock$"),
    re.compile(r"\.generated\."),
]


def should_skip(filename: str) -> bool:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext in SKIP_EXTENSIONS:
        return True
    return any(p.search(filename) for p in SKIP_PATTERNS)


def parse_diff(diff_text: str) -> dict[str, str]:
    """
    Split a unified diff into per-file diffs.
    Returns {filename: diff_text} for files that should be reviewed.

    Accumulates all lines between consecutive "diff --git" headers,
    then extracts the filename from the "+++ b/" line within each block.
    This handles both "git diff" and "git show" output formats correctly.
    """
    # Split into per-file blocks on "diff --git" boundaries
    blocks: list[list[str]] = []
    current: list[str] = []

    for line in diff_text.splitlines(keepends=True):
        if line.startswith("diff --git ") and current:
            blocks.append(current)
            current = []
        current.append(line)

    if current:
        blocks.append(current)

    # Extract filename from each block and filter skipped files
    files: dict[str, str] = {}
    for block in blocks:
        filename = None
        for line in block:
            if line.startswith("+++ b/"):
                filename = line[6:].strip()
                break
            # Handle renames and new files: "+++ /dev/null" means deletion — skip
            if line.startswith("+++ /dev/null"):
                break

        if filename and not should_skip(filename):
            files[filename] = "".join(block)

    return files


# ── Aggregated review result ──────────────────────────────────────────────────

@dataclass
class ReviewResult:
    files_reviewed:  int
    files_skipped:   int
    agent_results:   list[AgentResult]      = field(default_factory=list)
    findings:        list[Finding]          = field(default_factory=list)
    failed_agents:   list[str]              = field(default_factory=list)
    duration:        float                  = 0.0
    total_tokens:    int                    = 0

    @property
    def error_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "warning")

    @property
    def info_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "info")

    @property
    def has_blockers(self) -> bool:
        return self.error_count > 0


# ── Supervisor ────────────────────────────────────────────────────────────────

# All registered agents: (role_name, run_function)
AGENTS: list[tuple[str, Callable]] = [
    ("logic",    logic.run),
    ("security", security.run),
    ("style",    style.run),
    ("tests",    tests.run),
    ("docs",     docs.run),
]


def review_diff(
    diff_text:    str,
    provider:     Provider = Provider.ANTHROPIC,
    agents:       list[str] | None = None,   # None = run all
    max_workers:  int = 10,
) -> ReviewResult:
    """
    Core supervisor function. Takes a unified diff string and returns
    a ReviewResult with all findings from all agents.

    Parameters
    ----------
    diff_text   : unified diff (from git diff, GitHub API, etc.)
    provider    : LLM provider to use for all agents
    agents      : list of agent names to run; None = all agents
    max_workers : max concurrent threads (one per file×agent pair)
    """
    start = time.time()

    # Parse diff into per-file chunks
    total_in_diff = diff_text.count("\ndiff --git ") + (1 if diff_text.startswith("diff --git ") else 0)
    file_diffs    = parse_diff(diff_text)
    files_skipped = max(0, total_in_diff - len(file_diffs))

    if not file_diffs:
        log.info("No reviewable files found in diff")
        return ReviewResult(files_reviewed=0, files_skipped=files_skipped)

    # Select agents to run
    active_agents = [
        (name, fn) for name, fn in AGENTS
        if agents is None or name in agents
    ]

    log.info(
        "Reviewing %d file(s) with %d agent(s) [%s]",
        len(file_diffs), len(active_agents),
        ", ".join(n for n, _ in active_agents)
    )

    # Build work items: (filename, diff, agent_name, agent_fn)
    work_items = [
        (filename, diff, agent_name, agent_fn)
        for filename, diff in file_diffs.items()
        for agent_name, agent_fn in active_agents
    ]

    # Fan out — all work items run concurrently
    all_results: list[AgentResult] = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
        future_to_item = {
            pool.submit(agent_fn, filename, diff, provider): (filename, agent_name)
            for filename, diff, agent_name, agent_fn in work_items
        }

        for future in concurrent.futures.as_completed(future_to_item):
            filename, agent_name = future_to_item[future]
            try:
                result = future.result()
            except Exception as exc:
                # Safety net — agents should never raise, but just in case
                log.error("Unexpected exception from %s on %s: %s",
                          agent_name, filename, exc)
                result = AgentResult(
                    agent=agent_name, ok=False,
                    error=f"unexpected: {exc}"
                )
            all_results.append(result)
            status = "✓" if result.ok else "✗"
            log.debug(
                "  %s [%s] %s — %d finding(s)",
                status, result.agent, filename,
                len(result.findings)
            )

    # Aggregate
    all_findings: list[Finding] = []
    failed: list[str] = []
    total_tokens = 0

    for result in all_results:
        all_findings.extend(result.findings)
        total_tokens += result.tokens
        if not result.ok:
            failed.append(f"{result.agent}: {result.error}")

    # Sort findings: errors first, then by file, then by line
    all_findings.sort(key=lambda f: (
        {"error": 0, "warning": 1, "info": 2}.get(f.severity, 3),
        f.file,
        f.line or 0,
    ))

    return ReviewResult(
        files_reviewed = len(file_diffs),
        files_skipped  = files_skipped,
        agent_results  = all_results,
        findings       = all_findings,
        failed_agents  = failed,
        duration       = time.time() - start,
        total_tokens   = total_tokens,
    )


def review_staged(provider: Provider = Provider.ANTHROPIC,
                  agents: list[str] | None = None,
                  cwd: str | None = None) -> ReviewResult:
    """Review the currently staged git changes."""
    try:
        diff = subprocess.check_output(
            ["git", "diff", "--staged"],
            stderr=subprocess.STDOUT,
            text=True,
            cwd=cwd,
        )
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"git diff failed: {e.output}") from e

    if not diff.strip():
        raise RuntimeError(
            "No staged changes found. Run `git add` first, or use --diff to pass a diff file."
        )

    return review_diff(diff, provider=provider, agents=agents)


def review_commit(commit: str = "HEAD",
                  provider: Provider = Provider.ANTHROPIC,
                  agents: list[str] | None = None,
                  cwd: str | None = None) -> ReviewResult:
    """Review the changes in a specific commit."""
    try:
        has_parent = subprocess.call(
            ["git", "rev-parse", "--verify", f"{commit}^"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=cwd,
        ) == 0

        if has_parent:
            diff = subprocess.check_output(
                ["git", "diff", f"{commit}^", commit],
                stderr=subprocess.STDOUT,
                text=True,
                cwd=cwd,
            )
        else:
            # Root commit — no parent, use git show
            diff = subprocess.check_output(
                ["git", "show", "--format=", commit],
                stderr=subprocess.STDOUT,
                text=True,
                cwd=cwd,
            )

    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"git diff failed: {e.output}") from e

    if not diff.strip():
        raise RuntimeError(f"No changes found in commit {commit}.")

    return review_diff(diff, provider=provider, agents=agents)
