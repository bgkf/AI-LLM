"""
tools/user_tools.py
--------------------
OOO / availability checks using:
  1. GAM (GAMADV-XTD3) — Gmail vacation responder + Google Calendar OOO events
  2. Slack API          — custom status (emoji + expiration)

Both checks are combined into a single check_user_ooo() LangChain tool that
returns a structured dict the agent can reason over.

GAM commands used
-----------------
Vacation responder (Gmail):
    gam user <email> show vacation format

Out-of-Office calendar events (today → +14 days):
    gam user <email> print events \
        after today before +14d \
        eventtype outofoffice \
        fields summary,start,end,status \
        formatjson

Both commands require GAM to be configured with domain-wide delegation for the
service account, with the Calendar and Gmail API scopes authorised.

Slack API used
--------------
  users.lookupByEmail  → resolve email → Slack user ID
  users.profile.get    → status_text, status_emoji, status_expiration
  users.getPresence    → active | away  (supplemental)

Required Slack bot token scopes:
    users:read, users:read.email, users.profile:read
"""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
from datetime import datetime, timezone
from typing import Optional

import httpx
from dateutil import parser as dateutil_parser
from langchain_core.tools import tool
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
GAM_PATH = os.environ.get("GAM_PATH", "gam")
GOOGLE_DOMAIN = os.environ.get("GOOGLE_DOMAIN", "acme.com")
SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN", "")

# Slack status emojis that reliably indicate OOO
_OOO_EMOJIS = {
    ":palm_tree:",
    ":beach_with_umbrella:",
    ":airplane:",
    ":airplane_departure:",
    ":airplane_arriving:",
    ":sun_with_face:",
    ":desert_island:",
    ":sleeping:",
    ":zzz:",
    ":no_entry:",
    ":no_entry_sign:",
    ":calendar:",
    ":date:",
    ":house:",
    ":house_with_garden:",
    ":family:",
    ":baby:",
    ":medical_symbol:",
    ":face_with_thermometer:",
    ":construction:",
    ":clock1:",
}

# Keywords in Slack status text that indicate OOO
_OOO_KEYWORDS = [
    "ooo",
    "out of office",
    "on vacation",
    "on leave",
    "pto",
    "parental leave",
    "maternity",
    "paternity",
    "away",
    "traveling",
    "travelling",
    "holiday",
    "sick",
    "medical",
    "family leave",
    "off today",
    "offline",
    "brb",
]

# Patterns that signal OOO via a return date, e.g.:
#   "returning March 10"  "back Monday"  "back 3/14"  "returning 2026-03-10"
# The regex captures the optional date portion after the keyword so it can be
# extracted and surfaced in the Linear comment.
_RETURNING_RE = re.compile(
    r"\b(returning|back)\b"               # anchor keyword
    r"(?:\s+(?:on\s+)?(?:the\s+)?"        # optional filler: "on", "on the"
    r"(?P<date>"
    r"\d{4}-\d{2}-\d{2}"                  # ISO:    2026-03-14
    r"|\d{1,2}/\d{1,2}(?:/\d{2,4})?"     # US:     3/14  or  3/14/26
    r"|(?:mon|tue|wed|thu|fri|sat|sun)\w*"  # weekday: Monday, Tue, …
    r"|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*"  # month name
    r"(?:\s+\d{1,2}(?:st|nd|rd|th)?(?:\s+\d{4})?)?"            # + day + year
    r"|\d{1,2}(?:st|nd|rd|th)?"           # ordinal day:  14th
    r"))?",
    re.IGNORECASE,
)


# ── Output models ─────────────────────────────────────────────────────────────

class OOOResult(BaseModel):
    username: str
    email: str
    is_ooo: bool
    ooo_source: list[str]          # which signals flagged OOO
    vacation_responder_on: bool
    vacation_responder_subject: Optional[str] = None
    vacation_responder_end_date: Optional[str] = None
    calendar_ooo_events: list[dict] = []
    slack_status_text: Optional[str] = None
    slack_status_emoji: Optional[str] = None
    slack_status_expires: Optional[str] = None
    slack_returning_date: Optional[str] = None   # parsed from "back/returning <date>"
    slack_presence: Optional[str] = None
    notes: list[str] = []


# ── GAM helpers ───────────────────────────────────────────────────────────────

def _run_gam(*args: str, timeout: int = 30) -> tuple[int, str, str]:
    """Run a GAM command and return (returncode, stdout, stderr)."""
    cmd = [GAM_PATH, *args]
    logger.debug("GAM command: %s", " ".join(cmd))
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode, result.stdout, result.stderr
    except FileNotFoundError:
        msg = f"GAM binary not found at '{GAM_PATH}'. Set GAM_PATH in .env"
        logger.error(msg)
        return -1, "", msg
    except subprocess.TimeoutExpired:
        logger.error("GAM command timed out: %s", " ".join(cmd))
        return -1, "", "timeout"


def _gam_vacation(email: str) -> dict:
    """
    Check Gmail vacation / out-of-office responder status via GAM.

    Uses ``gam user <email> show vacation format`` — the ``format`` flag
    strips HTML from the response body and returns plain-text output.
    (Note: ``formatjson`` is NOT a valid option for ``show vacation``.)

    Returns a dict with keys: enabled, subject, startDate, endDate, message
    """
    rc, stdout, stderr = _run_gam("user", email, "show", "vacation", "format")
    if rc != 0:
        logger.warning("GAM vacation check failed for %s: %s", email, stderr)
        return {"enabled": False, "error": stderr}

    # ``gam show vacation format`` returns plain text like:
    #   User: username@acme.com, Vacation:
    #     Enabled: True
    #     Subject: Out of office
    #     Start Date: 2026-03-10
    #     End Date: 2026-03-20
    #     Message:
    #       I'm out of the office ...
    result: dict = {"enabled": False}
    for line in stdout.splitlines():
        line = line.strip()
        if line.startswith("Enabled:"):
            result["enabled"] = line.split(":", 1)[1].strip().lower() == "true"
        elif line.startswith("Subject:"):
            result["subject"] = line.split(":", 1)[1].strip()
        elif line.startswith("Start Date:"):
            result["startDate"] = line.split(":", 1)[1].strip()
        elif line.startswith("End Date:"):
            result["endDate"] = line.split(":", 1)[1].strip()
        elif line.startswith("Message:"):
            result["message"] = line.split(":", 1)[1].strip()
    return result


def _gam_calendar_ooo(email: str) -> list[dict]:
    """
    Fetch Out-of-Office calendar events for the user (today → +14 days) via GAM.

    Uses GAMADV-XTD3's eventtype outofoffice filter — this targets the native
    Google Calendar OOO event type, not just events with "OOO" in the title.
    """
    rc, stdout, stderr = _run_gam(
        "user", email,
        "print", "events",
        "after", "today",
        "before", "+14d",
        "eventtype", "outofoffice",
        "fields", "summary,start,end,status",
        "formatjson",
    )

    if rc != 0:
        logger.warning("GAM calendar OOO check failed for %s: %s", email, stderr)
        return []

    try:
        data = json.loads(stdout)
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and "events" in data:
            return data["events"]
        return []
    except json.JSONDecodeError:
        logger.debug("GAM calendar output not JSON for %s", email)
        return []


# ── Slack helpers ─────────────────────────────────────────────────────────────

def _slack_lookup_by_email(email: str) -> Optional[str]:
    """Resolve an email address to a Slack user ID."""
    if not SLACK_BOT_TOKEN:
        return None
    try:
        resp = httpx.get(
            "https://slack.com/api/users.lookupByEmail",
            params={"email": email},
            headers={"Authorization": f"Bearer {SLACK_BOT_TOKEN}"},
            timeout=10,
        )
        data = resp.json()
        if data.get("ok"):
            return data["user"]["id"]
    except Exception as e:
        logger.warning("Slack lookupByEmail failed for %s: %s", email, e)
    return None


def _slack_get_profile(user_id: str) -> dict:
    """Fetch Slack profile (includes custom status fields)."""
    if not SLACK_BOT_TOKEN:
        return {}
    try:
        resp = httpx.get(
            "https://slack.com/api/users.profile.get",
            params={"user": user_id},
            headers={"Authorization": f"Bearer {SLACK_BOT_TOKEN}"},
            timeout=10,
        )
        data = resp.json()
        if data.get("ok"):
            return data.get("profile", {})
    except Exception as e:
        logger.warning("Slack profile.get failed for %s: %s", user_id, e)
    return {}


def _slack_get_presence(user_id: str) -> Optional[str]:
    """Return 'active' or 'away' for the Slack user."""
    if not SLACK_BOT_TOKEN:
        return None
    try:
        resp = httpx.get(
            "https://slack.com/api/users.getPresence",
            params={"user": user_id},
            headers={"Authorization": f"Bearer {SLACK_BOT_TOKEN}"},
            timeout=10,
        )
        data = resp.json()
        if data.get("ok"):
            return data.get("presence")
    except Exception as e:
        logger.warning("Slack getPresence failed for %s: %s", user_id, e)
    return None


def _extract_returning_date(status_text: str) -> Optional[str]:
    """
    If the status text contains a 'returning'/'back' pattern followed by a
    recognisable date, parse and return it as an ISO date string (YYYY-MM-DD).
    Returns None if no date can be extracted.

    Examples that match:
        "returning March 10"      → "2026-03-10"
        "back Monday"             → nearest upcoming Monday as ISO date
        "back 3/14"               → "2026-03-14"
        "returning 2026-03-10"    → "2026-03-10"
        "OOO, back on the 14th"   → "2026-03-14"  (best-effort)
    """
    m = _RETURNING_RE.search(status_text)
    if not m:
        return None
    raw_date = (m.group("date") or "").strip()
    if not raw_date:
        return None   # keyword found but no parseable date token
    try:
        dt = dateutil_parser.parse(raw_date, fuzzy=True, default=datetime.now())
        return dt.strftime("%Y-%m-%d")
    except (ValueError, OverflowError):
        return None


def _is_slack_ooo(status_text: str, status_emoji: str) -> tuple[bool, Optional[str]]:
    """
    Heuristic: determine if a Slack status indicates OOO.

    Returns:
        (is_ooo: bool, returning_date: str | None)
        returning_date is an ISO date string when a return date can be parsed
        from a 'returning …' or 'back …' pattern in the status text.
    """
    text_lower = status_text.lower()

    # Check plain OOO keywords first
    if any(kw in text_lower for kw in _OOO_KEYWORDS):
        returning_date = _extract_returning_date(status_text)
        return True, returning_date

    # Check 'returning / back [date]' pattern — these alone signal OOO
    m = _RETURNING_RE.search(status_text)
    if m:
        returning_date = _extract_returning_date(status_text)
        return True, returning_date

    # Check OOO emoji
    if status_emoji in _OOO_EMOJIS:
        returning_date = _extract_returning_date(status_text)
        return True, returning_date

    return False, None


def _slack_status_expired(expiration_ts: int) -> bool:
    """Return True if the Slack status expiration has already passed."""
    if expiration_ts == 0:
        return False  # 0 = no expiration set → still active
    return datetime.now(tz=timezone.utc).timestamp() > expiration_ts


# ── Main tool ─────────────────────────────────────────────────────────────────

@tool
def check_user_ooo(email: str) -> dict:
    """
    Check whether a Acme user is currently Out of Office.

    Checks three independent signals and combines them:
      1. Gmail vacation responder (via GAM: `gam user <email> show vacation`)
      2. Google Calendar OOO events today → +14 days
         (via GAM: `gam user <email> print events eventtype outofoffice`)
      3. Slack custom status text + emoji  (via Slack API users.profile.get)

    IMPORTANT: Get the user's email from Jamf first by calling
    get_user_email(serial_number) — do NOT derive the email from the
    computer name, as Acme emails do not follow a predictable pattern.

    Args:
        email: The user's email address from Jamf (e.g. "username@acme.com").
               Must be obtained via get_user_email() before calling this tool.

    Returns:
        A dict with:
          is_ooo (bool): True if any signal indicates OOO.
          ooo_source (list[str]): Which signals flagged OOO.
          vacation_responder_on (bool)
          vacation_responder_end_date (str | None)
          calendar_ooo_events (list[dict]): OOO calendar events found.
          slack_status_text (str | None)
          slack_status_emoji (str | None)
          slack_status_expires (str | None)
          notes (list[str]): Human-readable summary lines.
    """
    # Extract username portion from email for display
    clean = email.split("@")[0] if "@" in email else email

    result = OOOResult(username=clean, email=email, is_ooo=False, ooo_source=[])
    ooo_signals: list[str] = []

    # ── 1. Gmail vacation responder ───────────────────────────────────────────
    vacation = _gam_vacation(email)
    result.vacation_responder_on = bool(vacation.get("enabled", False))
    if result.vacation_responder_on:
        result.vacation_responder_subject = vacation.get("subject")
        result.vacation_responder_end_date = vacation.get("endDate")
        ooo_signals.append("GMAIL_VACATION_RESPONDER")
        result.notes.append(
            f"✉️  Gmail vacation responder is ON"
            + (f" (ends {result.vacation_responder_end_date})" if result.vacation_responder_end_date else "")
        )

    # ── 2. Google Calendar OOO events ─────────────────────────────────────────
    cal_events = _gam_calendar_ooo(email)
    result.calendar_ooo_events = cal_events
    if cal_events:
        ooo_signals.append("GOOGLE_CALENDAR_OOO")
        event_summaries = [e.get("summary", "OOO") for e in cal_events[:3]]
        result.notes.append(
            f"📅  Google Calendar OOO event(s) found: {', '.join(event_summaries)}"
        )

    # ── 3. Slack status ───────────────────────────────────────────────────────
    slack_user_id = _slack_lookup_by_email(email)
    if slack_user_id:
        profile = _slack_get_profile(slack_user_id)
        status_text = profile.get("status_text", "")
        status_emoji = profile.get("status_emoji", "")
        status_expiration = int(profile.get("status_expiration", 0))

        result.slack_status_text = status_text
        result.slack_status_emoji = status_emoji

        if status_expiration:
            exp_dt = datetime.fromtimestamp(status_expiration, tz=timezone.utc)
            result.slack_status_expires = exp_dt.isoformat()

        # Only flag OOO if status hasn't expired
        if status_text or status_emoji:
            if not _slack_status_expired(status_expiration):
                is_ooo, returning_date = _is_slack_ooo(status_text, status_emoji)
                if is_ooo:
                    result.slack_returning_date = returning_date
                    ooo_signals.append("SLACK_STATUS")
                    returning_note = (
                        f" · returning {returning_date}" if returning_date else ""
                    )
                    result.notes.append(
                        f"💬  Slack status: {status_emoji} {status_text!r}"
                        + returning_note
                        + (f" (status expires {result.slack_status_expires})" if result.slack_status_expires else " (no expiry set)")
                    )

        result.slack_presence = _slack_get_presence(slack_user_id)
    else:
        result.notes.append(
            f"⚠️  Could not resolve {email} to a Slack user ID "
            "(check SLACK_BOT_TOKEN scope: users:read.email)"
        )

    # ── Combine signals ───────────────────────────────────────────────────────
    result.is_ooo = len(ooo_signals) > 0
    result.ooo_source = ooo_signals

    if not result.is_ooo:
        result.notes.append("✅  No OOO signals detected across Gmail, Calendar, and Slack.")

    return result.model_dump()


# ══════════════════════════════════════════════════════════════════════════════
# Okta activity check
# ══════════════════════════════════════════════════════════════════════════════
#
# Uses the Okta System Log API to find the user's most recent sign-in event.
# The key signal is whether a FastPass sign-in from a macOS device appears
# in the log — this is identified by:
#
#     target[].detailEntry.type == "macOS UDDevice"
#
# This indicates the user authenticated via Okta FastPass on a Mac, which is
# strong evidence they were recently active on a Mac (though we cannot confirm
# it is THIS specific computer as Okta does not expose the device UUID).
#
# Okta activity is only used as an OOO signal when no other OOO indicator
# (Gmail, Calendar, Slack) is present. If the user signed in recently and
# FastPass was used on a Mac, they are probably not OOO.
#
# Required env vars:
#   OKTA_DOMAIN      — e.g. acme.okta.com
#   OKTA_API_TOKEN   — SSWS token with okta.logs.read scope

import os as _os
from datetime import datetime as _datetime, timedelta as _timedelta, timezone as _timezone
from typing import Optional as _Optional

import httpx as _httpx
from langchain_core.tools import tool as _tool

_OKTA_DOMAIN = _os.environ.get("OKTA_DOMAIN", "")
_OKTA_API_TOKEN = _os.environ.get("OKTA_API_TOKEN", "")

_logger_okta = logging.getLogger(__name__ + ".okta")


def _okta_get_system_log(email: str, since_days: int = 14) -> list[dict]:
    """
    Fetch recent authentication events from the Okta System Log for a user.

    Queries for user.authentication.* events in the last `since_days` days.
    Returns a list of raw log event dicts (up to 50 most recent).
    """
    if not _OKTA_DOMAIN or not _OKTA_API_TOKEN:
        _logger_okta.warning("OKTA_DOMAIN or OKTA_API_TOKEN not configured — skipping Okta check")
        return []

    since = (_datetime.now(tz=_timezone.utc) - _timedelta(days=since_days)).isoformat()

    try:
        resp = _httpx.get(
            f"https://{_OKTA_DOMAIN}/api/v1/logs",
            params={
                "filter": f'actor.alternateId eq "{email}" and eventType sw "user.authentication"',
                "since": since,
                "limit": 50,
                "sortOrder": "DESCENDING",
            },
            headers={
                "Authorization": f"SSWS {_OKTA_API_TOKEN}",
                "Accept": "application/json",
            },
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        _logger_okta.error("Okta system log query failed for %s: %s", email, e)
        return []


def _find_fastpass_macos_signin(events: list[dict]) -> tuple[bool, _Optional[str]]:
    """
    Scan Okta log events for a FastPass sign-in from a macOS device.

    A FastPass macOS sign-in is identified by the presence of a target entry
    where detailEntry.type == "macOS UDDevice". This is the most specific
    signal that the user was active on a Mac recently.

    Returns:
        (found: bool, signin_datetime_iso: str | None)
    """
    for event in events:
        targets = event.get("target", [])
        for target in targets:
            detail_entry = target.get("detailEntry", {})
            if isinstance(detail_entry, dict):
                if detail_entry.get("type") == "macOS UDDevice":
                    signin_time = event.get("published")  # ISO 8601 string
                    return True, signin_time

    return False, None


@_tool
def check_okta_activity(email: str) -> dict:
    """
    Query the Okta System Log for the user's recent sign-in activity.

    Used as a SECONDARY OOO signal — only relevant when no other OOO
    indicator (Gmail vacation responder, Google Calendar OOO events, or
    Slack status) is present.

    If the user signed in recently, they are probably not OOO even if they
    haven't set a status anywhere.

    The most specific signal is a FastPass sign-in from a macOS device,
    identifiable by target[].detailEntry.type == "macOS UDDevice" in the
    Okta System Log. This means the user authenticated via Okta FastPass
    on a Mac. We cannot confirm it is THIS specific computer (Okta does not
    expose the device UUID), but it is a strong recency signal.

    Args:
        email: The user's Acme email address (e.g. username@acme.com).

    Returns:
        A dict with:
          last_signin (str | None): ISO datetime of most recent sign-in.
          last_signin_days_ago (int | None): How many days ago that was.
          fastpass_macos_signin (bool): True if a FastPass macOS sign-in
            was found in the last 14 days.
          fastpass_signin_date (str | None): ISO datetime of the FastPass
            macOS sign-in, if found.
          notes (list[str]): Human-readable summary lines.
          error (str | None): Set if the Okta API call failed.
    """
    if not _OKTA_DOMAIN or not _OKTA_API_TOKEN:
        return {
            "last_signin": None,
            "last_signin_days_ago": None,
            "fastpass_macos_signin": False,
            "fastpass_signin_date": None,
            "notes": ["⚠️  OKTA_DOMAIN or OKTA_API_TOKEN not configured — Okta check skipped."],
            "error": "OKTA_DOMAIN or OKTA_API_TOKEN not set",
        }

    events = _okta_get_system_log(email, since_days=14)
    notes: list[str] = []

    if not events:
        notes.append("⚠️  No Okta authentication events found in the last 14 days.")
        return {
            "last_signin": None,
            "last_signin_days_ago": None,
            "fastpass_macos_signin": False,
            "fastpass_signin_date": None,
            "notes": notes,
            "error": None,
        }

    # Most recent sign-in is first (DESCENDING sort)
    last_event = events[0]
    last_signin_iso = last_event.get("published")
    last_signin_days_ago: _Optional[int] = None

    if last_signin_iso:
        try:
            last_dt = _datetime.fromisoformat(last_signin_iso.replace("Z", "+00:00"))
            delta = _datetime.now(tz=_timezone.utc) - last_dt
            last_signin_days_ago = delta.days
            notes.append(
                f"🔑  Last Okta sign-in: {last_signin_iso} "
                f"({last_signin_days_ago} day{'s' if last_signin_days_ago != 1 else ''} ago)"
            )
        except ValueError:
            notes.append(f"🔑  Last Okta sign-in: {last_signin_iso} (could not parse date)")

    # Check for FastPass macOS device sign-in
    fastpass_found, fastpass_date = _find_fastpass_macos_signin(events)

    if fastpass_found:
        notes.append(
            f"🍎  FastPass macOS sign-in detected (Target.DetailEntry.Type = 'macOS UDDevice') "
            f"at {fastpass_date}. User was recently active on a Mac."
        )
    else:
        notes.append(
            "ℹ️  No FastPass macOS device sign-in found in the last 14 days "
            "(could be web/mobile sign-ins only, or no activity)."
        )

    return {
        "last_signin": last_signin_iso,
        "last_signin_days_ago": last_signin_days_ago,
        "fastpass_macos_signin": fastpass_found,
        "fastpass_signin_date": fastpass_date,
        "notes": notes,
        "error": None,
    }
