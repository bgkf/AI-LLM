"""
data/okta-mcp-server/tools/get_user_factors.py

MCP tool: get_user_factors
Returns enrolled MFA factors for a specific Okta user.
"""

from __future__ import annotations

import httpx

from auth import get_base_url, get_headers
from trimmer import trim_records


async def get_user_factors(user_id: str) -> list[dict]:
    """
    Return all enrolled MFA factors for a specific Okta user.

    Args:
        user_id:  Okta user ID (e.g. 00u1ab2cd3EFGhijKL4x5).

    Returns:
        List of trimmed factor records including type, provider, and status.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{get_base_url()}/users/{user_id}/factors",
            headers=get_headers(),
            timeout=30,
        )
        resp.raise_for_status()
        records = resp.json()

    if not isinstance(records, list):
        records = [records]

    return trim_records("get_user_factors", records)
