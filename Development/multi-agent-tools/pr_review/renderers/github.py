"""
pr_review/renderers/github.py
==============================
Renders a ReviewResult as a GitHub PR review comment.

Status: STUB — not yet implemented.
The CLI renderer works fully. This file exists to show the
architectural seam: swapping renderers requires no changes
to the supervisor or agents.

To implement:
  1. Set GITHUB_TOKEN in your .env
  2. Call post_review(result, owner, repo, pr_number)
  3. The supervisor will post findings as inline review comments
     (one comment per finding with a line reference) plus a
     summary comment on the PR itself.

GitHub API calls needed:
  POST /repos/{owner}/{repo}/pulls/{pr}/reviews
    — creates a review with inline comments

  Each inline comment:
    path     : finding.file
    line     : finding.line (or omit for file-level comments)
    body     : formatted finding text
    side     : "RIGHT" (commenting on the new version)

Useful reference:
  https://docs.github.com/en/rest/pulls/reviews
"""

from __future__ import annotations
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from pr_review.supervisor import ReviewResult


def format_comment_body(result: ReviewResult) -> str:
    """
    Format the top-level PR summary comment (in Markdown).
    This is what gets posted as the review body.
    """
    lines = ["## 🤖 Automated PR Review\n"]

    if not result.findings:
        lines.append("✅ **No issues found.** Looking good!")
        return "\n".join(lines)

    # Summary table
    lines.append("| Severity | Count |")
    lines.append("|----------|-------|")
    if result.error_count:
        lines.append(f"| 🔴 Error | {result.error_count} |")
    if result.warning_count:
        lines.append(f"| 🟡 Warning | {result.warning_count} |")
    if result.info_count:
        lines.append(f"| 🔵 Info | {result.info_count} |")
    lines.append("")

    # Agent breakdown
    agent_counts: dict[str, int] = {}
    for f in result.findings:
        agent_counts[f.agent] = agent_counts.get(f.agent, 0) + 1

    icons = {"logic":"🧠","security":"🔒","style":"✏️","tests":"🧪","docs":"📝"}
    for agent, count in sorted(agent_counts.items()):
        icon = icons.get(agent, "·")
        lines.append(f"- {icon} **{agent}**: {count} finding(s)")

    if result.failed_agents:
        lines.append(f"\n⚠️ {len(result.failed_agents)} agent(s) failed to run.")

    verdict = (
        "\n🚫 **Review required** — errors must be resolved before merging."
        if result.has_blockers
        else "\n✅ **Approved** — only warnings and suggestions."
    )
    lines.append(verdict)
    return "\n".join(lines)


def post_review(
    result:    ReviewResult,
    owner:     str,
    repo:      str,
    pr_number: int,
    commit_sha: str,
) -> None:
    """
    Post the review to GitHub.
    NOT YET IMPLEMENTED — raises NotImplementedError.
    """
    raise NotImplementedError(
        "GitHub renderer is not yet implemented. "
        "Use the CLI renderer for now: from pr_review.renderers.cli import print_full"
    )
