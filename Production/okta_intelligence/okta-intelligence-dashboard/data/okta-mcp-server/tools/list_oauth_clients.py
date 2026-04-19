"""
data/okta-mcp-server/tools/list_oauth_clients.py

MCP tool: list_oauth_clients
Lists OAuth 2.0 / OIDC client applications registered in the Okta org.
"""

from __future__ import annotations

import httpx

from auth import get_base_url, get_headers
from pagination import paginate
from trimmer import trim_records


async def list_oauth_clients(limit: int = 50) -> list[dict]:
    """
    List OAuth 2.0 / OIDC client applications registered in the Okta org.

    Note: this endpoint has a low rate limit (50/100 req/min).
    Use conservative limits and avoid frequent re-querying.

    Args:
        limit:  Maximum number of results to return (default 50, max 200).

    Returns:
        List of trimmed OAuth client records.
    """
    async with httpx.AsyncClient() as client:
        records = await paginate(
            client=client,
            url=f"{get_base_url()}/oauth2/v1/clients",
            headers=get_headers(),
            params={},
            limit=min(limit, 200),
        )

    return trim_records("list_oauth_clients", records)
