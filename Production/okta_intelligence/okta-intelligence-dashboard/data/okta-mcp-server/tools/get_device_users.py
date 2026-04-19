"""
data/okta-mcp-server/tools/get_device_users.py

MCP tool: get_device_users
Returns users associated with a specific Okta device ID.
"""

from __future__ import annotations

import httpx

from auth import get_base_url, get_headers
from trimmer import trim_records


async def get_device_users(device_id: str) -> list[dict]:
    """
    Return all users currently associated with a specific device ID.

    Args:
        device_id:  Okta device ID (e.g. from list_devices results).

    Returns:
        List of trimmed user records for that device.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{get_base_url()}/devices/{device_id}/users",
            headers=get_headers(),
            timeout=30,
        )
        resp.raise_for_status()
        records = resp.json()

    if not isinstance(records, list):
        records = [records]

    return trim_records("get_device_users", records)
