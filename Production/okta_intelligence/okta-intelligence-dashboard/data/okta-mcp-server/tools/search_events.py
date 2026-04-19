"""
data/okta-mcp-server/tools/search_events.py

MCP tool: search_events
Searches Okta system log events by event type or keyword. Never trimmed.
"""

from __future__ import annotations

import httpx

from auth import get_base_url, get_headers
from pagination import paginate


async def search_events(
    event_type: str | None = None,
    q: str | None = None,
    since: str | None = None,
    until: str | None = None,
    outcome: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """
    Search Okta system log events.

    Args:
        event_type: Okta event type, e.g. "user.authentication.sso".
        q:          Free-text keyword search.
        since:      ISO 8601 start time.
        until:      ISO 8601 end time.
        outcome:    Outcome result filter: SUCCESS | FAILURE | SKIPPED | ALLOW | DENY | UNKNOWN.
        limit:      Maximum number of events (default 50, max 500).

    Returns:
        List of full (untrimmed) log event objects.
    """
    filter_parts: list[str] = []
    if event_type:
        filter_parts.append(f'eventType eq "{event_type}"')
    if outcome:
        filter_parts.append(f'outcome.result eq "{outcome.upper()}"')

    params: dict = {}
    if filter_parts:
        params["filter"] = " and ".join(filter_parts)
    if q:
        params["q"] = q
    if since:
        params["since"] = since
    if until:
        params["until"] = until

    async with httpx.AsyncClient() as client:
        return await paginate(
            client=client,
            url=f"{get_base_url()}/logs",
            headers=get_headers(),
            params=params,
            limit=min(limit, 500),
        )
