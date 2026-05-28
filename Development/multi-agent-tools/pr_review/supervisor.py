"""
pr_review/supervisor.py
========================
Supervisor for the PR review agent system.

Responsibilities:
  1. Parse the git diff into per-file chunks
  2. Phase 1 — Fan out to all specialist agents concurrently (file × agent)
  3. Phase 2 — Deliberation: compute corroboration, conflicts, confidence
  4. Aggregate and return enriched findings

Architecture: two-phase supervisor-worker.

  Phase 1: parallel specialist pass
    Each (file, agent) pair is an independent unit of work.
    Findings are written to a SharedFindingStore as agents complete.
    A failure in one agent does not affect the others.

  Phase 2: deliberation
    The supervisor reads the SharedFindingStore and computes:
      - corroborated findings: multiple agents flagged the same line
      - conflicted findings:   agents disagree on severity for the same line
      - confidence scores:     single agent = 0.5, full agreement = 0.95
    This phase runs synchronously after Phase 1 completes.
    It is implemented as a pure function (deliberate()) so it can be
    extracted to a dedicated consensus-agent later without changing
    the supervisor's interface.

Entry points:
  review_diff(diff_text)     — review a diff string directly
  review_staged()            — review `git diff --staged`
  review_commit(sha)         — review a specific commit
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
from typing import Callable, Optional

from shared.llm import Provider
from shared.findings import Finding, AgentResult
from pr_review.agents import logic, security, style, tests, docs

# SharedFindingStore and deliberation are optional — the module works without
# them, falling back to the original single-phase behaviour.
try:
    from shared.finding_store import SharedFindingStore, EnrichedFinding
    from pr_review.deliberation import deliberate, DeliberationConfig, DeliberationSummary
    _HAS_DELIBERATION = True
except ImportError:
    SharedFindingStore = None       # type: ignore[assignment,misc]
    EnrichedFinding    = None       # type: ignore[assignment,misc]
    DeliberationConfig = None       # type: ignore[assignment,misc]
    DeliberationSummary = None      # type: ignore[assignment,misc]
    _HAS_DELIBERATION  = False

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
    This handles both "git diff" and "git show" output formats correctly,
    and correctly includes the "diff --git" header line in each file's chunk.
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
            # "+++ /dev/null" means deletion — skip
            if line.startswith("+++ /dev/null"):
                break

        if filename and not should_skip(filename):
            files[filename] = "".join(block)

    return files


# ── ReviewResult ──────────────────────────────────────────────────────────────

@dataclass
class ReviewResult:
    """
    Complete output of one review run.

    When the deliberation layer is available, enriched_findings carries
    corroboration and conflict metadata. The plain findings list is always
    populated for backwards compatibility with renderers and callers that
    access result.findings directly.
    """
    files_reviewed:  int
    files_skipped:   int
    agent_results:   list[AgentResult]       = field(default_factory=list)
    findings:        list[Finding]           = field(default_factory=list)

    # Deliberation fields — populated when _HAS_DELIBERATION is True
    enriched_findings: list                  = field(default_factory=list)  # list[EnrichedFinding]
    deliberation:    object                  = None   # Optional[DeliberationSummary]
    store:           object                  = None   # Optional[SharedFindingStore]

    failed_agents:   list[str]               = field(default_factory=list)
    duration:        float                   = 0.0
    total_tokens:    int                     = 0

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

    @property
    def corroborated_count(self) -> int:
        return sum(1 for f in self.enriched_findings if f.is_corroborated)

    @property
    def conflict_count(self) -> int:
        return sum(1 for f in self.enriched_findings if f.has_conflict)


# ── Supervisor ────────────────────────────────────────────────────────────────

AGENTS: list[tuple[str, Callable]] = [
    ("logic",    logic.run),
    ("security", security.run),
    ("style",    style.run),
    ("tests",    tests.run),
    ("docs",     docs.run),
]


def review_diff(
    diff_text:           str,
    provider:            Provider = Provider.ANTHROPIC,
    agents:              Optional[list[str]] = None,
    max_workers:         int = 10,
    deliberation_config: object = None,  # Optional[DeliberationConfig]
) -> ReviewResult:
    """
    Core supervisor function.

    When the deliberation layer is available, runs two phases:

      Phase 1: Concurrent specialist analysis
        - Parse diff into per-file chunks
        - Fan out all (file × agent) pairs to a ThreadPool
        - Write findings to SharedFindingStore as agents complete

      Phase 2: Deliberation
        - Group findings by (file, line)
        - Compute corroboration and conflict metadata
        - Enrich findings with confidence scores

    Without the deliberation layer, only Phase 1 runs and findings are
    aggregated directly — matching the original single-phase behaviour.

    Parameters
    ----------
    diff_text            : unified diff string
    provider             : LLM provider for all agents
    agents               : agent names to run; None = all
    max_workers          : max concurrent threads
    deliberation_config  : Phase 2 settings; uses defaults if None
    """
    start = time.time()

    # Count total files in diff before filtering, for accurate skipped count
    total_in_diff = diff_text.count("\ndiff --git ") + (
        1 if diff_text.startswith("diff --git ") else 0
    )
    file_diffs    = parse_diff(diff_text)
    files_skipped = max(0, total_in_diff - len(file_diffs))

    if not file_diffs:
        log.info("No reviewable files found in diff")
        return ReviewResult(files_reviewed=0, files_skipped=files_skipped)

    active_agents = [
        (name, fn) for name, fn in AGENTS
        if agents is None or name in agents
    ]

    log.info(
        "Phase 1: reviewing %d file(s) with %d agent(s) [%s]",
        len(file_diffs), len(active_agents),
        ", ".join(n for n, _ in active_agents),
    )

    # ── Phase 1: Parallel specialist pass ─────────────────────────────────────

    store = SharedFindingStore() if _HAS_DELIBERATION else None
    all_results: list[AgentResult] = []

    work_items = [
        (filename, diff, agent_name, agent_fn)
        for filename, diff in file_diffs.items()
        for agent_name, agent_fn in active_agents
    ]

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
                log.error("Unexpected exception from %s on %s: %s",
                          agent_name, filename, exc)
                result = AgentResult(
                    agent=agent_name, ok=False,
                    error=f"unexpected: {exc}",
                )
            all_results.append(result)

            # Stamp agent name and write to shared store (deliberation path)
            for f in result.findings:
                f.agent = agent_name
                if store is not None:
                    store.append(f)

            status = "✓" if result.ok else "✗"
            log.debug(
                "  %s [%s] %s — %d finding(s)",
                status, result.agent, filename, len(result.findings),
            )

    # ── Phase 2: Deliberation (when available) ────────────────────────────────

    enriched: list = []
    delib_summary = None

    if _HAS_DELIBERATION and store is not None:
        log.info(
            "Phase 1 complete: %d findings across %d agents",
            store.size(), len(active_agents),
        )
        log.info("Phase 2: deliberation over %d findings", store.size())

        agent_runners = {name: fn for name, fn in active_agents}
        enriched = deliberate(
            store=store,
            config=deliberation_config,
            agent_runners=agent_runners,
        )

        delib_summary = DeliberationSummary.from_enriched(enriched, store)
        log.info(
            "Phase 2 complete: %d corroborated, %d conflicted, %d high-confidence",
            delib_summary.corroborated_count,
            delib_summary.conflicted_count,
            delib_summary.high_confidence,
        )

    # ── Aggregate ─────────────────────────────────────────────────────────────

    failed: list[str] = []
    total_tokens = 0

    for result in all_results:
        total_tokens += result.tokens
        if not result.ok:
            failed.append(f"{result.agent}: {result.error}")

    # Build the plain Finding list.
    # When enriched findings are available, derive the plain list from them
    # so both lists stay in sync. Otherwise, aggregate directly from agents.
    if enriched:
        # Sort enriched: errors first, corroborated errors bubble up, then file/line
        enriched.sort(key=lambda f: (
            {"error": 0, "warning": 1, "info": 2}.get(f.severity, 3),
            0 if f.is_corroborated else 1,
            f.file,
            f.line or 0,
        ))

        all_findings = [
            Finding(
                message    = ef.message,
                file       = ef.file,
                severity   = ef.severity,
                line       = ef.line,
                suggestion = ef.suggestion,
                agent      = ef.agent,
                context    = ef.context,
            )
            for ef in enriched
        ]
    else:
        # Single-phase path: aggregate findings directly from agent results
        all_findings = []
        for result in all_results:
            all_findings.extend(result.findings)

        # Sort: errors first, then by file, then by line
        all_findings.sort(key=lambda f: (
            {"error": 0, "warning": 1, "info": 2}.get(f.severity, 3),
            f.file,
            f.line or 0,
        ))

    return ReviewResult(
        files_reviewed    = len(file_diffs),
        files_skipped     = files_skipped,
        agent_results     = all_results,
        findings          = all_findings,
        enriched_findings = enriched,
        deliberation      = delib_summary,
        store             = store,
        failed_agents     = failed,
        duration          = time.time() - start,
        total_tokens      = total_tokens,
    )


def review_staged(
    provider: Provider = Provider.ANTHROPIC,
    agents:   Optional[list[str]] = None,
    cwd:      Optional[str] = None,
) -> ReviewResult:
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
            "No staged changes found. Run `git add` first, "
            "or use --diff to pass a diff file."
        )

    return review_diff(diff, provider=provider, agents=agents)


def review_commit(
    commit:  str = "HEAD",
    provider: Provider = Provider.ANTHROPIC,
    agents:  Optional[list[str]] = None,
    cwd:     Optional[str] = None,
) -> ReviewResult:
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
