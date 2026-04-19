"""
data/okta-mcp-server/tools/get_access_reviews.py

MCP tools: list_access_reviews, get_access_review_detail
Lists security access reviews from Okta Identity Governance v2.
Requires Okta Identity Governance license.
"""

from __future__ import annotations

import httpx

from auth import get_gov_v2_base_url, get_headers
from pagination import paginate
from trimmer import trim_records


async def list_access_reviews(limit: int = 25) -> list[dict]:
    """
    List security access reviews from Okta Identity Governance v2.
    Returns review ID, status, campaign name, reviewer, and dates.

    Note: this endpoint has a very low rate limit (25/50 req/min).
    Default limit is intentionally conservative.

    Args:
        limit:  Maximum number of results to return (default 25, max 100).

    Returns:
        List of trimmed access review records.
    """
    async with httpx.AsyncClient() as client:
        records = await paginate(
            client=client,
            url=f"{get_gov_v2_base_url()}/security-access-reviews",
            headers=get_headers(),
            params={},
            limit=min(limit, 100),
        )

    return trim_records("list_access_reviews", records)


async def get_access_review_detail(review_id: str) -> list[dict]:
    """
    Return all access targets and their review status for a single review.

    Args:
        review_id:  Security access review ID.

    Returns:
        List of trimmed access review detail records.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{get_gov_v2_base_url()}/security-access-reviews/{review_id}/accesses",
            headers=get_headers(),
            timeout=30,
        )
        resp.raise_for_status()
        records = resp.json()

    if not isinstance(records, list):
        records = [records]

    return trim_records("get_access_review_detail", records)
