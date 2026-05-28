"""
shared/finding_store.py
=======================
Thread-safe append-only shared state store for agent findings.

This is the shared state layer introduced in the review-pr upgrade.
During Phase 1 (parallel specialist pass), agents write findings here
as they complete. Phase 2 (deliberation) reads the accumulated findings
to compute corroboration, conflicts, and confidence scores.

Design:
  - Append-only: findings are never mutated once written
  - Thread-safe: multiple agent threads write concurrently
  - Queryable: read by file, by line, by agent, or all
  - Reducer-based: the deliberation phase applies per-field merge rules

This implements the append-only log + field reducer patterns from the
multi-agent shared state KB — applied to a real production use case.
"""

from __future__ import annotations

import threading
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional


# ── Extended Finding ──────────────────────────────────────────────────────────
#
# The base Finding contract (message, file, severity, line, suggestion, agent,
# context) is unchanged — all agents continue to return plain Findings.
#
# The deliberation phase ENRICHES findings with three additional fields:
#   confidence      — 0.0–1.0: how certain we are (more agents agree = higher)
#   corroborated_by — other agents that flagged the same line
#   conflicts_with  — agents that flagged the same line with a different severity
#
# These are set AFTER phase 1 by DeliberationPhase, never by agents themselves.
# Agents don't know about confidence — that's the supervisor's concern.

@dataclass
class EnrichedFinding:
    """
    A Finding enriched with deliberation metadata.
    Wraps the original Finding dict so the base contract stays unchanged.
    """
    # Original Finding fields (copied, not mutated)
    message:    str
    file:       str
    severity:   str
    line:       Optional[int]
    suggestion: Optional[str]
    agent:      str
    context:    Optional[str]

    # Deliberation fields (set by DeliberationPhase, never by agents)
    confidence:      float       = 0.5   # 0.5 = single agent default; rises with corroboration
    corroborated_by: list[str]   = field(default_factory=list)
    conflicts_with:  list[str]   = field(default_factory=list)

    @classmethod
    def from_finding(cls, f) -> "EnrichedFinding":
        """Promote a plain Finding to an EnrichedFinding with defaults."""
        return cls(
            message    = f.message,
            file       = f.file,
            severity   = f.severity,
            line       = f.line,
            suggestion = f.suggestion,
            agent      = f.agent,
            context    = f.context,
        )

    def to_dict(self) -> dict:
        return {
            "agent":          self.agent,
            "severity":       self.severity,
            "file":           self.file,
            "line":           self.line,
            "message":        self.message,
            "suggestion":     self.suggestion,
            "context":        self.context,
            "confidence":     round(self.confidence, 2),
            "corroborated_by": self.corroborated_by,
            "conflicts_with": self.conflicts_with,
        }

    # Render helpers used by the CLI renderer
    @property
    def confidence_label(self) -> str:
        if len(self.corroborated_by) >= 2:
            return f"[{len(self.corroborated_by) + 1} agents agree]"
        if len(self.corroborated_by) == 1:
            return f"[confirmed by {self.corroborated_by[0]}]"
        return ""

    @property
    def conflict_label(self) -> str:
        if self.conflicts_with:
            return f"[conflicts with {', '.join(self.conflicts_with)}]"
        return ""

    @property
    def has_conflict(self) -> bool:
        return bool(self.conflicts_with)

    @property
    def is_corroborated(self) -> bool:
        return bool(self.corroborated_by)


# ── SharedFindingStore ────────────────────────────────────────────────────────

class SharedFindingStore:
    """
    Thread-safe append-only log of findings from all agents.

    Phase 1 (parallel agents) appends to this store as findings arrive.
    Phase 2 (deliberation) reads the accumulated findings to compute
    corroboration, conflicts, and confidence scores.

    The store is the shared state between phases. It replaces the simple
    list concatenation in the original supervisor with a queryable,
    ordered log that preserves the full history of what each agent found.

    Write pattern:  append-only (no mutations, no deletes)
    Read pattern:   snapshot queries (by file, by line, by agent)
    Concurrency:    single RLock guards all writes and index updates
    """

    def __init__(self) -> None:
        self._lock    = threading.RLock()
        self._log:    list[tuple[int, object]] = []    # (entry_id, Finding)
        self._next_id = 0

        # Indices for fast lookup — maintained incrementally on append
        self._by_file:  dict[str, list[object]]              = defaultdict(list)
        self._by_agent: dict[str, list[object]]              = defaultdict(list)
        self._by_line:  dict[tuple[str, int], list[object]]  = defaultdict(list)

    # ── Write ─────────────────────────────────────────────────────────────────

    def append(self, finding) -> None:
        """
        Append a finding to the log. Thread-safe.
        Updates all indices atomically with the append.
        """
        with self._lock:
            entry_id = self._next_id
            self._next_id += 1
            self._log.append((entry_id, finding))

            # Update indices
            self._by_file[finding.file].append(finding)
            self._by_agent[finding.agent].append(finding)
            if finding.line is not None:
                self._by_line[(finding.file, finding.line)].append(finding)

    def append_many(self, findings: list) -> None:
        """Batch append — acquires the lock once for the whole batch."""
        with self._lock:
            for f in findings:
                self.append(f)

    # ── Read ──────────────────────────────────────────────────────────────────

    def all(self) -> list:
        """Return all findings in insertion order."""
        with self._lock:
            return [f for _, f in self._log]

    def by_file(self, filename: str) -> list:
        """All findings for a specific file."""
        with self._lock:
            return list(self._by_file.get(filename, []))

    def by_agent(self, agent_name: str) -> list:
        """All findings from a specific agent."""
        with self._lock:
            return list(self._by_agent.get(agent_name, []))

    def by_line(self, filename: str, line: int) -> list:
        """All findings at a specific (file, line) location."""
        with self._lock:
            return list(self._by_line.get((filename, line), []))

    def files(self) -> list[str]:
        """All files that have at least one finding."""
        with self._lock:
            return list(self._by_file.keys())

    def agents(self) -> list[str]:
        """All agents that produced at least one finding."""
        with self._lock:
            return list(self._by_agent.keys())

    def hot_lines(self) -> list[tuple[str, int, int]]:
        """
        Return (file, line, count) for lines flagged by more than one agent,
        sorted by count descending. These are the candidates for deliberation.
        """
        with self._lock:
            candidates = [
                (file, line, len(findings))
                for (file, line), findings in self._by_line.items()
                if len(findings) > 1
            ]
        candidates.sort(key=lambda x: -x[2])
        return candidates

    def size(self) -> int:
        with self._lock:
            return len(self._log)

    def __repr__(self) -> str:
        return (f"SharedFindingStore("
                f"{self.size()} findings, "
                f"{len(self.files())} files, "
                f"{len(self.agents())} agents)")
