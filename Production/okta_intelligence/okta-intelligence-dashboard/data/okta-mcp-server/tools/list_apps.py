from __future__ import annotations
import httpx
from auth import get_base_url, get_headers
from pagination import paginate
from trimmer import trim_records


async def list_apps(
    status: str | None = "ACTIVE",
    limit: int = 50,
) -> list[dict]:
    """
    List Okta applications, trimmed to label, status, signOnMode, and
    assignedUserCount. The skinny_users endpoint is used when resolving
    per-app user assignments to stay within the low rate limit (50/100/min).
    """
    params: dict = {}
    if status:
        params["filter"] = f'status eq "{status}"'

    async with httpx.AsyncClient() as client:
        records = await paginate(
            client=client,
            url=f"{get_base_url()}/apps",
            headers=get_headers(),
            params=params,
            limit=min(limit, 200),
        )
    return trim_records("list_apps", records)


async def get_app_users(
    app_id: str,
    limit: int = 50,
) -> list[dict]:
    """
    Return users assigned to a specific application using the skinny_users
    endpoint (id + profile only). Avoids rate-limit exhaustion on large
    app assignments (skinny_users: 50/100/min vs users: same, but smaller payload).
    """
    async with httpx.AsyncClient() as client:
        records = await paginate(
            client=client,
            url=f"{get_base_url()}/apps/{app_id}/skinny_users",
            headers=get_headers(),
            params={},
            limit=min(limit, 500),
        )
    return trim_records("get_app_users_skinny", records)
