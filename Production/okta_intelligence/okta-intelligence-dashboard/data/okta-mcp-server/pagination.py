"""
data/okta-mcp-server/pagination.py

Okta cursor-based pagination using the Link header.
Respects the caller-supplied result limit and stops fetching when reached.
"""

from __future__ import annotations

import re
from typing import Any

import httpx


def _next_url(link_header: str | None) -> str | None:
    """Extract the 'next' URL from an Okta Link header, or None."""
    if not link_header:
        return None
    match = re.search(r'<([^>]+)>;\s*rel="next"', link_header)
    return match.group(1) if match else None


async def paginate(
    client: httpx.AsyncClient,
    url: str,
    headers: dict[str, str],
    params: dict[str, Any],
    limit: int,
) -> list[dict[str, Any]]:
    """
    Fetch pages from an Okta list endpoint until `limit` records are
    collected or no more pages exist.

    `limit` is passed as the `limit` query parameter on the first request
    (Okta caps individual page size at 200 for most endpoints). If the
    caller wants more than 200, we follow the Link cursor until we have
    enough records.

    Guards against infinite loops caused by a non-advancing cursor —
    if the next URL is the same as the current URL, or the page is empty,
    pagination stops.
    """
    # Okta page size cap per request
    page_size = min(limit, 200)
    params = {**params, "limit": page_size}

    results: list[dict[str, Any]] = []
    next_url: str | None = url
    prev_url: str | None = None

    while next_url and len(results) < limit:
        # Guard: stop if the cursor hasn't advanced
        if next_url == prev_url:
            break

        resp = await client.get(next_url, headers=headers, params=params if next_url == url else None)
        resp.raise_for_status()
        page: list[dict[str, Any]] = resp.json()

        # Guard: stop if the page is empty
        if not page:
            break

        results.extend(page)
        prev_url = next_url
        next_url = _next_url(resp.headers.get("Link"))

        # Only apply params on the first request; Link URLs are pre-parameterised
        params = None  # type: ignore[assignment]

    return results[:limit]