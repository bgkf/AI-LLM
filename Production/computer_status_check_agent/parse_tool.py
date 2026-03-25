"""
tools/parse_tool.py
-------------------
Thin LangChain @tool wrapper around parsers/issue_parser.py.
Keeps the parser module free of LangChain imports so it can be
unit-tested without the full stack.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from dateutil import parser as dateutil_parser
from langchain_core.tools import tool

from computer_status_agent.parsers.issue_parser import parse_issue_description


def _to_utc(value: Optional[str]) -> Optional[datetime]:
    """Parse an ISO date string into a UTC-aware datetime."""
    if not value:
        return None
    try:
        dt = dateutil_parser.parse(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt
    except (ValueError, OverflowError):
        return None


@tool
def parse_issue_description_tool(description: str, issue_created_at: str = "") -> dict:
    """
    Parse the raw description of a Computer Status Check Linear issue into
    structured fields.

    IMPORTANT: Always pass `issue_created_at` (the ISO date string from
    get_linear_issue's `created_at` field). Threshold comparisons (inventory
    stale, check-in stale) are evaluated relative to the issue creation date
    — not today — so the agent correctly identifies *why the issue was
    created* even if the ticket has been sitting in the queue.

    Returns a dict with all key metrics:
      computer_name, serial_number, os_version,
      last_inventory_update (ISO datetime string),
      last_checkin (ISO datetime string),
      uptime_days (int),
      super_status (str),
      failed_commands (int),
      pending_policy_ids (list[int]),
      failure_modes (list[str]),   ← ["INVENTORY", "CHECKIN", "UPTIME"]
      inventory_stale (bool),
      checkin_stale (bool),
      uptime_exceeded (bool),
      uptime_only (bool),          ← True when UPTIME is the ONLY failure
      num_computers (int),
      mdm_profile_expiration (ISO datetime string | null),
      issue_created_at (ISO datetime string)

    Args:
        description: The raw Markdown description text from the Linear issue.
        issue_created_at: ISO date string from the Linear issue's created_at
            field. Used as the baseline for staleness thresholds.
    """
    data = parse_issue_description(description)

    # Inject the issue creation date for threshold comparisons
    data.issue_created_at = _to_utc(issue_created_at)

    result = data.model_dump()

    # Convert datetime objects to ISO strings for JSON serialisation
    for field in (
        "last_inventory_update",
        "last_checkin",
        "jamf_protect_last_checkin",
        "most_recent_completed_command",
        "mdm_profile_expiration",
        "issue_created_at",
    ):
        val = result.get(field)
        if hasattr(val, "isoformat"):
            result[field] = val.isoformat()

    # Add derived properties (not part of model_dump by default)
    result["failure_modes"] = data.failure_modes
    result["inventory_stale"] = data.inventory_stale
    result["checkin_stale"] = data.checkin_stale
    result["uptime_exceeded"] = data.uptime_exceeded
    result["uptime_only"] = data.uptime_only

    return result
