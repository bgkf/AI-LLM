"""
data/okta-mcp-server/tools/list_devices.py

MCP tool: list_devices
Lists Okta-managed devices with optional status filter.
"""

from __future__ import annotations

import httpx

from auth import get_base_url, get_headers
from pagination import paginate
from trimmer import trim_records


async def list_devices(
    status: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """
    List managed devices registered in Okta.

    Args:
        status:  Device status filter: ACTIVE | INACTIVE.
        limit:   Maximum number of results to return (default 50, max 500).

    Returns:
        List of trimmed device records.
    """
    params: dict = {}
    if status:
        params["search"] = f'status eq "{status}"'

    async with httpx.AsyncClient() as client:
        records = await paginate(
            client=client,
            url=f"{get_base_url()}/devices",
            headers=get_headers(),
            params=params,
            limit=min(limit, 500),
        )

    return trim_records("list_devices", records)
