"""
data/okta-mcp-server/tools/list_sessions.py

MCP tool: get_user_sessions
Returns active sessions for a specific Okta user.
"""

from __future__ import annotations

import httpx

from auth import get_base_url, get_headers
from trimmer import trim_records


async def get_user_sessions(user_id: str) -> list[dict]:
    """
    Return all active sessions for a specific Okta user.

    Args:
        user_id:  Okta user ID (e.g. 00u1ab2cd3EFGhijKL4x5).

    Returns:
        List of trimmed session records.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{get_base_url()}/users/{user_id}/sessions",
            headers=get_headers(),
            timeout=30,
        )
        resp.raise_for_status()
        records = resp.json()

    if not isinstance(records, list):
        records = [records]

    return trim_records("get_user_sessions", records)
