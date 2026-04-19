"""
data/okta-mcp-server/tools/get_policy.py

MCP tool: get_policy
Returns Okta policies. Trimmed to name, status, type, conditions, rules.
"""

from __future__ import annotations

import httpx

from auth import get_base_url, get_headers
from trimmer import trim_records


async def get_policy(
    policy_type: str = "PASSWORD",
    status: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """
    Get Okta policies by type.

    Args:
        policy_type: Policy type: PASSWORD | OKTA_SIGN_ON | MFA_ENROLL |
                     OAUTH_AUTHORIZATION_POLICY | ACCESS_POLICY | PROFILE_ENROLLMENT.
                     Defaults to PASSWORD.
        status:      Filter by status: ACTIVE | INACTIVE.
        limit:       Maximum number of policies to return (default 50).

    Returns:
        List of trimmed policy records (name, status, type, conditions, rules).
    """
    params: dict = {"type": policy_type.upper()}
    if status:
        params["status"] = status.upper()

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{get_base_url()}/policies",
            params=params,
        )
        resp.raise_for_status()
        records: list[dict] = resp.json()

    # Enrich with rules for each policy (separate API call per policy)
    async with httpx.AsyncClient() as client:
        for record in records[:limit]:
            policy_id = record.get("id")
            if policy_id:
                rules_resp = await client.get(
                    f"{get_base_url()}/policies/{policy_id}/rules",
                    headers=get_headers(),
                )
                if rules_resp.is_success:
                    record["rules"] = rules_resp.json()

    return trim_records("get_policy", records[:limit])
