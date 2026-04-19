"""
data/okta-mcp-server/tools/get_principal_access.py

MCP tools: get_principal_access, list_principal_entitlements
Returns resources accessible by a given principal from Okta Identity Governance.
Requires Okta Identity Governance license.
"""

from __future__ import annotations

import httpx

from auth import get_gov_base_url, get_headers
from pagination import paginate
from trimmer import trim_records


async def get_principal_access(
    principal_id: str,
    limit: int = 50,
) -> list[dict]:
    """
    Return all resources accessible by a given principal (user or service account).
    Useful for access audits and identifying over-provisioning.

    Args:
        principal_id:  Okta user ID.
        limit:         Maximum number of results to return (default 50, max 200).

    Returns:
        List of trimmed principal access records.
    """
    async with httpx.AsyncClient() as client:
        records = await paginate(
            client=client,
            url=f"{get_gov_base_url()}/principal-access",
            headers=get_headers(),
            params={"principalId": principal_id},
            limit=min(limit, 200),
        )

    return trim_records("get_principal_access", records)


async def list_principal_entitlements(
    principal_id: str,
    limit: int = 50,
) -> list[dict]:
    """
    List all entitlements currently held by a principal.

    Args:
        principal_id:  Okta user ID.
        limit:         Maximum number of results to return (default 50, max 200).

    Returns:
        List of trimmed principal entitlement records.
    """
    async with httpx.AsyncClient() as client:
        records = await paginate(
            client=client,
            url=f"{get_gov_base_url()}/principal-entitlements",
            headers=get_headers(),
            params={"principalId": principal_id},
            limit=min(limit, 200),
        )

    return trim_records("list_principal_entitlements", records)
