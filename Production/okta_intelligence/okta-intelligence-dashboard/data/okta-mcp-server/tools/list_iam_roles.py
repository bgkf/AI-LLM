"""
data/okta-mcp-server/tools/list_iam_roles.py

MCP tool: list_iam_roles
Lists IAM roles and resource sets defined in the Okta org.
"""

from __future__ import annotations

import httpx

from auth import get_base_url, get_headers
from pagination import paginate
from trimmer import trim_records


async def list_iam_roles(limit: int = 50) -> list[dict]:
    """
    List IAM roles defined in the Okta org.
    Returns role name, type, description, and status.
    Requires a token with Read-only Admin role or higher.

    Args:
        limit:  Maximum number of results to return (default 50, max 200).

    Returns:
        List of trimmed IAM role records.
    """
    async with httpx.AsyncClient() as client:
        records = await paginate(
            client=client,
            url=f"{get_base_url()}/iam/roles",
            headers=get_headers(),
            params={},
            limit=min(limit, 200),
        )

    return trim_records("list_iam_roles", records)


async def list_iam_resource_sets(limit: int = 50) -> list[dict]:
    """
    List IAM resource sets (scoped admin targets) in the Okta org.

    Args:
        limit:  Maximum number of results to return (default 50, max 200).

    Returns:
        List of trimmed resource set records.
    """
    async with httpx.AsyncClient() as client:
        records = await paginate(
            client=client,
            url=f"{get_base_url()}/iam/resource-sets",
            headers=get_headers(),
            params={},
            limit=min(limit, 200),
        )

    return trim_records("list_iam_resource_sets", records)
