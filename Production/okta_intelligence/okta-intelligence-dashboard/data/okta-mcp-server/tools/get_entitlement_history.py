"""
data/okta-mcp-server/tools/get_entitlement_history.py

MCP tool: get_entitlement_history
Returns historical log of entitlement changes from Okta Identity Governance.
Requires Okta Identity Governance license.
"""

from __future__ import annotations

import httpx

from auth import get_gov_base_url, get_headers
from pagination import paginate
from trimmer import trim_records


async def get_entitlement_history(
    principal_id: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """
    Return the historical log of entitlement changes (grants and revocations).
    Answers "when did this user get or lose access to X."
    Useful for compliance audit trails and offboarding verification.

    Args:
        principal_id:  Okta user ID to filter history by (optional).
        limit:         Maximum number of results to return (default 50, max 200).

    Returns:
        List of trimmed entitlement history records.
    """
    params: dict = {}
    if principal_id:
        params["filter"] = f'principal.id eq "{principal_id}"'

    async with httpx.AsyncClient() as client:
        records = await paginate(
            client=client,
            url=f"{get_gov_base_url()}/principal-entitlements/history",
            headers=get_headers(),
            params=params,
            limit=min(limit, 200),
        )

    return trim_records("get_entitlement_history", records)
