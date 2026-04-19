from __future__ import annotations
import httpx
from auth import get_base_url, get_headers
from pagination import paginate
from trimmer import trim_records

SKINNY_THRESHOLD = 100


async def get_group(
    group_name: str | None = None,
    group_id: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """
    Return members of an Okta group, resolved by name or ID.

    For groups with many members the skinny_users endpoint is used
    automatically to stay within rate limits (returns id + profile only).
    Full profile data is only fetched for groups under SKINNY_THRESHOLD members.
    """
    async with httpx.AsyncClient() as client:
        if not group_id:
            if not group_name:
                raise ValueError("Provide group_name or group_id.")
            search_resp = await client.get(
                f"{get_base_url()}/groups",
                headers=get_headers(),
                params={"q": group_name, "limit": 5},
                timeout=30,
            )
            search_resp.raise_for_status()
            results = search_resp.json()
            if not results:
                return []
            group_id = results[0]["id"]

        count_resp = await client.get(
            f"{get_base_url()}/groups/{group_id}/stats",
            headers=get_headers(),
            timeout=30,
        )
        use_skinny = False
        if count_resp.status_code == 200:
            stats = count_resp.json()
            member_count = stats.get("usersCount", 0)
            use_skinny = member_count >= SKINNY_THRESHOLD
        else:
            use_skinny = True

        endpoint = (
            f"{get_base_url()}/groups/{group_id}/skinny_users"
            if use_skinny
            else f"{get_base_url()}/groups/{group_id}/users"
        )

        records = await paginate(
            client=client,
            url=endpoint,
            headers=get_headers(),
            params={},
            limit=min(limit, 500),
        )

    trim_key = "get_group_skinny" if use_skinny else "get_group"
    return trim_records(trim_key, records)
