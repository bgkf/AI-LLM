"""
data/okta-mcp-server/server.py

FastMCP entry point for the Okta MCP server.
Launched by apfel via --mcp flag using the project venv interpreter.
The Okta API token is injected per-call from the session state held in
dashboard/server.py — passed by apfel as a tool argument.
"""

import os
import pathlib
import sys

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Resolve paths and load environment
# ---------------------------------------------------------------------------

SERVER_DIR = pathlib.Path(__file__).parent
REPO_ROOT  = SERVER_DIR.parent.parent

load_dotenv(REPO_ROOT / ".env")

# Add server dir to path so tool imports resolve
sys.path.insert(0, str(SERVER_DIR))

# ---------------------------------------------------------------------------
# FastMCP app
# ---------------------------------------------------------------------------

from fastmcp import FastMCP

from tools.list_users     import list_users
from tools.get_group      import get_group
from tools.get_audit_logs import get_audit_logs
from tools.search_events  import search_events
from tools.list_apps      import list_apps
from tools.get_policy     import get_policy

mcp = FastMCP(
    name="okta-intelligence",
    instructions=(
        "Okta admin tools for an IT team. "
    ),
)

# ---------------------------------------------------------------------------
# Register tools
# ---------------------------------------------------------------------------

@mcp.tool(
    description=(
        "List Okta users. Optionally filter by status (ACTIVE | LOCKED_OUT | "
        "DEPROVISIONED | SUSPENDED | PASSWORD_EXPIRED), SCIM filter expression, "
        "or free-text search. Returns displayName, email, status, lastLogin "
        "plus any field present in the filter."
    )
)
async def tool_list_users(
    filter: str | None = None,
    search: str | None = None,
    status: str | None = None,
    limit: int = 50,
) -> list[dict]:
    return await list_users(
        filter=filter,
        search=search,
        status=status,
        limit=limit,
    )


@mcp.tool(
    description=(
        "Get members of an Okta group. Supply either group_id (preferred) or "
        "group_name. Returns displayName, email, status, lastLogin of each member "
        "plus any field present in the filter."
    )
)
async def tool_get_group(
    group_id: str | None = None,
    group_name: str | None = None,
    filter: str | None = None,
    limit: int = 50,
) -> list[dict]:
    return await get_group(
        group_id=group_id,
        group_name=group_name,
        filter=filter,
        limit=limit,
    )


@mcp.tool(
    description=(
        "Retrieve Okta audit log events (system log). Full event — no trimming. "
        "Supports time range (since/until as ISO 8601), SCIM filter, and keyword search. "
        "Use for compliance and security investigation."
    )
)
async def tool_get_audit_logs(
    since: str | None = None,
    until: str | None = None,
    filter: str | None = None,
    q: str | None = None,
    limit: int = 50,
) -> list[dict]:
    return await get_audit_logs(
        since=since,
        until=until,
        filter=filter,
        q=q,
        limit=limit,
    )


@mcp.tool(
    description=(
        "Search Okta system log events by event type, keyword, outcome, or time range. "
        "Full event — no trimming. Use for security investigation: failed logins, "
        "MFA failures, suspicious activity."
    )
)
async def tool_search_events(
    event_type: str | None = None,
    q: str | None = None,
    since: str | None = None,
    until: str | None = None,
    outcome: str | None = None,
    limit: int = 50,
) -> list[dict]:
    return await search_events(
        event_type=event_type,
        q=q,
        since=since,
        until=until,
        outcome=outcome,
        limit=limit,
    )


@mcp.tool(
    description=(
        "List Okta applications. Optionally filter by status (ACTIVE | INACTIVE) "
        "or search by name. Returns label, status, signOnMode, assignedUserCount."
    )
)
async def tool_list_apps(
    filter: str | None = None,
    q: str | None = None,
    status: str | None = None,
    limit: int = 50,
) -> list[dict]:
    return await list_apps(
        filter=filter,
        q=q,
        status=status,
        limit=limit,
    )


@mcp.tool(
    description=(
        "Get Okta policies by type. Supported types: PASSWORD | OKTA_SIGN_ON | "
        "MFA_ENROLL | ACCESS_POLICY | PROFILE_ENROLLMENT. "
        "Returns name, status, type, conditions, rules. Includes policy rules."
    )
)
async def tool_get_policy(
    policy_type: str = "PASSWORD",
    status: str | None = None,
    limit: int = 50,
) -> list[dict]:
    return await get_policy(
        policy_type=policy_type,
        status=status,
        limit=limit,
    )


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run()
