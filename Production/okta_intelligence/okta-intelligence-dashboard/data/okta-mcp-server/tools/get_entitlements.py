"""
data/okta-mcp-server/tools/get_entitlements.py

MCP tools: list_entitlements, list_grants
Lists entitlements and active grants from Okta Identity Governance.
Requires Okta Identity Governance license.
"""

from __future__ import annotations

import httpx

from auth import get_gov_base_url, get_headers
from pagination import paginate
from trimmer import trim_records


async def list_entitlements(limit: int = 50) -> list[dict]:
    """
    List all entitlements defined in Okta Identity Governance.
    Returns entitlement name, type, resource, and status.

    Args:
        limit:  Maximum number of results to return (default 50, max 200).

    Returns:
        List of trimmed entitlement records.
    """
    async with httpx.AsyncClient() as client:
        records = await paginate(
            client=client,
            url=f"{get_gov_base_url()}/entitlements",
            headers=get_headers(),
            params={},
            limit=min(limit, 200),
        )

    return trim_records("list_entitlements", records)


async def list_grants(
    principal_id: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """
    List active entitlement grants, optionally filtered by principal (user) ID.

    Args:
        principal_id:  Okta user ID to filter grants by (optional).
        limit:         Maximum number of results to return (default 50, max 200).

    Returns:
        List of trimmed grant records.
    """
    params: dict = {}
    if principal_id:
        params["filter"] = f'principal.id eq "{principal_id}"'

    async with httpx.AsyncClient() as client:
        records = await paginate(
            client=client,
            url=f"{get_gov_base_url()}/grants",
            headers=get_headers(),
            params=params,
            limit=min(limit, 200),
        )

    return trim_records("list_grants", records)
