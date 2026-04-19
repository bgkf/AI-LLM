"""
data/okta-mcp-server/tools/list_users.py

MCP tool: list_users
Lists Okta users with optional filter/search/status.
Response is trimmed to base fields + any queried field.
"""

from __future__ import annotations

import httpx

from auth import get_base_url, get_headers
from pagination import paginate
from trimmer import trim_records


async def list_users(
    filter: str | None = None,
    search: str | None = None,
    status: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """
    List Okta users.

    Args:
        filter:    Okta filter expression, e.g. 'profile.countryCode eq "CA"'.
        search:    Okta search expression, e.g. 'profile.department eq "Engineering"'.
        status:    User status filter: ACTIVE | INACTIVE | DEPROVISIONED |
                   SUSPENDED | RECOVERY | LOCKED_OUT | PASSWORD_EXPIRED.
        limit:     Maximum number of results to return (default 50, max 500).

    Returns:
        List of trimmed user records.
    """
    params: dict = {}
    if filter:
        params["filter"] = filter
    if search:
        params["search"] = search
    if status:
        # Build a filter expression if status is passed standalone
        existing = params.get("filter", "")
        status_expr = f'status eq "{status}"'
        params["filter"] = f"{existing} and {status_expr}".strip(" and ") if existing else status_expr

    async with httpx.AsyncClient() as client:
        records = await paginate(
            client=client,
            url=f"{get_base_url()}/users",
            headers=get_headers(),
            params=params,
            limit=min(limit, 500),
        )

    return trim_records("list_users", records, filter_str=filter, search_str=search)
