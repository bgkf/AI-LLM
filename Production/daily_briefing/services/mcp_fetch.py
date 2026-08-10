"""Fetch Slack saves and Notion updates via Claude Code MCP connectors."""

import json
import subprocess
from datetime import datetime, timedelta, timezone


CLAUDE_CLI = "claude"


def _claude_query(prompt):
    result = subprocess.run(
        [CLAUDE_CLI, "-p", "--output-format", "json", prompt],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        return None
    try:
        data = json.loads(result.stdout)
        return data.get("result", result.stdout)
    except json.JSONDecodeError:
        return result.stdout


def fetch_slack_saves():
    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
    prompt = (
        f'Search Slack for saved items using query "is:saved after:{cutoff}". '
        f"Set include_context to false and limit to 20. "
        f"Return ONLY a JSON array of objects with keys: channel, user, text. "
        f'text should be max 120 chars. If no results, return []. '
        f"Output raw JSON only, no markdown fences, no explanation."
    )
    raw = _claude_query(prompt)
    if raw is None:
        return []
    if isinstance(raw, list):
        return raw
    try:
        text = raw.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        return json.loads(text)
    except (json.JSONDecodeError, IndexError):
        return []


def fetch_notion_updates():
    prompt = (
        "Search Notion for recently updated pages. Set page_size to 10 and max_highlight_length to 0. "
        "Return ONLY a JSON array of objects with key: title. "
        "Include only pages edited in the last 24 hours. If no results, return []. "
        "Output raw JSON only, no markdown fences, no explanation."
    )
    raw = _claude_query(prompt)
    if raw is None:
        return []
    if isinstance(raw, list):
        return raw
    try:
        text = raw.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        return json.loads(text)
    except (json.JSONDecodeError, IndexError):
        return []
