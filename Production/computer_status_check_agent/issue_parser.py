"""
parsers/issue_parser.py
-----------------------
Parse the structured description of a Linear Computer Status Check issue
into a typed dict.  All date fields are returned as aware datetime objects
(UTC) so threshold comparisons are simple arithmetic.

Example description line:
    4. LAST INVENTORY UPDATE:: 2026-02-14 09:02 am EST
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional

from dateutil import parser as dateutil_parser
from pydantic import BaseModel, Field


# ── Data model ────────────────────────────────────────────────────────────────

class IssueData(BaseModel):
    """Typed representation of a parsed Computer Status Check issue."""

    computer_name: str = ""
    jamf_url: str = ""           # extracted from the Markdown link
    serial_number: str = ""
    os_version: str = ""

    last_inventory_update: Optional[datetime] = None
    last_checkin: Optional[datetime] = None
    jamf_protect_last_checkin: Optional[datetime] = None
    most_recent_completed_command: Optional[datetime] = None
    mdm_profile_expiration: Optional[datetime] = None

    # Issue creation date — used as the baseline for threshold comparisons
    # so that failure modes reflect *why the issue was created*, not how
    # stale the data looks at the time the agent runs.
    issue_created_at: Optional[datetime] = None

    super_status: str = ""       # e.g. "Pending", "Active", "Idle"
    uptime_days: int = 0
    failed_commands: int = 0
    num_computers: int = 1
    pending_policy_ids: list[int] = Field(default_factory=list)

    # ── Derived thresholds (read-only helpers) ────────────────────────────────
    #
    # All staleness checks compare against issue_created_at (not today).
    # This answers "was this metric stale when the issue was filed?" rather
    # than "is it stale now?"  — preventing tickets that simply sat in the
    # queue from being misrouted to Branch 2 when they were really Branch 3.

    @property
    def inventory_stale(self) -> bool:
        return self._days_before_baseline(self.last_inventory_update) > 14

    @property
    def checkin_stale(self) -> bool:
        return self._days_before_baseline(self.last_checkin) > 7

    @property
    def uptime_exceeded(self) -> bool:
        return self.uptime_days >= 30

    @property
    def uptime_only(self) -> bool:
        """True when high uptime is the ONLY failure mode (no stale check-in/inventory)."""
        return self.uptime_exceeded and not self.inventory_stale and not self.checkin_stale

    @property
    def has_pending_policies(self) -> bool:
        return len(self.pending_policy_ids) > 0

    @property
    def failure_modes(self) -> list[str]:
        modes = []
        if self.inventory_stale:
            modes.append("INVENTORY")
        if self.checkin_stale:
            modes.append("CHECKIN")
        if self.uptime_exceeded:
            modes.append("UPTIME")
        return modes

    def _days_before_baseline(self, dt: Optional[datetime]) -> float:
        """How many days before the baseline (issue_created_at) was *dt*?

        Falls back to datetime.now(UTC) if issue_created_at is not set,
        preserving backwards compatibility for unit tests and ad-hoc use.
        """
        if dt is None:
            return 0.0
        baseline = self.issue_created_at or datetime.now(tz=timezone.utc)
        return (baseline - dt).total_seconds() / 86_400


# ── Parser ────────────────────────────────────────────────────────────────────

# Matches:  4. LAST INVENTORY UPDATE:: 2026-02-14 09:02 am EST
_LINE_RE = re.compile(
    r"^\s*\d+\.\s+([A-Z][A-Z0-9 ]+?)::\s*(.+)$",
    re.MULTILINE,
)

# Extracts hostname and URL from Markdown link: [acme-username](<https://...>)
_LINK_RE = re.compile(r"\[([^\]]+)\]\(<([^>]+)>\)")


def _parse_date(value: str) -> Optional[datetime]:
    """Best-effort parse of a date string into a UTC-aware datetime."""
    value = value.strip()
    if not value or value.lower() in ("n/a", "none", "null", ""):
        return None
    try:
        dt = dateutil_parser.parse(value, fuzzy=True)
        if dt.tzinfo is None:
            # Treat naive datetimes as UTC (Jamf reports in UTC)
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt
    except (ValueError, OverflowError):
        return None


def _parse_policy_ids(value: str) -> list[int]:
    """Parse '67; 282; 432' → [67, 282, 432]."""
    ids = []
    for token in re.split(r"[;,\s]+", value):
        token = token.strip()
        if token.isdigit():
            ids.append(int(token))
    return ids


def _parse_uptime(value: str) -> int:
    """Parse '12 days' or '12' → 12."""
    m = re.search(r"(\d+)", value)
    return int(m.group(1)) if m else 0


def parse_issue_description(description: str) -> IssueData:
    """
    Parse the structured description of a Computer Status Check Linear issue.

    Returns an IssueData object with all fields populated from the description.
    Fields not found in the description retain their default (empty/None) values.
    """
    fields: dict[str, str] = {}

    for match in _LINE_RE.finditer(description):
        key = match.group(1).strip().upper()
        val = match.group(2).strip()
        fields[key] = val

    data = IssueData()

    # Computer name — may be a Markdown link
    raw_name = fields.get("COMPUTER NAME", "")
    link_match = _LINK_RE.search(raw_name)
    if link_match:
        data.computer_name = link_match.group(1)
        data.jamf_url = link_match.group(2)
    else:
        data.computer_name = raw_name.strip("[]()<> ")

    data.serial_number = fields.get("SERIAL NUMBER", "")
    data.os_version = fields.get("OS VERSION", "")

    data.last_inventory_update = _parse_date(fields.get("LAST INVENTORY UPDATE", ""))
    data.last_checkin = _parse_date(fields.get("LAST CHECKIN", ""))
    data.jamf_protect_last_checkin = _parse_date(
        fields.get("JAMF PROTECT LAST CHECK-IN", "")
    )
    data.most_recent_completed_command = _parse_date(
        fields.get("MOST RECENT COMPLETED COMMAND", "")
    )
    data.mdm_profile_expiration = _parse_date(
        fields.get("MDM PROFILE EXPIRATION DATE", "")
    )

    data.super_status = fields.get("SUPER STATUS", "")
    data.uptime_days = _parse_uptime(fields.get("UPTIME", "0"))
    data.failed_commands = int(
        re.search(r"\d+", fields.get("FAILED COMMANDS", "0")).group()  # type: ignore[union-attr]
    )
    data.num_computers = int(
        re.search(r"\d+", fields.get("NUMBER OF COMPUTERS FOR JAMF USER", "1")).group()  # type: ignore[union-attr]
    )
    data.pending_policy_ids = _parse_policy_ids(
        fields.get("PENDING POLICIES", "")
    )

    return data
