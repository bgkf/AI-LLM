"""
data/okta-mcp-server/tools/get_audit_logs.py

MCP tool: get_audit_logs
Returns Okta system log events. Never trimmed — full event returned.
"""

from __future__ import annotations

import httpx

from auth import get_base_url, get_headers
from pagination import paginate


async def get_audit_logs(
    since: str | None = None,
    until: str | None = None,
    filter: str | None = None,
    q: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """
    Retrieve Okta system log (audit log) events.

    Args:
        since:     ISO 8601 start time, e.g. "2026-01-01T00:00:00Z".
        until:     ISO 8601 end time.
        filter:    SCIM filter expression for log events.
        q:         Free-text keyword filter.
        limit:     Maximum number of events (default 50, max 500).

    Returns:
        List of full (untrimmed) log event objects.
    """
    params: dict = {}
    if since:
        params["since"] = since
    if until:
        params["until"] = until
    if filter:
        params["filter"] = filter
    if q:
        params["q"] = q

    async with httpx.AsyncClient() as client:
        return await paginate(
            client=client,
            url=f"{get_base_url()}/logs",
            headers=get_headers(),
            params=params,
            limit=min(limit, 500),
        )
